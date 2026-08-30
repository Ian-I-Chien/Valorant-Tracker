import asyncio
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp
from dotenv import load_dotenv

from .key_pool import ApiUnavailableError, KeyPool, configured_keys

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


KEY_POOL = KeyPool(
    configured_keys(os.environ), MAX_REQUESTS_PER_MINUTE, RATE_LIMIT_WINDOW_SECONDS
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
    try:
        return await asyncio.wait_for(_request_with_keys(url, params), timeout=30)
    except asyncio.TimeoutError:
        raise ApiUnavailableError("Henrik API request timed out; retry later") from None


async def _request_with_keys(
    url: str, params: Optional[dict[str, Any]] = None
) -> Optional[dict[str, Any]]:
    timeout = aiohttp.ClientTimeout(total=20, connect=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # A broken key must not turn one user query into unbounded retries.
        for _ in range(min(3, len(KEY_POOL.states))):
            async with KEY_POOL.lease() as state:
                headers = {"Authorization": state.secret, "accept": "application/json"}
                try:
                    async with session.get(
                        url, headers=headers, params=params, allow_redirects=False
                    ) as response:
                        rotate = await KEY_POOL.report(
                            state, response.status, response.headers
                        )
                        if response.status == HTTP_OK:
                            return await response.json()
                        if rotate:
                            continue
                        if response.status in (403, 408, 429) or response.status >= 500:
                            raise ApiUnavailableError(
                                f"Henrik API unavailable (HTTP {response.status}); retry later"
                            )
                        LOGGER.warning("Henrik API returned HTTP %s", response.status)
                        return None
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    await KEY_POOL.report(state, 0, {})
                    raise ApiUnavailableError(
                        "Could not reach Henrik API; retry later"
                    ) from None
        raise ApiUnavailableError("No usable Henrik API response within retry budget")


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
