import os
import json
import math
import time
import asyncio
import discord
from typing import Optional
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
            try:
                rank_data_dict = await player_instance.get_rank_by_api()
                if rank_data_dict:
                    return rank_data_dict
            except Exception as e:
                print(f"Error fetching rank for {player_instance.player_name}: {e}")
            attempt += 1
            await asyncio.sleep(delay)
        print(
            f"Failed to fetch rank for {player_instance.player_name} after {retries} attempts."
        )
        return None

    def check_melee_info(self):
        melee_killers = []
        melee_victims = []
        for kill in self.last_match_data["data"]["kills"]:
            weapon_type = kill["weapon"]["type"]
            if weapon_type == "Melee":
                killer_name = kill["killer"]["name"]
                victim_name = kill["victim"]["name"]
                melee_killers.append(killer_name)
                melee_victims.append(victim_name)
        return melee_killers, melee_victims

    def calculate_kast(self, match_data: dict = None) -> Optional[dict]:
        """Calculate KAST from Henrikdev API v4_match

        Args:
            match_data (dict): match data

        Returns:
            dict: all players kast information
        """
        if match_data is None:
            if self.last_match_data is None:
                raise ValueError(f"calculate_kast match_data is null.")
            match_data = self.last_match_data

        data = match_data.get("data", None)
        if data is None:
            raise ValueError("calculate_kast data is null.")

        players: list = data.get("players", None)
        if players is None:
            raise ValueError("calculate_kast players is null.")

        rounds: list = data.get("rounds", None)
        if rounds is None:
            raise ValueError("calculate_kast rounds is null.")

        kills: list = data.get("kills", None)
        if kills is None:
            raise ValueError("calculate_kast kills is null.")

        players_rounds_performance = {}
        for player in players:
            puuid: str = player["puuid"]
            players_rounds_performance[puuid] = []
            for _ in range(len(rounds)):
                players_rounds_performance[puuid].append(
                    {
                        "kill": 0,
                        "assistant": 0,
                        "death": 0,
                        "trade": 0,
                    }
                )

        kills = sorted(kills, key=lambda x: x["time_in_match_in_ms"])
        killer_list = {}  # who kill victim, which round and when
        round_temp = -1
        for kill in kills:
            round: int = kill["round"]
            time_in_round_in_ms: int = int(kill["time_in_round_in_ms"])
            killer: str = kill["killer"]["puuid"]
            victim: str = kill["victim"]["puuid"]
            assistants: list = kill["assistants"]

            # reset killer lists
            if round_temp != round:
                round_temp = round
                killer_list.clear()

            # got victim
            players_rounds_performance[victim][round]["death"] += 1

            # got trade
            if victim in killer_list:
                for victim_of_killer in killer_list[victim]:
                    if (time_in_round_in_ms - victim_of_killer["time"]) <= 3000:
                        players_rounds_performance[victim_of_killer["victim"]][round][
                            "trade"
                        ] += 1

            # got kill
            players_rounds_performance[killer][round]["kill"] += 1
            if not killer in killer_list:
                killer_list[killer] = list()
            killer_list[killer].append({"victim": victim, "time": time_in_round_in_ms})

            # got assistant
            for assistant in assistants:
                assistanter: str = assistant["puuid"]
                players_rounds_performance[assistanter][round]["assistant"] += 1

        result = {}
        for player_uuid, rounds_info in players_rounds_performance.items():
            kast_with_round = 0
            for round in range(len(rounds)):
                one_round_data = rounds_info[round]
                got_kill: int = one_round_data["kill"]
                got_death: int = one_round_data["death"]
                got_assistant: int = one_round_data["assistant"]
                got_trade: int = one_round_data["trade"]

                if got_kill > 0 or got_assistant > 0 or got_trade > 0 or got_death == 0:
                    kast_with_round += 1
            player_kast = (kast_with_round / len(rounds)) * 100
            result[player_uuid] = player_kast
        return result

    async def sorted_formatted_player(self):

        melee_killers, melee_victims = self.check_melee_info()
        players_kast = self.calculate_kast()

        sorted_players = sorted(
            self.last_match_data["data"]["players"],
            key=lambda x: x["stats"]["score"],
            reverse=True,
        )

        from .player import ValorantPlayer

        player_instances = [
            ValorantPlayer(player_name=p["name"], player_tag=p["tag"])
            for p in sorted_players
        ]

        rank_data_dicts = await asyncio.gather(
            *[self.get_rank_with_retries(player) for player in player_instances]
        )

        formatted_info = ""
        for index, (player, rank_data_dict) in enumerate(
            zip(sorted_players, rank_data_dicts)
        ):

            current_tier = (
                rank_data_dict.get("currenttierpatched", "Unrated")
                if rank_data_dict
                else "Unrated"
            )
            rank_in_tier = (
                rank_data_dict.get("ranking_in_tier") if rank_data_dict else None
            )
            mmr_change = (
                rank_data_dict.get("mmr_change_to_last_game")
                if rank_data_dict
                else None
            )

            stats = player.get("stats", {})
            score = math.floor(
                stats.get("score", 0)
                / (
                    self.last_match_data["data"]["teams"][0]["rounds"]["won"]
                    + self.last_match_data["data"]["teams"][0]["rounds"]["lost"]
                )
            )
            total_shots = sum(
                stats.get(k, 0) for k in ["bodyshots", "headshots", "legshots"]
            )
            headshot_percentage = (
                (stats.get("headshots", 0) / total_shots * 100)
                if total_shots > 0
                else 0
            )

            agent_name = player["agent"].get("name", "Unknown Agent")
            melee_info = ""
            melee_kill_count = melee_killers.count(player["name"])
            melee_victim_count = melee_victims.count(player["name"])

            if melee_kill_count > 0:
                melee_info += f"[Knifed x{melee_kill_count}] :>"
            if melee_victim_count > 0:
                melee_info += f"[Get Knifed x{melee_victim_count}] :<"

            formatted_info += "`{}`\n".format(
                f"[{player['team_id']}] [{current_tier}] "
                f"[{player['name']}#{player['tag']}]"
            )

            formatted_info += "`{}`\n".format(
                f"{agent_name} "
                f"{stats.get('kills', 0)}/{stats.get('deaths', 0)}/{stats.get('assists', 0)} "
                f"[{headshot_percentage:.2f}%] "
                f"[{score}] "
                f"[KAST: {players_kast[player['puuid']]:.2f}%]"
            )

            if (
                rank_in_tier is not None
                and mmr_change is not None
                and self.last_match_data["data"]["metadata"]["queue"]["name"]
                == "Competitive"
            ):
                formatted_info += "`{}`\n".format(
                    f"[{rank_in_tier}/99] " f"[{mmr_change:+d}]"
                )

            if melee_info:
                formatted_info += "`{}`\n".format(f"{melee_info}")
            formatted_info += "\n"

        blue_wins = next(
            team["rounds"]["won"]
            for team in self.last_match_data["data"]["teams"]
            if team["team_id"] == "Blue"
        )
        red_wins = next(
            team["rounds"]["won"]
            for team in self.last_match_data["data"]["teams"]
            if team["team_id"] == "Red"
        )

        winning_team = (
            "BLUE"
            if blue_wins > red_wins
            else "RED" if blue_wins < red_wins else "TIED"
        )

        ratio = f"{blue_wins}:{red_wins}"

        winning_team_text = (
            f"{winning_team} WIN!" if winning_team != "TIED" else winning_team
        )

        title_info = "{}".format(
            f"Last Match\t"
            f"{self.last_match_data['data']['metadata']['map']['name']}\n"
            f"{self.last_match_data['data']['metadata']['queue']['name']}\t"
            f"{winning_team_text}\t"
            f"[{ratio}]"
        )

        map_id = self.last_match_data["data"]["metadata"]["map"]["id"]
        image_url = f"https://media.valorant-api.com/maps/{map_id}/listviewicon.png"

        embed = discord.Embed(title=title_info, color=discord.Color.blurple())
        embed.set_image(url=image_url)
        embed.description = formatted_info
        return embed

    async def get_stored_match_by_id_by_api(self):
        url = url_json["match"].format(region=self.region, matchid=self.last_match_id)
        self.last_match_data = await fetch_json(url)
        if not self.last_match_data:
            return None
        return self.last_match_data

    async def get_complete_last_match(self):
        await self.get_last_match_id()
        await self.get_stored_match_by_id_by_api()
        if not self.last_match_data:
            return None
        return self.last_match_data

    async def get_last_match(self):
        await self.get_last_match_id()
        await self.get_stored_match_by_id_by_api()
        if not self.last_match_data:
            return None
        return await self.sorted_formatted_player()

    async def get_matches_v3_by_api(self):
        url = url_json["matches_v3"].format(
            region=self.region, player_name=self.player_name, player_tag=self.player_tag
        )
        matches_data = await fetch_json(url)
        if not matches_data:
            return None
        return matches_data

    async def get_last_match_id(self):
        matches_data = await self.get_matches_v3_by_api()
        if not matches_data:
            return None
        last_match = matches_data["data"][0]
        self.last_match_id = last_match["metadata"]["matchid"]
        return self.last_match_id

    async def get_five_match_id(self):
        match_ids = []
        matches_data = await self.get_matches_v3_by_api()
        if not matches_data:
            return None

        for i in range(len(matches_data["data"])):
            last_match = matches_data["data"][i]
            match_id = last_match["metadata"]["matchid"]
            match_ids.append(match_id)

        return "\n".join([f"\t{match_id}" for match_id in match_ids])

    async def get_match_by_id(self, matchid):
        url = url_json["get_match_by_id"].format(region=self.region, matchid=matchid)
        self.last_match_data = await fetch_json(url)
        return self.last_match_data

    def save_matches_to_file(self, data, file_path="./testcase/match_info.json"):
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        print(f"Matches data saved to {file_path}")
