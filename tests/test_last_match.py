import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import last_match_command as command


def interaction():
    return SimpleNamespace(
        guild=SimpleNamespace(id=1),
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        edit_original_response=AsyncMock(),
        followup=SimpleNamespace(send=AsyncMock()),
    )


@pytest.fixture
def lookup(monkeypatch):
    account = AsyncMock(
        return_value={"puuid": "p", "name": "Player", "tag": "TAG", "region": "eu"}
    )
    monkeypatch.setattr(command.ValorantPlayer, "fetch_account", account)
    history = AsyncMock(return_value={"data": [{"metadata": {"matchid": "latest"}}]})
    detail = AsyncMock(
        return_value={
            "data": {
                "metadata": {
                    "map": {"name": "Ascent"},
                    "queue": {"name": "Competitive"},
                    "started_at": "2026-08-30T10:00:00Z",
                },
                "players": [
                    {
                        "name": "Player",
                        "tag": "TAG",
                        "agent": {"name": "Jett"},
                        "stats": {"kills": 20, "deaths": 10, "assists": 5},
                    }
                ],
            }
        }
    )
    card = AsyncMock(return_value=b"png")
    monkeypatch.setattr(command.Match, "fetch_recent_matches", history)
    monkeypatch.setattr(command.Match, "fetch_match", detail)
    monkeypatch.setattr(command.Match, "build_match_card", card)
    return account, history, detail, card


@pytest.mark.parametrize("query", ["", "Player", "#TAG", "Player#", "a#b#c"])
def test_invalid_id_private_without_lookup(query, lookup):
    i = interaction()
    asyncio.run(command.show_last_match(i, query))
    assert i.response.send_message.call_args.kwargs["ephemeral"]
    lookup[0].assert_not_awaited()
    i.followup.send.assert_not_awaited()


def test_success_is_public_and_finishes_private_defer_first(lookup):
    i = interaction()
    events = []

    async def edit(**kwargs):
        events.append("private")

    async def send(**kwargs):
        assert events == ["private"]
        assert kwargs["ephemeral"] is False
        assert kwargs["file"].filename == "last-match.png"
        events.append("public")

    i.edit_original_response.side_effect = edit
    i.followup.send.side_effect = send
    asyncio.run(command.show_last_match(i, " Player # TAG "))
    i.response.defer.assert_awaited_once_with(ephemeral=True)
    lookup[3].assert_awaited_once_with(highlight_accounts={"player#tag"})
    assert events == ["private", "public"]


@pytest.mark.parametrize("payload", [{"data": []}, None, {"data": [{}]}])
def test_empty_or_invalid_history_never_public(lookup, payload):
    lookup[1].return_value = payload
    i = interaction()
    asyncio.run(command.show_last_match(i, "Player#TAG"))
    i.followup.send.assert_not_awaited()
    lookup[3].assert_not_awaited()
    assert i.edit_original_response.await_count == 1


@pytest.mark.parametrize("stage", [0, 1, 2])
def test_api_failures_private(lookup, stage):
    lookup[stage].side_effect = TimeoutError("upstream")
    i = interaction()
    asyncio.run(command.show_last_match(i, "Player#TAG"))
    i.followup.send.assert_not_awaited()
    assert "try again" in i.edit_original_response.call_args.kwargs["content"]


def test_fallback_has_player_stats(lookup):
    lookup[3].side_effect = ValueError("unsupported mode")
    i = interaction()
    asyncio.run(command.show_last_match(i, "Player#TAG"))
    result = i.followup.send.call_args.kwargs
    assert result["ephemeral"] is False
    assert {f.name: f.value for f in result["embed"].fields}["K/D/A"] == "20 / 10 / 5"


def test_region_and_exact_latest_match(monkeypatch, lookup):
    async def detail(self):
        assert self.region == "eu"
        assert self.last_match_id == "latest"
        return lookup[2].return_value

    monkeypatch.setattr(command.Match, "fetch_match", detail)
    i = interaction()
    asyncio.run(command.show_last_match(i, "Player#TAG"))
    i.followup.send.assert_awaited_once()


def test_unknown_account_and_dm_private(lookup):
    lookup[0].return_value = None
    i = interaction()
    asyncio.run(command.show_last_match(i, "Player#TAG"))
    lookup[1].assert_not_awaited()
    i.followup.send.assert_not_awaited()
    i.guild = None
    asyncio.run(command.show_last_match(i, "Player#TAG"))
    assert i.response.send_message.call_args.kwargs["ephemeral"] is True


def test_option_required_and_independent_of_shop(monkeypatch):
    monkeypatch.setenv("SHOP_ENABLED", "0")
    from bot import bot

    c = bot.tree.get_command("last_match")
    assert [(p.name, p.required) for p in c.parameters] == [("id", True)]


def test_card_highlighting_does_not_access_tracking_database(monkeypatch):
    import valorant.match as match_module

    def forbidden_db():
        raise AssertionError("standalone card must not access subscriptions")

    monkeypatch.setattr(match_module, "UserSQLiteDB", forbidden_db)
    monkeypatch.setattr(command.Match, "calculate_kast", lambda self: {"p": 100})
    monkeypatch.setattr(
        command.Match, "get_rank_with_retries", AsyncMock(return_value=None)
    )
    render = AsyncMock(return_value=b"image")
    monkeypatch.setattr(match_module.MatchCardRenderer, "render", render)
    match = command.Match("Player", "TAG")
    match.last_match_data = {
        "data": {
            "metadata": {
                "map": {"name": "Ascent", "id": "map"},
                "queue": {"name": "Competitive"},
                "started_at": "2026-08-30T10:00:00Z",
            },
            "players": [
                {
                    "name": "Player",
                    "tag": "TAG",
                    "puuid": "p",
                    "team_id": "Blue",
                    "agent": {"name": "Jett"},
                    "stats": {"score": 100},
                }
            ],
            "teams": [
                {"team_id": "Blue", "rounds": {"won": 13, "lost": 5}},
                {"team_id": "Red", "rounds": {"won": 5, "lost": 13}},
            ],
        }
    }
    assert (
        asyncio.run(match.build_match_card(highlight_accounts={"player#tag"}))
        == b"image"
    )
    assert render.call_args.args[0].players[0].registered


def test_public_delivery_failure_reports_privately(lookup):
    i = interaction()
    i.followup.send.side_effect = RuntimeError("missing permission")
    asyncio.run(command.show_last_match(i, "Player#TAG"))
    assert "permissions" in i.edit_original_response.call_args.kwargs["content"]


def test_malformed_detail_is_not_shared(lookup):
    lookup[2].return_value = {"data": {"metadata": {}}}
    i = interaction()
    asyncio.run(command.show_last_match(i, "Player#TAG"))
    i.followup.send.assert_not_awaited()
    lookup[3].assert_not_awaited()
