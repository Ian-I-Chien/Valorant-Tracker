import discord
from database.storage_json import UserJsonDB
from valorant.match import Match
from valorant.player import ValorantPlayer
from utils import parse_player_name, get_env_or_interaction_channel
import traceback


async def handle_polling_matches(interaction: discord.Interaction = None):
    """
    Background polling logic:
    - Load all registered users from JSON
    - For each Valorant account, fetch the last match ID from API
    - Compare with last_polled_match_id stored in JSON
    - If it is a new match, fetch match data and update last_polled_match_id
    - Return (formatted match result, discord_channel_id) when a new match is found
    """
    try:
        async with UserJsonDB() as user_model:
            users_data = await user_model.get_all()
            print("[DEBUG] Loaded user records:", users_data)

            for user_data in users_data:
                valorant_accounts = user_data.get("valorant_accounts") or []

                for account_data in valorant_accounts:
                    try:
                        account_str = account_data["valorant_account"]
                        player_name, player_tag = account_str.split("#")
                        valorant_puuid = account_data["valorant_puuid"]
                        dc_channel_id = user_data.get("dc_channel_id")

                        # Read last processed match id from JSON (per account)
                        last_polled_match_id = account_data.get("last_polled_match_id")

                        match = Match(player_name, player_tag)
                        last_match_id = await match.get_last_match_id()

                        # No matches found or unable to fetch
                        if not last_match_id:
                            continue

                        # If this match was already processed, skip immediately
                        if last_polled_match_id == last_match_id:
                            print(
                                f"[DEBUG] Match {last_match_id} already processed for {account_str}, skipping."
                            )
                            continue

                        print(
                            f"[DEBUG] Fetching new match {last_match_id} for {player_name}..."
                        )

                        # Fetch match data from API
                        match_data = await match.get_stored_match_by_id_by_api()
                        match.last_match_data = match_data

                        # Mark this match as processed for this account
                        account_data["last_polled_match_id"] = last_match_id

                        print(
                            f"[DEBUG] Processed new match {last_match_id} for {account_str}"
                        )

                        # Return formatted match info and channel ID
                        return (
                            await match.sorted_formatted_player(),
                            dc_channel_id,
                        )

                    except Exception as e:
                        print(
                            f"[ERROR] Error processing account {account_data.get('valorant_account')}: {e}"
                        )
                        traceback.print_exc()

    except Exception as e:
        print(f"[CRITICAL] Critical error in handle_polling_matches: {e}")
        traceback.print_exc()

    # No new matches found
    return None, None


async def delete_valorant_account(
    interaction: discord.Interaction, valorant_account: str
):
    """
    Removes a Valorant account from all registered users.
    """
    player_name, player_tag = await parse_player_name(interaction, valorant_account)
    if not player_name or not player_tag:
        await interaction.edit_original_response(
            content="Failed to parse Valorant account. Please check the format."
        )
        return

    async with UserJsonDB() as user_model:
        removed = await user_model.remove_valorant_account(valorant_account)

    if removed:
        await interaction.edit_original_response(
            content=f"Valorant account `{valorant_account}` removed successfully."
        )
    else:
        await interaction.edit_original_response(
            content=f"Valorant account `{valorant_account}` does not exist."
        )


async def registered_with_valorant_account(
    interaction: discord.Interaction, valorant_account: str
):
    """
    Registers a Valorant account to a Discord user.
    Saves the user and linked Valorant account into JSON storage.
    """
    player_name, player_tag = await parse_player_name(interaction, valorant_account)
    if not player_name or not player_tag:
        await interaction.edit_original_response(
            content="Invalid account format. Expected `name#tag`."
        )
        return

    dc_id = str(interaction.user.id)
    dc_global_name = interaction.user.global_name
    dc_display_name = interaction.user.display_name
    dc_server_id = str(interaction.guild.id)
    dc_channel_id = str(get_env_or_interaction_channel(interaction))

    print(
        f"[DEBUG] Registering user: id={dc_id}, global={dc_global_name}, "
        f"display={dc_display_name}, server={dc_server_id}, channel={dc_channel_id}"
    )

    try:
        player = ValorantPlayer(player_name, player_tag)
        account_data = await player.get_account_by_api()

        if account_data is None:
            await interaction.edit_original_response(
                content=f"Could not fetch account: `{valorant_account}`."
            )
            return

    except Exception as e:
        await interaction.edit_original_response(
            content=f"Error fetching Valorant account: {str(e)}"
        )
        return

    async with UserJsonDB() as user_model:
        try:
            await user_model.register_user(
                dc_id=dc_id,
                dc_global_name=dc_global_name,
                dc_display_name=dc_display_name,
                dc_server_id=dc_server_id,
                dc_channel_id=dc_channel_id,
                val_account=valorant_account,
                val_puuid=str(account_data["puuid"]),
            )
            await interaction.edit_original_response(
                content=f"Successfully registered `{valorant_account}`!"
            )

        except ValueError as e:
            await interaction.edit_original_response(
                content=f"Registration failed: {str(e)}"
            )
