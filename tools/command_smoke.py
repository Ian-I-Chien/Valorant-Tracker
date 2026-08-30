"""Run read-only command handlers without a gateway, polling, or real interactions."""

import argparse
import asyncio
import io
import json
import logging
import os
import tempfile
from functools import partial
from unittest.mock import patch
import dotenv
from pathlib import Path
from types import SimpleNamespace

import discord
from dotenv import dotenv_values

COMMANDS = ("last_match", "info", "predict", "help", "show_config")


class CapturedInteraction:
    def __init__(self, guild_id):
        self.guild = SimpleNamespace(id=guild_id)
        self.response = SimpleNamespace(
            defer=self.defer, send_message=self.send_message
        )
        self.followup = SimpleNamespace(send=self.followup_send)
        self.private = False
        self.output = None

    async def defer(self, *, ephemeral=False, **kwargs):
        self.private = ephemeral

    async def send_message(self, content=None, *, ephemeral=False, **kwargs):
        self.private = ephemeral
        self.output = dict(kwargs, content=content)

    async def followup_send(self, content=None, *, ephemeral=False, **kwargs):
        await self.send_message(content, ephemeral=ephemeral, **kwargs)

    async def edit_original_response(self, *, content=None, **kwargs):
        self.output = dict(kwargs, content=content)


def validate_target(config, bot, channel):
    """Fail closed unless the selected config explicitly allowlists this TEST target."""
    expected = [
        config.get(k, "")
        for k in ("SMOKE_TEST_BOT_ID", "SMOKE_TEST_GUILD_ID", "SMOKE_TEST_CHANNEL_ID")
    ]
    if not all(str(v).isdigit() for v in expected):
        raise ValueError("Set all three SMOKE_TEST_*_ID values in the TEST env file")
    actual = [bot.id, getattr(getattr(channel, "guild", None), "id", None), channel.id]
    if actual != [int(v) for v in expected] or "test" not in bot.name.casefold():
        raise ValueError(
            "Refusing delivery: bot or channel is not the configured TEST target"
        )


