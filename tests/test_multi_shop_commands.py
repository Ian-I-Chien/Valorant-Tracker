import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from discord.ext import commands

from multi_shop_commands import install_multi_commands
from shop_commands import display, shop_text


def fixture():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    service = SimpleNamespace(
        accounts=AsyncMock(
            return_value=(
                [
                    dict(id="one", label="One#TAG", expired=False),
                    dict(id="two", label="Two#TAG", expired=False),
                ],
                False,
            )
        ),
        shop=AsyncMock(),
        logout=AsyncMock(),
        set_notifications=AsyncMock(),
    )
    install_multi_commands(
        bot, service, AsyncMock(), display, shop_text, AsyncMock(return_value=b"png")
    )
    i = SimpleNamespace(
        user=SimpleNamespace(id=1, send=AsyncMock()),
        response=SimpleNamespace(
            send_message=AsyncMock(), defer=AsyncMock(), is_done=lambda: True
        ),
        followup=SimpleNamespace(send=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    return bot, service, i


def test_shop_all_continues_after_account_failure():
    async def run():
        bot, s, i = fixture()
        s.shop.side_effect = [
            RuntimeError("secret must not appear"),
            dict(riot_id="Two#TAG", expires=10, offers=[]),
        ]
        await bot.tree.get_command("shop").callback(i)
        assert s.shop.await_count == 2
        assert i.followup.send.await_count == 1
        assert i.followup.send.call_args.kwargs["ephemeral"] is False
        message = i.edit_original_response.call_args.kwargs["content"]
        assert "One#TAG" in message and "secret" not in message
        assert i.response.send_message.call_args.kwargs["ephemeral"] is True

    asyncio.run(run())


def test_shop_explicit_selects_only_one_account():
    async def run():
        bot, s, i = fixture()
        s.shop.return_value = dict(riot_id="Two#TAG", expires=10, offers=[])
        await bot.tree.get_command("shop").callback(i, "two")
        s.shop.assert_awaited_once_with(1, "two")
        assert not bot.tree.get_command("shop").parameters[0].required
        assert bot.tree.get_command("logout").parameters[0].required

    asyncio.run(run())


def test_panel_owner_guard_and_failed_dm_never_enables():
    async def run():
        bot, s, i = fixture()
        await bot.tree.get_command("accounts").callback(i)
        view = i.edit_original_response.call_args.kwargs["view"]
        other = SimpleNamespace(
            user=SimpleNamespace(id=2),
            response=SimpleNamespace(send_message=AsyncMock()),
        )
        assert not await view.interaction_check(other)
        i.user.send.side_effect = discord.Forbidden(
            SimpleNamespace(status=403, reason="Forbidden"), "no DM"
        )
        await view.toggle.callback(i)
        s.set_notifications.assert_not_awaited()

    asyncio.run(run())


def test_panel_toggle_uses_persisted_state_and_own_selection():
    async def run():
        bot, s, i = fixture()
        await bot.tree.get_command("accounts").callback(i)
        view = i.edit_original_response.call_args.kwargs["view"]
        await view.toggle.callback(i)
        s.set_notifications.assert_awaited_once_with(1, True)
        i.user.send.assert_awaited_once()
        view.selected = "one"
        await view.remove.callback(i)
        s.logout.assert_awaited_once_with(1, "one")

    asyncio.run(run())


def test_feature_registration_and_help_with_shop_enabled(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from shop_commands import register_shop_commands
    from help_command import build_help_embed

    key = tmp_path / "key"
    key.write_bytes(Fernet.generate_key())
    monkeypatch.setenv("SHOP_ENABLED", "1")
    monkeypatch.setenv("SHOP_ALLOWED_USER_IDS", "*")
    monkeypatch.setenv("SHOP_KEY_FILE", str(key))
    monkeypatch.setenv("SHOP_DB_PATH", str(tmp_path / "vault.db"))

    async def run():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        register_shop_commands(bot)
        names = {c.name for c in bot.tree.get_commands()}
        assert names == {"login", "shop", "logout", "accounts", "shop_notify"}
        text = "\n".join(f.value for f in build_help_embed().fields)
        for name in names:
            assert "/" + name in text
        assert not hasattr(bot, "shop_notification_task")
        assert not (tmp_path / "vault.db").exists()

    asyncio.run(run())
