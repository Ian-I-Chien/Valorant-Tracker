"""Coordinate user database mutations within one bot process."""

import asyncio
from typing import Optional

_userdb_lock: Optional[asyncio.Lock] = None


def get_userdb_lock() -> asyncio.Lock:
    """Return a lock created lazily on the active event loop."""
    global _userdb_lock
    if _userdb_lock is None:
        _userdb_lock = asyncio.Lock()
    return _userdb_lock
