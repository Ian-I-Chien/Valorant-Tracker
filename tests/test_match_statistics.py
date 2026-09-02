import pytest

from valorant.match import Match
from valorant.match_statistics import calculate_kast


def _kill(round_index, elapsed, killer, victim, assistants=()):
    return {
        "round": round_index,
        "time_in_match_in_ms": round_index * 100000 + elapsed,
        "time_in_round_in_ms": elapsed,
        "killer": {"puuid": killer},
        "victim": {"puuid": victim},
        "assistants": [{"puuid": puuid} for puuid in assistants],
    }


def test_calculate_kast_counts_kills_assists_survival_and_trades():
    payload = {
        "data": {
            "players": [{"puuid": p} for p in ("a", "b", "c")],
            "rounds": [{}, {}],
            "kills": [
                _kill(0, 1000, "a", "b"),
                _kill(0, 3500, "c", "a"),
                _kill(1, 1000, "a", "b", assistants=("c",)),
            ],
        }
    }

    assert calculate_kast(payload) == {"a": 100.0, "b": 50.0, "c": 100.0}


def test_match_method_delegates_to_pure_calculation():
    payload = {"data": {"players": [{"puuid": "a"}], "rounds": [{}], "kills": []}}
    match = Match("name", "tag")
    match.last_match_data = payload

    assert match.calculate_kast() == {"a": 100.0}


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "data is null"),
        ({"data": {}}, "players is null"),
        ({"data": {"players": []}}, "rounds is null"),
        ({"data": {"players": [], "rounds": []}}, "kills is null"),
    ],
)
def test_calculate_kast_rejects_incomplete_payloads(payload, message):
    with pytest.raises(ValueError, match=message):
        calculate_kast(payload)
