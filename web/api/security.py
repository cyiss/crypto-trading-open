"""
API security helpers.

This module centralizes simple API key authentication for state-changing
endpoints in the dashboard.
"""

import os

from fastapi import Header, HTTPException


DEFAULT_INTERNAL_DASHBOARD_API_KEY = "internal-grid-ops-6f9b2d4e91c84a6d"


async def require_api_key(x_api_key: str | None = Header(default=None)):
    """Require API key for write operations.

    The server must be configured with DASHBOARD_API_KEY.
    Clients send the key via `X-API-Key` header.
    """
    expected = os.getenv("DASHBOARD_API_KEY", DEFAULT_INTERNAL_DASHBOARD_API_KEY).strip()

    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
