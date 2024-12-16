import os
import aiohttp
import discord
from .match_stats import MatchStats
from .api import fetch_json, url_json


class ValorantPlayer:
    def __init__(self, player_name, player_tag, region="ap"):
        self.player_name = player_name
        self.player_tag = player_tag
        self.region = region
        self.account_data = None
        self.rank_data = None
        self.match_stats = MatchStats()

    async def get_account(self):
        url = url_json["account"].format(
            region=self.region, player_name=self.player_name, player_tag=self.player_tag
        )
        account_data = await fetch_json(url)
        self.account_data = account_data.get("data") if account_data else None
        return self.account_data

    async def get_rank(self):
        url = url_json["rank"].format(
            region=self.region, player_name=self.player_name, player_tag=self.player_tag
        )
        rank_data = await fetch_json(url)
        self.rank_data = rank_data.get("data") if rank_data else None
        return self.rank_data

    async def get_match_stats(self):
        url = url_json["matches_v1"].format(
            region=self.region, player_name=self.player_name, player_tag=self.player_tag
        )
        matches_data = await fetch_json(url)

        if not matches_data:
            return None

        matches = matches_data.get("data", [])

        for match in matches:
            if match["meta"]["mode"] == "Deathmatch":
                continue
            self.match_stats.update_stats(match)

        return self.match_stats.get_summary()

    async def get_player_info(self):
        account_data = await self.get_account()
        if not account_data:
            return {"error": "Unable to fetch account data."}

        rank_data = await self.get_rank()
        if not rank_data:
            return {"error": "Unable to fetch rank data."}

        stats = await self.get_match_stats()
        if not stats:
            return {"error": "Unable to fetch match stats."}

        (
            average_headshot_ratio,
            highest_ratio,
            lowest_ratio,
            highest_death,
            lowest_kill,
        ) = stats

        tier_image_url = rank_data.get("images", {}).get("large", None)
        player_card = account_data["card"]["small"]

        formatted_info = (
            f"Account Level: {account_data['account_level']}\n\n"
            f"Lowest Kill: {lowest_kill}\n"
            f"Highest Death: {highest_death}\n\n"
            f"Highest HS Rate: {highest_ratio}%\n"
            f"Lowest HS Rate: {lowest_ratio}%\n"
            f"Avg. HS Rate (100 Games): {average_headshot_ratio}%\n"
            f"### Rank Info:\n"
            f"Ranking in Tier: {rank_data['ranking_in_tier']}\n"
            f"Last Game: {rank_data['mmr_change_to_last_game']}\n"
        )

        embed = discord.Embed(
            title=f"{account_data['name']}#{account_data['tag']}",
            color=discord.Color.blurple(),
        )
        embed.description = formatted_info
        embed.set_thumbnail(url=player_card)
        embed.set_footer(text=rank_data["currenttierpatched"], icon_url=tier_image_url)

        return embed
