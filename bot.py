import discord
from dotenv import load_dotenv
import os
from commands import handle_rank_command, handle_insult, check_and_reset_mentions

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content == "!rank":
        await handle_rank_command(client, message)
    else:
        await handle_insult(client, message)

def run_bot():
    check_and_reset_mentions()
    client.run(TOKEN)
