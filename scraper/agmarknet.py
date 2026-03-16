"""
AGMARKNET Mandi Price Fetcher
Fetches daily agricultural commodity prices from data.gov.in API.
Source: AGMARKNET (Agricultural Marketing Network) — Government of India
"""
import httpx
from datetime import datetime, timedelta

# data.gov.in API endpoint for daily mandi prices
AGMARKNET_API_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
AGMARKNET_API_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"  # Public open data key

# Punjab mandis to track
PUNJAB_MANDIS = [
    "Patiala", "Ludhiana", "Amritsar", "Jalandhar",
    "Bathinda", "Chandigarh", "Mohali", "Khanna",
]

# Commodity name mapping for AGMARKNET
COMMODITY_MAP = {
    "rice": "Rice",
    "wheat": "Wheat",
    "pulses": "Moong Dal (Whole)",
    "oils": "Mustard Oil",
    "sugar": "Sugar",
    "dairy": "Ghee",
    "spices": "Turmeric",
}


async def fetch_punjab_prices() -> dict:
    """
    Fetch today's mandi prices for key commodities in Punjab.
    Returns dict keyed by category with modal price and change from yesterday.

    Example return:
    {
        "rice": {"modal": 3200, "min": 3000, "max": 3400, "change": 50, "mandi": "Patiala"},
        "wheat": {"modal": 2450, "min": 2300, "max": 2600, "change": -20, "mandi": "Ludhiana"},
    }
    """
    prices = {}
    today = datetime.now().strftime("%d/%m/%Y")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")

    async with httpx.AsyncClient(timeout=20) as client:
        for category, commodity_name in COMMODITY_MAP.items():
            try:
                # Fetch today's prices
                today_price = await _fetch_commodity_price(
                    client, commodity_name, today
                )
                # Fetch yesterday's for comparison
                yesterday_price = await _fetch_commodity_price(
                    client, commodity_name, yesterday
                )

                if today_price:
                    change = 0
                    if yesterday_price and yesterday_price.get("modal"):
                        change = today_price["modal"] - yesterday_price["modal"]

                    prices[category] = {
                        "modal": today_price["modal"],
                        "min": today_price.get("min", 0),
                        "max": today_price.get("max", 0),
                        "change": change,
                        "mandi": today_price.get("mandi", "Punjab"),
                    }
            except Exception as e:
                print(f"Price fetch error for {category}: {e}")
                continue

    return prices


async def _fetch_commodity_price(
    client: httpx.AsyncClient,
    commodity: str,
    date: str
) -> dict | None:
    """Fetch price for a single commodity on a given date from AGMARKNET."""
    params = {
        "api-key": AGMARKNET_API_KEY,
        "format": "json",
        "limit": 10,
        "filters[commodity]": commodity,
        "filters[state]": "Punjab",
        "filters[arrival_date]": date,
    }

    try:
        resp = await client.get(AGMARKNET_API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        records = data.get("records", [])
        if not records:
            return None

        # Find best record from Punjab mandis
        for mandi_name in PUNJAB_MANDIS:
            for record in records:
                if mandi_name.lower() in record.get("market", "").lower():
                    return {
                        "modal": float(record.get("modal_price", 0)),
                        "min": float(record.get("min_price", 0)),
                        "max": float(record.get("max_price", 0)),
                        "mandi": record.get("market", mandi_name),
                    }

        # Fallback: use first Punjab record
        for record in records:
            if "punjab" in record.get("state", "").lower():
                return {
                    "modal": float(record.get("modal_price", 0)),
                    "min": float(record.get("min_price", 0)),
                    "max": float(record.get("max_price", 0)),
                    "mandi": record.get("market", "Punjab"),
                }

        return None

    except Exception as e:
        print(f"AGMARKNET API error for {commodity}: {e}")
        return None


if __name__ == "__main__":
    import asyncio

    async def main():
        prices = await fetch_punjab_prices()
        print("\nToday's Punjab Mandi Prices:")
        for cat, p in prices.items():
            change = p["change"]
            arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
            print(f"  {cat.title():10s}: ₹{p['modal']}/quintal {arrow} ({change:+.0f}) @ {p['mandi']}")

    asyncio.run(main())
