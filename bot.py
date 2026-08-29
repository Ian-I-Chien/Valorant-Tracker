import os
import sys
import discord
from dotenv import load_dotenv
from discord import app_commands
from utils import parse_player_name
from discord.ext import commands, tasks
from database.storage_sqlite import migrate_legacy_json
from commands import (
    handle_polling_matches,
    mark_match_delivered,
    delete_valorant_account,
    registered_with_valorant_account,
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("[ERROR] Need to set TOKEN in env.")
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def setup_hook():
    migration = await migrate_legacy_json()
    if migration.backup_path:
        print(
            "[INFO] Migrated legacy JSON: "
            f"imported={migration.imported}, skipped={migration.skipped}, "
            f"invalid={migration.invalid}, backup={migration.backup_path}"
        )


@tasks.loop(seconds=30)
async def polling_matches():
    print("Start Polling 30 secs...")

    try:
        polling_result = await handle_polling_matches()

        if not polling_result:
            print("[INFO] No polling result returned.")
            return

        target_channels = []

        if polling_result.dc_channel_id:
            ch = bot.get_channel(int(polling_result.dc_channel_id))
            if ch:
                target_channels.append(ch)

        if not target_channels:
            print("[WARN] No valid channels found to send message.")
            return

        for ch in target_channels:
            await ch.send(embed=polling_result.embed)

        if not await mark_match_delivered(polling_result):
            print(
                f"[WARN] Match {polling_result.match_id} was delivered but "
                "its registration no longer exists."
            )

    except Exception as e:
        print(f"[ERROR] polling_matches: {e}")


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
    if not polling_matches.is_running():
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
