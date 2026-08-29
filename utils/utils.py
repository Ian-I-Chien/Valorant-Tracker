from typing import Optional

import discord


def fix_isoformat(iso_time: str) -> str:
    """Normalize Henrik timestamps for Python's ISO parser."""
    if iso_time.endswith("Z"):
        iso_time = iso_time[:-1]
    if "." in iso_time:
        date_part, fraction = iso_time.split(".", 1)
        iso_time = f"{date_part}.{fraction.ljust(6, '0')}"
    return iso_time


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
