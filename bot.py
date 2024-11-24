import discord
from dotenv import load_dotenv
import os
from discord.ext import commands
from commands import handle_rank_command, auto_handle_insult, check_and_reset_mentions

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await auto_handle_insult(message)
    await bot.process_commands(message)

@bot.command()
async def rank(ctx):
    await handle_rank_command(ctx)

def run_bot():
    check_and_reset_mentions()
    bot.run(TOKEN)
