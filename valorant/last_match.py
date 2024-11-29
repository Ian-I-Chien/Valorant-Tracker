import os
import json
import math
import asyncio
import discord
from .api import fetch_json, url_json

class LastMatch:
    def __init__(self, player_name, player_tag, region="ap"):
        self.last_match_id = None
        self.last_match_data = None
        self.player_name = player_name
        self.player_tag = player_tag
        self.region = region

    def sorted_player(self):
        sorted_players = sorted( self.last_match_data['data']['players']['all_players'], key=lambda x: x['stats']['score'], reverse=True)
        total_players = len(sorted_players)
        formatted_info = ""
        for index, player in enumerate(sorted_players):
            score = math.floor(player['stats']['score'] / self.last_match_data['data']['metadata']['rounds_played'])
            total_shots = player['stats']['bodyshots'] + player['stats']['headshots'] + player['stats']['legshots']
            headshot_percentage = (player['stats']['headshots'] / total_shots) * 100 if total_shots > 0 else 0
            
            formatted_info += "`{}`\n".format(
                f"[{player['team'][0]}] [{player['currenttier_patched']}] "
                f"[{player['name']}#{player['tag']}] "
            )

            formatted_info += "`{}`\n".format(
                f"{player['character']} "
                f"{player['stats']['kills']}/{player['stats']['deaths']}/{player['stats']['assists']} "
                f"[{headshot_percentage:.2f}%]"
                f"[{score}]"
            )
        title_info = "{}".format(
            f"Player LeaderBoard of Last Match\n"
            f"{self.last_match_data['data']['metadata']['mode']}"
        )
        embed = discord.Embed(title=title_info, color=discord.Color.blurple())
        embed.description = formatted_info
        return embed


    async def get_last_match(self):
        await self.get_last_match_id()
        url = url_json['match'].format(matchid=self.last_match_id)
        self.last_match_data = await fetch_json(url)
        if not self.last_match_data:
            return None
        return self.sorted_player()


    async def get_last_match_id(self):
        url = url_json['matches_v3'].format(region=self.region, player_name=self.player_name, player_tag=self.player_tag)
        matches_data = await fetch_json(url)
        if not matches_data:
            return None
        last_match = matches_data["data"][0]
        self.last_match_id = last_match["metadata"]["matchid"]


    async def save_matches_to_file(self, file_path="matches-id.json"):
        matches_data = await self.get_last_match_id()
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(matches_data, file, ensure_ascii=False, indent=4)
        print(f"Matches data saved to {file_path}")

