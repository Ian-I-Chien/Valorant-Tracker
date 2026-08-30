import asyncio
import time
from email.utils import formatdate

import pytest

from valorant import api
from valorant.key_pool import ApiUnavailableError, KeyPool, configured_keys, retry_delay


def test_config_precedence_whitespace_dedup_and_legacy():
    assert configured_keys({"API_KEYS": " A, B,, A ", "API_KEY": "C"}) == ("A", "B")
    assert configured_keys({"API_KEYS": " , ", "API_KEY": " C "}) == ("C",)
    assert configured_keys({}) == ()


def test_round_robin_and_independent_limits():
    async def run():
        pool = KeyPool(("A", "B", "C"), limit=2)
        labels = []
        for _ in range(6):
            async with pool.lease(max_wait=0) as key:
                labels.append(key.label)
        assert labels == ["key-1", "key-2", "key-3"] * 2
        with pytest.raises(ApiUnavailableError):
            await pool.acquire(max_wait=0)
        pool.states[1].requests.clear()
        async with pool.lease(max_wait=0) as key:
            assert key.label == "key-2"

    asyncio.run(run())


def test_concurrent_reservations_never_exceed_per_key_limit():
    async def run():
        pool = KeyPool(("A", "B"), limit=1)

        async def query():
            try:
                async with pool.lease(max_wait=0) as key:
                    await asyncio.sleep(0)
                    return key.label
            except ApiUnavailableError:
                return None

        results = await asyncio.gather(*(query() for _ in range(20)))
        assert results.count("key-1") == results.count("key-2") == 1

    asyncio.run(run())


def test_waiter_wakes_on_release_and_cancellation_releases_key():
    async def run():
        pool = KeyPool(("A",))
        entered = asyncio.Event()

        async def hold():
            async with pool.lease():
                entered.set()
                await asyncio.Event().wait()

        holder = asyncio.create_task(hold())
        await entered.wait()
        waiter = asyncio.create_task(pool.acquire(max_wait=1))
        await asyncio.sleep(0)
        holder.cancel()
        with pytest.raises(asyncio.CancelledError):
            await holder
        assert (await waiter).label == "key-1"

    asyncio.run(run())


def test_headers_lower_limit_and_remaining_reset():
    async def run():
        pool = KeyPool(("A",), limit=60)
        async with pool.lease() as key:
            await pool.report(
                key,
                200,
                {
                    "X-RateLimit-Limit": "1",
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": "60",
                },
            )
        with pytest.raises(ApiUnavailableError):
            await pool.acquire(max_wait=0)
        key.cooldown_until = key.reset_at = 0
        key.requests.clear()
        async with pool.lease(max_wait=0):
            pass
        with pytest.raises(ApiUnavailableError):
            await pool.acquire(max_wait=0)

    asyncio.run(run())


def test_personal_429_skips_only_exhausted_key():
    async def run():
        pool = KeyPool(("A", "B"))
        async with pool.lease() as key:
            assert await pool.report(
                key, 429, {"x-ratelimit-remaining": "0", "Retry-After": "120"}
            )
        async with pool.lease(max_wait=0) as key:
            assert key.label == "key-2"

    asyncio.run(run())


@pytest.mark.parametrize("status", [403, 429, 500, 503, 0])
def test_shared_failures_back_off_whole_pool(status):
    async def run():
        pool = KeyPool(("A", "B"))
        async with pool.lease() as key:
            assert not await pool.report(key, status, {})
        with pytest.raises(ApiUnavailableError):
            await pool.acquire(max_wait=0)
        assert not any(key.disabled for key in pool.states)

    asyncio.run(run())


def test_auth_disable_and_logs_do_not_expose_key(caplog):
    async def run():
        pool = KeyPool(("private-key-secret",))
        async with pool.lease() as key:
            assert "private-key-secret" not in repr(key)
            assert await pool.report(key, 401, {})
        with pytest.raises(ApiUnavailableError):
            await pool.acquire(max_wait=0)

    asyncio.run(run())
    assert "private-key-secret" not in caplog.text
    assert "key-1" in caplog.text


