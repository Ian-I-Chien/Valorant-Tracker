import asyncio

from valorant import player as player_module
from valorant.player import ValorantPlayer


def test_fetch_account_forces_refresh_and_keeps_canonical_riot_id(monkeypatch):
    requests = []

    async def fake_fetch_json(url, params=None):
        requests.append((url, params))
        if params == {"force": "true"}:
            return {
                "data": {
                    "puuid": "player-puuid",
                    "name": "RCHU",
                    "tag": "1103",
                }
            }
        return None

    monkeypatch.setattr(player_module, "fetch_json", fake_fetch_json)
    player = ValorantPlayer("Rchu", "1103")

    account = asyncio.run(player.fetch_account())

    assert len(requests) == 2
    assert "/Rchu/1103" in requests[0][0]
    assert requests[0][1] is None
    assert "/Rchu/1103" in requests[1][0]
    assert requests[1][1] == {"force": "true"}
    assert account["puuid"] == "player-puuid"
    assert (player.player_name, player.player_tag) == ("RCHU", "1103")


def test_fetch_account_returns_none_after_refresh_also_fails(monkeypatch):
    requests = []

    async def fake_fetch_json(url, params=None):
        requests.append((url, params))
        return None

    monkeypatch.setattr(player_module, "fetch_json", fake_fetch_json)
    player = ValorantPlayer("RCHU", "1103")

    assert asyncio.run(player.fetch_account()) is None
    assert len(requests) == 2
    assert requests[1][1] == {"force": "true"}
