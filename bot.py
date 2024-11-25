import discord
from dotenv import load_dotenv
import os
from discord.ext import commands
from discord import app_commands
from commands import handle_rank_command, auto_handle_insult, check_and_reset_mentions

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

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await auto_handle_insult(message)
    await bot.process_commands(message)

def run_bot():
    check_and_reset_mentions()
    bot.run(TOKEN)
