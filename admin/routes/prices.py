"""
On-demand mandi price fetch — GET /admin/prices

Hits AGMARKNET / data.gov.in live and returns the latest available prices.
Typically takes 30-60 seconds due to the slow government API.
"""
from fastapi import APIRouter, Depends

from admin.auth import require_admin_key

router = APIRouter(prefix="/prices", tags=["Admin – Prices"])


@router.get("", dependencies=[Depends(require_admin_key)])
async def get_live_prices():
    """
    Fetch latest AGMARKNET mandi prices on demand.
    Data typically lags 1-2 days behind the current date.
    """
    from scraper.agmarknet import fetch_punjab_prices
    prices = await fetch_punjab_prices()
    return {
        "source": "AGMARKNET via data.gov.in",
        "note": "Data typically lags 1-2 days. Prices are in INR per quintal.",
        "commodities_returned": len(prices),
        "prices": prices,
    }
