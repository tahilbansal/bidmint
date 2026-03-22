"""
API key authentication for all /admin/* endpoints.

Set ADMIN_API_KEY in environment variables.
Pass it as a request header:  X-Admin-Key: <your-key>
"""
import os
from fastapi import Header, HTTPException, status

_ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")


async def require_admin_key(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    """FastAPI dependency — validates X-Admin-Key header on every admin request."""
    if not _ADMIN_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_KEY is not configured on this server",
        )
    if x_admin_key != _ADMIN_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key",
        )
