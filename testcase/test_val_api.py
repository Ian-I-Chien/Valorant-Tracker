import argparse
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from valorant.player import ValorantPlayer
from valorant.match import Match

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def get_account(player):
    return await player.get_account_by_api()


async def get_rank(player):
    return await player.get_rank_by_api()


async def get_last_match_id(match):
    return await match.get_last_match_id()


async def get_last_match(match):
    data = await match.get_complete_last_match()
    match.save_matches_to_file(data)


async def get_match_by_id(match, match_id):
    data = await match.get_match_by_id(match_id)
    match.save_matches_to_file(data, "./testcase/match_by_id.json")
    logging.info("Check data in ./testcase/match_by_id.json")


async def get_melee_killer(match, match_id):
    await match.get_match_by_id(match_id)
    return match.check_melee_info()


async def main():
    parser = argparse.ArgumentParser(
        description="Valorant API Test CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "command",
        type=str,
        help="""API command to execute. Available commands:
    - get_account                : Retrieve account information
    - get_rank                   : Get current rank
    - get_last_match_id          : Get the last match ID
    - get_last_match             : Retrieve details of the last match
    - get_match_by_id [MATCH_ID] : Fetch match details by match ID
    - get_melee_killer [MATCH_ID]: Retrieve melee kill stats for a match""",
    )

    parser.add_argument(
        "account", type=str, help="Valorant account name (e.g., MyAccount)"
    )
    parser.add_argument("tag", type=str, help="Valorant account tag (e.g., 1234)")
    parser.add_argument(
        "match_id",
        type=str,
        nargs="?",
        help="Optional Match ID (required for some commands)",
    )

    args = parser.parse_args()

    player = ValorantPlayer(args.account, args.tag)
    match = Match(args.account, args.tag)

    commands = {
        "get_account": lambda: get_account(player),
        "get_rank": lambda: get_rank(player),
        "get_last_match_id": lambda: get_last_match_id(match),
        "get_last_match": lambda: get_last_match(match),
        "get_match_by_id": lambda: get_match_by_id(match, args.match_id),
        "get_melee_killer": lambda: get_melee_killer(match, args.match_id),
    }

    if args.command not in commands:
        parser.print_help()
        return

    try:
        result = await commands[args.command]()
        if result:
            print(result)
    except Exception as e:
        logging.error(f"Error executing {args.command}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
