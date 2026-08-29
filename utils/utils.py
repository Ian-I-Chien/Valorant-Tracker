import logging
import os
from typing import Optional

import discord
from dotenv import load_dotenv

load_dotenv()
LOGGER = logging.getLogger(__name__)


def fix_isoformat(iso_time: str) -> str:
    """Normalize Henrik timestamps for Python's ISO parser."""
    if iso_time.endswith("Z"):
        iso_time = iso_time[:-1]
    if "." in iso_time:
        date_part, fraction = iso_time.split(".", 1)
        iso_time = f"{date_part}.{fraction.ljust(6, '0')}"
    return iso_time


def get_env_or_interaction_channel(
    interaction: discord.Interaction,
) -> Optional[int]:
    configured_ids = [
        int(value.strip())
        for value in os.getenv("CHANNEL_ID", "").split(",")
        if value.strip().isdigit()
    ]

    if interaction.guild:
        for channel_id in configured_ids:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                LOGGER.debug(
                    "Using configured channel %s (%s)", channel.name, channel.id
                )
                return channel.id

    channel = interaction.channel
    if channel is None:
        return None
    LOGGER.debug("Using interaction channel %s", channel.id)
    return channel.id


async def parse_player_name(
    interaction: discord.Interaction, player_full_name: str
) -> tuple[Optional[str], Optional[str]]:
    """Parse and acknowledge a Riot ID in the form game-name#tag."""
    try:
        player_name, player_tag = player_full_name.rsplit("#", 1)
    except ValueError:
        await interaction.response.send_message(
            "Wrong format. Expected `player_name#tag`."
        )
        return None, None

    player_name = player_name.strip()
    player_tag = player_tag.strip()
    if not player_name or not player_tag:
        await interaction.response.send_message(
            "Wrong format. Expected `player_name#tag`."
        )
        return None, None

    await interaction.response.send_message("Parsing data... Please wait.")
    return player_name, player_tag
