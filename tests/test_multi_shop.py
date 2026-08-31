import asyncio
import time
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from valorant.multi_shop import MultiShopService
from valorant.shop_service import Vault, LoginExpired, ShopError

P1 = "00000000-0000-0000-0000-000000000001"
P2 = "00000000-0000-0000-0000-000000000002"


class Client:
    def __init__(self):
        self.puuid = P1
        self.now = time.time()
        self.expiry = self.now + 86400
        self.expired = set()
        self.fail = set()
        self.seen = []

    async def login(self, *args):
        return dict(
            puuid=self.puuid,
            name="Account" + self.puuid[-1],
            tag="TAG",
            region="ap",
            expires=time.time() + 3600,
            access_token="secret",
            refresh_token="secret-refresh",
        )

    async def refresh(self, account):
        return dict(account, expires=time.time() + 3600, refresh_token="rotated")

    async def shop(self, account):
        self.seen.append(account["puuid"])
        if account["puuid"] in self.expired:
            raise LoginExpired("Use /login again.")
        if account["puuid"] in self.fail:
            raise ShopError("Temporary error")
        return dict(expires=self.expiry, offers=[dict(id="skin", price=1000)])

    async def skin(self, item):
        return dict(name="Test skin", icon=None)


async def setup(tmp_path):
    vault = Vault(tmp_path / "vault.db", Fernet.generate_key())
    await vault.initialize()
    client = Client()
    return MultiShopService(vault, client, None), client


async def link(service, client, puuid=P1, owner=1):
    client.puuid = puuid
    attempt, _ = service.begin(owner)
    await service.login(owner, attempt, "http://localhost/redirect?code=fake")


def test_add_relogin_remove_and_owner_isolation(tmp_path):
    async def run():
        s, c = await setup(tmp_path)
        await link(s, c)
        await link(s, c, P2)
        await link(s, c)
        assert len((await s.accounts(1))[0]) == 2
        with pytest.raises(ShopError):
            await s.shop(2, P1)
        await s.logout(1, P1)
        assert (await s.accounts(1))[0][0]["id"] == P2
        assert (await s.shop(1, P2))["riot_id"] == "Account2#TAG"
        assert b"secret-refresh" not in s.vault.path.read_bytes()

    asyncio.run(run())


def test_legacy_migration_is_encrypted_and_idempotent(tmp_path):
    async def run():
        s, c = await setup(tmp_path)
        await s.vault.put(1, await c.login())
        accounts, enabled = await s.accounts(1)
        assert len(accounts) == 1 and not enabled
        again = MultiShopService(s.vault, c, None)
        assert await again.accounts(1) == (accounts, False)
        assert (await s.vault.get(1))["version"] == 2
        assert b"secret" not in s.vault.path.read_bytes()

    asyncio.run(run())


def test_notifications_baseline_rollover_restart_and_new_accounts(tmp_path):
    async def run():
        s, c = await setup(tmp_path)
        await link(s, c)
        await s.set_notifications(1, True, {"guild": 20, "channel": 10})
        send = AsyncMock(return_value=True)
        await s.notify_owner(1, send)
        send.assert_not_awaited()
        data = await s.vault.get(1)
        data["states"][P1]["next"] = time.time() - 1
        await s.vault.put(1, data)
        s.cache.clear()
        await s.notify_owner(1, send)
        assert len(send.call_args.args[1]) == 1
        restored = MultiShopService(s.vault, c, None)
        await restored.notify_owner(1, send)
        assert send.await_count == 1
        await link(restored, c, P2)
        await restored.notify_owner(1, send)
        assert send.await_count == 1  # added account baselines, not today's backfill
        assert P2 in (await restored.vault.get(1))["states"]
        await restored.set_notifications(1, False)
        await restored.notify_owner(1, send)
        assert send.await_count == 1

    asyncio.run(run())


