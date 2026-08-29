import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import discord
from database.storage_sqlite import UserSQLiteDB
from valorant.match import Match
from valorant.player import ValorantPlayer
from utils import parse_player_name

LOGGER = logging.getLogger(__name__)

# Keep polling, registration, and deletion ordered within this bot process.
_userdb_lock: Optional[asyncio.Lock] = None


@dataclass(frozen=True)
class PollingMatchResult:
    embed: discord.Embed
    server_id: str
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


async def handle_polling_matches(
    interaction: Optional[discord.Interaction] = None,
) -> Optional[PollingMatchResult]:
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
                subscriptions = await user_model.list_subscriptions()
                LOGGER.debug("Loaded %s subscriptions", len(subscriptions))

                for subscription in subscriptions:
                    try:
                        account_str = subscription.valorant_account
                        player_name, player_tag = account_str.split("#")
                        valorant_puuid = subscription.valorant_puuid
                        dc_id = subscription.discord_user_id

                        # Read the last processed match ID for this account
                        last_polled_match_id = subscription.last_polled_match_id

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
                            initialized = await user_model.update_last_polled_match(
                                subscription_id=subscription.id,
                                expected_match_id=None,
                                match_id=last_match_id,
                            )
                            if not initialized:
                                LOGGER.warning(
                                    "Could not initialize checkpoint for %s; "
                                    "subscription changed",
                                    account_str,
                                )
                            LOGGER.debug(
                                "Initialized checkpoint %s for %s",
                                last_match_id,
                                account_str,
                            )
                            continue

                        # Skip if this match has already been processed
                        if last_polled_match_id == last_match_id:
                            LOGGER.debug(
                                "Match %s already processed for %s",
                                last_match_id,
                                account_str,
                            )
                            continue

                        LOGGER.debug(
                            "Fetching new match %s for %s",
                            last_match_id,
                            player_name,
                        )

                        # Fetch match data from Riot API
                        match_data = await match.fetch_match()
                        match.last_match_data = match_data

                        LOGGER.debug(
                            "Prepared new match %s for %s",
                            last_match_id,
                            account_str,
                        )

                        # Delivery must succeed before this match is checkpointed.
                        return PollingMatchResult(
                            embed=await match.build_embed(),
                            server_id=subscription.server_id,
                            dc_id=dc_id,
                            valorant_puuid=valorant_puuid,
                            match_id=last_match_id,
                            subscription_id=subscription.id,
                            previous_match_id=last_polled_match_id,
                        )

                    except Exception:
                        LOGGER.exception(
                            "Error processing account %s",
                            subscription.valorant_account,
                        )

        except Exception:
            LOGGER.exception("Critical error while polling matches")

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


async def get_notification_channel_id(server_id: str) -> Optional[str]:
    async with UserSQLiteDB() as repository:
        settings = await repository.get_guild_settings(server_id)
    return settings.notification_channel_id if settings else None


async def set_notification_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
) -> None:
    if interaction.guild is None:
        LOGGER.warning(
            "Rejected notification channel change outside a server: actor_id=%s",
            interaction.user.id,
        )
        await interaction.response.send_message(
            "This command can only be used in a Discord server.", ephemeral=True
        )
        return

    server_id = str(interaction.guild.id)
    channel_id = str(channel.id)
    actor_id = str(interaction.user.id)
    bot_member = interaction.guild.me
    permissions = channel.permissions_for(bot_member) if bot_member else None
    if not permissions or not (
        permissions.view_channel
        and permissions.send_messages
        and permissions.embed_links
    ):
        LOGGER.warning(
            "Rejected notification channel change: server_id=%s "
            "channel_id=%s actor_id=%s reason=missing_permissions",
            server_id,
            channel_id,
            actor_id,
        )
        await interaction.response.send_message(
            "I need View Channel, Send Messages, and Embed Links permissions "
            f"in {channel.mention}.",
            ephemeral=True,
        )
        return

    async with UserSQLiteDB() as repository:
        existing_settings = await repository.get_guild_settings(server_id)
        await repository.set_guild_notification_channel(server_id, channel_id)

    action = "created" if existing_settings is None else "updated"
    LOGGER.info(
        "Guild notification channel %s: server_id=%s channel_id=%s actor_id=%s",
        action,
        server_id,
        channel_id,
        actor_id,
    )

    await interaction.response.send_message(
        f"Match notifications will be sent to {channel.mention}.", ephemeral=True
    )


async def show_server_config(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a Discord server.", ephemeral=True
        )
        return

    channel_id = await get_notification_channel_id(str(interaction.guild.id))
    if channel_id is None:
        message = "No notification channel is configured. Use `/set_channel`."
    else:
        message = f"Match notification channel: <#{channel_id}>."
    await interaction.response.send_message(message, ephemeral=True)


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
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a Discord server.", ephemeral=True
        )
        return

    dc_server_id = str(interaction.guild.id)
    dc_channel_id = await get_notification_channel_id(dc_server_id)
    if dc_channel_id is None:
        await interaction.response.send_message(
            "This server has no notification channel. "
            "Ask an administrator to use `/set_channel` first.",
            ephemeral=True,
        )
        return

    player_name, player_tag = await parse_player_name(interaction, valorant_account)
    if not player_name or not player_tag:
        await interaction.edit_original_response(
            content="Invalid account format. Expected `name#tag`."
        )
        return

    dc_id = str(interaction.user.id)
    dc_global_name = interaction.user.global_name
    dc_display_name = interaction.user.display_name
    LOGGER.debug(
        "Registering Discord user %s in server %s, channel %s",
        dc_id,
        dc_server_id,
        dc_channel_id,
    )

    try:
        player = ValorantPlayer(player_name, player_tag)
        account_data = await player.fetch_account()

        if account_data is None:
            await interaction.edit_original_response(
                content=f"Could not fetch account: `{valorant_account}`."
            )
            return

    except Exception:
        LOGGER.exception("Could not fetch Valorant account %s", valorant_account)
        await interaction.edit_original_response(
            content="Error fetching Valorant account. Please try again later."
        )
        return

    lock = get_userdb_lock()

    # Serialize registration with polling/deletion in this process.
    async with lock:
        async with UserSQLiteDB() as user_model:
            try:
                canonical_account = f"{player.player_name}#{player.player_tag}"
                await user_model.register_user(
                    dc_id=dc_id,
                    dc_global_name=dc_global_name,
                    dc_display_name=dc_display_name,
                    dc_server_id=dc_server_id,
                    dc_channel_id=dc_channel_id,
                    val_account=canonical_account,
                    val_puuid=str(account_data["puuid"]),
                )
                await interaction.edit_original_response(
                    content=f"Successfully registered `{canonical_account}`!"
                )

            except ValueError as e:
                await interaction.edit_original_response(
                    content=f"Registration failed: {str(e)}"
                )
