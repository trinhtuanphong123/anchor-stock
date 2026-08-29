"""services.api.app.db.ping — lightweight read-only DB connectivity probe.

Exposes a single function:

    ping(url: str) -> Literal["ok", "error"]

Designed to be called from an async context via asyncio.to_thread so that
the synchronous psycopg2 call never blocks the FastAPI event loop.

Security contract:
- The connection URL is never logged or surfaced in any return value.
- Exception details are discarded; only the signal string is returned.
- No writes, no schema operations, no data reads beyond SELECT 1.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 3  # seconds; keeps health checks fast


def ping(url: str) -> str:
    """Open a psycopg2 connection, run SELECT 1, close, return "ok" or "error".

    Args:
        url: A PostgreSQL connection URL.  Never logged or re-raised.

    Returns:
        ``"ok"`` if the database accepted the connection and returned a row.
        ``"error"`` for any failure (wrong credentials, unreachable host, etc.).
    """
    try:
        import psycopg2  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("psycopg2 not installed — database ping unavailable")
        return "error"

    conn = None
    try:
        conn = psycopg2.connect(url, connect_timeout=_CONNECT_TIMEOUT)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return "ok"
    except Exception:  # noqa: BLE001
        # Swallow all details — never surface URL, credentials, or stack trace.
        logger.debug("DB ping failed (details suppressed for security)")
        return "error"
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
