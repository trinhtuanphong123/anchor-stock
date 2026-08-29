"""pipelines.common.logging — pipeline_runs DB logger with stdout fallback.

Provides :func:`log_run` which writes a job execution record to the
``pipeline_runs`` table.  When the DB is absent or the table does not exist
for any reason, the record is printed to stdout only and the caller continues
normally — the worker never crashes due to a missing DB.

Usage::

    from pipelines.common.logging import log_run

    log_run("daily_features", "succeeded",
            started_at=t0, ended_at=t1)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

# Use a private name to avoid shadowing the stdlib ``logging`` module for
# callers who import this module's namespace.
_logger = logging.getLogger(__name__)


def log_run(
    job_name: str,
    status: str,
    trigger: str = "scheduled",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record a pipeline job execution to ``pipeline_runs``, or stdout if unavailable.

    Args:
        job_name:      Job identifier (e.g. ``'universe_sync'``).
        status:        ``'started'`` | ``'succeeded'`` | ``'failed'`` | ``'skipped'``.
        trigger:       ``'scheduled'`` | ``'manual'``.
        started_at:    Job start time (UTC).  Defaults to ``now()`` when ``None``.
        ended_at:      Job completion time (UTC).  ``None`` while in progress.
        error_message: Brief exception summary for failed jobs.
                       Never a raw traceback or a connection string.
        metadata:      Optional counts / identifiers (must be JSON-serialisable).
    """
    if started_at is None:
        started_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Attempt DB insert into pipeline_runs
    # ------------------------------------------------------------------
    try:
        from pipelines.common.db import cursor  # noqa: PLC0415

        meta_json = json.dumps(metadata) if metadata else None
        with cursor() as cur:
            cur.execute(
                """
                INSERT INTO pipeline_runs
                    (job_name, status, trigger, started_at, ended_at,
                     error_message, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    job_name,
                    status,
                    trigger,
                    started_at,
                    ended_at,
                    error_message,
                    meta_json,
                ),
            )
        return  # DB write succeeded
    except Exception:  # noqa: BLE001
        pass  # Fall through to stdout logging

    # ------------------------------------------------------------------
    # Stdout fallback — DB absent, pipeline_runs not yet created, or
    # table schema not yet applied.  Worker continues normally.
    # ------------------------------------------------------------------
    ended_str = ended_at.isoformat() if ended_at else "-"
    _logger.info(
        "[mock-db] pipeline_runs | job=%-40s status=%-10s trigger=%-10s "
        "started=%s ended=%s error=%s",
        job_name,
        status,
        trigger,
        started_at.isoformat(),
        ended_str,
        error_message or "-",
    )
