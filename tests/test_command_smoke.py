import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from tools.command_smoke import (
    CapturedInteraction,
    deliver,
    export_output,
    parser,
    validate_target,
)


def test_default_is_preview_only_and_mutations_are_not_supported():
    args = parser().parse_args(["--test-env", "/tmp/test.env"])
    assert not args.send and not args.include_private
    with pytest.raises(SystemExit):
        parser().parse_args(["--test-env", "/tmp/test.env", "--commands", "logout"])


def test_private_original_and_public_followup():
    async def run():
        i = CapturedInteraction(1)
        await i.response.defer(ephemeral=True)
        await i.edit_original_response(content="working")
        assert i.private
        await i.followup.send("result", ephemeral=False)
        assert not i.private and i.output["content"] == "result"
        await i.response.send_message("error", ephemeral=True)
        assert i.private

    asyncio.run(run())


@pytest.mark.parametrize(
    "bot_id,guild_id,channel_id,name",
    [
        (9, 2, 3, "Test bot"),
        (1, 9, 3, "Test bot"),
        (1, 2, 9, "Test bot"),
        (1, 2, 3, "Production"),
    ],
)
def test_mismatched_target_rejected(bot_id, guild_id, channel_id, name):
    cfg = dict(
        SMOKE_TEST_BOT_ID="1", SMOKE_TEST_GUILD_ID="2", SMOKE_TEST_CHANNEL_ID="3"
    )
    with pytest.raises(ValueError):
        validate_target(
            cfg,
            SimpleNamespace(id=bot_id, name=name),
            SimpleNamespace(id=channel_id, guild=SimpleNamespace(id=guild_id)),
        )


def test_explicit_test_target_accepted():
    cfg = dict(
        SMOKE_TEST_BOT_ID="1", SMOKE_TEST_GUILD_ID="2", SMOKE_TEST_CHANNEL_ID="3"
    )
    validate_target(
        cfg,
        SimpleNamespace(id=1, name="Tracker Test"),
        SimpleNamespace(id=3, guild=SimpleNamespace(id=2)),
    )
    with pytest.raises(ValueError):
        validate_target({}, SimpleNamespace(id=1, name="Test"), SimpleNamespace(id=3))


def test_private_preview_requires_opt_in():
    async def run():
        i = CapturedInteraction(1)
        await i.response.send_message("private", ephemeral=True)
        channel = SimpleNamespace(send=AsyncMock())
        await deliver(channel, i, [], "help")
        channel.send.assert_not_awaited()
        await deliver(channel, i, [], "help", True)
        kwargs = channel.send.call_args.kwargs
        assert "PRIVATE RESPONSE PREVIEW" in kwargs["content"]
        assert kwargs["allowed_mentions"].everyone is False

    asyncio.run(run())


def test_export_handles_files_and_json(tmp_path):
    i = CapturedInteraction(1)
    i.output = {"file": discord.File(io.BytesIO(b"png"), filename="unsafe/ignored.png")}
    assert export_output(i, tmp_path, "last_match") == [b"png"]
    assert (tmp_path / "last_match-0.png").read_bytes() == b"png"
    assert (tmp_path / "last_match.json").exists()


def test_preview_runs_offline_with_isolated_database(tmp_path):
    import hashlib
    import os
    from pathlib import Path
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    database = root / "database" / "valorant_tracker.db"

    def fingerprint():
        return (
            hashlib.sha256(database.read_bytes()).hexdigest()
            if database.exists()
            else None
        )

    before = fingerprint()
    cfg = tmp_path / "test.env"
    cfg.write_text("SMOKE_TEST_GUILD_ID=1\n")
    output = tmp_path / "output"
    env = dict(os.environ, BOT_TOKEN="must-not-be-used", API_KEYS="must-not-be-used")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.command_smoke",
            "--test-env",
            str(cfg),
            "--commands",
            "help",
            "show_config",
            "--output-dir",
            str(output),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout
    assert fingerprint() == before
    assert (output / "help.json").exists()
    assert "No notification channel" in (output / "show_config.json").read_text()
