import discord
from dotenv import load_dotenv
import os
from discord.ext import commands
from discord import app_commands
from valorant import get_player_info_via_api
from commands import handle_rank_command, auto_handle_praise, auto_handle_insult, check_and_reset_mentions

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        await bot.tree.sync()
        print("Slash commands synced successfully.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

    print("Registered commands:")
    for command in bot.tree.get_commands():
        print(f"- {command.name}")

@bot.tree.command(name="rank", description="Historical Ranking")
async def rank(interaction: discord.Interaction):
    await handle_rank_command(interaction)

@bot.tree.command(name="info", description="Player Information")
async def info(interaction: discord.Interaction, player_full_name: str):
    try:
        player_name, player_tag = player_full_name.split('#')
    except ValueError:
        await interaction.response.send_message("Wrong Format")
        return
    await interaction.response.send_message("Fetching player data... Please wait.")

    player_data = await get_player_info_via_api(player_name, player_tag)
    if isinstance(player_data, dict) and "error" in player_data:
        await interaction.followup.send(player_data["error"], ephemeral=True)
        return

    await interaction.followup.send(embed=player_data)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await auto_handle_praise(message)
    await auto_handle_insult(message)
    await bot.process_commands(message)

def run_bot():
    check_and_reset_mentions()
    bot.run(TOKEN)
