import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
import multi_shop_commands
import shop_notifications
from discord.ext import commands

from multi_shop_commands import install_multi_commands
from shop_commands import display, shop_text


@pytest.fixture(autouse=True)
def configured_report_channel(monkeypatch):
    lookup = AsyncMock(return_value="10")
    monkeypatch.setattr(multi_shop_commands, "get_notification_channel_id", lookup)
    monkeypatch.setattr(shop_notifications, "get_notification_channel_id", lookup)


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
        notification_target=AsyncMock(return_value=None),
    )
    install_multi_commands(
        bot, service, AsyncMock(), display, shop_text, AsyncMock(return_value=b"png")
    )
    i = SimpleNamespace(
        guild=SimpleNamespace(id=20, me=object()),
        channel=SimpleNamespace(
            id=10,
            permissions_for=lambda member: SimpleNamespace(
                view_channel=True, send_messages=True
            ),
        ),
        user=SimpleNamespace(id=1, send=AsyncMock()),
        response=SimpleNamespace(
            send_message=AsyncMock(), defer=AsyncMock(), is_done=lambda: True
        ),
        followup=SimpleNamespace(send=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    bot.report_channel = SimpleNamespace(
        id=10,
        guild=SimpleNamespace(
            id=20, me=object(), fetch_member=AsyncMock(return_value=object())
        ),
        send=AsyncMock(),
        permissions_for=lambda member: SimpleNamespace(
            view_channel=True, send_messages=True
        ),
    )
    bot.fetch_channel = AsyncMock(return_value=bot.report_channel)
    i.channel.id = 99  # Invocation is deliberately not the configured report channel.
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
        assert bot.report_channel.send.await_count == 1
        assert "ephemeral" not in bot.report_channel.send.call_args.kwargs
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
        i.guild = None
        await view.toggle.callback(i)
        s.set_notifications.assert_not_awaited()

    asyncio.run(run())


def test_panel_toggle_uses_persisted_state_and_own_selection():
    async def run():
        bot, s, i = fixture()
        await bot.tree.get_command("accounts").callback(i)
        view = i.edit_original_response.call_args.kwargs["view"]
        await view.toggle.callback(i)
        s.set_notifications.assert_awaited_once_with(
            1, True, {"guild": 20, "channel": 10}
        )
        i.user.send.assert_not_awaited()
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
        assert names == {"login", "shop", "logout", "accounts"}
        text = "\n".join(f.value for f in build_help_embed().fields)
        for name in names:
            assert "/" + name in text
        assert not hasattr(bot, "shop_notification_task")
        assert not (tmp_path / "vault.db").exists()

    asyncio.run(run())


def test_multiple_accounts_are_sent_in_one_combined_image(monkeypatch):
    import io
    from PIL import Image
    import multi_shop_commands
    from valorant.combined_shop_card import combine_cards

    raw = io.BytesIO()
    Image.new("RGB", (100, 50), "red").save(raw, format="PNG")
    rendered = combine_cards([raw.getvalue(), raw.getvalue()])
    with Image.open(io.BytesIO(rendered)) as image:
        assert image.height == 116

    async def run():
        bot, s, i = fixture()
        s.shop.side_effect = [
            dict(riot_id="One#TAG", expires=10, offers=[]),
            dict(riot_id="Two#TAG", expires=10, offers=[]),
        ]
        render = AsyncMock(return_value=rendered)
        monkeypatch.setattr(multi_shop_commands, "combined_shop_card", render)
        await bot.tree.get_command("shop").callback(i)
        assert len(render.call_args.args[0]) == 2
        bot.report_channel.send.assert_awaited_once()
        assert (
            bot.report_channel.send.call_args.kwargs["file"].filename
            == "daily-stores.jpg"
        )
        assert bot.tree.get_command("shop_notify") is None

    asyncio.run(run())


def test_failed_public_delivery_is_not_retried(monkeypatch):
    import multi_shop_commands

    async def run():
        bot, s, i = fixture()
        s.shop.return_value = dict(riot_id="One#TAG", expires=10, offers=[])
        monkeypatch.setattr(
            multi_shop_commands, "combined_shop_card", AsyncMock(return_value=b"jpeg")
        )
        bot.report_channel.send.side_effect = RuntimeError("delivery failed")
        await bot.tree.get_command("shop").callback(i, "one")
        bot.report_channel.send.assert_awaited_once()
        assert "failed" in i.edit_original_response.call_args.kwargs["content"]

    asyncio.run(run())


def test_notifications_use_saved_channel_never_dm():
    async def run():
        bot, s, i = fixture()
        bot.wait_until_ready = AsyncMock()
        member = object()
        guild = SimpleNamespace(
            id=20, me=object(), fetch_member=AsyncMock(return_value=member)
        )
        channel = SimpleNamespace(
            id=10,
            guild=guild,
            send=AsyncMock(),
            permissions_for=lambda m: SimpleNamespace(
                view_channel=True, send_messages=True
            ),
        )
        bot.fetch_channel = AsyncMock(return_value=channel)
        bot.fetch_user = AsyncMock()
        s.vault = SimpleNamespace(initialize=AsyncMock())
        s.owners = AsyncMock(return_value=[1])
        finished = asyncio.Event()

        async def notify(owner, send):
            assert await send(
                owner,
                [dict(riot_id="One#TAG", expires=10, offers=[])],
                ["expired-secret"],
                {"guild": 20, "channel": 10},
            )
            finished.set()

        s.notify_owner = notify
        await bot.extra_events["on_ready"][0]()
        try:
            await asyncio.wait_for(finished.wait(), 2)
            bot.fetch_channel.assert_awaited_once_with(10)
            bot.fetch_user.assert_not_awaited()
            channel.send.assert_awaited_once()
            assert "expired-secret" not in channel.send.call_args.args[0]
            guild.fetch_member.assert_awaited_once_with(1)
        finally:
            bot.shop_notification_task.cancel()
            await asyncio.gather(bot.shop_notification_task, return_exceptions=True)

    asyncio.run(run())


def test_missing_set_channel_does_not_fall_back_to_invocation(monkeypatch):
    async def run():
        bot, s, i = fixture()
        unavailable = AsyncMock(return_value=None)
        monkeypatch.setattr(
            multi_shop_commands, "get_notification_channel_id", unavailable
        )
        monkeypatch.setattr(
            shop_notifications, "get_notification_channel_id", unavailable
        )
        await bot.tree.get_command("shop").callback(i)
        s.shop.assert_not_awaited()
        bot.report_channel.send.assert_not_awaited()
        assert "/set_channel" in i.edit_original_response.call_args.kwargs["content"]

    asyncio.run(run())


def test_enable_copy_is_short_and_uses_configured_channel():
    async def run():
        bot, s, i = fixture()
        await bot.tree.get_command("accounts").callback(i)
        view = i.edit_original_response.call_args.kwargs["view"]
        assert not any("Move" in getattr(child, "label", "") for child in view.children)
        await view.toggle.callback(i)
        s.set_notifications.assert_awaited_once_with(
            1, True, {"guild": 20, "channel": 10}
        )
        assert (
            i.edit_original_response.call_args.kwargs["content"]
            == "Notifications enabled in <#10>."
        )

    asyncio.run(run())
