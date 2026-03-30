"""
Runtime configuration store for the BidMint scraper.

Values are initialised from environment variables on startup.
Updates via PATCH /admin/config are in-memory only and reset on restart.
To make a change permanent, update the corresponding env var in Render / .env.
"""
import os
from typing import Any

_config: dict[str, Any] = {
    # Which portals to scrape — comma-separated subset of: gem, cppp, punjab, haryana
    "portals": [p.strip() for p in os.getenv("ACTIVE_PORTALS", "gem,cppp,punjab,haryana").split(",")],

    # States whose tenders are accepted (used by filter)
    "states": [s.strip() for s in os.getenv("ACTIVE_STATES", "punjab,haryana,delhi,himachal,j&k,jammu").split(",")],

    # Minimum AI match score (0-100) to send a WhatsApp alert
    "min_match_score": int(os.getenv("MIN_MATCH_SCORE", "70")),

    # Daily scrape schedule — IST (Asia/Kolkata)
    "scrape_hour": int(os.getenv("SCRAPE_HOUR", "6")),
    "scrape_minute": int(os.getenv("SCRAPE_MINUTE", "30")),

    # Mandi prices digest schedule — IST
    "price_hour": int(os.getenv("PRICE_HOUR", "8")),
    "price_minute": int(os.getenv("PRICE_MINUTE", "0")),
}

_ALLOWED_KEYS = set(_config.keys())


def get_config() -> dict[str, Any]:
    """Return a snapshot of the current runtime config."""
    return dict(_config)


def update_config(patch: dict[str, Any]) -> dict[str, Any]:
    """
    Apply a partial update to the runtime config.
    Raises ValueError for unknown keys.
    Returns the full updated config.
    """
    unknown = set(patch.keys()) - _ALLOWED_KEYS
    if unknown:
        raise ValueError(f"Unknown config key(s): {', '.join(sorted(unknown))}")
    _config.update(patch)
    return dict(_config)
