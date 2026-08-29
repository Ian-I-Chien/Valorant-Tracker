import asyncio
from datetime import datetime, timedelta, timezone

from valorant.player_info import PlayerInfoCardRenderer, build_player_info


def _match(now, mode, won, agent, party_id, kills=20, deaths=10, assists=5):
    return {
        "metadata": {
            "game_start": int(now.timestamp()),
            "rounds_played": 20,
            "mode": mode,
        },
        "players": {
            "all_players": [
                {
                    "puuid": "target",
                    "team": "Red",
                    "party_id": party_id,
                    "character": agent,
                    "assets": {"agent": {"small": None}},
                    "damage_made": 3000,
                    "stats": {
                        "score": 4400,
                        "kills": kills,
                        "deaths": deaths,
                        "assists": assists,
                        "headshots": 20,
                        "bodyshots": 50,
                        "legshots": 10,
                    },
                },
                {
                    "puuid": "friend",
                    "team": "Red",
                    "party_id": party_id,
                    "character": "Omen",
                    "stats": {},
                },
            ]
        },
        "teams": {"red": {"has_won": won}},
        "rounds": [
            {"player_stats": [{"player_puuid": "target", "kills": int(index % 3 == 0)}]}
            for index in range(20)
        ],
        "kills": [],
    }


def test_builds_recent_ng_rk_player_info():
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    matches = [
        _match(now - timedelta(days=1), "Competitive", True, "Jett", "party"),
        _match(now - timedelta(days=2), "Unrated", False, "Jett", None),
        _match(now - timedelta(days=3), "Swiftplay", True, "Omen", "party"),
    ]
    rank_history = [
        {
            "currenttierpatched": "Platinum 2",
            "ranking_in_tier": 16,
            "mmr_change_to_last_game": 23,
            "images": {"small": None},
        }
    ]
    data = build_player_info("yui#1121", "target", matches, rank_history, now)
    assert data is not None
    assert data.matches == 2
    assert data.win_rate == 50
    assert data.competitive_record == (1, 0)
    assert data.unrated_record == (0, 1)
    assert data.kd == 2
    assert data.agents[0].name == "JETT"
    assert {party.label for party in data.parties} == {"SOLO", "DUO"}


def test_renders_without_remote_assets():
    class EmptyAssets:
        async def get(self, url):
            return None

    now = datetime.now(timezone.utc)
    data = build_player_info(
        "player#tag", "target", [_match(now, "Competitive", True, "Jett", None)], []
    )
    assert data is not None
    image = asyncio.run(PlayerInfoCardRenderer(EmptyAssets()).render(data))
    assert image.startswith(b"\x89PNG")


def test_returns_none_without_recent_ng_rk_matches():
    assert build_player_info("player#tag", "target", [], []) is None
