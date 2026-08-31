import os
import asyncio
from contextlib import suppress
import logging
import io

import discord
from dotenv import load_dotenv
from discord import app_commands
from utils import parse_player_name
from discord.ext import commands, tasks
from database.storage_sqlite import migrate_legacy_json
from help_command import show_help
from last_match_command import show_last_match
from commands import (
    get_notification_channel_id,
    handle_polling_matches,
    mark_match_delivered,
    delete_valorant_account,
    registered_with_valorant_account,
    set_notification_channel,
    show_server_config,
    predict_registered_player,
    show_registered_player_info,
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
    async def close(self):
        worker = getattr(self, "shop_notification_task", None)
        if worker is not None:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        await super().close()

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

        channel_id = await get_notification_channel_id(polling_result.server_id)
        if channel_id is None:
            LOGGER.warning(
                "Server %s has no notification channel", polling_result.server_id
            )
            return

        channel = bot.get_channel(int(channel_id))
        if channel is None:
            channel = await bot.fetch_channel(int(channel_id))
        if not hasattr(channel, "send"):
            LOGGER.warning("Configured channel %s cannot receive messages", channel_id)
            return

        if polling_result.image is not None:
            filename = "match-scoreboard.png"
            image_embed = discord.Embed(color=discord.Color.from_str("#ff4655"))
            image_embed.set_image(url=f"attachment://{filename}")
            await channel.send(
                embed=image_embed,
                file=discord.File(io.BytesIO(polling_result.image), filename=filename),
            )
        else:
            await channel.send(embed=polling_result.embed)

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

    await bot.change_presence(
        activity=discord.Game("Tracking your Valorant matches | Daily shop")
    )
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


@bot.tree.command(name="set_channel", description="Set the match notification channel")
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(channel="Channel used for Valorant match notifications")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    await set_notification_channel(interaction, channel)


@bot.tree.command(name="show_config", description="Show this server's bot settings")
async def show_config(interaction: discord.Interaction):
    await show_server_config(interaction)


@bot.tree.command(
    name="predict", description="Predict a registered player's next match"
)
@app_commands.describe(username="Registered Valorant username or name#tag")
async def predict(interaction: discord.Interaction, username: str):
    await predict_registered_player(interaction, username)


@bot.tree.command(
    name="last_match", description="Show the latest completed match for a Riot ID"
)
@app_commands.describe(id="Required full Riot ID: name#tag")
async def last_match(interaction: discord.Interaction, id: str):
    await show_last_match(interaction, id)


@bot.tree.command(name="info", description="Show recent stats for a registered player")
@app_commands.describe(username="Registered Valorant username or name#tag")
async def info(interaction: discord.Interaction, username: str):
    await show_registered_player_info(interaction, username)


@bot.tree.command(
    name="help", description="Show commands and how to use Valorant Tracker"
)
async def help_command(interaction: discord.Interaction):
    await show_help(interaction)


if os.getenv("SHOP_ENABLED", "0") == "1":
    from shop_commands import register_shop_commands

    register_shop_commands(bot)


def run_bot():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN must be set")
    bot.run(TOKEN)
