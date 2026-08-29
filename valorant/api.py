import asyncio
import logging
import os
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv()

LOGGER = logging.getLogger(__name__)
MAX_REQUESTS_PER_MINUTE = int(os.getenv("API_REQUESTS_PER_MINUTE", "60"))
RATE_LIMIT_WINDOW_SECONDS = 60
HTTP_OK = 200
CACHE_MAX_ENTRIES = int(os.getenv("API_CACHE_MAX_ENTRIES", "256"))

API_URLS = {
    "rank": "https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{player_name}/{player_tag}",
    "account": "https://api.henrikdev.xyz/valorant/v1/account/{player_name}/{player_tag}",
    "match": "https://api.henrikdev.xyz/valorant/v4/match/{region}/{matchid}",
    "matches_v3": "https://api.henrikdev.xyz/valorant/v3/matches/{region}/{player_name}/{player_tag}",
    "mmr_history": "https://api.henrikdev.xyz/valorant/v1/mmr-history/{region}/{player_name}/{player_tag}",
}


class SlidingWindowRateLimiter:
    """Process-local sliding-window limiter for Henrik API requests."""

    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window_seconds = window_seconds
        self._request_times: deque[float] = deque()
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self) -> None:
        async with self._get_lock():
            now = time.monotonic()
            self._discard_expired(now)
            if len(self._request_times) >= self.limit:
                delay = self.window_seconds - (now - self._request_times[0])
                LOGGER.info("API rate limit reached; waiting %.2f seconds", delay)
                await asyncio.sleep(max(delay, 0))
                now = time.monotonic()
                self._discard_expired(now)
            self._request_times.append(now)

    def _discard_expired(self, now: float) -> None:
        while (
            self._request_times and now - self._request_times[0] >= self.window_seconds
        ):
            self._request_times.popleft()


RATE_LIMITER = SlidingWindowRateLimiter(
    MAX_REQUESTS_PER_MINUTE, RATE_LIMIT_WINDOW_SECONDS
)


@dataclass
class CacheEntry:
    payload: dict[str, Any]
    expires_at: float
    stale_until: float


class AsyncResponseCache:
    """Bounded in-memory TTL cache with single-flight request coalescing."""

    def __init__(self, max_entries: int = CACHE_MAX_ENTRIES):
        self.max_entries = max_entries
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._inflight: dict[str, asyncio.Task[Optional[dict[str, Any]]]] = {}
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def get(self, key: str, *, allow_stale: bool = False) -> Optional[dict[str, Any]]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        now = time.monotonic()
        if now <= entry.expires_at or (allow_stale and now <= entry.stale_until):
            self._entries.move_to_end(key)
            return entry.payload
        if now > entry.stale_until:
            self._entries.pop(key, None)
        return None

    def put(
        self,
        key: str,
        payload: dict[str, Any],
        ttl_seconds: float,
        stale_seconds: float,
    ) -> None:
        now = time.monotonic()
        self._entries[key] = CacheEntry(
            payload=payload,
            expires_at=now + ttl_seconds,
            stale_until=now + ttl_seconds + stale_seconds,
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    async def run(self, key: str, request) -> Optional[dict[str, Any]]:
        owner = False
        async with self._get_lock():
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(request())
                self._inflight[key] = task
                owner = True
        try:
            return await task
        finally:
            if owner:
                async with self._get_lock():
                    if self._inflight.get(key) is task:
                        self._inflight.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()


RESPONSE_CACHE = AsyncResponseCache()


def _request_key(url: str, params: Optional[dict[str, Any]]) -> str:
    encoded_params = "&".join(
        f"{key}={value}" for key, value in sorted((params or {}).items())
    )
    return f"{url}?{encoded_params}"


async def _request_json(
    url: str, params: Optional[dict[str, Any]] = None
) -> Optional[dict[str, Any]]:
    await RATE_LIMITER.acquire()
    headers = {
        "Authorization": os.getenv("API_KEY", ""),
        "accept": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status == HTTP_OK:
                return await response.json()
            LOGGER.warning("Henrik API returned HTTP %s for %s", response.status, url)
            return None


async def fetch_json(
    url: str,
    params: Optional[dict[str, Any]] = None,
    *,
    cache_ttl: float = 0,
    stale_ttl: float = 3600,
) -> Optional[dict[str, Any]]:
    if cache_ttl <= 0:
        return await _request_json(url, params)

    key = _request_key(url, params)
    cached = RESPONSE_CACHE.get(key)
    if cached is not None:
        return cached

    async def request() -> Optional[dict[str, Any]]:
        try:
            payload = await _request_json(url, params)
        except Exception:
            stale = RESPONSE_CACHE.get(key, allow_stale=True)
            if stale is not None:
                LOGGER.warning("Henrik request failed for %s; using stale cache", url)
                return stale
            raise
        if payload is not None:
            RESPONSE_CACHE.put(key, payload, cache_ttl, stale_ttl)
            return payload
        stale = RESPONSE_CACHE.get(key, allow_stale=True)
        if stale is not None:
            LOGGER.warning("Henrik returned no data for %s; using stale cache", url)
        return stale

    return await RESPONSE_CACHE.run(key, request)
