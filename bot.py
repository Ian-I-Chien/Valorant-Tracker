import os
import discord
from dotenv import load_dotenv
from discord.ext import commands, tasks
from discord import app_commands
from valorant.match import Match
from valorant.player import ValorantPlayer
from utils import parse_player_name
import sys
from commands import (
    handle_rank_command,
    auto_handle_praise,
    auto_handle_insult,
    check_and_reset_mentions,
    auto_nlp_process,
    registered_with_valorant_account,
    handle_polling_matches,
    delete_valorant_account,
)
from model.toxic_detector import ToxicMessageProcessor

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_IDS = [
    channel_id.strip()
    for channel_id in os.getenv("CHANNEL_ID", "").split(",")
    if channel_id.strip()
]


if not TOKEN or not CHANNEL_IDS:
    sys.exit(1)

toxic_message_processor = ToxicMessageProcessor()

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

    await bot.change_presence(activity=discord.Game("看誰在壞"))
    polling_matches.start()


@bot.tree.command(name="rank", description="Historical Ranking")
async def rank(interaction: discord.Interaction):
    await handle_rank_command(interaction)


@bot.tree.command(name="whoami", description="Who Am I")
async def rank(interaction: discord.Interaction):
    # await whoami(interaction)
    return


@bot.tree.command(name="info", description="Player Information")
async def info(interaction: discord.Interaction, player_full_name: str):
    player_name, player_tag = await parse_player_name(interaction, player_full_name)
    if not player_name or not player_tag:
        return

    player = ValorantPlayer(player_name, player_tag)
    player_info = await player.get_player_info()

    if isinstance(player_info, dict) and "error" in player_info:
        error_embed: discord.Embed = discord.Embed(
            title="Ouch!!", description=player_info["error"]
        )
        await interaction.edit_original_response(content=None, embed=error_embed)
        return

    await interaction.edit_original_response(content=None, embed=player_info)


@bot.tree.command(name="lm", description="Last Match Information")
async def lastmatch(interaction: discord.Interaction, player_full_name: str):
    player_name, player_tag = await parse_player_name(interaction, player_full_name)
    if not player_name or not player_tag:
        return

    match = Match(player_name, player_tag)
    last_match = await match.get_last_match()

    if not last_match:
        error_embed: discord.Embed = discord.Embed(
            title="Ouch!!", description="No match data found."
        )
        await interaction.edit_original_response(content=None, embed=error_embed)
        return

    await interaction.edit_original_response(content=None, embed=last_match)


@bot.tree.command(
    name="reg_val", description="Registered Self discord account with valorant account."
)
@app_commands.describe(valorant_account="valorant account with hashtag. ex:user#1234")
async def reg_val(interaction: discord.Interaction, valorant_account: str):
    await registered_with_valorant_account(interaction, valorant_account)


@bot.tree.command(name="del_val", description="Delete Valorant User")
async def del_val(interaction: discord.Interaction, valorant_account: str):
    await delete_valorant_account(interaction, valorant_account)


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await auto_nlp_process(message, toxic_message_processor)
    await auto_handle_praise(message)
    await auto_handle_insult(message)
    await bot.process_commands(message)


def run_bot():
    check_and_reset_mentions()
    toxic_message_processor.init_nlp_model()  # Initail NLP model
    bot.run(TOKEN)
