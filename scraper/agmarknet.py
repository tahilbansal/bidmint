"""
AGMARKNET Mandi Price Fetcher
Fetches daily agricultural commodity prices from data.gov.in API.
Source: AGMARKNET (Agricultural Marketing Network) — Government of India
"""
import asyncio
import httpx
from datetime import datetime, timedelta

# data.gov.in API endpoint for daily mandi prices
AGMARKNET_API_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
AGMARKNET_API_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"  # Public open data key

# Punjab mandis to prioritise when multiple records returned
PUNJAB_MANDIS = [
    "Patiala", "Ludhiana", "Amritsar", "Jalandhar",
    "Bathinda", "Chandigarh", "Mohali", "Khanna",
]

# If Punjab has no data for a commodity (e.g. Wheat is sold via FCI/MSP, not open auctions)
# fall back to geographically-adjacent states for a market reference price.
_FALLBACK_STATES = ["Punjab", "Haryana", "Uttar Pradesh", "Rajasthan", "Madhya Pradesh"]

# Commodity name mapping for AGMARKNET
COMMODITY_MAP = {
    "rice": "Rice",
    "wheat": "Wheat",
    "pulses": "Moong Dal (Whole)",
    "oils": "Mustard",
    "sugar": "Sugar",
    "dairy": "Ghee",
    "spices": "Turmeric",
}


async def _get_latest_available_date(client: httpx.AsyncClient) -> str:
    """
    AGMARKNET data typically lags 1-3 days behind the current date.
    Probe the API (no date filter) to find the most recent date that has data.
    """
    try:
        resp = await client.get(
            AGMARKNET_API_URL,
            params={"api-key": AGMARKNET_API_KEY, "format": "json", "limit": 1,
                    "filters[state]": "Punjab"},
        )
        resp.raise_for_status()
        records = resp.json().get("records", [])
        if records:
            return records[0]["arrival_date"]
    except Exception:
        pass
    # Fallback: yesterday
    return (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")


async def fetch_punjab_prices() -> dict:
    """
    Fetch latest mandi prices for key commodities from AGMARKNET.
    Tries Punjab state first; falls back to nearby states when Punjab has no data.
    Returns dict keyed by category with modal price and change from previous day.

    Example return:
    {
        "rice": {"modal": 3200, "min": 3000, "max": 3400, "change": 50, "mandi": "Patiala"},
        "wheat": {"modal": 2450, "min": 2300, "max": 2600, "change": -20, "mandi": "Ambala (Haryana)"},
    }
    """
    prices = {}
    # Limit concurrent API calls — data.gov.in throttles when all 14 fire at once
    sem = asyncio.Semaphore(4)

    async with httpx.AsyncClient(timeout=40) as client:
        # Discover the most recent date AGMARKNET has data for
        latest_date_str = await _get_latest_available_date(client)
        try:
            latest_date = datetime.strptime(latest_date_str, "%d/%m/%Y")
        except ValueError:
            latest_date = datetime.now() - timedelta(days=1)
        prev_date_str = (latest_date - timedelta(days=1)).strftime("%d/%m/%Y")

        # Fetch all commodities in parallel (rate-limited by semaphore)
        categories = list(COMMODITY_MAP.keys())
        today_tasks = [
            _fetch_commodity_price(client, COMMODITY_MAP[c], latest_date_str, sem)
            for c in categories
        ]
        prev_tasks = [
            _fetch_commodity_price(client, COMMODITY_MAP[c], prev_date_str, sem)
            for c in categories
        ]
        today_results = await asyncio.gather(*today_tasks, return_exceptions=True)
        prev_results = await asyncio.gather(*prev_tasks, return_exceptions=True)

        for category, today_price, yesterday_price in zip(categories, today_results, prev_results):
            if isinstance(today_price, Exception) or not today_price:
                continue
            change = 0
            if isinstance(yesterday_price, dict) and yesterday_price.get("modal"):
                change = today_price["modal"] - yesterday_price["modal"]
            prices[category] = {
                "modal": today_price["modal"],
                "min": today_price.get("min", 0),
                "max": today_price.get("max", 0),
                "change": change,
                "mandi": today_price.get("mandi", "Punjab"),
            }

    return prices


async def _fetch_commodity_price(
    client: httpx.AsyncClient,
    commodity: str,
    date: str,
    sem: asyncio.Semaphore,
) -> dict | None:
    """
    Fetch price for a single commodity on a given date.
    Iterates _FALLBACK_STATES until a record is found, so Wheat (absent from Punjab
    open mandis) will be sourced from Haryana or UP instead.
    """
    for state in _FALLBACK_STATES:
        params = {
            "api-key": AGMARKNET_API_KEY,
            "format": "json",
            "limit": 10,
            "filters[commodity]": commodity,
            "filters[state]": state,
            "filters[arrival_date]": date,
        }
        try:
            async with sem:
                resp = await client.get(AGMARKNET_API_URL, params=params)
            resp.raise_for_status()
            records = resp.json().get("records", [])
            if not records:
                continue

            # For Punjab, prefer known mandi names
            if state == "Punjab":
                for mandi_name in PUNJAB_MANDIS:
                    for record in records:
                        if mandi_name.lower() in record.get("market", "").lower():
                            return {
                                "modal": float(record.get("modal_price", 0)),
                                "min": float(record.get("min_price", 0)),
                                "max": float(record.get("max_price", 0)),
                                "mandi": record.get("market", mandi_name),
                            }

            # Use first available record from this state
            record = records[0]
            label = record.get("market", state)
            if state != "Punjab":
                label = f"{label} ({state})"
            return {
                "modal": float(record.get("modal_price", 0)),
                "min": float(record.get("min_price", 0)),
                "max": float(record.get("max_price", 0)),
                "mandi": label,
            }

        except httpx.TimeoutException:
            continue  # silently skip — API is slow, try next state
        except Exception as e:
            print(f"AGMARKNET API error for {commodity}/{state}: {e}")
            continue

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
