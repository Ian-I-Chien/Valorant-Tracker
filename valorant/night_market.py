"""Normalize optional BonusStore data; no purchases or reveal requests.

Schema reference: https://valapidocs.techchrism.me/endpoint/storefront
The v3 response still needs verification during a live Night Market.
"""

import uuid

VP = "85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741"


def amount(value):
    return value if type(value) is int and value >= 0 else None


def parse_night_market(storefront, now):
    bonus = storefront.get("BonusStore")
    if bonus is None:
        return None
    if not isinstance(bonus, dict):
        raise ValueError("Unexpected Night Market layout")
    duration = bonus.get("BonusStoreRemainingDurationInSeconds")
    if type(duration) is not int:
        raise ValueError("Unexpected Night Market duration")
    if duration <= 0:
        return None
    offers = bonus.get("BonusStoreOffers")
    if not isinstance(offers, list) or len(offers) > 6:
        raise ValueError("Unexpected Night Market offers")
    if not offers:
        return None
    normalized = []
    for item in offers:
        offer = item["Offer"]
        rewards = offer["Rewards"]
        if len(rewards) != 1:
            raise ValueError("Unexpected Night Market rewards")
        item_id = str(uuid.UUID(rewards[0]["ItemID"]))
        discount = amount(item.get("DiscountPercent"))
        if discount is not None and discount > 100:
            discount = None
        original = amount((offer.get("Cost") or {}).get(VP))
        price = amount((item.get("DiscountCosts") or {}).get(VP))
        if original is not None and price is not None and price > original:
            raise ValueError("Unexpected Night Market prices")
        normalized.append(
            {
                "id": item_id,
                "price": price,
                "original_price": original,
                "discount_percent": discount,
            }
        )
    return {"expires": now + min(duration, 90 * 86400), "offers": normalized}


def active_night_market(data, now):
    market = data.get("night_market")
    return market if market and market["offers"] and market["expires"] > now else None
