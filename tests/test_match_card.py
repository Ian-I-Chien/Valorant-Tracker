from valorant.match_card import MatchCardPlayer, _build_party_styles, _format_rr


def _player(team_id: str, party_id: str) -> MatchCardPlayer:
    return MatchCardPlayer(
        riot_id="player#tag",
        agent_name="Sage",
        agent_id="agent-id",
        team_id=team_id,
        party_id=party_id,
        rank_name="Gold 1",
        rank_icon_url=None,
        kills=0,
        deaths=0,
        assists=0,
        acs=0,
        headshot_percentage=0,
        kast=0,
        rank_rating=None,
        rr_change=None,
    )


def test_party_labels_are_numbered_independently_per_team():
    teams = {
        "Blue": [
            _player("Blue", "blue-trio"),
            _player("Blue", "blue-trio"),
            _player("Blue", "blue-trio"),
            _player("Blue", "blue-duo"),
            _player("Blue", "blue-duo"),
        ],
        "Red": [
            _player("Red", "red-duo"),
            _player("Red", "red-duo"),
            _player("Red", "red-solo-1"),
            _player("Red", "red-solo-2"),
            _player("Red", "red-solo-3"),
        ],
    }

    styles = _build_party_styles(teams)

    assert styles[("Blue", "blue-trio")][0] == "TRIO A"
    assert styles[("Blue", "blue-duo")][0] == "DUO B"
    assert styles[("Red", "red-duo")][0] == "DUO A"
    assert ("Red", "red-solo-1") not in styles


def test_rr_is_only_shown_for_competitive_queue():
    player = MatchCardPlayer(
        **{**_player("Blue", "solo").__dict__, "rank_rating": 73, "rr_change": 18}
    )

    assert _format_rr("Competitive", player) == "  RR 73 (+18)"
    assert _format_rr("Unrated", player) == ""
