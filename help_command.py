"""Offline help: no account lookup, subscription changes, or API requests."""

import discord
import os


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Valorant Tracker — Help",
        description="Look up player stats or track new matches in your server.",
        color=discord.Color.from_str("#ff4655"),
    )
    embed.add_field(
        name="Last match - standalone lookup",
        value="`/last_match id:name#tag` - Share the latest completed match. "
        "Full Riot ID is required. No registration or shop login needed; "
        "does not change tracking. Errors are visible only to you.",
        inline=False,
    )
    embed.add_field(
        name="Player lookup — no registration needed",
        value=(
            "`/info username:name#tag` — View recent stats and the RR trend.\n"
            "`/predict username:name#tag` — Estimate your next match's win chance "
            "(for entertainment, not a guarantee).\n"
            "Use a full Riot ID, or a unique registered name in this server. "
            "These commands do not enable match tracking.\n"
            "Stats use eligible Competitive / Unrated matches from the latest "
            "20 matches within 30 days; no eligible matches means no data."
        ),
        inline=False,
    )
    embed.add_field(
        name="Match notifications",
        value=(
            "`/reg_val valorant_account:name#tag` — Start tracking an account.\n"
            "`/del_val valorant_account:name#tag` — Stop tracking an account "
            "you registered in this server.\n"
            "A server manager must set the notification channel first. "
            "Tracking starts from the current latest match; older matches "
            "are not replayed."
        ),
        inline=False,
    )
    embed.add_field(
        name="Server settings",
        value=(
            "`/set_channel channel:#channel` — Set this server's notification "
            "channel (requires Manage Server).\n"
            "`/show_config` — View the current notification channel "
            "(available to everyone).\n"
            "Each server has its own notification channel and registrations."
        ),
        inline=False,
    )
    embed.add_field(
        name="More help",
        value=(
            "`/help` — Show this guide, visible only to you.\n"
            "Use the player and tracking commands in a Discord server.\n"
            "[Documentation & source](https://github.com/Ian-I-Chien/Valorant-Tracker)"
        ),
        inline=False,
    )
    if os.getenv("SHOP_ENABLED", "0") == "1":
        embed.add_field(
            name=(
                "Experimental shop"
                if os.getenv("SHOP_ALLOWED_USER_IDS", "").strip() == "*"
                else "Experimental shop — invited testers only"
            ),
            value="`/login` — Link your own Riot account after reading the consent notice.\n"
            "`/shop [account]` — Share all linked daily shops, or one selected account.\n"
            "`/accounts` — Manage accounts and all-account channel notifications.\n"
            "`/logout account` — Remove one account (does not revoke Riot sessions).",
            inline=False,
        )
    return embed


async def show_help(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=build_help_embed(), ephemeral=True)
