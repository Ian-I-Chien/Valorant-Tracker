"""Credential-free shop card renderer. Inputs contain display data only.

Public artwork retrieval is bounded and never receives Riot credentials.
"""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

BG, PANEL, LINE = "#0f1923", "#1b2d39", "#304957"
WHITE, MUTED, RED, GREEN = "#f4f4f5", "#91a6b5", "#ff4655", "#38d3ad"


def font(size, bold=False):
    paths = [
        "C:/Windows/Fonts/msjhbd.ttc" if bold else "C:/Windows/Fonts/msjh.ttc",
        (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
            if bold
            else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
    ]
    for path in paths:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def fit(draw, value, width, size, minimum=18):
    value = " ".join(str(value).split())[:200]
    for current in range(size, minimum - 1, -1):
        face = font(current, True)
        if draw.textlength(value, font=face) <= width:
            return value, face
    while value and draw.textlength(value + "…", font=face) > width:
        value = value[:-1]
    return value + "…", face


def countdown(expires, now):
    seconds = max(0, int(expires - now))
    if not seconds:
        return "REFRESH DUE"
    if seconds >= 86400:
        return f"{seconds // 86400}d {(seconds % 86400) // 3600:02d}h"
    return f"{seconds // 3600:02d}h {(seconds % 3600) // 60:02d}m"


def render_shop_card(data, artwork=None, *, now=None, preview=False):
    """Render daily offers plus an optional, unexpired Night Market section."""
    from valorant.night_market import active_night_market, amount

    now = datetime.now(timezone.utc).timestamp() if now is None else now
    artwork = artwork or {}
    market = active_night_market(data, now)
    offers = data.get("offers", [])
    if len(offers) > 4 or (market and len(market["offers"]) > 6):
        raise ValueError("Unexpected store offer count")
    height = 1950 if market else 930
    card = Image.new("RGB", (1000, height), BG)
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 0, 14, height), fill=RED)
    draw.text((55, 32), "VALORANT STORE", font=font(24, True), fill=RED)
    label, face = fit(draw, data.get("riot_id") or "Linked account", 890, 39)
    draw.text((55, 76), label, font=face, fill=WHITE)
    draw.text((55, 133), "YOUR PERSONAL OFFERS", font=font(13, True), fill=MUTED)

    def section(title, subtitle, y):
        draw.text((55, y), title, font=font(23, True), fill=WHITE)
        draw.text((945, y + 5), subtitle, anchor="ra", font=font(17, True), fill=GREEN)

    def tile(index, item, y0, night=False):
        x, y = 55 + (index % 2) * 457, y0 + (index // 2) * 304
        draw.rounded_rectangle((x, y, x + 433, y + 284), radius=20, fill=PANEL)
        draw.text((x + 24, y + 17), f"0{index+1}", font=font(13, True), fill=MUTED)
        discount = item.get("discount_percent")
        if night and discount is not None:
            draw.rounded_rectangle(
                (x + 328, y + 13, x + 410, y + 46), radius=8, fill=RED
            )
            draw.text(
                (x + 369, y + 29),
                f"-{discount}%",
                anchor="mm",
                font=font(18, True),
                fill=WHITE,
            )
        source = artwork.get(item.get("id"))
        if source is not None:
            weapon = source.convert("RGBA")
            bounds = weapon.getbbox()
            if bounds:
                weapon = weapon.crop(bounds)
            weapon = ImageOps.contain(weapon, (385, 132), Image.Resampling.LANCZOS)
            card.paste(
                weapon,
                (x + (433 - weapon.width) // 2, y + 48 + (132 - weapon.height) // 2),
                weapon,
            )
        else:
            draw.text(
                (x + 216, y + 114),
                "IMAGE UNAVAILABLE",
                anchor="mm",
                font=font(17, True),
                fill=MUTED,
            )
        draw.line((x + 24, y + 190, x + 409, y + 190), fill=LINE)
        label, face = fit(draw, item.get("name") or "Unknown skin", 385, 24)
        draw.text((x + 24, y + 202), label, font=face, fill=WHITE)
        price = amount(item.get("price"))
        price_text = f"{price:,} VP" if price is not None else "PRICE UNAVAILABLE"
        if not night:
            draw.text(
                (x + 24, y + 241),
                price_text,
                font=font(23, True),
                fill=GREEN if price is not None else MUTED,
            )
        else:
            original = amount(item.get("original_price"))
            old = f"{original:,} VP" if original is not None else "BASE N/A"
            draw.text((x + 24, y + 249), old, font=font(17), fill=MUTED)
            if original is not None:
                draw.line(
                    (
                        x + 23,
                        y + 260,
                        x + 24 + draw.textlength(old, font=font(17)),
                        y + 260,
                    ),
                    fill=MUTED,
                    width=2,
                )
            draw.text(
                (x + 409, y + 239),
                price_text,
                anchor="ra",
                font=font(26 if price is not None else 16, True),
                fill=GREEN if price is not None else MUTED,
            )

    section("DAILY STORE", "REFRESHES IN  " + countdown(data["expires"], now), 175)
    for i, item in enumerate(offers):
        tile(i, item, 224)
    if not offers:
        draw.text(
            (500, 480),
            "NO DAILY OFFERS AVAILABLE",
            anchor="mm",
            font=font(24, True),
            fill=MUTED,
        )
    if market:
        draw.line((55, 850, 945, 850), fill=LINE)
        section("NIGHT MARKET", "ENDS IN  " + countdown(market["expires"], now), 876)
        for i, item in enumerate(market["offers"]):
            tile(i, item, 926, True)
    footer = height - 86
    draw.line((55, footer, 945, footer), fill=LINE)
    stamp = (
        datetime.fromtimestamp(data.get("fetched_at", now), timezone.utc)
        .strftime("%d %b %Y  %H:%M UTC")
        .upper()
    )
    draw.text((55, footer + 19), "UPDATED  " + stamp, font=font(13, True), fill=MUTED)
    draw.text(
        (945, footer + 19),
        "DEMO DATA" if preview else "VALORANT TRACKER",
        anchor="ra",
        font=font(13, True),
        fill=RED if preview else MUTED,
    )
    note = (
        "Night Market data unavailable; try /shop again later."
        if data.get("night_market_unavailable")
        else "Countdowns at render time · run /shop to refresh"
    )
    draw.text((55, footer + 48), note, font=font(12), fill=MUTED)
    output = BytesIO()
    card.save(output, format="PNG")
    return output.getvalue()


async def shop_card_png(data):
    """Download at most ten public images, then draw off the event loop."""
    import asyncio
    from urllib.parse import urlsplit
    import aiohttp
    from valorant.night_market import active_night_market

    def decode(payload):
        with Image.open(BytesIO(payload)) as source:
            if source.width * source.height > 4_000_000:
                return None
            image = source.convert("RGBA")
            image.thumbnail((512, 256), Image.Resampling.LANCZOS)
            return image

    async def load(session, item):
        url = item.get("icon")
        if not isinstance(url, str):
            return None
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc != "media.valorant-api.com":
            return None
        try:
            async with session.get(url, allow_redirects=False) as response:
                if response.status != 200:
                    return None
                payload = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    payload.extend(chunk)
                    if len(payload) > 8_000_000:
                        return None
            return await asyncio.to_thread(decode, bytes(payload))
        except Exception:
            return None

    offers = data.get("offers", [])[:4]
    market = active_night_market(data, datetime.now(timezone.utc).timestamp())
    if market:
        offers = offers + market["offers"][:6]
    offers = list({item.get("id"): item for item in offers}.values())
    limit = asyncio.Semaphore(3)

    async def limited_load(session, item):
        async with limit:
            return await load(session, item)

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
        images = await asyncio.gather(*(limited_load(session, item) for item in offers))
    artwork = {
        item.get("id"): image
        for item, image in zip(offers, images)
        if image is not None
    }
    return await asyncio.to_thread(render_shop_card, data, artwork)
