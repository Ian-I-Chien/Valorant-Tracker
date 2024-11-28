
import discord

async def parse_player_name(interaction: discord.Interaction, player_full_name: str):
    try:
        player_name, player_tag = player_full_name.split('#')
    except ValueError:
        await interaction.response.send_message("Wrong Format 'player_name#tag'。", ephemeral=True)
        return None, None
    
    await interaction.response.send_message("Fetching data... Please wait.", ephemeral=True)
    
    return player_name, player_tag
