"""Pure calculations derived from completed match payloads."""

from typing import Optional


def calculate_kast(match_data: dict) -> dict[str, float]:
    """Calculate each player's kill/assist/survive/trade round percentage."""
    data = match_data.get("data")
    if data is None:
        raise ValueError("calculate_kast data is null.")
    players = data.get("players")
    if players is None:
        raise ValueError("calculate_kast players is null.")
    rounds = data.get("rounds")
    if rounds is None:
        raise ValueError("calculate_kast rounds is null.")
    kills = data.get("kills")
    if kills is None:
        raise ValueError("calculate_kast kills is null.")

    performance = {
        player["puuid"]: [
            {"kill": 0, "assistant": 0, "death": 0, "trade": 0} for _ in rounds
        ]
        for player in players
    }
    killers: dict[str, list[dict[str, object]]] = {}
    current_round = -1
    for kill in sorted(kills, key=lambda item: item["time_in_match_in_ms"]):
        round_index = kill["round"]
        time_in_round = int(kill["time_in_round_in_ms"])
        killer = kill["killer"]["puuid"]
        victim = kill["victim"]["puuid"]

        if current_round != round_index:
            current_round = round_index
            killers.clear()

        performance[victim][round_index]["death"] += 1
        for earlier in killers.get(victim, []):
            if time_in_round - int(earlier["time"]) <= 3000:
                performance[str(earlier["victim"])][round_index]["trade"] += 1

        performance[killer][round_index]["kill"] += 1
        killers.setdefault(killer, []).append({"victim": victim, "time": time_in_round})
        for assistant in kill["assistants"]:
            performance[assistant["puuid"]][round_index]["assistant"] += 1

    result = {}
    for puuid, round_stats in performance.items():
        kast_rounds = sum(
            stats["kill"] > 0
            or stats["assistant"] > 0
            or stats["trade"] > 0
            or stats["death"] == 0
            for stats in round_stats
        )
        result[puuid] = kast_rounds / len(rounds) * 100
    return result
