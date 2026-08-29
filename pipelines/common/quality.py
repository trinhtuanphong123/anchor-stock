"""pipelines.common.quality — shared data-quality reporting utilities.

Provides write_dqr() for recording check results to data_quality_reports,
usable from ingestion, feature computation, and any other pipeline stage.

Convention for report_scope values
-----------------------------------
Ingestion:  "daily_ohlcv:ticker:<TICKER>",  "daily_ohlcv:run"
Index:      "index_bars:<SYMBOL>",          "index_bars:run"
Alignment:  "alignment:<run_label>"          — sessions/tickers dropped assembling X and f
Artifact:   "artifact:<artifact_id>"         — validation results on write or load

The UNIQUE constraint on (report_scope, ref_date, check_name, pipeline_run_id)
is satisfied as long as each job run uses distinct scope strings and a single
pipeline_run_id per run.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def write_dqr(
    pipeline_run_id: int | None,
    report_scope: str,
    ref_date: date | None,
    check_name: str,
    passed: bool,
    severity: str,
    details: dict[str, Any],
) -> None:
    """Write one quality-check row to data_quality_reports.

    Silently no-ops when the DB is unavailable (DATABASE_URL not set,
    DB unreachable, or table missing). Never logs connection strings or secrets.

    Args:
        pipeline_run_id:  FK into pipeline_runs.id; None when unavailable.
        report_scope:     Scope string identifying what was checked.
        ref_date:         Trading date the check applies to.
        check_name:       Identifier for the type of check (e.g., "sanity_bounds").
        passed:           True = check OK; False = check failed or warned.
        severity:         "info" | "warning" | "error" — informational severity.
        details:          JSON-serialisable dict with check specifics.
    """
    try:
        from pipelines.common.db import cursor  # noqa: PLC0415

        with cursor() as cur:
            cur.execute(
                """
                INSERT INTO data_quality_reports
                    (pipeline_run_id, report_scope, ref_date,
                     check_name, passed, severity, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    pipeline_run_id,
                    report_scope,
                    ref_date,
                    check_name,
                    passed,
                    severity,
                    json.dumps(details, default=str),
                ),
            )
        logger.debug(
            "DQR written: scope=%s check=%s passed=%s", report_scope, check_name, passed
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "data_quality_reports write skipped (scope=%s check=%s): %s",
            report_scope,
            check_name,
            exc,
        )
