"""One-off match lookup, independent of shop auth and tracking subscriptions."""

import asyncio
import io
import logging
from urllib.parse import quote

import discord

from valorant.match import Match
from valorant.player import ValorantPlayer

LOGGER = logging.getLogger(__name__)


def summary_embed(data: dict, riot_id: str) -> discord.Embed:
    """A small fallback that also supports modes without a two-team scoreboard."""
    metadata = data.get("metadata", {})
    embed = discord.Embed(
        title="Last match",
        description=discord.utils.escape_markdown(riot_id),
        color=discord.Color.from_str("#ff4655"),
    )
    embed.add_field(
        name="Map", value=str(metadata.get("map", {}).get("name", "Unknown"))
    )
    embed.add_field(
        name="Mode", value=str(metadata.get("queue", {}).get("name", "Unknown"))
    )
    embed.add_field(name="Played at", value=str(metadata.get("started_at", "Unknown")))
    for player in data.get("players", []):
        if f"{player.get('name')}#{player.get('tag')}".casefold() == riot_id.casefold():
            stats = player.get("stats", {})
            embed.add_field(
                name="Agent", value=str(player.get("agent", {}).get("name", "Unknown"))
            )
            embed.add_field(
                name="K/D/A",
                value=" / ".join(
                    str(stats.get(k, 0)) for k in ("kills", "deaths", "assists")
                ),
            )
            team = next(
                (
                    t
                    for t in data.get("teams", [])
                    if t.get("team_id") == player.get("team_id")
                ),
                None,
            )
            if team and "rounds" in team:
                won, lost = team["rounds"].get("won", 0), team["rounds"].get("lost", 0)
                embed.add_field(name="Score", value=f"{won} : {lost}")
            break
    return embed


async def show_last_match(interaction: discord.Interaction, riot_id: str) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "Use this command in a Discord server.", ephemeral=True
        )
        return
    parts = riot_id.strip().split("#")
    if len(parts) != 2 or not all(p.strip() for p in parts) or len(riot_id) > 128:
        await interaction.response.send_message(
            "Enter a full Riot ID: `name#tag`.", ephemeral=True
        )
        return
    name, tag = (p.strip() for p in parts)
    await interaction.response.defer(ephemeral=True)
    try:
        async with asyncio.timeout(90):
            player = ValorantPlayer(quote(name, safe=""), quote(tag, safe=""))
            account = await player.fetch_account()
            if not account or not account.get("puuid"):
                await interaction.edit_original_response(
                    content="Could not find that Riot ID. Check the ID or try again later."
                )
                return
            name, tag = account.get("name", name), account.get("tag", tag)
            canonical_id = f"{name}#{tag}"
            match = Match(
                quote(name, safe=""),
                quote(tag, safe=""),
                region=account.get("region") or "ap",
            )
            payload = await match.fetch_recent_matches(size=1, cache_ttl=60)
            if not payload or not isinstance(payload.get("data"), list):
                raise ValueError("Invalid match history response")
            if not payload["data"]:
                await interaction.edit_original_response(
                    content="No completed matches were found for that Riot ID."
                )
                return
            match.last_match_id = payload["data"][0]["metadata"]["matchid"]
            detail = await match.fetch_match()
            if not detail or not isinstance(detail.get("data"), dict):
                raise ValueError("Missing match detail")
            players = detail["data"].get("players")
            if not isinstance(players, list) or not any(
                p.get("puuid") == account["puuid"]
                or f"{p.get('name')}#{p.get('tag')}".casefold()
                == canonical_id.casefold()
                for p in players
            ):
                raise ValueError("Requested player missing from match detail")
            match.player_name, match.player_tag = name, tag
            match.last_match_data = detail
            fallback = summary_embed(detail["data"], canonical_id)
            try:
                image = await asyncio.wait_for(
                    match.build_match_card(
                        highlight_accounts={canonical_id.casefold()}
                    ),
                    timeout=45,
                )
            except Exception:
                LOGGER.warning(
                    "Last-match card unavailable; using summary", exc_info=True
                )
                image = None
        # Finish the private deferred response before sending a public follow-up.
        await interaction.edit_original_response(
            content="Match found. Sharing the result in this channel."
        )
        kwargs = {
            "ephemeral": False,
            "allowed_mentions": discord.AllowedMentions.none(),
        }
        if image is not None:
            kwargs["file"] = discord.File(io.BytesIO(image), filename="last-match.png")
        else:
            kwargs["embed"] = fallback
        await interaction.followup.send(**kwargs)
    except Exception:
        LOGGER.warning("Last-match lookup or delivery failed", exc_info=True)
        await interaction.edit_original_response(
            content="Could not retrieve or share the last match. Please try again later and check my channel permissions."
        )
