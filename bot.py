import os
import sys
import discord
from dotenv import load_dotenv
from discord import app_commands
from utils import parse_player_name
from discord.ext import commands, tasks
from commands import (
    handle_polling_matches,
    delete_valorant_account,
    registered_with_valorant_account,
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_IDS = [
    channel_id.strip()
    for channel_id in os.getenv("CHANNEL_ID", "").split(",")
    if channel_id.strip()
]


if not TOKEN or not CHANNEL_IDS:
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)


@tasks.loop(seconds=30)
async def polling_matches():
    print("Start Polling 30 secs...")
    polling_info = await handle_polling_matches()
    if polling_info:
        for channel_id in CHANNEL_IDS:
            try:
                channel = bot.get_channel(int(channel_id))
                if channel:
                    await channel.send(embed=polling_info)
            except ValueError:
                print(f"Invalid channel ID: {channel_id}")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        await bot.tree.sync()
        print("Slash commands synced successfully.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

    print("Registered commands:")
    for command in bot.tree.get_commands():
        print(f"- {command.name}")

    await bot.change_presence(activity=discord.Game("Tracking your Valorant matches"))
    polling_matches.start()


@bot.tree.command(
    name="reg_val", description="Registered Self discord account with valorant account."
)
@app_commands.describe(valorant_account="valorant account with hashtag. ex:user#1234")
async def reg_val(interaction: discord.Interaction, valorant_account: str):
    await registered_with_valorant_account(interaction, valorant_account)


@bot.tree.command(name="del_val", description="Delete Valorant User")
async def del_val(interaction: discord.Interaction, valorant_account: str):
    await delete_valorant_account(interaction, valorant_account)


def run_bot():
    bot.run(TOKEN)
