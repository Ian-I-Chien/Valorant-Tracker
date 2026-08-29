import asyncio

import commands


def test_first_poll_initializes_checkpoint_without_notification(monkeypatch):
    account = {
        "valorant_account": "player#tag",
        "valorant_puuid": "player-puuid",
        "last_polled_match_id": None,
        "subscription_id": 1,
    }
    users = [
        {
            "dc_id": "discord-user",
            "dc_channel_id": "discord-channel",
            "valorant_accounts": [account],
        }
    ]

    class FakeUserSQLiteDB:
        checkpoint = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def get_all(self):
            return users

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

        async def get_stored_match_by_id_by_api(self):
            raise AssertionError("existing match data should not be fetched")

    monkeypatch.setattr(commands, "UserSQLiteDB", FakeUserSQLiteDB)
    monkeypatch.setattr(commands, "Match", FakeMatch)
    commands._userdb_lock = None

    result = asyncio.run(commands.handle_polling_matches())

    assert result is None
    assert FakeUserSQLiteDB.checkpoint == (1, None, "existing-match")
