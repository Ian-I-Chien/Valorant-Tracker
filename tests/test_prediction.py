from datetime import datetime, timedelta, timezone

from valorant.prediction import (
    PredictionCardRenderer,
    RecentPerformance,
    extract_recent_performances,
    predict_next_match,
)


def test_extracts_only_matches_from_last_30_days():
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    matches = [
        {
            "metadata": {
                "game_start_patched": "Thursday, August 27, 2026 02:29 PM",
                "game_start": int((now - timedelta(days=2)).timestamp()),
                "rounds_played": 20,
                "mode": "Unrated",
            },
            "players": [
                {
                    "puuid": "p1",
                    "team_id": "Blue",
                    "stats": {"score": 4400, "kills": 20, "deaths": 10},
                }
            ],
            "teams": [{"team_id": "Blue", "rounds": {"won": 13, "lost": 7}}],
        },
        {
            "metadata": {
                "started_at": (now - timedelta(days=31)).isoformat(),
                "rounds_played": 20,
                "mode": "Competitive",
            },
            "players": [
                {
                    "puuid": "p1",
                    "team_id": "Red",
                    "stats": {"score": 3000, "kills": 10, "deaths": 20},
                }
            ],
            "teams": [{"team_id": "Red", "rounds": {"won": 5, "lost": 13}}],
        },
        {
            "metadata": {
                "started_at": (now - timedelta(days=1)).isoformat(),
                "rounds_played": 12,
                "mode": "Swiftplay",
            },
            "players": [
                {
                    "puuid": "p1",
                    "team_id": "Blue",
                    "stats": {"score": 5000, "kills": 30, "deaths": 2},
                }
            ],
            "teams": [{"team_id": "Blue", "rounds": {"won": 5, "lost": 1}}],
        },
    ]
    result = extract_recent_performances(matches, "p1", now=now)
    assert len(result) == 1
    assert result[0].won is True
    assert result[0].acs == 220


def test_prediction_is_bounded_and_card_is_png():
    now = datetime.now(timezone.utc)
    performances = [
        RecentPerformance(now - timedelta(days=index), index != 3, 230 + index, 1.2)
        for index in range(6)
    ]
    result = predict_next_match("player#tag", performances)
    assert result is not None
    assert 25 <= result.win_probability <= 75
    assert result.confidence == "MEDIUM"
    assert PredictionCardRenderer().render(result).startswith(b"\x89PNG")


def test_no_recent_matches_has_no_prediction():
    assert predict_next_match("player#tag", []) is None
