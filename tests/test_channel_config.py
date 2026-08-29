import asyncio
import logging
from types import SimpleNamespace

import commands


class FakeResponse:
    def __init__(self):
        self.message = None
        self.ephemeral = None

    async def send_message(self, message, ephemeral=False):
        self.message = message
        self.ephemeral = ephemeral


class FakeChannel:
    id = 456
    mention = "<#456>"

    def __init__(self, *, allowed=True):
        self.allowed = allowed

    def permissions_for(self, member):
        return SimpleNamespace(
            view_channel=self.allowed,
            send_messages=self.allowed,
            embed_links=self.allowed,
        )


def make_interaction(*, guild=True):
    return SimpleNamespace(
        guild=SimpleNamespace(id=123, me=object()) if guild else None,
        user=SimpleNamespace(id=789),
        response=FakeResponse(),
    )


def test_set_channel_logs_created_configuration(monkeypatch, caplog):
    class FakeRepository:
        saved = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def get_guild_settings(self, server_id):
            return None

        async def set_guild_notification_channel(self, server_id, channel_id):
            self.__class__.saved = (server_id, channel_id)

    monkeypatch.setattr(commands, "UserSQLiteDB", FakeRepository)
    interaction = make_interaction()

    with caplog.at_level(logging.INFO, logger=commands.LOGGER.name):
        asyncio.run(commands.set_notification_channel(interaction, FakeChannel()))

    assert FakeRepository.saved == ("123", "456")
    assert interaction.response.ephemeral is True
    assert "Guild notification channel created" in caplog.text
    assert "server_id=123 channel_id=456 actor_id=789" in caplog.text


def test_set_channel_logs_permission_rejection(caplog):
    interaction = make_interaction()

    with caplog.at_level(logging.WARNING, logger=commands.LOGGER.name):
        asyncio.run(
            commands.set_notification_channel(interaction, FakeChannel(allowed=False))
        )

    assert interaction.response.ephemeral is True
    assert "Rejected notification channel change" in caplog.text
    assert "reason=missing_permissions" in caplog.text
    assert "server_id=123 channel_id=456 actor_id=789" in caplog.text
