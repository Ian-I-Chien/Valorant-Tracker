import asyncio
from dataclasses import dataclass
from typing import Optional

import discord
from database.storage_sqlite import UserSQLiteDB
from valorant.match import Match
from valorant.player import ValorantPlayer
from utils import parse_player_name, get_env_or_interaction_channel
import traceback

# Keep polling, registration, and deletion ordered within this bot process.
_userdb_lock: Optional[asyncio.Lock] = None


@dataclass(frozen=True)
class PollingMatchResult:
    embed: discord.Embed
    dc_channel_id: Optional[str]
    dc_id: str
    valorant_puuid: str
    match_id: str
    subscription_id: int
    previous_match_id: Optional[str]


def get_userdb_lock() -> asyncio.Lock:
    """
    Lazily initialize and return the global user DB lock.

    The lock is created the first time it is needed, on the active
    event loop. This avoids "Future attached to a different loop"
    errors caused by creating a Lock at import time.
    """
    global _userdb_lock
    if _userdb_lock is None:
        _userdb_lock = asyncio.Lock()
    return _userdb_lock


async def handle_polling_matches(interaction: discord.Interaction = None):
    """
    Background polling logic:
    - Load all subscriptions from SQLite
    - For each Valorant account, fetch the last match ID from API
    - Compare with last_polled_match_id stored on the subscription
    - If it is a new match, fetch and format the match data
    - Return delivery metadata without updating last_polled_match_id
    """
    lock = get_userdb_lock()

    # Avoid racing a poll with registration or deletion in this process.
    async with lock:
        try:
            async with UserSQLiteDB() as user_model:
                users_data = await user_model.get_all()
                print("[DEBUG] Loaded user records:", users_data)

                for user_data in users_data:
                    valorant_accounts = user_data.get("valorant_accounts") or []

                    for account_data in valorant_accounts:
                        try:
                            account_str = account_data["valorant_account"]
                            player_name, player_tag = account_str.split("#")
                            valorant_puuid = account_data["valorant_puuid"]
                            dc_id = user_data["dc_id"]
                            dc_channel_id = user_data.get("dc_channel_id")

                            # Read the last processed match ID for this account
                            last_polled_match_id = account_data.get(
                                "last_polled_match_id"
                            )

                            match = Match(player_name, player_tag)
                            last_match_id = await match.get_last_match_id()

                            # No matches found or failed to fetch
                            if not last_match_id:
                                continue

                            # A newly registered account has no checkpoint yet.
                            # Treat its current latest match as the baseline so
                            # matches completed before registration are not sent
                            # as new notifications.
                            if last_polled_match_id is None:
                                account_data["last_polled_match_id"] = last_match_id
                                print(
                                    f"[DEBUG] Initialized match checkpoint {last_match_id} "
                                    f"for {account_str}, skipping existing match."
                                )
                                continue

                            # Skip if this match has already been processed
                            if last_polled_match_id == last_match_id:
                                print(
                                    f"[DEBUG] Match {last_match_id} already processed for {account_str}, skipping."
                                )
                                continue

                            print(
                                f"[DEBUG] Fetching new match {last_match_id} for {player_name}..."
                            )

                            # Fetch match data from Riot API
                            match_data = await match.get_stored_match_by_id_by_api()
                            match.last_match_data = match_data

                            print(
                                f"[DEBUG] Prepared new match {last_match_id} for {account_str}"
                            )

                            # Delivery must succeed before this match is checkpointed.
                            return PollingMatchResult(
                                embed=await match.sorted_formatted_player(),
                                dc_channel_id=dc_channel_id,
                                dc_id=dc_id,
                                valorant_puuid=valorant_puuid,
                                match_id=last_match_id,
                                subscription_id=account_data["subscription_id"],
                                previous_match_id=last_polled_match_id,
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
        return None


async def mark_match_delivered(result: PollingMatchResult) -> bool:
    """Persist a match checkpoint only after Discord delivery succeeds."""
    lock = get_userdb_lock()
    async with lock:
        async with UserSQLiteDB() as user_model:
            return await user_model.update_last_polled_match(
                subscription_id=result.subscription_id,
                expected_match_id=result.previous_match_id,
                match_id=result.match_id,
            )


async def delete_valorant_account(
    interaction: discord.Interaction, valorant_account: str
):
    """
    Remove a Valorant account owned by this user in this Discord server.
    """
    player_name, player_tag = await parse_player_name(interaction, valorant_account)
    if not player_name or not player_tag:
        await interaction.edit_original_response(
            content="Failed to parse Valorant account. Please check the format."
        )
        return

    lock = get_userdb_lock()
    dc_id = str(interaction.user.id)
    dc_server_id = str(interaction.guild.id)

    # Serialize deletion with polling/registration in this process.
    async with lock:
        async with UserSQLiteDB() as user_model:
            removed = await user_model.remove_valorant_account(
                dc_id=dc_id,
                dc_server_id=dc_server_id,
                valorant_account=valorant_account,
            )

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
    Saves the user, Valorant account, and channel subscription in SQLite.
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

    lock = get_userdb_lock()

    # Serialize registration with polling/deletion in this process.
    async with lock:
        async with UserSQLiteDB() as user_model:
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
