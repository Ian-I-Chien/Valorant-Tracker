import requests
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

async def get_average_headshot_ratio(player_name, player_tag):
    url = url_json['matches_v1'].format(region="ap", player_name=player_name, player_tag=player_tag)
    response = requests.get(url, headers=headers)

    if response.status_code == API_SUCCESS:
        highest_ratio = -1
        lowest_ratio = 101
        total_head = 0
        total_shots = 0
        matches = response.json().get("data", [])
        for match in matches:
            if match["meta"]["mode"] == "Deathmatch":
                continue
            shots = match["stats"]["shots"]
            head = shots["head"]
            body = shots["body"]
            leg = shots["leg"]
            total_shots_in_match = head + body + leg

            total_head += head
            total_shots += total_shots_in_match
            if  total_shots_in_match > 0:
                headshot_ratio_each_match = (head / total_shots_in_match) * 100
                highest_ratio = max(highest_ratio, headshot_ratio_each_match)
                lowest_ratio = min(lowest_ratio, headshot_ratio_each_match)
        if total_shots > 0:
            average_headshot_ratio = (total_head / total_shots) * 100
            return round(average_headshot_ratio, 2), round(highest_ratio, 2), round(lowest_ratio, 2)
        else:
            return None
    else:
        return None

async def get_account(player_name, player_tag):
    url = url_json['account'].format(region="ap", player_name=player_name, player_tag=player_tag)
    response = requests.get(url, headers=headers)
    if response.status_code == API_SUCCESS:
        account_data = response.json()['data']
        return account_data
    else:
        return None

async def get_rank(player_name, player_tag):
    url = url_json['rank'].format(region="ap", player_name=player_name, player_tag=player_tag)
    response = requests.get(url, headers=headers)

    if response.status_code == API_SUCCESS:
        rank_data = response.json()['data']
        return rank_data
    else:
        return None

async def get_player_info_via_api(player_name, player_tag):
    account_data = await get_account(player_name, player_tag)
    if account_data is None:
        return {"error": "Unable to fetch account data."}

    rank_data = await get_rank(player_name, player_tag)
    if rank_data is None:
        return {"error": "Unable to fetch rank data."}
    
    average_headshot_ratio, highest_ratio, lowest_ratio = await get_average_headshot_ratio(player_name, player_tag)
    if average_headshot_ratio is None:
        return {"error": "Unable to fetch headshot ratio."}

    tier_image_url = rank_data.get('images', {}).get('small', None)
    
    formatted_info = (
        f"### Account Info:\n"
        f"Name: {account_data['name']}#{account_data['tag']}\n"
        f"Region: {account_data['region']}\n"
        f"Account Level: {account_data['account_level']}\n"
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
