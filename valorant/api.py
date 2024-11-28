import aiohttp
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("API_KEY")
API_SUCCESS = 200

headers = {
    'Authorization': f'{API_KEY}',
    'accept': 'application/json'
}

url_json = {
    'rank': 'https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{player_name}/{player_tag}',
    'account': 'https://api.henrikdev.xyz/valorant/v1/account/{player_name}/{player_tag}',
    'match': "https://api.henrikdev.xyz/valorant/v2/match/{matchid}",
    'matches_v1': 'https://api.henrikdev.xyz/valorant/v1/stored-matches/{region}/{player_name}/{player_tag}',
    'matches_v3': "https://api.henrikdev.xyz/valorant/v3/matches/{region}/{player_name}/{player_tag}",
}

async def fetch_json(url, params=None):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status == API_SUCCESS:
                return await response.json()
            return None
