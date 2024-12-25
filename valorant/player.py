import os
import aiohttp
import discord
from .match import Match
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

    async def get_stored_match_by_api(self):
        url = url_json["matches_v1"].format(
            region=self.region, player_name=self.player_name, player_tag=self.player_tag
        )
        matches_data = await fetch_json(url)
        if not matches_data:
            return None
        return matches_data

    async def get_match_stats(self):
        matches_data = await self.get_stored_match_by_api()
        if not matches_data:
            return None

        matches = matches_data.get("data", [])

        for match in matches:
            mode = match["meta"]["mode"]
            if mode == "Competitive" and len(self.competitive_matches_id) < 10:
                self.competitive_matches_id.append(match["meta"]["id"])
                self.match_stats.update_stats(match)

        for match in matches:
            mode = match["meta"]["mode"]
            if (
                mode == "Unrated"
                and len(self.competitive_matches_id) + len(self.unrated_matches_id) < 10
            ):
                self.unrated_matches_id.append(match["meta"]["id"])
                self.match_stats.update_stats(match)

        return self.match_stats.get_summary()

    async def get_10_matches_melee_info(self):
        melee_killers_count, melee_victims_count = 0, 0
        all_match_ids = self.competitive_matches_id + self.unrated_matches_id

        for match_id in all_match_ids:
            await self.match.get_match_by_id(match_id)
            melee_killers, melee_victims = self.match.check_melee_info()

            player_name_lower = self.player_name.lower()

            if any(player.lower() == player_name_lower for player in melee_killers):
                melee_killers_count += 1

            if any(player.lower() == player_name_lower for player in melee_victims):
                melee_victims_count += 1

        return melee_killers_count, melee_victims_count

    async def get_player_info(self):
        account_data = await self.get_account_by_api()
        if not account_data:
            return {"error": "Unable to fetch account data."}

        rank_data = await self.get_rank_by_api()
        if not rank_data:
            return {"error": "Unable to fetch rank data."}

        stats = await self.get_match_stats()

        melee_killers_count, melee_victims_count = (
            await self.get_10_matches_melee_info()
        )

        if not stats:
            return {"error": "Unable to fetch match stats."}

        (
            average_headshot_ratio,
            highest_ratio,
            lowest_ratio,
            highest_kills,
            average_kda,
            win_rate,
        ) = stats

        tier_image_url = rank_data.get("images", {}).get("large", None)
        player_card = account_data["card"]["small"]

        formatted_info = (
            f"Account Level: {account_data['account_level']}\n"
            f"### Info in 10 Games\n"
            f"WIN Rate: {win_rate}%\n\n"
            f"H Kills: {highest_kills}\n"
            f"Avg. KDA: {average_kda}\n\n"
            f"H HS: {highest_ratio}%\n"
            f"L HS: {lowest_ratio}%\n"
            f"Avg. HS: {average_headshot_ratio}%\n\n"
            f"Knifed: {melee_killers_count} Times\n"
            f"Got knifed: {melee_victims_count} Times\n"
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
