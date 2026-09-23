"""Developer-only live probe; prints metadata, never tokens or offer details."""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from valorant.multi_shop import MultiShopService
from valorant.shop_service import RiotStoreClient, ShopError, Vault


async def run(args):
    vault = Vault(args.database, Path(args.key_file).read_bytes().strip())
    service = MultiShopService(vault, RiotStoreClient(), {args.owner})
    accounts, _ = await service.accounts(args.owner)
    print(f"linked_accounts={len(accounts)}")
    for account in accounts:
        try:
            result = await service.night_market(args.owner, account["id"])
            remaining = max(0, int(result["expires"] - time.time()))
            print(
                "night_market_ok",
                account["label"],
                f"offers={len(result['offers'])}",
                f"remaining_seconds={remaining}",
            )
        except ShopError as error:
            print("night_market_unavailable", account["label"], str(error))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--owner", required=True, type=int)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
