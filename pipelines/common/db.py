"""pipelines.common.db - Database connection helper and schema file checker.

Connection helper
-----------------
Reads DATABASE_URL from the environment only.  Never hard-codes credentials.
Load .env before importing if running outside the scheduler::

    from dotenv import load_dotenv; load_dotenv()
    from pipelines.common.db import get_connection, cursor

Schema checker
--------------
Run with::

    python -m pipelines.common.db --check-schema-files
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from collections.abc import Generator
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


def get_connection():
    """Return an open psycopg2 connection using DATABASE_URL from the environment.

    The caller is responsible for closing the connection (or use the
    ``cursor`` context manager, which handles that automatically).

    Raises:
        RuntimeError: DATABASE_URL is not set.
        ImportError:  psycopg2 is not installed.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Add it to .env or export it in the shell before running pipelines."
        )
    try:
        import psycopg2  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "psycopg2 is required for DB access. "
            "Install with: pip install psycopg2-binary"
        ) from exc
    return psycopg2.connect(url)


@contextlib.contextmanager
def cursor() -> Generator:  # type: ignore[type-arg]
    """Context manager that yields a psycopg2 cursor inside a transaction.

    Commits on clean exit; rolls back and re-raises on any exception.
    Always closes the connection on exit.::

        with cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()
    """
    conn = get_connection()
    try:
        with conn:  # auto-commit / rollback
            with conn.cursor() as cur:
                yield cur
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Path to migrations directory (relative to repo root)
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"

# Required table names that must appear in at least one migration.
# Grouped by the baseline migration that creates them. Superseded pre-anchor migrations live
# in migrations/_archive/ and are deliberately NOT scanned — glob("*.sql") is non-recursive.
REQUIRED_TABLES = [
    # 00001_reference
    "stocks",
    "universe_snapshots",
    "universe_members",
    "trading_calendar",
    # 00002_market_data
    "ohlc_raw",
    "daily_bars",
    "market_index_bars",
    # 00003_returns
    "daily_returns",
    "index_returns",
    # 00004_indicators
    "technical_indicators_daily",
    # 00005_model_artifact
    "model_runs",
    "model_universe",
    "model_ticker_params",
    "model_anchors",
    "model_similarity_anchor",
    "model_similarity_full",
    "model_groups",
    # 00006_research
    "stability_studies",
    "anchor_frequency",
    "cross_year_eval",
    "measure_comparison",
    # 00007_live_monitors
    "live_residuals",
    "live_rolling_similarity",
    "live_coverage_monitor",
    "live_beta_drift",
    # 00008_operational
    "pipeline_runs",
    "data_quality_reports",
]

# ---------------------------------------------------------------------------
# Schema checker
# ---------------------------------------------------------------------------


def check_schema_files() -> bool:
    """Verify migration files exist and contain required table names.

    Returns True if all checks pass, False otherwise.
    """
    logger.info("Schema file check starting")
    logger.info("Migrations directory: %s", MIGRATIONS_DIR)

    # 1. Check migrations directory exists
    if not MIGRATIONS_DIR.is_dir():
        logger.error("Migrations directory does not exist: %s", MIGRATIONS_DIR)
        return False

    # 2. Find .sql migration files
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        logger.error("No .sql migration files found in %s", MIGRATIONS_DIR)
        return False

    logger.info("Found %d migration file(s):", len(sql_files))
    for f in sql_files:
        logger.info("  %s (%d bytes)", f.name, f.stat().st_size)

    # 3. Concatenate all migration SQL
    all_sql = ""
    for f in sql_files:
        all_sql += f.read_text(encoding="utf-8").lower() + "\n"

    # 4. Check each required table name appears
    missing: list[str] = []
    found: list[str] = []
    for table in REQUIRED_TABLES:
        # Look for CREATE TABLE ... <table_name>
        if table.lower() in all_sql:
            found.append(table)
        else:
            missing.append(table)

    logger.info("")
    logger.info("Required tables: %d", len(REQUIRED_TABLES))
    logger.info("Found:           %d", len(found))

    if found:
        for t in found:
            logger.info("  [OK]   %s", t)

    if missing:
        logger.error("Missing: %d", len(missing))
        for t in missing:
            logger.error("  [MISS] %s", t)
        return False

    logger.info("")
    logger.info("All required tables found in migration files.")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for python -m pipelines.common.db."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    if "--check-schema-files" in sys.argv:
        ok = check_schema_files()
        if ok:
            logger.info("Schema check PASSED.")
            sys.exit(0)
        else:
            logger.error("Schema check FAILED.")
            sys.exit(1)
    else:
        logger.info("Usage: python -m pipelines.common.db --check-schema-files")
        sys.exit(0)


if __name__ == "__main__":
    main()