def test_retry_header_parsing():
    assert retry_delay({"Retry-After": "12", "x-ratelimit-reset": "99"}) == 12
    assert retry_delay({"x-ratelimit-reset": "15"}) == 15
    assert 9 <= retry_delay({"x-ratelimit-reset": str(time.time() + 10)}) <= 10
    assert (
        8
        <= retry_delay({"Retry-After": formatdate(time.time() + 10, usegmt=True)})
        <= 10
    )
    for invalid in ("NaN", "inf", "-1", "bad"):
        assert retry_delay({"Retry-After": invalid, "x-ratelimit-reset": invalid}) == 60


def install_http(monkeypatch, responses):
    calls = []

    class Response:
        def __init__(self, status, headers):
            self.status, self.headers = status, headers

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def json(self):
            return {"data": "ok"}

    class Session:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def get(self, url, *, headers, params, allow_redirects):
            assert not allow_redirects
            calls.append(headers["Authorization"])
            return Response(*responses.pop(0))

    monkeypatch.setattr(api.aiohttp, "ClientSession", Session)
    monkeypatch.setattr(api, "KEY_POOL", KeyPool(("A", "B", "C", "D")))
    monkeypatch.setattr(api, "RESPONSE_CACHE", api.AsyncResponseCache())
    return calls


def test_http_failover_and_shared_cache(monkeypatch):
    calls = install_http(
        monkeypatch, [(401, {}), (429, {"x-ratelimit-remaining": "0"}), (200, {})]
    )

    async def run():
        results = await asyncio.gather(
            *(api.fetch_json("test", cache_ttl=300) for _ in range(10))
        )
        assert results == [{"data": "ok"}] * 10
        assert await api.fetch_json("test", cache_ttl=300) == results[0]

    asyncio.run(run())
    assert calls == ["A", "B", "C"]


def test_retry_count_is_bounded(monkeypatch):
    calls = install_http(monkeypatch, [(401, {})] * 4)
    with pytest.raises(ApiUnavailableError):
        asyncio.run(api._request_json("test"))
    assert len(calls) == 3


def test_global_429_does_not_rotate_and_uses_stale_cache(monkeypatch):
    calls = install_http(monkeypatch, [(429, {})])
    key = api._request_key("test", None)
    api.RESPONSE_CACHE.put(key, {"data": "old"}, -1, 300)
    assert asyncio.run(api.fetch_json("test", cache_ttl=300)) == {"data": "old"}
    assert calls == ["A"]


def test_empty_pool_fails_without_http(monkeypatch):
    calls = install_http(monkeypatch, [])
    monkeypatch.setattr(api, "KEY_POOL", KeyPool(()))
    with pytest.raises(ApiUnavailableError):
        asyncio.run(api._request_json("test"))
    assert not calls


def test_network_failure_releases_key_and_does_not_rotate(monkeypatch):
    calls = install_http(monkeypatch, [])

    def fail_get(self, url, **kwargs):
        calls.append(kwargs["headers"]["Authorization"])
        raise api.aiohttp.ClientConnectionError("private upstream detail")

    monkeypatch.setattr(api.aiohttp.ClientSession, "get", fail_get)
    with pytest.raises(ApiUnavailableError, match="Could not reach Henrik") as error:
        asyncio.run(api._request_json("test"))
    assert "private upstream detail" not in str(error.value)
    assert calls == ["A"]
    assert not any(key.busy for key in api.KEY_POOL.states)
    assert api.KEY_POOL._global_until > time.monotonic()


def test_request_deadline_is_bounded(monkeypatch):
    original_wait_for = asyncio.wait_for
    cancelled = []

    async def shorten_deadline(awaitable, timeout):
        assert timeout == 30
        return await original_wait_for(awaitable, timeout=0.01)

    async def slow_request(url, params):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    monkeypatch.setattr(api, "_request_with_keys", slow_request)
    monkeypatch.setattr(api.asyncio, "wait_for", shorten_deadline)
    with pytest.raises(ApiUnavailableError, match="timed out"):
        asyncio.run(api._request_json("test"))
    assert cancelled == [True]
