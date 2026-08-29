import logging
import math
import asyncio
import discord
from typing import Any, Optional
from datetime import datetime, timezone
from .api import API_URLS, fetch_json
from database.storage_sqlite import UserSQLiteDB
from utils import fix_isoformat


LOGGER = logging.getLogger(__name__)


class Match:
    def __init__(self, player_name: str, player_tag: str, region: str = "ap"):
        self.last_match_id = None
        self.last_match_data = None
        self.player_name = player_name
        self.player_tag = player_tag
        self.region = region

    async def get_rank_with_retries(
        self, player_instance, retries: int = 5, delay: float = 2
    ) -> Optional[dict[str, Any]]:
        """
        Fetch rank data with retries to avoid transient API failures.
        """
        attempt = 0
        while attempt < retries:
            try:
                rank_data_dict = await player_instance.fetch_rank()
                if rank_data_dict:
                    return rank_data_dict
            except Exception:
                LOGGER.exception(
                    "Error fetching rank for %s", player_instance.player_name
                )
            attempt += 1
            await asyncio.sleep(delay)

        LOGGER.warning(
            "Failed to fetch rank for %s after %s attempts",
            player_instance.player_name,
            retries,
        )
        return None

    def check_melee_info(self):
        """
        Collect melee kills and melee deaths information from the match.
        Returns:
            tuple(list, list): (melee_killers, melee_victims)
        """
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
        """
        Calculate KAST from Henrikdev API v4_match.

        Args:
            match_data (dict): match data

        Returns:
            dict: {player_puuid: kast_percentage}
        """
        if match_data is None:
            if self.last_match_data is None:
                raise ValueError("calculate_kast match_data is null.")
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

        # Initialize per-player, per-round performance structure
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

        # Sort kills by time in match to handle trades correctly
        kills = sorted(kills, key=lambda x: x["time_in_match_in_ms"])
        killer_list = {}  # track who killed whom and when in the same round
        round_temp = -1

        for kill in kills:
            round_index: int = kill["round"]
            time_in_round_in_ms: int = int(kill["time_in_round_in_ms"])
            killer: str = kill["killer"]["puuid"]
            victim: str = kill["victim"]["puuid"]
            assistants: list = kill["assistants"]

            # Reset killer list when round changes
            if round_temp != round_index:
                round_temp = round_index
                killer_list.clear()

            # Record death
            players_rounds_performance[victim][round_index]["death"] += 1

            # Check for trade kills within 3 seconds
            if victim in killer_list:
                for victim_of_killer in killer_list[victim]:
                    if (time_in_round_in_ms - victim_of_killer["time"]) <= 3000:
                        players_rounds_performance[victim_of_killer["victim"]][
                            round_index
                        ]["trade"] += 1

            # Record kill
            players_rounds_performance[killer][round_index]["kill"] += 1
            if killer not in killer_list:
                killer_list[killer] = []
            killer_list[killer].append({"victim": victim, "time": time_in_round_in_ms})

            # Record assists
            for assistant in assistants:
                assistanter: str = assistant["puuid"]
                players_rounds_performance[assistanter][round_index]["assistant"] += 1

        # Calculate KAST for each player
        result = {}
        for player_uuid, rounds_info in players_rounds_performance.items():
            kast_rounds = 0
            for round_index in range(len(rounds)):
                one_round_data = rounds_info[round_index]
                got_kill: int = one_round_data["kill"]
                got_death: int = one_round_data["death"]
                got_assistant: int = one_round_data["assistant"]
                got_trade: int = one_round_data["trade"]

                if got_kill > 0 or got_assistant > 0 or got_trade > 0 or got_death == 0:
                    kast_rounds += 1

            player_kast = (kast_rounds / len(rounds)) * 100
            result[player_uuid] = player_kast

        return result

    async def build_embed(self) -> discord.Embed:
        """
        Build a Discord embed showing the last match summary and
        sorted player stats with rank, HS, KAST, etc.
        """
        from valorant.player import ValorantPlayer

        if self.last_match_data is None:
            raise ValueError("build_embed called with no match data")

        # Build a set of all registered Valorant accounts from SQLite storage
        async with UserSQLiteDB() as user_model:
            subscriptions = await user_model.list_subscriptions()

        registered_accounts = {
            subscription.valorant_account for subscription in subscriptions
        }

        melee_killers, melee_victims = self.check_melee_info()
        players_kast = self.calculate_kast()

        # Sort players by score (descending)
        sorted_players = sorted(
            self.last_match_data["data"]["players"],
            key=lambda x: x["stats"]["score"],
            reverse=True,
        )

        # Create ValorantPlayer instances for rank fetching
        player_instances = [
            ValorantPlayer(player_name=p["name"], player_tag=p["tag"])
            for p in sorted_players
        ]

        # Fetch rank information in parallel
        rank_data_dicts = await asyncio.gather(
            *[self.get_rank_with_retries(player) for player in player_instances]
        )

        formatted_info = ""
        for index, (player, rank_data_dict) in enumerate(
            zip(sorted_players, rank_data_dicts)
        ):
            player_name = f"{player['name']}#{player['tag']}"

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
            total_rounds = (
                self.last_match_data["data"]["teams"][0]["rounds"]["won"]
                + self.last_match_data["data"]["teams"][0]["rounds"]["lost"]
            )

            score = math.floor(stats.get("score", 0) / total_rounds)

            total_shots = sum(
                stats.get(k, 0) for k in ["bodyshots", "headshots", "legshots"]
            )
            headshot_percentage = (
                (stats.get("headshots", 0) / total_shots * 100)
                if total_shots > 0
                else 0
            )

            agent_name = player["agent"].get("name", "Unknown Agent")

            # Melee info (knife kills / deaths)
            melee_info = ""
            melee_kill_count = melee_killers.count(player["name"])
            melee_victim_count = melee_victims.count(player["name"])

            if melee_kill_count > 0:
                melee_info += f"[Knifed x{melee_kill_count}] :>"
            if melee_victim_count > 0:
                melee_info += f"[Get Knifed x{melee_victim_count}] :<"

            # Team + rank header
            formatted_info += "`{}` ".format(
                f"[{'🔵' if player['team_id'] == 'Blue' else '🔴'}] "
                f"[{current_tier}]"
            )

            # Highlight players that are registered in our JSON DB
            if player_name in registered_accounts:
                formatted_info += "**`{}`**\n".format(f"[{player_name}]")
            else:
                formatted_info += "`{}`\n".format(f"[{player_name}]")

            # Detailed stats (except for Team Deathmatch)
            queue_name = self.last_match_data["data"]["metadata"]["queue"]["name"]
            if queue_name != "Team Deathmatch":
                formatted_info += "`{}`\n".format(
                    f"{agent_name} "
                    f"{stats.get('kills', 0)}/{stats.get('deaths', 0)}/{stats.get('assists', 0)} "
                    f"[{headshot_percentage:.2f}%] "
                    f"[{score}] "
                    f"[KAST: {players_kast[player['puuid']]:.2f}%]"
                )
            else:
                formatted_info += "`{}`\n".format(
                    f"{agent_name} "
                    f"{stats.get('kills', 0)}/{stats.get('deaths', 0)}/{stats.get('assists', 0)} "
                    f"[{headshot_percentage:.2f}%]"
                )

            # Rank progress (only for Competitive queue)
            if (
                rank_in_tier is not None
                and mmr_change is not None
                and queue_name == "Competitive"
            ):
                formatted_info += "`{}`\n".format(
                    f"[{rank_in_tier}/99] [{mmr_change:+d}]"
                )

            # Melee info line, if any
            if melee_info:
                formatted_info += "`{}`\n".format(melee_info)

            formatted_info += "\n"

        # Compute team scores and winning side
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

        # Match time
        iso_time = self.last_match_data["data"]["metadata"]["started_at"]
        dt = datetime.fromisoformat(fix_isoformat(iso_time))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        readable_time = dt.astimezone().strftime("%Y/%m/%d %H:%M")

        title_info = "{}".format(
            f"Last Match\t"
            f"{self.last_match_data['data']['metadata']['map']['name']}\n"
            f"{queue_name}\t"
            f"{winning_team_text}\t"
            f"[{ratio}]\n"
            f"Time: {readable_time}"
            # f"Match ID: {self.last_match_id}"
        )

        # Map image
        map_id = self.last_match_data["data"]["metadata"]["map"]["id"]
        image_url = f"https://media.valorant-api.com/maps/{map_id}/listviewicon.png"

        # Embed color by winning team
        color = (
            discord.Color.blue()
            if winning_team == "BLUE"
            else (
                discord.Color.red()
                if winning_team == "RED"
                else discord.Color.greyple()
            )
        )

        embed = discord.Embed(title=title_info, color=color)
        embed.set_image(url=image_url)
        embed.description = formatted_info

        return embed

    async def fetch_match(self) -> Optional[dict[str, Any]]:
        """
        Fetch full match data using the stored last_match_id.
        """
        url = API_URLS["match"].format(region=self.region, matchid=self.last_match_id)
        self.last_match_data = await fetch_json(url)
        if not self.last_match_data:
            return None
        return self.last_match_data

    async def fetch_recent_matches(self) -> Optional[dict[str, Any]]:
        """
        Fetch recent matches for the player from Henrikdev API (v3).
        """
        url = API_URLS["matches_v3"].format(
            region=self.region,
            player_name=self.player_name,
            player_tag=self.player_tag,
        )
        matches_data = await fetch_json(url)
        if not matches_data:
            return None
        return matches_data

    async def get_last_match_id(self):
        """
        Fetch and store the latest match ID for this player.
        """
        matches_data = await self.fetch_recent_matches()
        if not matches_data:
            return None

        last_match = matches_data["data"][0]
        self.last_match_id = last_match["metadata"]["matchid"]
        return self.last_match_id