def test_expired_account_preserved_warning_once_and_relogin(tmp_path):
    async def run():
        s, c = await setup(tmp_path)
        await link(s, c)
        await link(s, c, P2)
        c.expired.add(P1)
        await s.set_notifications(1, True, {"guild": 20, "channel": 10})
        send = AsyncMock(return_value=True)
        await s.notify_owner(1, send)
        assert send.call_args.args[2] == ["Account1#TAG"]
        await s.notify_owner(1, send)
        assert send.await_count == 1
        record = (await s.vault.get(1))["accounts"][P1]
        assert record["auth_required"] and "refresh_token" not in record
        assert (await s.shop(1, P2))["offers"]
        c.expired.clear()
        await link(s, c)
        assert not (await s.accounts(1))[0][0]["expired"]

    asyncio.run(run())


def test_blocked_dm_disables_without_removing_accounts(tmp_path):
    async def run():
        s, c = await setup(tmp_path)
        await link(s, c)
        await s.set_notifications(1, True, {"guild": 20, "channel": 10})
        c.expired.add(P1)
        await s.notify_owner(1, AsyncMock(return_value=False))
        accounts, enabled = await s.accounts(1)
        assert len(accounts) == 1 and not enabled

    asyncio.run(run())


def test_transient_error_does_not_delete_credentials_or_stop_other_accounts(tmp_path):
    async def run():
        s, c = await setup(tmp_path)
        await link(s, c)
        await link(s, c, P2)
        await s.set_notifications(1, True, {"guild": 20, "channel": 10})
        c.fail.add(P1)
        await s.notify_owner(1, AsyncMock())
        data = await s.vault.get(1)
        assert "refresh_token" in data["accounts"][P1]
        assert data["states"][P1]["retry"] > time.time()
        assert data["states"][P2]["next"] > time.time()

    asyncio.run(run())


def test_claim_saved_before_ambiguous_delivery_failure(tmp_path):
    async def run():
        s, c = await setup(tmp_path)
        await link(s, c)
        await s.set_notifications(1, True, {"guild": 20, "channel": 10})
        await s.notify_owner(1, AsyncMock())
        data = await s.vault.get(1)
        data["states"][P1]["next"] = time.time() - 1
        await s.vault.put(1, data)
        send = AsyncMock(side_effect=RuntimeError("ambiguous"))
        with pytest.raises(RuntimeError):
            await s.notify_owner(1, send)
        again = MultiShopService(s.vault, c, None)
        send = AsyncMock()
        await again.notify_owner(1, send)
        send.assert_not_awaited()

    asyncio.run(run())


def test_logout_serialized_with_refresh_cannot_resurrect_account(tmp_path):
    async def run():
        s, c = await setup(tmp_path)
        await link(s, c)
        entered, release = asyncio.Event(), asyncio.Event()
        original = c.shop

        async def slow(account):
            entered.set()
            await release.wait()
            return await original(account)

        c.shop = slow
        task = asyncio.create_task(s.shop(1, P1))
        await entered.wait()
        remove = asyncio.create_task(s.logout(1, P1))
        await asyncio.sleep(0)
        assert not remove.done()
        release.set()
        await task
        await remove
        assert (await s.accounts(1))[0] == []

    asyncio.run(run())


def test_rotated_token_persisted_before_store_failure(tmp_path):
    async def run():
        s, c = await setup(tmp_path)
        await link(s, c)
        data = await s.vault.get(1)
        data["accounts"][P1]["expires"] = 0
        await s.vault.put(1, data)
        c.fail.add(P1)
        with pytest.raises(ShopError):
            await s.shop(1, P1)
        assert (await s.vault.get(1))["accounts"][P1]["refresh_token"] == "rotated"

    asyncio.run(run())


def test_old_dm_consent_cannot_become_public_channel_consent(tmp_path):
    async def run():
        s, c = await setup(tmp_path)
        await link(s, c)
        data = await s.vault.get(1)
        data["notify"] = True
        data.pop("notify_target", None)
        await s.vault.put(1, data)
        assert not (await s.accounts(1))[1]
        with pytest.raises(ShopError):
            await s.set_notifications(1, True)
        await s.set_notifications(1, True, {"guild": 20, "channel": 10})
        assert await s.notification_target(1) == {"guild": 20, "channel": 10}
        await s.set_notifications(1, True, {"guild": 20, "channel": 11})
        assert await s.notification_target(1) == {"guild": 20, "channel": 11}

    asyncio.run(run())
