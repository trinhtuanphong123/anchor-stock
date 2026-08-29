"""GET /api/anchors, /api/anchors/{anchor} — the greedy selection and its groups (D-18, P9.5).

Two routes over ``v_active_anchors`` (00012, P9.0) and ``v_anchor_group_detail`` (00010). Neither
computes: the greedy algorithm ran once in ``pipelines`` and its output was frozen into the
artifact -- these routes select, order and serialise what was already decided.

``/api/anchors`` returns all ``k_max`` selection steps, not just the published ``k``. The
complete marginal-gain curve then arrives in one read and the 10-chip selector on the dashboard
becomes a filter at the display edge -- the same reasoning ``v_top_movers`` already embodies for
direction and limit: the view publishes the facts, the caller chooses the cut.

Unit contract for this module specifically: ``coverage_fbar``, ``rho2_mean``, ``rho2_min`` and
``coverage_c`` are fractions in [0, 1] (the usual ratio rule). ``marginal_gain``, ``coverage_f``
and ``f_j`` are NOT fractions -- they are sums of per-ticker coverage over a set that can exceed
1 in size, so their own magnitude is not bounded by 1 either. Rounded the same way, at the same
width, because the shape of the curve (whether it is genuinely non-increasing) matters more than
which of the two categories a given column falls into.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.db.connection import NotFound, as_float, fetch_all, fetch_one, iso_date

router = APIRouter(prefix="/api/anchors", tags=["anchors"])

_RATIO_DIGITS = 6  # coverage_fbar, rho2_mean, rho2_min, coverage_c, ret_*, dist_from_sma_200_pct,
# drawdown_from_252d_high
_GAIN_DIGITS = 6  # marginal_gain, coverage_f, f_j -- not fractions, same precision need
_VALUE_DIGITS = 2  # turnover_value
_OSC_DIGITS = 2  # rsi_14 -- bounded [0, 100], not a fraction

_ANCHOR_FIELDS = """
    step_k, anchor_ticker, position, marginal_gain, coverage_f, coverage_fbar,
    in_published_set, size, f_j, rho2_mean, rho2_min, sector_composition,
    company_name, sector
"""

_LIST_SQL = f"""
SELECT {_ANCHOR_FIELDS}
  FROM v_active_anchors
 ORDER BY step_k ASC
"""

_ANCHOR_SQL = f"""
SELECT {_ANCHOR_FIELDS}
  FROM v_active_anchors
 WHERE anchor_ticker = %s
"""

# coverage_c DESC: the strongest-covered member first. member_ticker ASC breaks ties, so the
# same data always yields the same response -- the same determinism rule greedy follows when it
# breaks ties by smallest index.
_MEMBERS_SQL = """
SELECT member_ticker, company_name, sector, position, coverage_c, is_anchor, under_tau,
       indicator_date, ret_1d, ret_5d, ret_20d, turnover_value, rsi_14,
       dist_from_sma_200_pct, drawdown_from_252d_high
  FROM v_anchor_group_detail
 WHERE anchor_ticker = %s
 ORDER BY coverage_c DESC, member_ticker ASC
"""


def _serialise_anchor(r: dict) -> dict:
    return {
        "step_k": r["step_k"],
        "anchor_ticker": r["anchor_ticker"],
        "position": r["position"],
        "company_name": r["company_name"],
        "sector": r["sector"],
        "marginal_gain": as_float(r["marginal_gain"], _GAIN_DIGITS),
        "coverage_f": as_float(r["coverage_f"], _GAIN_DIGITS),
        "coverage_fbar": as_float(r["coverage_fbar"], _RATIO_DIGITS),
        "in_published_set": r["in_published_set"],
        # NULL past the published boundary (step_k > k): model_groups has no row for an
        # unpublished step. That is the truth, not a join bug -- v_active_anchors's own
        # COMMENT ON VIEW says so.
        "size": r["size"],
        "f_j": as_float(r["f_j"], _GAIN_DIGITS),
        "rho2_mean": as_float(r["rho2_mean"], _RATIO_DIGITS),
        "rho2_min": as_float(r["rho2_min"], _RATIO_DIGITS),
        # jsonb arrives already deserialised (psycopg2's default jsonb adapter) -- passed
        # through as-is. Evidence of external validation (docs/02 §3g), never an input: sector
        # never entered the similarity matrix or the objective.
        "sector_composition": r["sector_composition"],
    }


@router.get("")
def list_anchors() -> dict:
    """Return every selection step of the active run, published or not, in selection order."""
    rows = fetch_all(_LIST_SQL)
    return {"count": len(rows), "anchors": [_serialise_anchor(r) for r in rows]}


@router.get("/{anchor}")
def anchor_detail(anchor: str) -> dict:
    """Return one anchor's own selection-step row plus its group's members.

    404 when the ticker was never selected at any step_k in the active run -- not merely
    "not one of the published k". An anchor selected but not published (step_k > k) still has a
    row here (S5), just with size/f_j/rho2_* NULL and an empty member list, since group
    membership (model_ticker_params.anchor_ticker) is only ever assigned to a published anchor.
    """
    anchor = anchor.strip().upper()
    row = fetch_one(_ANCHOR_SQL, (anchor,))
    if row is None:
        raise NotFound(f"'{anchor}' was not selected as an anchor in the active run.")

    members = fetch_all(_MEMBERS_SQL, (anchor,))

    return {
        "anchor": _serialise_anchor(row),
        "members": [
            {
                "ticker": m["member_ticker"],
                "company_name": m["company_name"],
                "sector": m["sector"],
                "position": m["position"],
                "coverage_c": as_float(m["coverage_c"], _RATIO_DIGITS),
                "is_anchor": m["is_anchor"],
                "under_tau": m["under_tau"],
                "indicator_date": iso_date(m["indicator_date"]),
                "ret_1d": as_float(m["ret_1d"], _RATIO_DIGITS),
                "ret_5d": as_float(m["ret_5d"], _RATIO_DIGITS),
                "ret_20d": as_float(m["ret_20d"], _RATIO_DIGITS),
                "turnover_value": as_float(m["turnover_value"], _VALUE_DIGITS),
                "rsi_14": as_float(m["rsi_14"], _OSC_DIGITS),
                "dist_from_sma_200_pct": as_float(m["dist_from_sma_200_pct"], _RATIO_DIGITS),
                "drawdown_from_252d_high": as_float(
                    m["drawdown_from_252d_high"], _RATIO_DIGITS
                ),
            }
            for m in members
        ],
    }
