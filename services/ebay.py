
import base64
import os
import requests

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"

class EbayError(RuntimeError):
    pass

def get_app_token():
    client_id = os.getenv("EBAY_CLIENT_ID")
    client_secret = os.getenv("EBAY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise EbayError("Missing EBAY_CLIENT_ID or EBAY_CLIENT_SECRET in .env")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials", "scope": SCOPE},
        timeout=20,
    )
    if not response.ok:
        raise EbayError(f"OAuth failed ({response.status_code}): {response.text[:500]}")
    return response.json()["access_token"]

def _float_or_none(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _int_or_none(value):
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None

def _money(container):
    try:
        return float((container or {}).get("value", 0) or 0)
    except (TypeError, ValueError):
        return 0.0

def search_items(token, query, min_price=None, max_price=None, limit=75):
    marketplace = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US")
    filters = []
    if min_price is not None and max_price is not None:
        filters += [f"price:[{min_price}..{max_price}]", "priceCurrency:USD"]
    elif min_price is not None:
        filters += [f"price:[{min_price}..]", "priceCurrency:USD"]
    elif max_price is not None:
        filters += [f"price:[..{max_price}]", "priceCurrency:USD"]

    params = {"q": query, "limit": min(int(limit), 200)}
    if filters:
        params["filter"] = ",".join(filters)

    response = requests.get(
        SEARCH_URL,
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace,
        },
        timeout=30,
    )
    if not response.ok:
        raise EbayError(
            f"Browse search failed ({response.status_code}): {response.text[:700]}"
        )

    output = []
    for item in response.json().get("itemSummaries", []):
        price = _money(item.get("price"))
        options = item.get("shippingOptions") or []
        shipping = _money(options[0].get("shippingCost")) if options else 0.0
        seller = item.get("seller") or {}
        output.append({
            "ebay_item_id": item.get("itemId"),
            "title": item.get("title") or "",
            "price": price,
            "shipping": shipping,
            "total_cost": round(price + shipping, 2),
            "image_url": (item.get("image") or {}).get("imageUrl"),
            "item_url": item.get("itemWebUrl"),
            "seller_username": seller.get("username"),
            "seller_feedback": _float_or_none(seller.get("feedbackPercentage")),
            "seller_feedback_count": _int_or_none(seller.get("feedbackScore")),
            "item_end_date": item.get("itemEndDate"),
        })
    return output
