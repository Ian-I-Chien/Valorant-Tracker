import asyncio
import io
import logging
from dataclasses import dataclass
from typing import Optional

import discord
from database.storage_sqlite import UserSQLiteDB
from userdb_coordination import get_userdb_lock
from valorant.player import ValorantPlayer
from valorant.player_info import PlayerInfoCardRenderer, build_player_info
from valorant.prediction import (
    PredictionCardRenderer,
    extract_recent_performances,
    predict_next_match,
)
from utils import parse_player_name

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedPlayer:
    riot_id: str
    puuid: str


async def resolve_player_query(
    server_id: str, account_query: str
) -> Optional[ResolvedPlayer]:
    """Resolve a registered player or look up an unregistered full Riot ID.

    This is intentionally read-only: ad-hoc lookups never create a subscription
    or a polling checkpoint.
    """
    query = account_query.strip()
    async with UserSQLiteDB() as repository:
        subscription = await repository.find_subscription(server_id, query)
    if subscription is not None:
        return ResolvedPlayer(
            riot_id=subscription.valorant_account,
            puuid=subscription.valorant_puuid,
        )

    if "#" not in query:
        return None
    name, tag = (part.strip() for part in query.rsplit("#", 1))
    if not name or not tag:
        return None

    player = ValorantPlayer(name, tag)
    account = await player.fetch_account()
    if not account or not account.get("puuid"):
        return None
    return ResolvedPlayer(
        riot_id=f"{player.player_name}#{player.player_tag}",
        puuid=str(account["puuid"]),
    )


async def get_notification_channel_id(server_id: str) -> Optional[str]:
    async with UserSQLiteDB() as repository:
        settings = await repository.get_guild_settings(server_id)
    return settings.notification_channel_id if settings else None


async def predict_registered_player(
    interaction: discord.Interaction, account_query: str
) -> None:
    """Create a pre-match prediction for a registered or ad-hoc player."""
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a Discord server.", ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=True)
    try:
        player = await resolve_player_query(str(interaction.guild.id), account_query)
    except Exception:
        LOGGER.exception("Could not resolve player for prediction: %s", account_query)
        await interaction.edit_original_response(
            content="The Valorant API is temporarily unavailable. Please try again later."
        )
        return
    if player is None:
        await interaction.edit_original_response(
            content="No unique registered player matched that username. "
            "For an unregistered player, use the complete `name#tag`."
        )
        return
    player_name, player_tag = player.riot_id.rsplit("#", 1)
    try:
        matches_payload = await Match(player_name, player_tag).fetch_recent_matches(
            size=20
        )
    except Exception:
        LOGGER.exception("Could not fetch prediction data for %s", player.riot_id)
        await interaction.edit_original_response(
            content="The Valorant API is temporarily unavailable. Please try again later."
        )
        return
    matches = (matches_payload or {}).get("data") or []
    performances = extract_recent_performances(matches, player.puuid)
    result = predict_next_match(player.riot_id, performances)
    if result is None:
        await interaction.edit_original_response(
            content=f"`{player.riot_id}` has no completed matches in the last 30 days, so there is not enough data to predict."
        )
        return
    try:
        image = PredictionCardRenderer().render(result)
        await interaction.edit_original_response(
            attachments=[
                discord.File(io.BytesIO(image), filename="prematch-prediction.png")
            ]
        )
    except Exception:
        LOGGER.exception("Could not render prediction card")
        await interaction.edit_original_response(
            content=(
                f"**{result.riot_id} — next match prediction**\n"
                f"Win chance: **{result.win_probability}%** ({result.confidence.lower()} confidence)\n"
                f"Based on {result.match_count} matches in the last 30 days."
            )
        )


async def show_registered_player_info(
    interaction: discord.Interaction, account_query: str
) -> None:
    """Render recent NG/RK statistics for a registered or ad-hoc player."""
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a Discord server.", ephemeral=True
        )
        return
    await interaction.response.defer()
    try:
        resolved = await resolve_player_query(str(interaction.guild.id), account_query)
    except Exception:
        LOGGER.exception("Could not resolve player info query: %s", account_query)
        await interaction.edit_original_response(
            content="The Valorant API is temporarily unavailable. Please try again later."
        )
        return
    if resolved is None:
        await interaction.edit_original_response(
            content="No unique registered player matched that username. "
            "For an unregistered player, use the complete name#tag."
        )
        return
    name, tag = resolved.riot_id.rsplit("#", 1)
    player = ValorantPlayer(name, tag)
    try:
        matches_payload, rank_history = await asyncio.gather(
            Match(name, tag).fetch_recent_matches(size=20),
            player.fetch_rank_history(),
        )
    except Exception:
        LOGGER.exception("Could not fetch player info for %s", resolved.riot_id)
        await interaction.edit_original_response(
            content="The Valorant API is temporarily unavailable. Please try again later."
        )
        return
    data = build_player_info(
        resolved.riot_id,
        resolved.puuid,
        (matches_payload or {}).get("data") or [],
        rank_history,
    )
    if data is None:
        await interaction.edit_original_response(
            content=f"{resolved.riot_id} has no NG/RK matches in the last 30 days."
        )
        return
    try:
        image = await PlayerInfoCardRenderer().render(data)
        await interaction.edit_original_response(
            attachments=[discord.File(io.BytesIO(image), filename="player-info.png")]
        )
    except Exception:
        LOGGER.exception("Could not render player info card")
        await interaction.edit_original_response(
            content=(
                f"**{data.riot_id} - recent player info**\n"
                f"{data.matches} matches | {data.win_rate}% WR | "
                f"{data.kd:.2f} K/D | {data.average_acs} ACS"
            )
        )


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
