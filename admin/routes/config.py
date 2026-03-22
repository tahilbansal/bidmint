"""
Runtime scraper configuration endpoints.

GET   /admin/config   — show current config values
PATCH /admin/config   — update one or more values at runtime (in-memory, resets on restart)
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from admin.auth import require_admin_key
from admin.config_store import get_config, update_config

router = APIRouter(prefix="/config", tags=["Admin – Config"])

_VALID_PORTALS = {"gem", "cppp", "punjab"}


class ConfigPatch(BaseModel):
    portals: Optional[List[str]] = None
    """Active scraper portals. Valid values: gem, cppp, punjab"""

    states: Optional[List[str]] = None
    """States whose tenders are accepted, e.g. ["punjab", "haryana"]"""

    min_match_score: Optional[int] = None
    """Minimum AI match score (0-100) required to send a WhatsApp alert"""

    scrape_hour: Optional[int] = None
    """Hour to run daily scrape in IST (0-23)"""

    scrape_minute: Optional[int] = None
    """Minute to run daily scrape (0-59)"""

    price_hour: Optional[int] = None
    """Hour to send mandi price digest in IST (0-23)"""

    price_minute: Optional[int] = None
    """Minute to send mandi price digest (0-59)"""

    @field_validator("portals")
    @classmethod
    def validate_portals(cls, v: List[str]) -> List[str]:
        invalid = set(v) - _VALID_PORTALS
        if invalid:
            raise ValueError(f"Invalid portal(s): {invalid}. Valid: {_VALID_PORTALS}")
        return v

    @field_validator("min_match_score")
    @classmethod
    def validate_score(cls, v: int) -> int:
        if not 0 <= v <= 100:
            raise ValueError("min_match_score must be between 0 and 100")
        return v

    @field_validator("scrape_hour", "price_hour")
    @classmethod
    def validate_hour(cls, v: int) -> int:
        if not 0 <= v <= 23:
            raise ValueError("Hour must be between 0 and 23")
        return v

    @field_validator("scrape_minute", "price_minute")
    @classmethod
    def validate_minute(cls, v: int) -> int:
        if not 0 <= v <= 59:
            raise ValueError("Minute must be between 0 and 59")
        return v


@router.get("", dependencies=[Depends(require_admin_key)])
async def show_config():
    """Return the current runtime configuration."""
    cfg = get_config()
    cfg["_note"] = (
        "Changes via PATCH /admin/config are in-memory only "
        "and will reset on the next server restart. "
        "Update the corresponding env var in Render to make them permanent."
    )
    return cfg


@router.patch("", dependencies=[Depends(require_admin_key)])
async def patch_config(body: ConfigPatch):
    """Update one or more config values at runtime."""
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    try:
        updated = update_config(patch)
        return {"status": "updated", "config": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
