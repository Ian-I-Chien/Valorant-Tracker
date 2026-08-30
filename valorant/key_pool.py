"""Startup-only Henrik credentials with independent, process-local budgets."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Mapping

LOGGER = logging.getLogger(__name__)


class ApiUnavailableError(RuntimeError):
    """Safe to log: messages never contain credentials or upstream bodies."""


def configured_keys(environ: Mapping[str, str]) -> tuple[str, ...]:
    values = [value.strip() for value in environ.get("API_KEYS", "").split(",")]
    keys = tuple(dict.fromkeys(value for value in values if value))
    if keys:
        return keys
    legacy = environ.get("API_KEY", "").strip()
    return (legacy,) if legacy else ()


def _number(value: str | None) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


def retry_delay(headers: Mapping[str, str], fallback: float = 60) -> float:
    """Retry-After takes priority; tolerate epoch or delta reset headers."""
    headers = {name.lower(): value for name, value in headers.items()}
    retry = headers.get("retry-after")
    number = _number(retry)
    if number is not None:
        return max(1, number)
    if retry:
        try:
            return max(1, parsedate_to_datetime(retry).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            pass
    reset = _number(headers.get("x-ratelimit-reset"))
    if reset is not None:
        return max(1, reset - time.time() if reset > 1_000_000_000 else reset)
    return fallback


@dataclass(eq=False)
class KeyState:
    secret: str = field(repr=False)
    label: str
    requests: deque[float] = field(default_factory=deque, repr=False)
    busy: bool = False
    disabled: bool = False
    cooldown_until: float = 0
    server_limit: int | None = None
    remaining: int | None = None
    reset_at: float = 0


class KeyPool:
    """Reserve one in-flight request per key; never wait while holding the lock.

    Serializing each key avoids stale, out-of-order remaining-quota headers.
    Different keys may still issue requests concurrently.
    """

    def __init__(self, keys: tuple[str, ...], limit: int = 60, window: float = 60):
        if limit <= 0 or window <= 0:
            raise ValueError("API request limit and window must be positive")
        self.states = [
            KeyState(key, f"key-{index + 1}") for index, key in enumerate(keys)
        ]
        self.limit = limit
        self.window = window
        self._next = 0
        self._condition = asyncio.Condition()
        self._global_until = 0.0
        self._failures = 0

    async def acquire(self, max_wait: float = 5) -> KeyState:
        deadline = time.monotonic() + max_wait
        async with self._condition:
            while True:
                now = time.monotonic()
                if not any(not state.disabled for state in self.states):
                    raise ApiUnavailableError(
                        "No usable Henrik API keys; check configuration"
                    )
                wake_at = deadline
                for offset in range(len(self.states)):
                    index = (self._next + offset) % len(self.states)
                    state = self.states[index]
                    if state.disabled or state.busy:
                        continue
                    while state.requests and now - state.requests[0] >= self.window:
                        state.requests.popleft()
                    if state.reset_at <= now:
                        state.remaining = None
                    ready_at = max(state.cooldown_until, self._global_until)
                    limit = min(self.limit, state.server_limit or self.limit)
                    if len(state.requests) >= limit:
                        ready_at = max(ready_at, state.requests[0] + self.window)
                    if state.remaining == 0:
                        ready_at = max(ready_at, state.reset_at)
                    if ready_at <= now:
                        state.requests.append(now)
                        state.busy = True
                        if state.remaining is not None:
                            state.remaining = max(0, state.remaining - 1)
                        self._next = (index + 1) % len(self.states)
                        return state
                    wake_at = min(wake_at, ready_at)
                if now >= deadline:
                    raise ApiUnavailableError(
                        "Henrik API keys are busy or cooling down; retry later"
                    )
                try:
                    await asyncio.wait_for(
                        self._condition.wait(), max(0.001, wake_at - now)
                    )
                except asyncio.TimeoutError:
                    pass

    @asynccontextmanager
    async def lease(self, max_wait: float = 5):
        state = await self.acquire(max_wait)
        try:
            yield state
        finally:
            async with self._condition:
                state.busy = False
                self._condition.notify_all()

    async def report(
        self, state: KeyState, status: int, headers: Mapping[str, str]
    ) -> bool:
        """Return True only when retrying a different key is appropriate."""
        headers = {name.lower(): value for name, value in headers.items()}
        now = time.monotonic()
        delay = retry_delay(headers, self.window)
        async with self._condition:
            limit = _number(headers.get("x-ratelimit-limit"))
            remaining = _number(headers.get("x-ratelimit-remaining"))
            if limit is not None and limit >= 1:
                state.server_limit = int(limit)
            if remaining is not None:
                state.remaining = int(remaining)
                state.reset_at = now + delay
                if state.remaining == 0:
                    state.cooldown_until = max(state.cooldown_until, now + delay)
            if status == 401:
                state.disabled = True
                LOGGER.warning(
                    "Henrik %s disabled after HTTP 401; fix key and restart",
                    state.label,
                )
                return True
            if status == 429 and remaining == 0:
                LOGGER.warning(
                    "Henrik %s quota exhausted; cooling down %.1fs", state.label, delay
                )
                return True
            if status in (403, 429):
                # Henrik documents 403 as possibly maintenance; 429 without
                # personal exhaustion can be global. Do not rotate around it.
                self._global_until = max(self._global_until, now + delay)
                LOGGER.warning("Henrik HTTP %s; pool cooling down %.1fs", status, delay)
            elif status == 0 or status >= 500 or status == 408:
                self._failures = min(self._failures + 1, 6)
                delay = max(min(2**self._failures, 60), retry_delay(headers, 0))
                self._global_until = max(self._global_until, now + delay)
                LOGGER.warning("Henrik unavailable; pool backing off %.1fs", delay)
            elif status == 200:
                self._failures = 0
            return False
