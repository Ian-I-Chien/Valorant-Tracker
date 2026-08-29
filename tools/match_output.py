"""Build and optionally send a match embed without changing polling state."""

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import Optional

import aiohttp
import discord
from dotenv import load_dotenv

from database.storage_sqlite import UserSQLiteDB
from valorant.match import Match

DISCORD_API_BASE_URL = "https://discord.com/api/v10"


@dataclass(frozen=True)
class MatchOutputPreview:
    account: str
    match_id: str
    embed: discord.Embed


def parse_riot_id(account: str) -> tuple[str, str]:
    try:
        player_name, player_tag = account.rsplit("#", 1)
    except ValueError as exc:
        raise ValueError("Account must use the format name#tag") from exc

    player_name = player_name.strip()
    player_tag = player_tag.strip()
    if not player_name or not player_tag:
        raise ValueError("Account must use the format name#tag")
    return player_name, player_tag


async def prepare_match_output(
    account: str, match_id: Optional[str] = None
) -> MatchOutputPreview:
    player_name, player_tag = parse_riot_id(account)
    match = Match(player_name, player_tag)

    selected_match_id = match_id or await match.get_last_match_id()
    if not selected_match_id:
        raise RuntimeError(f"No recent match found for {account}")

    match.last_match_id = selected_match_id
    if not await match.fetch_match():
        raise RuntimeError(f"Could not fetch match {selected_match_id}")

    embed = await match.build_embed()
    embed.set_footer(text=f"Manual developer test • Match ID: {selected_match_id}")
    return MatchOutputPreview(account, selected_match_id, embed)


async def get_server_channel_id(server_id: str) -> str:
    async with UserSQLiteDB() as repository:
        settings = await repository.get_guild_settings(server_id)
    if settings is None:
        raise RuntimeError(
            f"Server {server_id} has no channel; configure it with /set_channel"
        )
    return settings.notification_channel_id


async def send_embed(channel_id: str, embed: discord.Embed, bot_token: str) -> None:
    if not channel_id.isdigit():
        raise ValueError("Discord channel ID must contain digits only")

    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }
    payload = {"embeds": [embed.to_dict()]}
    url = f"{DISCORD_API_BASE_URL}/channels/{channel_id}/messages"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status not in {200, 201}:
                raise RuntimeError(
                    f"Discord rejected the test output with HTTP {response.status}"
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the latest Valorant match embed and optionally send it to "
            "a configured Discord server channel. This never updates polling state."
        )
    )
    parser.add_argument("--account", required=True, help="Riot ID in name#tag format")
    parser.add_argument(
        "--match-id",
        help="Specific match ID; omit to query the account's latest match",
    )
    parser.add_argument(
        "--server-id",
        help="Discord server whose configured notification channel receives the test",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the embed; without this flag the command is a dry run",
    )
    return parser


async def run(args: argparse.Namespace) -> None:
    if args.send and not args.server_id:
        raise ValueError("--server-id is required with --send")

    preview = await prepare_match_output(args.account, args.match_id)
    print(f"ACCOUNT={preview.account}")
    print(f"MATCH_ID={preview.match_id}")
    print(f"EMBED_TITLE={preview.embed.title}")

    if not args.send:
        print("RESULT=DRY_RUN (add --server-id SERVER_ID --send to deliver)")
        return

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN must be set before using --send")

    channel_id = await get_server_channel_id(args.server_id)
    await send_embed(channel_id, preview.embed, bot_token)
    print(f"SERVER_ID={args.server_id}")
    print(f"CHANNEL_ID={channel_id}")
    print("RESULT=SENT (polling checkpoint unchanged)")


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
