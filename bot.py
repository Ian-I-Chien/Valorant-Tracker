import os
import logging

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
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True


class ValorantTrackerBot(commands.Bot):
    async def setup_hook(self) -> None:
        migration = await migrate_legacy_json()
        if migration.backup_path:
            LOGGER.info(
                "Migrated legacy JSON: imported=%s, skipped=%s, "
                "invalid=%s, backup=%s",
                migration.imported,
                migration.skipped,
                migration.invalid,
                migration.backup_path,
            )


bot = ValorantTrackerBot(command_prefix="/", intents=intents)


@tasks.loop(seconds=30)
async def polling_matches():
    LOGGER.debug("Polling for completed matches")

    try:
        polling_result = await handle_polling_matches()

        if not polling_result:
            LOGGER.debug("No new match found")
            return

        target_channels = []

        if polling_result.dc_channel_id:
            ch = bot.get_channel(int(polling_result.dc_channel_id))
            if ch:
                target_channels.append(ch)

        if not target_channels:
            LOGGER.warning("No valid channel found for match notification")
            return

        for ch in target_channels:
            await ch.send(embed=polling_result.embed)

        if not await mark_match_delivered(polling_result):
            LOGGER.warning(
                "Match %s was delivered but its subscription changed",
                polling_result.match_id,
            )

    except Exception:
        LOGGER.exception("Unexpected error while polling matches")


@bot.event
async def on_ready():
    LOGGER.info("Logged in as %s", bot.user)
    try:
        await bot.tree.sync()
        LOGGER.info("Slash commands synced successfully")
    except Exception:
        LOGGER.exception("Could not sync slash commands")

    for command in bot.tree.get_commands():
        LOGGER.debug("Registered command: %s", command.name)

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
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN must be set")
    bot.run(TOKEN)
