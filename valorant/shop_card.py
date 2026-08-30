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


def render_shop_card(data, artwork=None, *, now=None, preview=False):
    """Return PNG bytes; artwork maps offer IDs to decoded PIL images.

    No network, credential reads, or private cache writes happen here. Missing
    artwork and prices remain explicit, and an empty shop is supported.
    """
    artwork = artwork or {}
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    offers = data.get("offers", [])
    if len(offers) > 4:
        raise ValueError("Daily shop card supports at most four offers")
    canvas = Image.new("RGB", (1000, 1000), BG)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 14, 1000), fill=RED)
    draw.text((55, 36), "DAILY STORE", font=font(25, True), fill=RED)
    label, face = fit(draw, data.get("riot_id") or "Linked account", 575, 39)
    draw.text((55, 77), label, font=face, fill=WHITE)
    draw.text(
        (55, 132),
        "PERSONAL ROTATION  •  DAILY OFFERS",
        font=font(14, True),
        fill=MUTED,
    )
    draw.rounded_rectangle(
        (682, 40, 945, 155), radius=20, fill=PANEL, outline=LINE, width=2
    )
    draw.text((707, 57), "REFRESHES IN", font=font(14, True), fill=MUTED)
    remaining = max(0, int(data["expires"] - now))
    clock = (
        f"{remaining // 3600:02d}h {(remaining % 3600) // 60:02d}m"
        if remaining
        else "REFRESH DUE"
    )
    draw.text((707, 86), clock, font=font(26, True), fill=GREEN)

    for index, item in enumerate(offers):
        x, y = 55 + (index % 2) * 457, 198 + (index // 2) * 344
        draw.rounded_rectangle((x, y, x + 433, y + 319), radius=20, fill=PANEL)
        draw.text(
            (x + 24, y + 18),
            f"0{index + 1}  /  DAILY OFFER",
            font=font(13, True),
            fill=MUTED,
        )
        source = artwork.get(item.get("id"))
        if source is not None:
            weapon = source.convert("RGBA")
            bounds = weapon.getbbox()
            if bounds:
                weapon = weapon.crop(bounds)
            weapon = ImageOps.contain(weapon, (389, 150), Image.Resampling.LANCZOS)
            canvas.paste(
                weapon,
                (x + (433 - weapon.width) // 2, y + 50 + (150 - weapon.height) // 2),
                weapon,
            )
        else:
            draw.text(
                (x + 216, y + 115),
                "IMAGE UNAVAILABLE",
                anchor="mm",
                font=font(17, True),
                fill=MUTED,
            )
        draw.line((x + 24, y + 213, x + 409, y + 213), fill=LINE)
        name, face = fit(draw, item.get("name") or "Unknown skin", 385, 24)
        draw.text((x + 24, y + 231), name, font=face, fill=WHITE)
        price = item.get("price")
        price_text = (
            f"{price:,} VP"
            if isinstance(price, int) and not isinstance(price, bool) and price >= 0
            else "PRICE UNAVAILABLE"
        )
        draw.text(
            (x + 24, y + 271),
            price_text,
            font=font(21, True),
            fill=GREEN if price is not None else MUTED,
        )
    if not offers:
        draw.text(
            (500, 470),
            "NO DAILY OFFERS AVAILABLE",
            anchor="mm",
            font=font(25, True),
            fill=MUTED,
        )
    draw.line((55, 907, 945, 907), fill=LINE)
    stamp = (
        datetime.fromtimestamp(data.get("fetched_at", now), timezone.utc)
        .strftime("%d %b %Y  %H:%M UTC")
        .upper()
    )
    draw.text((55, 930), "UPDATED  " + stamp, font=font(13, True), fill=MUTED)
    draw.text(
        (945, 930),
        "DEMO DATA" if preview else "VALORANT TRACKER",
        anchor="ra",
        font=font(13, True),
        fill=RED if preview else MUTED,
    )
    draw.text(
        (55, 958),
        "Countdown at render time · run /shop to refresh",
        font=font(12),
        fill=MUTED,
    )
    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


async def shop_card_png(data):
    """Download at most four public images, then draw off the event loop."""
    import asyncio
    from urllib.parse import urlsplit
    import aiohttp

    def decode(payload):
        with Image.open(BytesIO(payload)) as source:
            if source.width * source.height > 4_000_000:
                return None
            return source.convert("RGBA")

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
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
        images = await asyncio.gather(*(load(session, item) for item in offers))
    artwork = {
        item.get("id"): image
        for item, image in zip(offers, images)
        if image is not None
    }
    return await asyncio.to_thread(render_shop_card, data, artwork)
