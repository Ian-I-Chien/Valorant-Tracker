import asyncio

import commands


def test_first_poll_initializes_checkpoint_without_notification(monkeypatch):
    account = {
        "valorant_account": "player#tag",
        "valorant_puuid": "player-puuid",
        "last_polled_match_id": None,
    }
    users = [
        {
            "dc_id": "discord-user",
            "dc_channel_id": "discord-channel",
            "valorant_accounts": [account],
        }
    ]

    class FakeUserJsonDB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def get_all(self):
            return users

    class FakeMatch:
        def __init__(self, player_name, player_tag):
            pass

        async def get_last_match_id(self):
            return "existing-match"

        async def get_stored_match_by_id_by_api(self):
            raise AssertionError("existing match data should not be fetched")

    monkeypatch.setattr(commands, "UserJsonDB", FakeUserJsonDB)
    monkeypatch.setattr(commands, "Match", FakeMatch)
    commands._userdb_lock = None

    result = asyncio.run(commands.handle_polling_matches())

    assert result is None
    assert account["last_polled_match_id"] == "existing-match"
