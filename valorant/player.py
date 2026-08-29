import logging
from typing import Any, Optional

from .api import API_URLS, fetch_json

LOGGER = logging.getLogger(__name__)


class ValorantPlayer:
    def __init__(self, player_name: str, player_tag: str, region: str = "ap"):
        self.player_name = player_name
        self.player_tag = player_tag
        self.region = region
        self.account_data = None
        self.rank_data = None

    async def fetch_account(self) -> Optional[dict[str, Any]]:
        url = API_URLS["account"].format(
            region=self.region, player_name=self.player_name, player_tag=self.player_tag
        )
        account_data = await fetch_json(url)
        if not account_data or not account_data.get("data"):
            LOGGER.info(
                "Cached account lookup failed for %s#%s; forcing refresh",
                self.player_name,
                self.player_tag,
            )
            account_data = await fetch_json(url, params={"force": "true"})

        self.account_data = account_data.get("data") if account_data else None
        if self.account_data:
            self.player_name = self.account_data.get("name", self.player_name)
            self.player_tag = self.account_data.get("tag", self.player_tag)

        return self.account_data

    async def fetch_rank(self) -> Optional[dict[str, Any]]:
        url = API_URLS["rank"].format(
            region=self.region, player_name=self.player_name, player_tag=self.player_tag
        )
        rank_data = await fetch_json(url)
        self.rank_data = rank_data.get("data") if rank_data else None
        return self.rank_data
