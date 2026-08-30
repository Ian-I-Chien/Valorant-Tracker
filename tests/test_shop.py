import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

from shop_commands import private_result, LoginModal, LoginView
from valorant.shop_service import (
    LoginExpired,
    ShopError,
    ShopService,
    Vault,
    parse_callback,
    RiotStoreClient,
)


class Client:
    def __init__(self):
        self.refreshes = 0
        self.requests = 0
        self.failure = None

    async def login(self, code, nonce):
        return {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "expires": 0,
        }

    async def refresh(self, account):
        self.refreshes += 1
        return {
            **account,
            "refresh_token": "rotated-secret",
            "expires": time.time() + 3600,
        }

    async def shop(self, account):
        self.requests += 1
        if self.failure:
            raise self.failure
        return {
            "expires": time.time() + 3600,
            "offers": [{"id": "skin", "price": 1000}],
        }

    async def skin(self, item_id):
        return {"name": "Test Skin", "icon": None}


async def make_service(tmp_path):
    key = Fernet.generate_key()
    vault = Vault(tmp_path / "credentials.db", key)
    await vault.initialize()
    service = ShopService(vault, Client(), {1, 2})
    return service, key


async def link(service, owner=1):
    attempt, url = service.begin(owner)
    assert "auth.riotgames.com/authorize?" in url
    await service.login(owner, attempt, "http://localhost/redirect?code=fake")


def test_encryption_restart_and_wrong_key(tmp_path):
    async def run():
        service, key = await make_service(tmp_path)
        await link(service)
        raw = service.vault.path.read_bytes()
        assert b"access-secret" not in raw and b"refresh-secret" not in raw
        restored = Vault(service.vault.path, key)
        assert (await restored.get(1))["refresh_token"] == "refresh-secret"
        with pytest.raises(ShopError, match="decrypt"):
            await Vault(service.vault.path, Fernet.generate_key()).get(1)

    asyncio.run(run())


@pytest.mark.parametrize(
    "callback",
    [
        "https://localhost/redirect?code=a",
        "http://evil/redirect?code=a",
        "http://localhost.evil/redirect?code=a",
        "http://localhost/redirect?code=a&code=b",
        "http://localhost/redirect?code=a#token=secret",
        "http://localhost/redirect",
        "http://localhost:80/redirect?code=a",
        "http://user@localhost/redirect?code=a",
    ],
)
def test_callback_rejects_unexpected_destinations(callback):
    with pytest.raises(ShopError):
        parse_callback(callback)


def test_login_expiry_replay_replacement_and_allowlist(tmp_path):
    async def run():
        service, _ = await make_service(tmp_path)
        with pytest.raises(ShopError):
            service.begin(3)
        attempt, _ = service.begin(1)
        service.begin(1)
        with pytest.raises(ShopError):
            await service.login(1, attempt, "http://localhost/redirect?code=fake")
        attempt, nonce, _ = service.pending[1]
        service.pending[1] = (attempt, nonce, 0)
        with pytest.raises(ShopError):
            await service.login(1, attempt, "http://localhost/redirect?code=fake")
        await link(service)
        with pytest.raises(ShopError):
            await service.login(1, attempt, "http://localhost/redirect?code=fake")

    asyncio.run(run())


def test_concurrent_refresh_cache_and_owner_isolation(tmp_path):
    async def run():
        service, _ = await make_service(tmp_path)
        await link(service)
        results = await asyncio.gather(*(service.shop(1) for _ in range(5)))
        assert len(results) == 5
        assert service.client.refreshes == service.client.requests == 1
        assert (await service.vault.get(1))["refresh_token"] == "rotated-secret"
        with pytest.raises(ShopError, match="link"):
            await service.shop(2)
        await link(service, 2)
        await service.shop(2)
        assert service.client.requests == 2
        await service.logout(1)
        assert await service.vault.get(1) is None
        assert await service.vault.get(2) is not None
        assert 1 not in service.cache

    asyncio.run(run())


def test_transient_failure_preserves_rotated_token_but_expiry_removes_it(tmp_path):
    async def run():
        service, _ = await make_service(tmp_path)
        await link(service)
        service.client.failure = ShopError("Riot unavailable")
        with pytest.raises(ShopError):
            await service.shop(1)
        assert (await service.vault.get(1))["refresh_token"] == "rotated-secret"
        service.client.failure = LoginExpired("Expired")
        with pytest.raises(LoginExpired):
            await service.shop(1)
        assert await service.vault.get(1) is None

    asyncio.run(run())


