import asyncio
import time

from valorant import api


def _install_isolated_cache(monkeypatch, max_entries=256):
    cache = api.AsyncResponseCache(max_entries=max_entries)
    monkeypatch.setattr(api, "RESPONSE_CACHE", cache)
    return cache


def test_ttl_cache_avoids_duplicate_requests(monkeypatch):
    _install_isolated_cache(monkeypatch)
    calls = 0

    async def fake_request(url, params=None):
        nonlocal calls
        calls += 1
        return {"data": calls}

    monkeypatch.setattr(api, "_request_json", fake_request)

    async def run():
        first = await api.fetch_json("https://example.test/data", cache_ttl=300)
        second = await api.fetch_json("https://example.test/data", cache_ttl=300)
        return first, second

    first, second = asyncio.run(run())
    assert first == second == {"data": 1}
    assert calls == 1


def test_concurrent_requests_are_coalesced(monkeypatch):
    _install_isolated_cache(monkeypatch)
    calls = 0

    async def fake_request(url, params=None):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"data": "shared"}

    monkeypatch.setattr(api, "_request_json", fake_request)

    async def run():
        return await asyncio.gather(
            *[
                api.fetch_json("https://example.test/shared", cache_ttl=300)
                for _ in range(5)
            ]
        )

    results = asyncio.run(run())
    assert results == [{"data": "shared"}] * 5
    assert calls == 1


def test_stale_cache_is_used_when_refresh_fails(monkeypatch):
    cache = _install_isolated_cache(monkeypatch)
    calls = 0

    async def fake_request(url, params=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"data": "last-known-good"}
        raise OSError("upstream unavailable")

    monkeypatch.setattr(api, "_request_json", fake_request)

    async def run():
        first = await api.fetch_json(
            "https://example.test/stale", cache_ttl=300, stale_ttl=3600
        )
        entry = next(iter(cache._entries.values()))
        entry.expires_at = time.monotonic() - 1
        second = await api.fetch_json(
            "https://example.test/stale", cache_ttl=300, stale_ttl=3600
        )
        return first, second

    first, second = asyncio.run(run())
    assert first == second == {"data": "last-known-good"}
    assert calls == 2


def test_cache_evicts_oldest_entry_at_capacity():
    cache = api.AsyncResponseCache(max_entries=2)
    cache.put("one", {"value": 1}, 300, 300)
    cache.put("two", {"value": 2}, 300, 300)
    cache.put("three", {"value": 3}, 300, 300)

    assert cache.get("one") is None
    assert cache.get("two") == {"value": 2}
    assert cache.get("three") == {"value": 3}
