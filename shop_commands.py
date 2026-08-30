"""Private experimental Discord shop commands. No Riot secrets in logs."""

import asyncio
import logging
import os
from io import BytesIO
from pathlib import Path

import discord
from discord import app_commands

from valorant.shop_service import RiotStoreClient, ShopError, ShopService, Vault
from valorant.shop_card import shop_card_png

LOGGER = logging.getLogger(__name__)


def display(value):
    return discord.utils.escape_markdown(" ".join(str(value).split()))[:250]


def shop_text(result):
    title = display(result.get("riot_id") or "Linked account")
    lines = [f"**{title} — Daily Store**", f"Refreshes <t:{int(result['expires'])}:R>"]
    for item in result["offers"][:4]:
        price = (
            f"{item['price']} VP"
            if item.get("price") is not None
            else "Price unavailable"
        )
        lines.append(f"• {display(item.get('name') or 'Unknown skin')} — {price}")
    if not result["offers"]:
        lines.append("No daily offers available.")
    return "\n".join(lines)


async def private_result(interaction, operation, success=None, *, public_shop=False):
    if public_shop:
        # A real private response avoids Discord inheriting a deferred
        # response's ephemeral flag on the first followup.
        await interaction.response.send_message("Loading your store…", ephemeral=True)
    else:
        await interaction.response.defer(ephemeral=True)
    try:
        async with asyncio.timeout(90):
            result = await operation()
        if success:
            content = success(result) if callable(success) else success
            await interaction.edit_original_response(
                content=content,
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            try:
                async with asyncio.timeout(15):
                    png = await shop_card_png(result)
                attachment = discord.File(BytesIO(png), filename="daily-store.png")
                try:
                    content = f"**{display(result.get('riot_id') or 'Linked account')} — Daily Store** • Refreshes <t:{int(result['expires'])}:R>"
                    if public_shop:
                        await interaction.followup.send(
                            content=content,
                            file=attachment,
                            ephemeral=False,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    else:
                        await interaction.edit_original_response(
                            content=content,
                            attachments=[attachment],
                            embeds=[],
                            view=None,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                finally:
                    attachment.close()
            except Exception:
                LOGGER.warning("Shop card unavailable; using text fallback")
                if public_shop:
                    await interaction.followup.send(
                        content=shop_text(result),
                        ephemeral=False,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                else:
                    await interaction.edit_original_response(
                        content=shop_text(result),
                        attachments=[],
                        embeds=[],
                        view=None,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
            if public_shop:
                await interaction.edit_original_response(
                    content="Store shared in this channel.", view=None
                )
    except ShopError as error:
        await interaction.edit_original_response(content=str(error), view=None)
    except Exception:
        # Never log the exception, interaction payload, URL, or upstream body.
        LOGGER.warning("Private shop operation failed; sensitive details suppressed")
        await interaction.edit_original_response(
            content="Shop request failed or timed out. Please try again later.",
            view=None,
        )


class LoginModal(discord.ui.Modal, title="Link Riot account"):
    callback = discord.ui.TextInput(
        label="Paste the full localhost URL",
        placeholder="http://localhost/redirect?...",
        max_length=4000,
    )

    def __init__(self, service, owner, attempt):
        super().__init__(timeout=300)
        self.service, self.owner, self.attempt = service, owner, attempt

    async def on_submit(self, interaction):
        if interaction.user.id != self.owner:
            await interaction.response.send_message(
                "This is not your login request.", ephemeral=True
            )
            return
        await private_result(
            interaction,
            lambda: self.service.login(self.owner, self.attempt, str(self.callback)),
            lambda label: f"Linked: **{display(label)}** · Use /shop to view your store.",
        )

    async def on_error(self, interaction, error):
        LOGGER.warning("Shop login modal failed; sensitive details suppressed")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Login failed. Start /login again.", ephemeral=True
            )


class LoginView(discord.ui.View):
    def __init__(self, service, owner, attempt, url):
        super().__init__(timeout=300)
        self.service, self.owner, self.attempt = service, owner, attempt
        # Keep the buttons in the same order as the instructions.
        self.remove_item(self.submit)
        self.add_item(discord.ui.Button(label="1. Riot login", url=url))
        self.add_item(self.submit)

    async def interaction_check(self, interaction):
        if interaction.user.id == self.owner:
            return True
        await interaction.response.send_message(
            "This is not your login request.", ephemeral=True
        )
        return False

    @discord.ui.button(label="2. Agree & paste URL", style=discord.ButtonStyle.primary)
    async def submit(self, interaction, button):
        await interaction.response.send_modal(
            LoginModal(self.service, self.owner, self.attempt)
        )


def register_shop_commands(bot):
    if os.getenv("SHOP_ENABLED", "0") != "1":
        return
    # Missing/invalid settings fail closed. Do not create an unencrypted vault.
    try:
        allowed = {
            int(value.strip())
            for value in os.environ["SHOP_ALLOWED_USER_IDS"].split(",")
            if value.strip()
        }
        if not allowed or len(allowed) > 100:
            raise ValueError()
        key = Path(os.environ["SHOP_KEY_FILE"]).read_bytes().strip()
        vault = Vault(os.getenv("SHOP_DB_PATH", "private-shop/credentials.db"), key)
    except Exception:
        LOGGER.error("Shop disabled: configure a valid key file and 1-100 tester IDs")
        return
    service = ShopService(vault, RiotStoreClient(), allowed)
    initialized = False
    init_lock = asyncio.Lock()

    async def ready(owner):
        nonlocal initialized
        service.check(owner)
        async with init_lock:
            if not initialized:
                await vault.initialize()
                initialized = True

    @bot.tree.command(
        name="login", description="Link your own Riot account for the experimental shop"
    )
    async def login(interaction: discord.Interaction):
        try:
            await ready(interaction.user.id)
            current = await service.linked_account(interaction.user.id)
            status = (
                f"Current: **{display(current)}** · Relinking replaces this account.\n\n"
                if current
                else ""
            )
            attempt, url = service.begin(interaction.user.id)
            await interaction.response.send_message(
                "**Link Riot account**\n" + status + "1. Open Riot login and sign in.\n"
                "2. Copy the final localhost URL, then paste it below.\n"
                "-# A localhost error is normal. Complete within 5 minutes.\n\n"
                "**Note:** Unofficial test feature with account risks. Submitting shares login authorization "
                "with Discord and this bot; encrypted tokens stay on the RPI. "
                "Never post the URL publicly or submit your password.",
                view=LoginView(service, interaction.user.id, attempt, url),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except ShopError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
        except Exception:
            LOGGER.warning("Shop login setup failed; sensitive details suppressed")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Shop setup failed. Contact the bot owner.", ephemeral=True
                )

    @bot.tree.command(
        name="shop",
        description="Share your linked account's daily shop in this channel",
    )
    async def shop(interaction: discord.Interaction):
        async def operation():
            await ready(interaction.user.id)
            return await service.shop(interaction.user.id)

        await private_result(interaction, operation, public_shop=True)

    @bot.tree.command(
        name="logout",
        description="Delete your stored shop credentials and private cache",
    )
    async def logout(interaction: discord.Interaction):
        async def operation():
            await ready(interaction.user.id)
            await service.logout(interaction.user.id)

        await private_result(
            interaction,
            operation,
            "Shop account unlinked; local credentials and cache deleted.\n"
            "-# Riot sessions and external backups are not revoked or deleted.",
        )
