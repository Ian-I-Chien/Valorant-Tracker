import os
import aiohttp
import discord
from .match import Match
from .api import fetch_json, url_json


class ValorantPlayer:
    def __init__(self, player_name, player_tag, region="ap"):
        self.player_name = player_name
        self.player_tag = player_tag
        self.region = region
        self.account_data = None
        self.rank_data = None
        self.match = Match(player_name, player_tag, region="ap")
        self.competitive_matches_id = []
        self.unrated_matches_id = []

    async def get_account_by_api(self):
        url = url_json["account"].format(
            region=self.region, player_name=self.player_name, player_tag=self.player_tag
        )
        account_data = await fetch_json(url)
        self.account_data = account_data.get("data") if account_data else None
        return self.account_data

    async def get_rank_by_api(self):
        url = url_json["rank"].format(
            region=self.region, player_name=self.player_name, player_tag=self.player_tag
        )
        rank_data = await fetch_json(url)
        self.rank_data = rank_data.get("data") if rank_data else None
        return self.rank_data
