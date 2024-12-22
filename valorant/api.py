import os
import time
import asyncio
import aiohttp
from dotenv import load_dotenv

MAX_REQUESTS_PER_MINUTE = 90
TIME_WINDOW = 60

request_times = []

load_dotenv()
API_KEY = os.getenv("API_KEY")
API_SUCCESS = 200

headers = {"Authorization": f"{API_KEY}", "accept": "application/json"}

url_json = {
    "rank": "https://api.henrikdev.xyz/valorant/v1/mmr/{region}/{player_name}/{player_tag}",
    "account": "https://api.henrikdev.xyz/valorant/v1/account/{player_name}/{player_tag}",
    "match": "https://api.henrikdev.xyz/valorant/v4/match/{region}/{matchid}",
    "matches_v1": "https://api.henrikdev.xyz/valorant/v1/stored-matches/{region}/{player_name}/{player_tag}",
    "matches_v3": "https://api.henrikdev.xyz/valorant/v3/matches/{region}/{player_name}/{player_tag}",
    "get_match_by_id": "https://api.henrikdev.xyz/valorant/v4/match/{region}/{matchid}",
}


async def check_rate_limit():

    global request_times
    current_time = time.time()

    request_times = [t for t in request_times if current_time - t < TIME_WINDOW]

    if len(request_times) >= MAX_REQUESTS_PER_MINUTE:
        wait_time = TIME_WINDOW - (current_time - request_times[0])
        print(f"Rate limit reached. Waiting for {wait_time:.2f} seconds.")
        await asyncio.sleep(wait_time)
        current_time = time.time()
        request_times = [t for t in request_times if current_time - t < TIME_WINDOW]


async def fetch_json(url, params=None):
    await check_rate_limit()
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            request_times.append(time.time())
            print(request_times)
            if response.status == API_SUCCESS:
                return await response.json()
            return None
