from valorant.player import ValorantPlayer
from valorant.last_match import LastMatch
import asyncio
import sys

def help_message():
    print("Usage:\npython3 -m testcase.test_val_api.py [API Command] Account Tag")
    print("[API Command]: [get_account, get_rank, get_last_match_id", "get_last_match, get_five_match_id]")
    print("python3 -m testcase.test_val_api.py get_match_by_id [MATCHID]")

  
async def main():
    if len(sys.argv) < 4 or len(sys.argv) > 5:
        help_message()
        sys.exit(1)
    case = sys.argv[1]

    player = ValorantPlayer(sys.argv[2], sys.argv[3])
    last_match = LastMatch(sys.argv[2], sys.argv[3])

    if case == "get_account":
        print(await player.get_account())
    elif case == "get_rank":
        print(await player.get_rank())
    elif case == "get_last_match_id":
        print(await last_match.get_last_match_id())
    elif case == "get_last_match":
        data = await last_match.get_complete_last_match()
        last_match.save_matches_to_file(data)
    elif case == "get_five_match_id":
        print(await last_match.get_five_match_id())
    elif case == "get_match_by_id":
        data = await last_match.get_match_by_id(sys.argv[4])
        last_match.save_matches_to_file(data)
    else:
        help_message()
        sys.exit(1)

# python3 -m testcase.test_val_api args account tag
if __name__ == "__main__":
    asyncio.run(main())





