import asyncio

import match_polling
import userdb_coordination
import discord
from database.storage_sqlite import SubscriptionRecord


def test_first_poll_initializes_checkpoint_without_notification(monkeypatch):
    subscriptions = [
        SubscriptionRecord(
            id=1,
            server_id="discord-server",
            discord_user_id="discord-user",
            valorant_account="player#tag",
            valorant_puuid="player-puuid",
            last_polled_match_id=None,
        )
    ]

    class FakeUserSQLiteDB:
        checkpoint = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def list_subscriptions(self):
            return subscriptions

        async def update_last_polled_match(
            self, subscription_id, expected_match_id, match_id
        ):
            self.__class__.checkpoint = (
                subscription_id,
                expected_match_id,
                match_id,
            )
            return True

    class FakeMatch:
        def __init__(self, player_name, player_tag):
            pass

        async def get_last_match_id(self):
            return "existing-match"

        async def fetch_match(self):
            raise AssertionError("existing match data should not be fetched")

    monkeypatch.setattr(match_polling, "UserSQLiteDB", FakeUserSQLiteDB)
    monkeypatch.setattr(match_polling, "Match", FakeMatch)
    userdb_coordination._userdb_lock = None

    result = asyncio.run(match_polling.handle_polling_matches())

    assert result is None
    assert FakeUserSQLiteDB.checkpoint == (1, None, "existing-match")


def _configure_new_match(monkeypatch, match_class):
    subscriptions = [
        SubscriptionRecord(
            id=7,
            server_id="server-id",
            discord_user_id="discord-user",
            valorant_account="player#tag",
            valorant_puuid="player-puuid",
            last_polled_match_id="old-match",
        )
    ]

    class FakeUserSQLiteDB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def list_subscriptions(self):
            return subscriptions

    monkeypatch.setattr(match_polling, "UserSQLiteDB", FakeUserSQLiteDB)
    monkeypatch.setattr(match_polling, "Match", match_class)
    userdb_coordination._userdb_lock = None


def test_new_match_prefers_graphical_card(monkeypatch):
    class FakeMatch:
        def __init__(self, player_name, player_tag):
            pass

        async def get_last_match_id(self):
            return "new-match"

        async def fetch_match(self):
            return {"data": {}}

        async def build_match_card(self):
            return b"png-data"

        async def build_embed(self):
            raise AssertionError(
                "text embed should not be built when rendering succeeds"
            )

    _configure_new_match(monkeypatch, FakeMatch)
    result = asyncio.run(match_polling.handle_polling_matches())

    assert result is not None
    assert result.image == b"png-data"
    assert result.embed is None


def test_new_match_falls_back_to_text_embed(monkeypatch):
    fallback = discord.Embed(title="Text fallback")

    class FakeMatch:
        def __init__(self, player_name, player_tag):
            pass

        async def get_last_match_id(self):
            return "new-match"

        async def fetch_match(self):
            return {"data": {}}

        async def build_match_card(self):
            raise OSError("asset unavailable")

        async def build_embed(self):
            return fallback

    _configure_new_match(monkeypatch, FakeMatch)
    result = asyncio.run(match_polling.handle_polling_matches())

    assert result is not None
    assert result.image is None
    assert result.embed is fallback
