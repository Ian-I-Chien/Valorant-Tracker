"""Prepare match notifications and checkpoint successful deliveries."""

import logging
from dataclasses import dataclass
from typing import Optional

import discord
from database.storage_sqlite import UserSQLiteDB
from userdb_coordination import get_userdb_lock
from valorant.match import Match

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PollingMatchResult:
    embed: Optional[discord.Embed]
    image: Optional[bytes]
    server_id: str
    dc_id: str
    valorant_puuid: str
    match_id: str
    subscription_id: int
    previous_match_id: Optional[str]


async def handle_polling_matches() -> Optional[PollingMatchResult]:
    """Prepare the first unseen subscribed match without claiming delivery."""
    async with get_userdb_lock():
        try:
            async with UserSQLiteDB() as repository:
                subscriptions = await repository.list_subscriptions()
                LOGGER.debug("Loaded %s subscriptions", len(subscriptions))
                for subscription in subscriptions:
                    result = await _prepare_subscription(repository, subscription)
                    if result is not None:
                        return result
        except Exception:
            LOGGER.exception("Critical error while polling matches")
    return None


async def _prepare_subscription(repository, subscription):
    try:
        account = subscription.valorant_account
        player_name, player_tag = account.split("#")
        match = Match(player_name, player_tag)
        latest = await match.get_last_match_id()
        if not latest:
            return None

        previous = subscription.last_polled_match_id
        if previous is None:
            initialized = await repository.update_last_polled_match(
                subscription_id=subscription.id,
                expected_match_id=None,
                match_id=latest,
            )
            if not initialized:
                LOGGER.warning(
                    "Could not initialize checkpoint for %s; subscription changed",
                    account,
                )
            LOGGER.debug("Initialized checkpoint %s for %s", latest, account)
            return None
        if previous == latest:
            LOGGER.debug("Match %s already processed for %s", latest, account)
            return None

        LOGGER.debug("Fetching new match %s for %s", latest, player_name)
        match.last_match_data = await match.fetch_match()
        try:
            image = await match.build_match_card()
            embed = None
        except Exception:
            LOGGER.exception(
                "Could not render match card %s; using text fallback", latest
            )
            image = None
            embed = await match.build_embed()

        return PollingMatchResult(
            embed=embed,
            image=image,
            server_id=subscription.server_id,
            dc_id=subscription.discord_user_id,
            valorant_puuid=subscription.valorant_puuid,
            match_id=latest,
            subscription_id=subscription.id,
            previous_match_id=previous,
        )
    except Exception:
        LOGGER.exception("Error processing account %s", subscription.valorant_account)
        return None


async def mark_match_delivered(result: PollingMatchResult) -> bool:
    """Persist a match checkpoint only after Discord delivery succeeds."""
    async with get_userdb_lock():
        async with UserSQLiteDB() as repository:
            return await repository.update_last_polled_match(
                subscription_id=result.subscription_id,
                expected_match_id=result.previous_match_id,
                match_id=result.match_id,
            )
