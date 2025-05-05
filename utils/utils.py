import discord

import os
from typing import Optional
import discord
from dotenv import load_dotenv

load_dotenv()


def get_env_or_interaction_channel(
    interaction: discord.Interaction,
) -> Optional[discord.abc.Messageable]:
    channel_ids_str = os.getenv("CHANNEL_ID", "")
    env_channel_ids = [
        int(cid.strip()) for cid in channel_ids_str.split(",") if cid.strip().isdigit()
    ]

    if interaction.guild:
        for cid in env_channel_ids:
            channel = interaction.guild.get_channel(cid)
            if channel:
                print(
                    f"[DEBUG] Found matching channel in env: {channel.name} ({channel.id})"
                )
                return channel.id

    print(
        f"[DEBUG] No matching env channel found, using interaction.channel: {interaction.channel.id}"
    )
    return interaction.channel.id


async def parse_player_name(interaction: discord.Interaction, player_full_name: str):
    try:
        player_name, player_tag = player_full_name.split("#")
    except ValueError:
        await interaction.response.send_message("Wrong Format 'player_name#tag'。")
        return None, None

    await interaction.response.send_message("Parsing data... Please wait.")

    return player_name, player_tag