def test_logout_cancels_pending_login(tmp_path):
    async def run():
        service, _ = await make_service(tmp_path)
        attempt, _ = service.begin(1)
        await service.logout(1)
        with pytest.raises(ShopError):
            await service.login(1, attempt, "http://localhost/redirect?code=fake")

    asyncio.run(run())


def test_private_failure_redacts_exception(caplog):
    interaction = SimpleNamespace(
        response=SimpleNamespace(defer=AsyncMock()), edit_original_response=AsyncMock()
    )
    operation = AsyncMock(side_effect=RuntimeError("secret-credential"))
    asyncio.run(private_result(interaction, operation))
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert "secret-credential" not in caplog.text
    assert "secret-credential" not in str(interaction.edit_original_response.call_args)


@pytest.mark.parametrize("public", [False, True])
def test_private_shop_image_response(monkeypatch, public):
    import shop_commands

    monkeypatch.setattr(shop_commands, "shop_card_png", AsyncMock(return_value=b"png"))
    interaction = SimpleNamespace(
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        edit_original_response=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    operation = AsyncMock(
        return_value={
            "expires": 12345,
            "offers": [
                {
                    "name": "Skin",
                    "price": 100,
                    "icon": "https://media.valorant-api.com/test.png",
                }
            ],
        }
    )
    asyncio.run(private_result(interaction, operation, public_shop=public))
    if public:
        interaction.response.send_message.assert_awaited_once_with(
            "Loading your store…", ephemeral=True
        )
        interaction.response.defer.assert_not_awaited()
        response = interaction.followup.send.call_args.kwargs
        assert response["ephemeral"] is False
        assert response["file"].filename == "daily-store.png"
    else:
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        response = interaction.edit_original_response.call_args.kwargs
        assert response["attachments"][0].filename == "daily-store.png"
        assert response["embeds"] == []
    assert response["allowed_mentions"].everyone is False


def test_public_shop_failure_stays_private():
    interaction = SimpleNamespace(
        response=SimpleNamespace(send_message=AsyncMock()),
        edit_original_response=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    asyncio.run(
        private_result(
            interaction,
            AsyncMock(side_effect=ShopError("Use /login first.")),
            public_shop=True,
        )
    )
    interaction.followup.send.assert_not_awaited()
    assert (
        interaction.edit_original_response.call_args.kwargs["content"]
        == "Use /login first."
    )


def test_public_shop_text_fallback(monkeypatch):
    import shop_commands

    monkeypatch.setattr(
        shop_commands, "shop_card_png", AsyncMock(side_effect=ValueError("secret"))
    )
    interaction = SimpleNamespace(
        response=SimpleNamespace(send_message=AsyncMock()),
        edit_original_response=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    result = {
        "riot_id": "Player#TEST",
        "expires": 12345,
        "offers": [{"name": "Skin", "price": 100}],
    }
    asyncio.run(
        private_result(interaction, AsyncMock(return_value=result), public_shop=True)
    )
    interaction.followup.send.assert_awaited_once()
    response = interaction.followup.send.call_args.kwargs
    assert response["ephemeral"] is False and "Player#TEST" in response["content"]
    assert "secret" not in response["content"]


def test_card_failure_keeps_private_text_and_does_not_repeat_shop(monkeypatch):
    import shop_commands

    monkeypatch.setattr(
        shop_commands, "shop_card_png", AsyncMock(side_effect=ValueError("secret"))
    )
    interaction = SimpleNamespace(
        response=SimpleNamespace(defer=AsyncMock()), edit_original_response=AsyncMock()
    )
    operation = AsyncMock(
        return_value={
            "riot_id": "Player#TEST",
            "expires": 12345,
            "offers": [{"name": "Skin", "price": None}],
        }
    )
    asyncio.run(private_result(interaction, operation))
    operation.assert_awaited_once()
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    response = interaction.edit_original_response.call_args.kwargs
    assert "Player#TEST" in response["content"]
    assert "Price unavailable" in response["content"]
    assert "secret" not in response["content"]
    assert response["attachments"] == []


def test_legacy_identity_upgrade_persists_and_excludes_secrets(tmp_path):
    async def run():
        service, key = await make_service(tmp_path)
        await link(service)
        service.client.identity = AsyncMock(
            side_effect=lambda account: {**account, "name": "Player", "tag": "TEST"}
        )
        result = await service.shop(1)
        assert result["riot_id"] == "Player#TEST"
        assert "secret" not in str(result)
        assert "access_token" not in result and "refresh_token" not in result
        restored = ShopService(Vault(service.vault.path, key), service.client, {1})
        assert await restored.linked_account(1) == "Player#TEST"
        await restored.shop(1)
        service.client.identity.assert_awaited_once()
        await service.logout(1)
        assert await service.linked_account(1) is None

    asyncio.run(run())


def test_identity_failure_still_returns_shop(tmp_path):
    async def run():
        service, _ = await make_service(tmp_path)
        await link(service)
        service.client.identity = AsyncMock(side_effect=ShopError("Unavailable"))
        result = await service.shop(1)
        assert result["offers"] and "tag unavailable" in result["riot_id"]
        assert await service.vault.get(1) is not None

    asyncio.run(run())


def test_identity_response_cannot_replace_other_account():
    client = RiotStoreClient()
    client.request = AsyncMock(
        return_value={
            "sub": "00000000-0000-0000-0000-000000000002",
            "acct": {"game_name": "Wrong", "tag_line": "USER"},
        }
    )
    with pytest.raises(ShopError, match="identity mismatch"):
        asyncio.run(
            client.identity(
                {
                    "access_token": "secret",
                    "puuid": "00000000-0000-0000-0000-000000000001",
                }
            )
        )


def test_modal_and_view_reject_other_user():
    async def run():
        service = SimpleNamespace(login=AsyncMock())
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=2),
            response=SimpleNamespace(send_message=AsyncMock()),
        )
        modal = LoginModal(service, 1, "attempt")
        await modal.on_submit(interaction)
        service.login.assert_not_awaited()
        view = LoginView(service, 1, "attempt", "https://auth.riotgames.com/authorize")
        assert not await view.interaction_check(interaction)

    asyncio.run(run())


def test_logout_waits_for_inflight_refresh_and_then_deletes(tmp_path):
    async def run():
        service, _ = await make_service(tmp_path)
        await link(service)
        started, release = asyncio.Event(), asyncio.Event()
        original_refresh = service.client.refresh

        async def slow_refresh(account):
            started.set()
            await release.wait()
            return await original_refresh(account)

        service.client.refresh = slow_refresh
        query = asyncio.create_task(service.shop(1))
        await started.wait()
        logout = asyncio.create_task(service.logout(1))
        await asyncio.sleep(0)
        assert not logout.done()
        release.set()
        await asyncio.gather(query, logout)
        assert await service.vault.get(1) is None
        assert 1 not in service.cache

    asyncio.run(run())


@pytest.mark.parametrize(
    "status,body,exception",
    [
        (429, {}, ShopError),
        (503, {}, ShopError),
        (403, {}, ShopError),
        (400, {"error": "invalid_grant"}, LoginExpired),
        (401, {}, LoginExpired),
    ],
)
def test_riot_errors_are_bounded_and_redacted(monkeypatch, status, body, exception):
    import valorant.shop_service as module

    calls = []

    class Response:
        headers = {"Retry-After": "60"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def json(self):
            return {**body, "sensitive": "secret-credential"}

    Response.status = status

    class Session:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def request(self, method, url, **kwargs):
            assert kwargs["allow_redirects"] is False
            calls.append(True)
            return Response()

    monkeypatch.setattr(module.aiohttp, "ClientSession", Session)
    client = RiotStoreClient()
    with pytest.raises(exception) as error:
        asyncio.run(
            client.request(
                "POST", "https://auth.riotgames.com/token", token_request=True
            )
        )
    assert "secret-credential" not in str(error.value)
    assert len(calls) == 1


def test_login_checks_nonce_before_identity_request():
    import base64
    import json

    claims = base64.urlsafe_b64encode(json.dumps({"nonce": "wrong"}).encode()).decode()
    client = RiotStoreClient()
    client.tokens = AsyncMock(return_value={"id_token": f"header.{claims}.signature"})
    client.request = AsyncMock()
    with pytest.raises(ShopError, match="mismatch"):
        asyncio.run(client.login("fake-code", "expected"))
    client.request.assert_not_awaited()
