"""Render a Valorant match as a Discord-friendly scoreboard image."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageOps

LOGGER = logging.getLogger(__name__)

CARD_WIDTH = 1200
HEADER_HEIGHT = 230
ROW_HEIGHT = 104
CARD_HEIGHT = HEADER_HEIGHT + (ROW_HEIGHT * 5) + 70
ASSET_CACHE = Path("data/assets")


@dataclass(frozen=True)
class MatchCardPlayer:
    riot_id: str
    agent_name: str
    agent_id: str
    team_id: str
    party_id: Optional[str]
    rank_name: str
    rank_icon_url: Optional[str]
    kills: int
    deaths: int
    assists: int
    acs: int
    headshot_percentage: float
    kast: float
    rank_rating: Optional[int]
    rr_change: Optional[int]
    registered: bool = False


@dataclass(frozen=True)
class MatchCardData:
    map_name: str
    map_id: str
    queue_name: str
    score: str
    result: str
    played_at: str
    players: tuple[MatchCardPlayer, ...]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msjhbd.ttc" if bold else "C:/Windows/Fonts/msjh.ttc"),
        Path(
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
            if bold
            else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
        ),
        Path(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size=size)


def _draw_mixed_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    value: str,
    size: int,
    fill: str,
    bold: bool = False,
) -> None:
    """Draw mixed CJK/Latin text with a per-character font fallback."""
    latin_font = _font(size, bold)
    cjk_path = Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf")
    cjk_font = (
        ImageFont.truetype(str(cjk_path), size) if cjk_path.exists() else latin_font
    )
    x, y = position
    for character in value:
        font = cjk_font if "\u2e80" <= character <= "\u9fff" else latin_font
        draw.text((x, y), character, font=font, fill=fill)
        x += draw.textlength(character, font=font)


class AssetCache:
    """Download remote image assets once and reuse them on later matches."""

    def __init__(self, root: Path = ASSET_CACHE):
        self.root = root

    async def get(self, url: Optional[str]) -> Optional[Image.Image]:
        if not url:
            return None
        suffix = Path(url.split("?", 1)[0]).suffix or ".img"
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        path = self.root / f"{digest}{suffix}"
        try:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        path.write_bytes(await response.read())
            with Image.open(path) as image:
                return image.convert("RGBA")
        except (aiohttp.ClientError, OSError):
            LOGGER.warning("Could not load match-card asset %s", url, exc_info=True)
            return None


def _build_party_styles(
    teams: dict[str, list[MatchCardPlayer]],
) -> dict[tuple[str, str], tuple[str, str]]:
    styles: dict[tuple[str, str], tuple[str, str]] = {}
    colors = ("#bd7bff", "#45d6c4", "#ffae57", "#f074a5")
    for team_id in ("Blue", "Red"):
        groups: dict[str, list[MatchCardPlayer]] = {}
        for player in teams[team_id]:
            if player.party_id:
                groups.setdefault(player.party_id, []).append(player)
        grouped_parties = [group for group in groups.values() if len(group) > 1]
        for group_index, group in enumerate(grouped_parties):
            size_name = {
                2: "DUO",
                3: "TRIO",
                4: "4 STACK",
                5: "5 STACK",
            }[len(group)]
            party_id = group[0].party_id
            if party_id:
                styles[(team_id, party_id)] = (
                    f"{size_name} {chr(65 + group_index)}",
                    colors[group_index % len(colors)],
                )
    return styles


def _format_rr(queue_name: str, player: MatchCardPlayer) -> str:
    if (
        queue_name.casefold() != "competitive"
        or player.rank_rating is None
        or player.rr_change is None
    ):
        return ""
    return f"  RR {player.rank_rating} ({player.rr_change:+d})"


class MatchCardRenderer:
    def __init__(self, assets: Optional[AssetCache] = None):
        self.assets = assets or AssetCache()

    async def render(self, data: MatchCardData) -> bytes:
        map_url = f"https://media.valorant-api.com/maps/{data.map_id}/splash.png"
        agent_urls = [
            f"https://media.valorant-api.com/agents/{player.agent_id}/displayicon.png"
            for player in data.players
        ]
        images = await asyncio.gather(
            self.assets.get(map_url),
            *[self.assets.get(url) for url in agent_urls],
            *[self.assets.get(player.rank_icon_url) for player in data.players],
        )
        map_image = images[0]
        count = len(data.players)
        agent_images = images[1 : count + 1]
        rank_images = images[count + 1 :]
        return await asyncio.to_thread(
            self._draw, data, map_image, agent_images, rank_images
        )

    @staticmethod
    def _draw(
        data: MatchCardData,
        map_image: Optional[Image.Image],
        agent_images: list[Optional[Image.Image]],
        rank_images: list[Optional[Image.Image]],
    ) -> bytes:
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), "#0f1923")
        draw = ImageDraw.Draw(card)

        if map_image:
            background = ImageOps.fit(
                map_image.convert("RGB"), (CARD_WIDTH, HEADER_HEIGHT)
            )
            background = Image.blend(
                background, Image.new("RGB", background.size, "#081018"), 0.58
            )
            card.paste(background, (0, 0))

        draw.rectangle(
            (0, HEADER_HEIGHT - 5, CARD_WIDTH, HEADER_HEIGHT), fill="#ff4655"
        )
        draw.text((46, 38), data.map_name.upper(), font=_font(52, True), fill="white")
        draw.text(
            (48, 104),
            f"{data.queue_name}  •  {data.played_at}",
            font=_font(23),
            fill="#d8e1e8",
        )
        result_color = "#72e5ad" if "WIN" in data.result.upper() else "#ff6673"
        score_box = (885, 42, 1150, 174)
        draw.rounded_rectangle(
            score_box, radius=18, fill="#101c27", outline=result_color, width=3
        )
        draw.text(
            (1018, 60), data.score, anchor="ma", font=_font(44, True), fill="white"
        )
        draw.text(
            (1018, 122),
            data.result,
            anchor="ma",
            font=_font(22, True),
            fill=result_color,
        )

        teams = {
            "Blue": [p for p in data.players if p.team_id == "Blue"][:5],
            "Red": [p for p in data.players if p.team_id == "Red"][:5],
        }
        party_styles = _build_party_styles(teams)
        player_indexes = {
            id(player): index for index, player in enumerate(data.players)
        }
        for column, team_id in enumerate(("Blue", "Red")):
            left = 30 + (column * 585)
            accent = "#4ea6ff" if team_id == "Blue" else "#ff4655"
            for row, player in enumerate(teams[team_id]):
                top = HEADER_HEIGHT + 22 + (row * ROW_HEIGHT)
                box = (left, top, left + 555, top + 88)
                border = "#f7c948" if player.registered else "#293946"
                draw.rounded_rectangle(
                    box, radius=12, fill="#172631", outline=border, width=3
                )
                draw.rectangle((left, top + 12, left + 5, top + 76), fill=accent)

                index = player_indexes[id(player)]
                agent = agent_images[index]
                if agent:
                    icon = ImageOps.fit(agent, (72, 72))
                    card.paste(icon, (left + 12, top + 8), icon)
                rank = rank_images[index]
                if rank:
                    icon = ImageOps.contain(rank, (40, 40))
                    card.paste(icon, (left + 91, top + 10), icon)

                name_x = left + 140
                _draw_mixed_text(
                    draw, (name_x, top + 9), player.riot_id, 20, "white", bold=True
                )
                draw.text(
                    (name_x, top + 39),
                    f"{player.agent_name}  •  {player.rank_name}",
                    font=_font(15),
                    fill="#aebcc7",
                )
                party_style = party_styles.get((player.team_id, player.party_id or ""))
                if party_style:
                    party_label, party_color = party_style
                    badge = (left + 458, top + 38, left + 540, top + 59)
                    draw.rounded_rectangle(badge, radius=8, fill=party_color)
                    draw.text(
                        (left + 499, top + 48),
                        party_label,
                        anchor="mm",
                        font=_font(11, True),
                        fill="#0f1923",
                    )

                rr = _format_rr(data.queue_name, player)
                stats = (
                    f"{player.kills}/{player.deaths}/{player.assists}   "
                    f"ACS {player.acs}   HS {player.headshot_percentage:.0f}%   "
                    f"KAST {player.kast:.0f}%{rr}"
                )
                draw.text((name_x, top + 63), stats, font=_font(13), fill="#dce5eb")

        draw.text(
            (CARD_WIDTH // 2, CARD_HEIGHT - 25),
            "VALORANT TRACKER  •  tracked players are highlighted",
            anchor="mm",
            font=_font(15, True),
            fill="#6f8492",
        )
        output = io.BytesIO()
        card.save(output, format="PNG", optimize=True)
        return output.getvalue()
