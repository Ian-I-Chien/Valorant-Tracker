import asyncio
from io import BytesIO
from unittest.mock import MagicMock

from PIL import Image
import pytest

from valorant.shop_card import render_shop_card, shop_card_png


@pytest.mark.parametrize(
    "offers",
    [
        [],
        [{"id": "missing", "name": "名稱" * 100, "price": None}],
        [{"id": str(i), "name": "Skin", "price": 1775} for i in range(4)],
    ],
)
def test_valid_png_for_missing_and_full_offers(offers):
    payload = render_shop_card(
        {"riot_id": "玩家#TEST", "expires": 0, "offers": offers}, now=1
    )
    with Image.open(BytesIO(payload)) as image:
        image.load()
        assert image.size == (1000, 1000)
        assert image.format == "PNG"


@pytest.mark.parametrize(
    "url",
    [
        "http://media.valorant-api.com/a.png",
        "https://evil.test/a.png",
        "https://media.valorant-api.com.evil.test/a.png",
        "https://user@media.valorant-api.com/a.png",
        "https://media.valorant-api.com:444/a.png",
    ],
)
def test_untrusted_artwork_never_requested(monkeypatch, url):
    import aiohttp

    get = MagicMock(side_effect=AssertionError("Must not fetch"))
    monkeypatch.setattr(aiohttp.ClientSession, "get", get)
    result = asyncio.run(
        shop_card_png({"expires": 0, "offers": [{"id": "a", "icon": url}]})
    )
    assert result.startswith(b"\x89PNG")
    get.assert_not_called()
