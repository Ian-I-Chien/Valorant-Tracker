"""Combine account cards into one bounded image without changing their layout."""

import asyncio
from io import BytesIO
from PIL import Image


def combine_cards(cards):
    images = []
    try:
        for raw in cards[:25]:
            with Image.open(BytesIO(raw)) as source:
                image = source.convert("RGB")
                if image.width > 1000:
                    resized = image.resize(
                        (1000, max(1, round(image.height * 1000 / image.width)))
                    )
                    image.close()
                    image = resized
                images.append(image)
        if not images:
            raise ValueError("No cards")
        width = max(i.width for i in images)
        total = sum(i.height for i in images) + 16 * (len(images) - 1)
        scale = min(1, 16000 / total)
        canvas = Image.new(
            "RGB", (max(1, int(width * scale)), max(1, int(total * scale))), "#101823"
        )
        y = 0
        for image in images:
            small = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
            )
            canvas.paste(small, (0, y))
            y += small.height + int(16 * scale)
            small.close()
        try:
            for quality in (90, 75, 55):
                output = BytesIO()
                canvas.save(output, format="JPEG", quality=quality, optimize=True)
                if output.tell() <= 7_500_000:
                    return output.getvalue()
            raise ValueError("Combined card exceeds upload budget")
        finally:
            canvas.close()
    finally:
        for image in images:
            image.close()


async def combined_shop_card(results, render):
    cards = []
    for result in results:
        async with asyncio.timeout(15):
            cards.append(await render(result))
    return await asyncio.to_thread(combine_cards, cards)
