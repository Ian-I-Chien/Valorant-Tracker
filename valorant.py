import aiohttp
import discord
from dotenv import load_dotenv
import os


url_json = {
    'matches_v1': 'https://api.henrikdev.xyz/valorant/v1/stored-matches/{region}/{player_name}/{player_tag}',
    'account': 'https://api.henrikdev.xyz/valorant/v1/account/{player_name}/{player_tag}',
    'rank': 'https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{player_name}/{player_tag}',
}

API_SUCCESS = 200

load_dotenv()
api_key = os.getenv("API_KEY")

headers = {
    'Authorization': f'{api_key}',
    'accept': 'application/json'
}

class MatchStats:
    def __init__(self):
        self.highest_ratio = -1
        self.highest_ratio = -1
        self.highest_deaths = -1
        self.total_head = 0
        self.total_shots = 0
        self.lowest_kill = int(1e9)
        self.lowest_ratio = int(1e9)

    def update_stats(self, match):
        kills = match["stats"]["kills"]
        deaths = match["stats"]["deaths"]
        shots = match["stats"]["shots"]
        head = shots["head"]
        body = shots["body"]
        leg = shots["leg"]
        
        total_shots_in_match = head + body + leg

        self.lowest_kill = min(self.lowest_kill, kills)
        self.highest_deaths = max(self.highest_deaths, deaths)

        self.total_head += head
        self.total_shots += total_shots_in_match
        if total_shots_in_match > 0:
            headshot_ratio_each_match = (head / total_shots_in_match) * 100
            self.highest_ratio = max(self.highest_ratio, headshot_ratio_each_match)
            self.lowest_ratio = min(self.lowest_ratio, headshot_ratio_each_match)

    def get_summary(self):
        if self.total_shots > 0:
            average_headshot_ratio = (self.total_head / self.total_shots) * 100
            return (
                round(average_headshot_ratio, 2),
                round(self.highest_ratio, 2),
                round(self.lowest_ratio, 2),
                self.highest_deaths,
                self.lowest_kill,
            )
        else:
            return None

async def fetch_json(url, params=None):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status == API_SUCCESS:
                return await response.json()
            return None

async def get_data_from_matches_v1(player_name, player_tag):
    url = url_json['matches_v1'].format(region="ap", player_name=player_name, player_tag=player_tag)
    matches_data = await fetch_json(url)

    if not matches_data:
        return None
    
    match_stats = MatchStats()
    matches = matches_data.get("data", [])
    
    for match in matches:
        if match["meta"]["mode"] == "Deathmatch":
            continue
        match_stats.update_stats(match)
    
    return match_stats.get_summary()

async def get_account(player_name, player_tag):
    url = url_json['account'].format(region="ap", player_name=player_name, player_tag=player_tag)
    account_data = await fetch_json(url)
    return account_data.get('data') if account_data else None

async def get_rank(player_name, player_tag):
    url = url_json['rank'].format(region="ap", player_name=player_name, player_tag=player_tag)
    rank_data = await fetch_json(url)
    return rank_data.get('data') if rank_data else None

async def get_player_info_via_api(player_name, player_tag):
    account_data = await get_account(player_name, player_tag)
    if not account_data:
        return {"error": "Unable to fetch account data."}

    rank_data = await get_rank(player_name, player_tag)
    if not rank_data:
        return {"error": "Unable to fetch rank data."}
    
    stats = await get_data_from_matches_v1(player_name, player_tag)
    if not stats:
        return {"error": "Unable to fetch match stats."}

    average_headshot_ratio, highest_ratio, lowest_ratio, highest_death, lowest_kill = stats

    tier_image_url = rank_data.get('images', {}).get('small', None)
    
    formatted_info = (
        f"### Account Info:\n"
        f"Name: {account_data['name']}#{account_data['tag']}\n"
        f"Account Level: {account_data['account_level']}\n\n"
        f'Lowest Kill: {lowest_kill}\n'
        f'Highest Death: {highest_death}\n\n'
        f"Highest HS Rate: {highest_ratio}%\n"
        f"Lowest HS Rate: {lowest_ratio}%\n"
        f"Avg. HS Rate (100 Games): {average_headshot_ratio}%\n"

        f"### Rank Info:\n"
        f"Rank: {rank_data['currenttierpatched']}\n"
        f"Ranking in Tier: {rank_data['ranking_in_tier']}\n"
        f"Last Game: {rank_data['mmr_change_to_last_game']}\n"
    )
    
    embed = discord.Embed(title=f"I caught u <3", color=discord.Color.blurple())
    embed.description = formatted_info
    
    if tier_image_url:
        embed.set_image(url=tier_image_url)

    return embed