def export_output(interaction, directory, command):
    if interaction.output is None:
        raise RuntimeError("Command returned without a response")
    output = interaction.output
    files = output.get("attachments") or (
        [output["file"]] if output.get("file") else []
    )
    images = []
    for index, attachment in enumerate(files):
        attachment.fp.seek(0)
        data = attachment.fp.read()
        target = directory / f"{command}-{index}.png"
        target.write_bytes(data)
        images.append(data)
        attachment.close()
    embed = output.get("embed")
    (directory / f"{command}.json").write_text(
        json.dumps(
            {
                "simulated": True,
                "private": interaction.private,
                "content": output.get("content"),
                "embed": embed.to_dict() if embed else None,
                "image_count": len(images),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return images


async def deliver(channel, interaction, images, command, include_private=False):
    if interaction.private and not include_private:
        return None
    output = interaction.output
    label = f"[TEST simulated output] /{command}"
    if interaction.private:
        label += " | PRIVATE RESPONSE PREVIEW - intentionally public in TEST"
    kwargs = {
        "content": label + "\n" + (output.get("content") or ""),
        "allowed_mentions": discord.AllowedMentions.none(),
    }
    if output.get("embed"):
        kwargs["embed"] = output["embed"]
    if images:
        kwargs["files"] = [
            discord.File(io.BytesIO(data), filename=f"{command}-{i}.png")
            for i, data in enumerate(images)
        ]
    return await channel.send(**kwargs)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--test-env", type=Path, required=True)
    p.add_argument("--account", help="Full Riot ID, required for player lookups")
    p.add_argument("--commands", nargs="+", choices=COMMANDS, default=["help"])
    p.add_argument("--output-dir", type=Path)
    p.add_argument(
        "--send", action="store_true", help="Send to the env-file TEST allowlist only"
    )
    p.add_argument(
        "--include-private",
        action="store_true",
        help="Also publish private-response previews in TEST",
    )
    return p


async def run(args):
    config = dotenv_values(args.test_env.resolve())
    if not config:
        raise ValueError("Missing or empty TEST env file")
    if (
        any(c in args.commands for c in ("last_match", "info", "predict"))
        and not args.account
    ):
        raise ValueError("--account is required for player lookups")
    # Do not inherit credentials from a parent production shell or a nearby .env.
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    for key in list(os.environ):
        if key.startswith("API_KEY") or key == "BOT_TOKEN":
            del os.environ[key]
    os.environ.update({k: v for k, v in config.items() if v is not None})
    os.environ["SHOP_ENABLED"] = "0"
    # Handler exceptions can contain upstream response details; report types only.
    logging.disable(logging.CRITICAL)
    with patch.object(dotenv, "load_dotenv", return_value=False):
        from commands import (
            show_registered_player_info,
            predict_registered_player,
            show_server_config,
        )
        from last_match_command import show_last_match
        from help_command import show_help
        from database import storage_sqlite

    handlers = {
        "last_match": show_last_match,
        "info": show_registered_player_info,
        "predict": predict_registered_player,
        "help": show_help,
        "show_config": show_server_config,
    }
    directory = args.output_dir or Path(
        tempfile.mkdtemp(prefix="command-smoke-output-")
    )
    directory.mkdir(parents=True, exist_ok=True)
    client = None
    import commands
    import valorant.match as match_module

    repository = storage_sqlite.UserSQLiteDB
    failures = 0
    with tempfile.TemporaryDirectory(prefix="command-smoke-db-") as scratch:
        isolated_repository = partial(
            repository, database_file=Path(scratch) / "tracking.db"
        )
        original_commands_db, original_match_db = (
            commands.UserSQLiteDB,
            match_module.UserSQLiteDB,
        )
        commands.UserSQLiteDB = match_module.UserSQLiteDB = isolated_repository
        try:
            channel = None
            if args.send:
                if not all(
                    str(config.get(k, "")).isdigit()
                    for k in (
                        "SMOKE_TEST_BOT_ID",
                        "SMOKE_TEST_GUILD_ID",
                        "SMOKE_TEST_CHANNEL_ID",
                    )
                ) or not config.get("BOT_TOKEN"):
                    raise ValueError(
                        "Sending requires BOT_TOKEN and all SMOKE_TEST_*_ID settings"
                    )
                client = discord.Client(intents=discord.Intents.none())
                await client.login(config["BOT_TOKEN"])
                channel = await client.fetch_channel(
                    int(config["SMOKE_TEST_CHANNEL_ID"])
                )
                validate_target(config, client.user, channel)
            guild_id = int(config.get("SMOKE_TEST_GUILD_ID") or 1)
            for name in dict.fromkeys(args.commands):
                capture = CapturedInteraction(guild_id)
                try:
                    call_args = (
                        (args.account,)
                        if name in ("last_match", "info", "predict")
                        else ()
                    )
                    await asyncio.wait_for(handlers[name](capture, *call_args), 150)
                    images = export_output(capture, directory, name)
                    message = (
                        await deliver(
                            channel, capture, images, name, args.include_private
                        )
                        if channel
                        else None
                    )
                    print(
                        name,
                        "SENT " + message.jump_url if message else "SAVED",
                        flush=True,
                    )
                except Exception as exc:
                    failures += 1
                    print(name, "FAILED", type(exc).__name__, flush=True)
        finally:
            if client:
                await client.close()
            commands.UserSQLiteDB = original_commands_db
            match_module.UserSQLiteDB = original_match_db
    print("Artifacts:", directory)
    return failures


def main():
    args = parser().parse_args()
    try:
        failures = asyncio.run(run(args))
    except Exception as exc:
        print("Smoke test failed:", type(exc).__name__)
        raise SystemExit(1)
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
