"""Private account controls and opt-in DM notifications; no match tracking."""

import asyncio
import logging
import time
from io import BytesIO

import discord
from discord import app_commands

LOGGER = logging.getLogger(__name__)


def install_multi_commands(bot, service, ready, display, shop_text, shop_card_png):
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
        failures, count = [], 0
        try:
            await ready(interaction.user.id)
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
                attachment = None
                try:
                    async with asyncio.timeout(60):
                        result = await service.shop(interaction.user.id, identifier)
                    try:
                        async with asyncio.timeout(15):
                            png = await shop_card_png(result)
                        attachment = discord.File(
                            BytesIO(png), filename="daily-store.png"
                        )
                        kwargs = dict(
                            content=f"**{display(result['riot_id'])} - Daily Store**",
                            file=attachment,
                        )
                    except Exception:
                        kwargs = dict(content=shop_text(result))
                    await interaction.followup.send(
                        **kwargs,
                        ephemeral=False,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    count += 1
                except Exception:
                    failures.append(labels.get(identifier, "Selected account"))
                finally:
                    if attachment:
                        attachment.close()
            message = f"Shared {count} store(s)."
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

        @discord.ui.button(label="Notifications", style=discord.ButtonStyle.primary)
        async def toggle(self, interaction, button):
            await interaction.response.defer(ephemeral=True)
            # Resolve current persisted state; an old panel must not invert a stale value.
            accounts, enabled = await service.accounts(self.owner)
            if not enabled:
                if not accounts:
                    await interaction.edit_original_response(
                        content="Use /login first.", view=None
                    )
                    return
                try:
                    await interaction.user.send(
                        "Shop notification delivery test. Enabling notifications for ALL linked accounts, starting from the next observed shop update.",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    await interaction.edit_original_response(
                        content="Cannot DM you. Allow DMs and try again; notifications remain off.",
                        view=None,
                    )
                    return
            await service.set_notifications(self.owner, not enabled)
            await interaction.edit_original_response(
                content=(
                    "Notifications disabled."
                    if enabled
                    else "Notifications enabled for all linked accounts, including future logins. Starts from the next observed shop update."
                ),
                view=None,
            )

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
        description="Manage linked shop accounts and all-account DM notifications",
    )
    async def accounts(interaction: discord.Interaction):
        await panel(interaction)

    @bot.tree.command(
        name="shop_notify",
        description="Enable or disable shop update DMs for all linked accounts",
    )
    async def shop_notify(interaction: discord.Interaction):
        await panel(interaction)

    async def send_notifications(owner, stores, warnings):
        try:
            user = await bot.fetch_user(owner)
            sections = [shop_text(store) for store in stores]
            sections.extend(
                "Login required: **"
                + display(label)
                + "**. Use /login to restore this account."
                for label in warnings
            )
            chunk = ""
            for section in sections:
                if len(chunk) + len(section) + 2 > 1900 and chunk:
                    await user.send(
                        chunk, allowed_mentions=discord.AllowedMentions.none()
                    )
                    chunk = ""
                chunk += ("\n\n" if chunk else "") + section
            if chunk:
                await user.send(chunk, allowed_mentions=discord.AllowedMentions.none())
            return True
        except discord.Forbidden:
            return False
        except Exception:
            # Ambiguous delivery: do not replay a claimed update on restart.
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
