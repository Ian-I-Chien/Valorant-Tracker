import asyncio
import logging
import os
import time
from collections import deque
from typing import Any, Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv()

LOGGER = logging.getLogger(__name__)
MAX_REQUESTS_PER_MINUTE = 90
RATE_LIMIT_WINDOW_SECONDS = 60
HTTP_OK = 200

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


async def fetch_json(
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
