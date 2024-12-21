from valorant.player import ValorantPlayer
from valorant.match import Match
import asyncio
import sys


def help_message():
    print("Usage:\npython3 -m testcase.test_val_api [API Command] Account Tag")
    print(
        "[API Command]: [get_account, get_rank, get_last_match_id",
        "get_last_match, get_five_match_id, get_melee_killer, get_stored_match_by_api], get_matches_v3_by_api",
    )
    print("python3 -m testcase.test_val_api get_melee_killer Account Tag [MATCHID]")


async def main():
    if len(sys.argv) < 4 or len(sys.argv) > 5:
        help_message()
        sys.exit(1)
    case = sys.argv[1]

    player = ValorantPlayer(sys.argv[2], sys.argv[3])
    match = Match(sys.argv[2], sys.argv[3])

    try:
        if case == "get_account":
            print(await player.get_account_by_api())
        elif case == "get_rank":
            print(await player.get_rank_by_api())
        elif case == "get_last_match_id":
            print(await match.get_last_match_id())
        elif case == "get_last_match":
            data = await match.get_complete_last_match()
            match.save_matches_to_file(data)
        elif case == "get_five_match_id":
            print(await match.get_five_match_id())
        elif case == "get_match_by_id":
            data = await match.get_match_by_id(sys.argv[4])
            match.save_matches_to_file(data, "./testcase/match_by_id.json")
            print("Check data in ./testcase/match_by_id.json")
        elif case == "get_melee_killer":
            data = await match.get_match_by_id(sys.argv[4])
            print(match.check_melee_info())
        elif case == "get_match_stats":
            data = await player.get_stored_match_by_api()
            match.save_matches_to_file(data, "./testcase/match_states.json")
            print("Check data in ./testcase/match_states.json")
        elif case == "get_matches_v3_by_api":
            data = await match.get_matches_v3_by_api()
            match.save_matches_to_file(data, "./testcase/match_v3.json")
            print("Check data in ./testcase/match_v3.json")
        else:
            help_message()
            sys.exit(1)
    except Exception as e:
        help_message()
        sys.exit(1)


# python3 -m testcase.test_val_api args account tag
if __name__ == "__main__":
    asyncio.run(main())
