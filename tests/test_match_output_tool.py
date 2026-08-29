import asyncio
from types import SimpleNamespace

import discord

from tools import match_output


def test_prepare_latest_match_output_builds_marked_embed(monkeypatch):
    class FakeMatch:
        def __init__(self, player_name, player_tag):
            assert (player_name, player_tag) == ("Player", "Tag")
            self.last_match_id = None

        async def get_last_match_id(self):
            self.last_match_id = "latest-match"
            return self.last_match_id

        async def fetch_match(self):
            return {"data": {}}

        async def build_embed(self):
            return discord.Embed(title="Match result")

    monkeypatch.setattr(match_output, "Match", FakeMatch)

    preview = asyncio.run(match_output.prepare_match_output("Player#Tag"))

    assert preview.match_id == "latest-match"
    assert preview.embed.title == "Match result"
    assert "Manual developer test" in preview.embed.footer.text
    assert "latest-match" in preview.embed.footer.text


def test_prepare_specific_match_does_not_query_latest(monkeypatch):
    class FakeMatch:
        def __init__(self, player_name, player_tag):
            self.last_match_id = None

        async def get_last_match_id(self):
            raise AssertionError("latest match lookup should be skipped")

        async def fetch_match(self):
            assert self.last_match_id == "chosen-match"
            return {"data": {}}

        async def build_embed(self):
            return discord.Embed(title="Chosen match")

    monkeypatch.setattr(match_output, "Match", FakeMatch)

    preview = asyncio.run(
        match_output.prepare_match_output("Player#Tag", "chosen-match")
    )

    assert preview.match_id == "chosen-match"


def test_dry_run_never_sends(monkeypatch, capsys):
    preview = match_output.MatchOutputPreview(
        account="Player#Tag",
        match_id="latest-match",
        embed=discord.Embed(title="Match result"),
    )

    async def fake_prepare(account, match_id):
        return preview

    async def fail_send(*args):
        raise AssertionError("dry run must not send")

    monkeypatch.setattr(match_output, "prepare_match_output", fake_prepare)
    monkeypatch.setattr(match_output, "send_embed", fail_send)
    args = SimpleNamespace(
        account="Player#Tag", match_id=None, server_id=None, send=False
    )

    asyncio.run(match_output.run(args))

    output = capsys.readouterr().out
    assert "MATCH_ID=latest-match" in output
    assert "RESULT=DRY_RUN" in output
