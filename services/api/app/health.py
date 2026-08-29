"""GET /health — liveness / readiness probe.

Response contract (HTTP 200 always when the process is alive):

    {
        "status":   "ok",
        "service":  "anchor-model-api",
        "database": "ok" | "unconfigured" | "error",
        "time":     "2026-06-29T03:00:00Z"
    }

Security rules:
- Never exposes DATABASE_URL, secrets, stack traces, or infrastructure details.
- database = "unconfigured" when DATABASE_URL is absent (no crash, no 500).
- database = "ok"           when a live SELECT 1 succeeded.
- database = "error"        when DATABASE_URL is set but the ping failed.

The synchronous psycopg2 ping runs via asyncio.to_thread so it never
blocks the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter

from app.config import settings
from app.db.ping import ping

router = APIRouter(tags=["operational"])


@router.get("/health", include_in_schema=True)
async def health_check() -> dict:
    """Return service liveness and database connectivity signal."""
    database = await _database_signal()
    return {
        "status": "ok",
        "service": settings.service_name,
        "database": database,
        "time": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


async def _database_signal() -> str:
    """Return the database connectivity signal without blocking the event loop.

    - ``"unconfigured"`` — DATABASE_URL not set; service starts normally.
    - ``"ok"``           — SELECT 1 succeeded.
    - ``"error"``        — DATABASE_URL is set but the ping failed.
    """
    url = settings.database_url
    if not url:
        return "unconfigured"
    return await asyncio.to_thread(ping, url)
