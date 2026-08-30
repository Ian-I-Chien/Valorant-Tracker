import asyncio
import copy
import time
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from valorant.night_market import VP, parse_night_market
from valorant.shop_service import RiotStoreClient, ShopError, LoginExpired
from valorant.shop_card import render_shop_card
from shop_commands import shop_text
from test_shop import make_service, link

ITEM = "00000000-0000-0000-0000-000000000001"


def storefront():
    return {
        "SkinsPanelLayout": {
            "SingleItemOffers": [ITEM],
            "SingleItemStoreOffers": [{"OfferID": ITEM, "Cost": {VP: 1775}}],
            "SingleItemOffersRemainingDurationInSeconds": 3600,
        },
        "BonusStore": {
            "BonusStoreRemainingDurationInSeconds": 600,
            "BonusStoreOffers": [
                {
                    "Offer": {
                        "OfferID": "not-the-skin-id",
                        "Cost": {VP: 1775},
                        "Rewards": [{"ItemID": ITEM}],
                    },
                    "DiscountPercent": 40,
                    "DiscountCosts": {VP: 1065},
                    "IsSeen": False,
                }
            ],
        },
    }


def test_parser_uses_reward_id_and_server_discount_price():
    result = parse_night_market(storefront(), 100)
    assert result["expires"] == 700
    assert result["offers"] == [
        {"id": ITEM, "price": 1065, "original_price": 1775, "discount_percent": 40}
    ]
    assert "IsSeen" not in str(result)


@pytest.mark.parametrize(
    "bonus",
    [
        None,
        {"BonusStoreRemainingDurationInSeconds": 0},
        {"BonusStoreRemainingDurationInSeconds": -1},
        {"BonusStoreRemainingDurationInSeconds": 100, "BonusStoreOffers": []},
    ],
)
def test_no_active_market(bonus):
    assert parse_night_market({"BonusStore": bonus}, 0) is None
    assert parse_night_market({}, 0) is None


def test_missing_prices_not_invented():
    raw = storefront()
    offer = raw["BonusStore"]["BonusStoreOffers"][0]
    offer.pop("DiscountCosts")
    offer.pop("DiscountPercent")
    offer["Offer"].pop("Cost")
    item = parse_night_market(raw, 0)["offers"][0]
    assert item["price"] is item["original_price"] is item["discount_percent"] is None


@pytest.mark.parametrize(
    "bonus",
    [
        "bad",
        {},
        {"BonusStoreRemainingDurationInSeconds": True},
        {"BonusStoreRemainingDurationInSeconds": 100, "BonusStoreOffers": [{}]},
    ],
)
def test_optional_schema_failure_preserves_daily(bonus):
    async def run():
        client = RiotStoreClient()
        raw = storefront()
        raw["BonusStore"] = bonus
        client.versions = AsyncMock(return_value={"riotClientVersion": "test"})
        client.request = AsyncMock(side_effect=[{"entitlements_token": "secret"}, raw])
        result = await client.shop(
            {"access_token": "secret", "region": "ap", "puuid": ITEM}
        )
        assert result["offers"][0]["price"] == 1775
        assert result["night_market_unavailable"] is True
        assert result["night_market"] is None
        assert "secret" not in str(result)
        assert client.request.await_count == 2  # No purchases / reveal calls.

    asyncio.run(run())


def test_cache_refresh_detects_opening_and_logout_clears_combined_data(tmp_path):
    async def run():
        service, _ = await make_service(tmp_path)
        await link(service)
        first = await service.shop(1)
        assert first["cache_until"] <= time.time() + 300
        market = parse_night_market(storefront(), time.time())
        service.client.shop = AsyncMock(
            return_value={
                "expires": time.time() + 3600,
                "offers": [{"id": ITEM, "price": 1775}],
                "night_market": market,
            }
        )
        service.client.skin = AsyncMock(
            return_value={"name": "Test Skin", "icon": None}
        )
        await service.shop(1)
        service.client.shop.assert_not_awaited()
        service.cache[1]["cache_until"] = 0
        result = await service.shop(1)
        assert result["night_market"]["offers"][0]["name"] == "Test Skin"
        service.client.skin.assert_awaited_once()  # Same skin across both sections.
        assert result["cache_until"] <= market["expires"]
        with pytest.raises(ShopError):
            await service.shop(2)
        await service.logout(1)
        assert 1 not in service.cache
        assert await service.vault.get(1) is None

    asyncio.run(run())


def test_expired_authorization_removes_combined_cache(tmp_path):
    async def run():
        service, _ = await make_service(tmp_path)
        await link(service)
        await service.shop(1)
        service.cache[1]["cache_until"] = 0
        service.client.shop = AsyncMock(side_effect=LoginExpired("Expired"))
        with pytest.raises(LoginExpired):
            await service.shop(1)
        assert 1 not in service.cache and await service.vault.get(1) is None

    asyncio.run(run())


def test_both_render_modes_and_text_bounds():
    now = time.time()
    item = {
        "id": ITEM,
        "name": "Long name " * 30,
        "price": 1065,
        "original_price": 1775,
        "discount_percent": 40,
    }
    data = {
        "riot_id": "Player#TEST",
        "expires": now + 3600,
        "offers": [copy.copy(item) for _ in range(4)],
        "night_market": {
            "expires": now + 60,
            "offers": [copy.copy(item) for _ in range(6)],
        },
    }
    with Image.open(BytesIO(render_shop_card(data, now=now))) as image:
        assert image.size == (1000, 1950)
    text = shop_text(data)
    assert "Night Market" in text and "~~1775 VP~~" in text and "1065 VP (-40%)" in text
    assert len(text) <= 2000
    data["night_market"]["expires"] = now - 1
    with Image.open(BytesIO(render_shop_card(data, now=now))) as image:
        assert image.size == (1000, 930)
    assert "Night Market" not in shop_text(data)
