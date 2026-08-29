"""Render a real match to PNG for developer UI review."""

import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from tools.match_output import parse_riot_id
from valorant.match import Match


async def render(account: str, match_id: str | None, output: Path) -> None:
    player_name, player_tag = parse_riot_id(account)
    match = Match(player_name, player_tag)
    match.last_match_id = match_id or await match.get_last_match_id()
    if not match.last_match_id:
        raise RuntimeError(f"No recent match found for {account}")
    if not await match.fetch_match():
        raise RuntimeError(f"Could not fetch match {match.last_match_id}")
    image = await match.build_match_card()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    print(f"MATCH_ID={match.last_match_id}")
    print(f"OUTPUT={output.resolve()}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Render a Valorant match scoreboard PNG"
    )
    parser.add_argument("--account", required=True, help="Riot ID in name#tag format")
    parser.add_argument("--match-id", help="Specific match ID; defaults to latest")
    parser.add_argument("--output", type=Path, default=Path("match-scoreboard.png"))
    args = parser.parse_args()
    try:
        asyncio.run(render(args.account, args.match_id, args.output))
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
