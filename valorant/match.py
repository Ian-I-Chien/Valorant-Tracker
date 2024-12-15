import os
import json
import math
import time
import asyncio
import discord
from .player import ValorantPlayer
from .api import fetch_json, url_json


class Match:
    def __init__(self, player_name, player_tag, region="ap"):
        self.last_match_id = None
        self.last_match_data = None
        self.player_name = player_name
        self.player_tag = player_tag
        self.region = region

    async def get_rank_with_retries(self, player_instance, retries=5, delay=2):
        attempt = 0
        while attempt < retries:
            rank_data_dict = await player_instance.get_rank()
            if rank_data_dict:
                return rank_data_dict
            attempt += 1
            await asyncio.sleep(delay)
        return None


    async def get_rank_with_retries(self, player_instance, retries=5, delay=2):
        attempt = 0
        while attempt < retries:
            try:
                rank_data_dict = await player_instance.get_rank()
                if rank_data_dict:
                    return rank_data_dict
            except Exception as e:
                print(f"Error fetching rank for {player_instance.player_name}: {e}")
            attempt += 1
            await asyncio.sleep(delay)
        print(f"Failed to fetch rank for {player_instance.player_name} after {retries} attempts.")
        return None


    async def sorted_formatted_player(self):
        sorted_players = sorted(
            self.last_match_data['data']['players']['all_players'],
            key=lambda x: x['stats']['score'],
            reverse=True
        )
        
        player_instances = [
            ValorantPlayer(player_name=p['name'], player_tag=p['tag'])
            for p in sorted_players
        ]

        rank_data_dicts = await asyncio.gather(*[
            self.get_rank_with_retries(player) for player in player_instances
        ])

        formatted_info = ""
        for index, (player, rank_data_dict) in enumerate(zip(sorted_players, rank_data_dicts)):
            current_tier = rank_data_dict.get('currenttierpatched', 'Unrated') if rank_data_dict else 'Unrated'
            rank_in_tier = rank_data_dict.get('ranking_in_tier') if rank_data_dict else None
            mmr_change = rank_data_dict.get('mmr_change_to_last_game') if rank_data_dict else None

            stats = player.get('stats', {})
            score = math.floor(stats.get('score', 0) / self.last_match_data['data']['metadata'].get('rounds_played', 1))
            total_shots = sum(stats.get(k, 0) for k in ['bodyshots', 'headshots', 'legshots'])
            headshot_percentage = (stats.get('headshots', 0) / total_shots * 100) if total_shots > 0 else 0

            formatted_info += "`{}`\n".format(
                f"[{player['team'][0]}] [{current_tier}] "
                f"[{player['name']}#{player['tag']}] "
            )
            formatted_info += "`{}`\n".format(
                f"{player['character']} "
                f"{stats.get('kills', 0)}/{stats.get('deaths', 0)}/{stats.get('assists', 0)} "
                f"[{headshot_percentage:.2f}%] "
                f"[{score}]"
            )
            print(rank_in_tier , mmr_change)
            if rank_in_tier is not None and mmr_change is not None and self.last_match_data['data']['metadata']['mode'] == 'Competitive':
                formatted_info += "`{}`\n".format(
                    f"[{rank_in_tier}/99] "
                    f"[{mmr_change:+d}]"
                )

        blue_wins = self.last_match_data['data']['teams']['blue']['rounds_won']
        red_wins = self.last_match_data['data']['teams']['red']['rounds_won']
        winning_team = "BLUE" if blue_wins > red_wins else "RED" if blue_wins < red_wins else "TIED"
        ratio = f"{blue_wins}:{red_wins}"

        winning_team_text = f"{winning_team} WIN!" if winning_team != "TIED" else winning_team

        title_info = "{}".format(
            f"Last Match\t"
            f"{self.last_match_data['data']['metadata']['map']}\n"
            f"{self.last_match_data['data']['metadata']['mode']}\t"
            f"{winning_team_text}\t"
            f"[{ratio}]"
        )

        embed = discord.Embed(title=title_info, color=discord.Color.blurple())
        embed.description = formatted_info
        return embed
    
    async def get_complete_last_match(self):
        await self.get_last_match_id()
        url = url_json['match'].format(matchid=self.last_match_id)
        self.last_match_data = await fetch_json(url)
        if not self.last_match_data:
            return None
        return self.last_match_data

    async def get_last_match(self):
        await self.get_last_match_id()
        url = url_json['match'].format(matchid=self.last_match_id)
        self.last_match_data = await fetch_json(url)
        if not self.last_match_data:
            return None
        return await self.sorted_formatted_player()


    async def get_last_match_id(self):
        url = url_json['matches_v3'].format(region=self.region, player_name=self.player_name, player_tag=self.player_tag)
        matches_data = await fetch_json(url)

        if not matches_data:
            return None
        last_match = matches_data["data"][0]
        self.last_match_id = last_match["metadata"]["matchid"]
        return self.last_match_id

    async def get_five_match_id(self):
        match_ids = []
        url = url_json['matches_v3'].format(region=self.region, player_name=self.player_name, player_tag=self.player_tag)
        matches_data = await fetch_json(url)

        if not matches_data:
            return None

        for i in range(len(matches_data["data"])):
            last_match = matches_data["data"][i]
            match_id = last_match["metadata"]["matchid"]
            match_ids.append(match_id)

        return '\n'.join([f'\t{match_id}' for match_id in match_ids])

    async def get_match_by_id(self, matchid):
        url = url_json['get_match_by_id'].format(region=self.region, matchid=matchid)
        matches_data = await fetch_json(url)
        return matches_data

    def save_matches_to_file(self, data, file_path="./testcase/match_info.json"):
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        print(f"Matches data saved to {file_path}")
