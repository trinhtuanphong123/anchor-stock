"""GET /api/model/active — the parameter set the dashboard is currently serving (D-18).

Provenance, not decoration. ``docs/04`` §5 requires the active run's estimation window to be on
screen, and here the gap it exposes is real: the anchor set was estimated on one window while
the prices rendered beside it run to the collection date. This endpoint returns both ends of
that gap — the run's ``window_start``/``window_end`` and the latest session actually landed —
so the dashboard can state it rather than let a reader assume they agree.

Reads views only. Computes nothing: every figure here was frozen into the artifact by
``pipelines`` and loaded by ``pipelines/artifact/load.py``.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.db.connection import NoData, as_float, fetch_one, iso_date, iso_ts

router = APIRouter(prefix="/api/model", tags=["model"])

# v_active_model_run holds at most one row (ux_model_runs_one_active, migration 00005);
# v_latest_session holds exactly one. Reading both in a single statement rather than two is not
# premature optimisation — read_cursor() opens a fresh connection per call, so a second query
# would double this endpoint's cost against a pooler an ocean away. Composing two views is still
# "the API reads views" (D-18); the CROSS JOIN computes nothing.
_ACTIVE_RUN_SQL = """
SELECT r.run_id, r.artifact_id, r.scope, r.scope_label, r.similarity_measure,
       r.universe_version, r.index_symbol,
       r.window_start, r.window_end, r.prior_close_date,
       r.n_sessions, r.n_tickers, r.q, r.k, r.k_max, r.tau,
       r.coverage_f, r.coverage_fbar, r.n_under_tau,
       r.is_primary, r.created_at, r.loaded_at,
       s.session_date AS latest_session
  FROM v_active_model_run r
 CROSS JOIN v_latest_session s
"""

# as_float() rounds to 3 decimals by default. These columns are FRACTIONS — tau is 0.10 and
# coverage_fbar is ~0.26, close enough to the rounding step at 3 digits to matter — so every
# ratio gets an explicit width instead of the default.
_RATIO_DIGITS = 6


@router.get("/active")
def active_model_run() -> dict:
    """Return the active run's identity, estimation window and published coverage figures."""
    row = fetch_one(_ACTIVE_RUN_SQL)
    if row is None:
        # No active run. 503 rather than 404: the resource is not missing, the system is not
        # ready — nothing has been activated yet. _errors.py maps NoData to 503.
        raise NoData()

    return {
        "run_id": row["run_id"],
        "artifact_id": row["artifact_id"],
        "scope": row["scope"],
        "scope_label": row["scope_label"],
        "similarity_measure": row["similarity_measure"],
        "universe_version": row["universe_version"],
        "index_symbol": row["index_symbol"],
        # The two dates the provenance strip exists to contrast.
        "window_start": iso_date(row["window_start"]),
        "window_end": iso_date(row["window_end"]),
        "latest_session": iso_date(row["latest_session"]),
        # Outside the window by construction: T returns need T+1 closes (docs/01 §1, D-11).
        "prior_close_date": iso_date(row["prior_close_date"]),
        "n_sessions": row["n_sessions"],
        "n_tickers": row["n_tickers"],
        "q": as_float(row["q"], _RATIO_DIGITS),
        "k": row["k"],
        "k_max": row["k_max"],
        "tau": as_float(row["tau"], _RATIO_DIGITS),
        "coverage_f": as_float(row["coverage_f"], _RATIO_DIGITS),
        "coverage_fbar": as_float(row["coverage_fbar"], _RATIO_DIGITS),
        "n_under_tau": row["n_under_tau"],
        "is_primary": row["is_primary"],
        "created_at": iso_ts(row["created_at"]),
        "loaded_at": iso_ts(row["loaded_at"]),
    }
