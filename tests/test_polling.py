import asyncio

import commands
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

    monkeypatch.setattr(commands, "UserSQLiteDB", FakeUserSQLiteDB)
    monkeypatch.setattr(commands, "Match", FakeMatch)
    commands._userdb_lock = None

    result = asyncio.run(commands.handle_polling_matches())

    assert result is None
    assert FakeUserSQLiteDB.checkpoint == (1, None, "existing-match")
import asyncio

import commands
from database.storage_sqlite import SubscriptionRecord


def test_first_poll_initializes_checkpoint_without_notification(monkeypatch):
    subscriptions = [
        SubscriptionRecord(
            id=1,
            server_id="discord-server",
            discord_user_id="discord-user",
            channel_id="discord-channel",
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

    monkeypatch.setattr(commands, "UserSQLiteDB", FakeUserSQLiteDB)
    monkeypatch.setattr(commands, "Match", FakeMatch)
    commands._userdb_lock = None

    result = asyncio.run(commands.handle_polling_matches())

    assert result is None
    assert FakeUserSQLiteDB.checkpoint == (1, None, "existing-match")
