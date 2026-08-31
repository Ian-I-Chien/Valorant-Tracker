"""Private account controls and opt-in channel notifications; no match tracking."""

import asyncio
import logging
import time
from io import BytesIO

import discord
from discord import app_commands
from commands import get_notification_channel_id
from valorant.combined_shop_card import combined_shop_card

LOGGER = logging.getLogger(__name__)


def install_multi_commands(bot, service, ready, display, shop_text, shop_card_png):
    async def report_channel(guild_id, owner):
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

    async def choices(interaction, current):
        try:
            await ready(interaction.user.id)
            accounts, _ = await service.accounts(interaction.user.id)
            return [
                app_commands.Choice(name=a["label"][:100], value=a["id"])
                for a in accounts
                if current.casefold() in a["label"].casefold()
            ][:25]
        except Exception:
            return []

    @bot.tree.command(
        name="shop", description="Share all linked shops, or one selected account"
    )
    @app_commands.describe(account="Optional: choose one account; omitted means all")
    @app_commands.autocomplete(account=choices)
    async def shop(interaction: discord.Interaction, account: str = None):
        await interaction.response.send_message(
            "Loading your stores...", ephemeral=True
        )
        failures, results = [], []
        try:
            await ready(interaction.user.id)
            if interaction.guild is None:
                await interaction.edit_original_response(
                    content="Use /shop in a server."
                )
                return
            try:
                destination = await report_channel(
                    interaction.guild.id, interaction.user.id
                )
            except Exception:
                await interaction.edit_original_response(
                    content="Report channel unavailable. Check /set_channel and channel permissions."
                )
                return
            accounts, _ = await service.accounts(interaction.user.id)
            selected = [account] if account else [a["id"] for a in accounts]
            if not selected:
                await interaction.edit_original_response(
                    content="Use /login to add an account first."
                )
                return
            labels = {a["id"]: display(a["label"]) for a in accounts}
            deadline = time.monotonic() + 720
            for identifier in selected:
                if time.monotonic() > deadline:
                    failures.append("Remaining accounts (request time limit)")
                    break
                try:
                    async with asyncio.timeout(60):
                        results.append(
                            await service.shop(interaction.user.id, identifier)
                        )
                except Exception:
                    failures.append(labels.get(identifier, "Selected account"))
            if results:
                attachment = None
                try:
                    try:
                        async with asyncio.timeout(90):
                            image = await combined_shop_card(results, shop_card_png)
                        attachment = discord.File(
                            BytesIO(image), filename="daily-stores.jpg"
                        )
                        kwargs = dict(
                            content=f"Daily stores - {len(results)} account(s)",
                            file=attachment,
                        )
                    except Exception:
                        text = "\n\n".join(shop_text(result) for result in results)
                        if len(text) <= 1900:
                            kwargs = dict(content=text)
                        else:
                            attachment = discord.File(
                                BytesIO(text.encode()), filename="daily-stores.txt"
                            )
                            kwargs = dict(
                                content="Store image unavailable; all accounts are in this text file.",
                                file=attachment,
                            )
                    # Exactly one public send; delivery errors never trigger another send.
                    await destination.send(
                        **kwargs,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                finally:
                    if attachment:
                        attachment.close()
            message = f"Shared {len(results)} store(s) in <#{destination.id}>."
            if failures:
                message += (
                    "\nCould not load/share: "
                    + ", ".join(failures)
                    + ". Check /accounts or try again later."
                )
            await interaction.edit_original_response(
                content=message[:1900], allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception:
            await interaction.edit_original_response(
                content="Shop request failed. Please try again later."
            )

    @bot.tree.command(
        name="logout",
        description="Remove one linked shop account and its notifications",
    )
    @app_commands.autocomplete(account=choices)
    async def logout(interaction: discord.Interaction, account: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await ready(interaction.user.id)
            await service.logout(interaction.user.id, account)
            message = (
                "Account removed. Riot sessions and external backups are not revoked."
            )
        except Exception:
            message = (
                "Could not remove account. Select one of your accounts with /accounts."
            )
        await interaction.edit_original_response(content=message)

    class AccountsView(discord.ui.View):
        def __init__(self, owner, accounts, enabled):
            super().__init__(timeout=180)
            self.owner, self.selected, self.enabled = owner, None, enabled
            self.toggle.label = (
                "Notifications OFF - enable"
                if not enabled
                else "Notifications ON - disable"
            )
            if accounts:
                select = discord.ui.Select(
                    placeholder="Select an account to remove",
                    options=[
                        discord.SelectOption(
                            label=a["label"][:100],
                            value=a["id"],
                            description="Login required" if a["expired"] else "Linked",
                        )
                        for a in accounts[:25]
                    ],
                )

                async def select_account(interaction):
                    self.selected = select.values[0]
                    await interaction.response.defer()

                select.callback = select_account
                self.add_item(select)

        async def interaction_check(self, interaction):
            if interaction.user.id == self.owner:
                return True
            await interaction.response.send_message(
                "This panel belongs to another user.", ephemeral=True
            )
            return False

        async def on_error(self, interaction, error, item):
            LOGGER.warning("Account panel failed; sensitive details suppressed")
            if interaction.response.is_done():
                await interaction.edit_original_response(
                    content="Operation failed. Open /accounts again.", view=None
                )
            else:
                await interaction.response.send_message(
                    "Operation failed. Open /accounts again.", ephemeral=True
                )

        async def enable_here(self, interaction):
            if interaction.guild is None:
                await interaction.edit_original_response(
                    content="Open /accounts in a server.", view=None
                )
                return
            try:
                channel = await report_channel(interaction.guild.id, self.owner)
            except Exception:
                await interaction.edit_original_response(
                    content="Report channel unavailable. Check /set_channel and channel permissions.",
                    view=None,
                )
                return
            target = {"guild": interaction.guild.id, "channel": channel.id}
            await service.set_notifications(self.owner, True, target)
            await interaction.edit_original_response(
                content=f"Notifications enabled in <#{channel.id}>.", view=None
            )

        @discord.ui.button(label="Notifications", style=discord.ButtonStyle.primary)
        async def toggle(self, interaction, button):
            await interaction.response.defer(ephemeral=True)
            _, enabled = await service.accounts(self.owner)
            if enabled:
                await service.set_notifications(self.owner, False)
                await interaction.edit_original_response(
                    content="Notifications disabled.", view=None
                )
            else:
                await self.enable_here(interaction)

        @discord.ui.button(
            label="Remove selected account", style=discord.ButtonStyle.danger
        )
        async def remove(self, interaction, button):
            if not self.selected:
                await interaction.response.send_message(
                    "Select an account first.", ephemeral=True
                )
                return
            await interaction.response.defer(ephemeral=True)
            await service.logout(self.owner, self.selected)
            await interaction.edit_original_response(
                content="Selected account removed. Open /accounts to refresh the list.",
                view=None,
            )

    async def panel(interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await ready(interaction.user.id)
            accounts, enabled = await service.accounts(interaction.user.id)
            lines = [
                "**Shop accounts**",
                "Notifications: " + ("ON (all accounts)" if enabled else "OFF"),
            ]
            target = await service.notification_target(interaction.user.id)
            guild_id = (
                target["guild"]
                if enabled and target
                else getattr(interaction.guild, "id", None)
            )
            channel_id = (
                await get_notification_channel_id(str(guild_id)) if guild_id else None
            )
            lines.append(
                f"Report channel: <#{channel_id}>"
                if channel_id
                else "Report channel: not configured; use /set_channel"
            )
            lines.extend(
                display(a["label"])
                + (" - login required" if a["expired"] else " - linked")
                for a in accounts
            )
            if not accounts:
                lines.append("Use /login to add an account.")
            await interaction.edit_original_response(
                content="\n".join(lines)[:1900],
                view=AccountsView(interaction.user.id, accounts, enabled),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception:
            await interaction.edit_original_response(
                content="Could not load accounts. Please try again later."
            )

    @bot.tree.command(
        name="accounts",
        description="Manage linked shop accounts and all-account channel notifications",
    )
    async def accounts(interaction: discord.Interaction):
        await panel(interaction)

    async def send_notifications(owner, stores, warnings, target):
        if not stores:
            return True  # Authorization failures are shown privately in /accounts.
        try:
            channel = await report_channel(target["guild"], owner)
            sections = [shop_text(store) for store in stores]
            chunk = f"Shop update for <@{owner}>\n"
            for section in sections:
                if len(chunk) + len(section) + 2 > 1900:
                    await channel.send(
                        chunk, allowed_mentions=discord.AllowedMentions.none()
                    )
                    chunk = ""
                chunk += ("\n\n" if chunk else "") + section
            if chunk:
                await channel.send(
                    chunk, allowed_mentions=discord.AllowedMentions.none()
                )
            return True
        except (discord.Forbidden, discord.NotFound, ValueError):
            return False
        except Exception:
            LOGGER.warning("Shop notification delivery unavailable; details suppressed")
            return True

    async def worker():
        await bot.wait_until_ready()
        while not bot.is_closed():
            try:
                # Initialization must not require a particular allowed owner.
                await service.vault.initialize()
                for owner in await service.owners():
                    try:
                        await service.notify_owner(owner, send_notifications)
                    except Exception:
                        LOGGER.warning(
                            "Shop notification check failed; details suppressed"
                        )
                    await asyncio.sleep(1)
            except Exception:
                LOGGER.warning(
                    "Shop notification worker unavailable; details suppressed"
                )
            await asyncio.sleep(60)

    async def start_worker():
        task = getattr(bot, "shop_notification_task", None)
        if task is None or task.done():
            bot.shop_notification_task = asyncio.create_task(worker())

    bot.add_listener(start_worker, "on_ready")
