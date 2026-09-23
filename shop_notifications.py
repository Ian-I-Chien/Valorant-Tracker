"""Resolve report channels and run opt-in shop notification polling."""

import asyncio
import logging
from io import BytesIO

import discord

from commands import get_notification_channel_id

LOGGER = logging.getLogger(__name__)


async def resolve_report_channel(bot, guild_id: int, owner: int):
    """Return the configured channel after membership and permission checks."""
    channel_id = await get_notification_channel_id(str(guild_id))
    if not channel_id:
        raise ValueError("Report channel is not configured")
    channel = await bot.fetch_channel(int(channel_id))
    if not getattr(channel, "guild", None) or channel.guild.id != guild_id:
        raise ValueError("Invalid report channel")

    member = await channel.guild.fetch_member(owner)
    me = channel.guild.me or await channel.guild.fetch_member(bot.user.id)
    permissions = channel.permissions_for(me)
    can_send = (
        permissions.send_messages_in_threads
        if isinstance(channel, discord.Thread)
        else permissions.send_messages
    )
    if (
        not channel.permissions_for(member).view_channel
        or not permissions.view_channel
        or not can_send
    ):
        raise ValueError("Report channel is inaccessible")
    return channel


def notification_sender(bot, shop_text, combined_shop_card, shop_card_png):
    async def send(owner, stores, warnings, target):
        if not stores:
            return True  # Authorization failures are shown privately in /accounts.
        attachment = None
        try:
            channel = await resolve_report_channel(bot, target["guild"], owner)
            try:
                async with asyncio.timeout(90):
                    image = await combined_shop_card(stores, shop_card_png)
                attachment = discord.File(BytesIO(image), filename="daily-stores.jpg")
                await channel.send(
                    content=f"Daily stores - {len(stores)} account(s)",
                    file=attachment,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except Exception:
                LOGGER.warning(
                    "Shop notification card unavailable; using text fallback"
                )
                text = f"Daily stores - {len(stores)} account(s)\n\n" + "\n\n".join(
                    shop_text(store) for store in stores
                )
                if len(text) <= 1900:
                    await channel.send(
                        text, allowed_mentions=discord.AllowedMentions.none()
                    )
                else:
                    attachment = discord.File(
                        BytesIO(text.encode()), filename="daily-stores.txt"
                    )
                    await channel.send(
                        content=f"Daily stores - {len(stores)} account(s)",
                        file=attachment,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            return True
        except (discord.Forbidden, discord.NotFound, ValueError):
            return False
        except Exception:
            LOGGER.warning("Shop notification delivery unavailable; details suppressed")
            return True
        finally:
            if attachment:
                attachment.close()

    return send


async def notification_worker(bot, service, send):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await service.vault.initialize()
            for owner in await service.owners():
                try:
                    await service.notify_owner(owner, send)
                except Exception:
                    LOGGER.warning("Shop notification check failed; details suppressed")
                await asyncio.sleep(1)
        except Exception:
            LOGGER.warning("Shop notification worker unavailable; details suppressed")
        await asyncio.sleep(60)


def install_shop_notification_worker(
    bot, service, shop_text, combined_shop_card, shop_card_png
):
    """Register one idempotent background worker on the bot ready event."""
    send = notification_sender(bot, shop_text, combined_shop_card, shop_card_png)

    async def start_worker():
        task = getattr(bot, "shop_notification_task", None)
        if task is None or task.done():
            bot.shop_notification_task = asyncio.create_task(
                notification_worker(bot, service, send)
            )

    bot.add_listener(start_worker, "on_ready")
