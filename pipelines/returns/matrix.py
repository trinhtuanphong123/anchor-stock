"""pipelines.returns.matrix — assemble the aligned return matrix X and factor f.

The alignment step (spec 01-data-pipeline §1.4): from the persisted per-series log
returns (daily_returns + index_returns), build a rectangular

    X ∈ ℝ^{T×N}   column j = ticker j's log-return series
    f ∈ ℝ^{T}     the market-index log-return series

restricted to the sessions where the index AND **every** ticker in the set have a
return — so X has no missing cells and needs no imputation. This is what the factor
model (§2) consumes for a given ticker set + window.

Determinism
-----------
Tickers are ordered ascending by symbol and dates ascending. This fixed order is
what makes the downstream greedy anchor selection reproducible (its tie-break is
smallest index, which depends on column order).

Honesty (§1.4)
--------------
Nothing is silently omitted. A ticker missing **any** session of the window —
whether it has zero overlap with the index calendar or merely incomplete overlap —
is excluded from the matrix entirely and recorded in ``AlignmentReport.dropped_tickers``
with a reason. The alternative, keeping a partially-covered ticker and letting it drag
the *whole* matrix down to its own shortest coverage, is what silently cost 2021 all but
18 of its 250 sessions before this fix: one late 2021 listing (20 sessions) shrank T for
every other ticker in the set. Dropping the ticker instead means every other column keeps
its full T; the loss is attributed to the one column that caused it, not smeared across
all of them. See ``AlignmentReport`` below for the full audit trail this produces.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

SOURCE: str = "VCI"


# ---------------------------------------------------------------------------
# AlignmentReport — the honesty artefact for one window's alignment
# ---------------------------------------------------------------------------


@dataclass
class AlignmentReport:
    """What one call to :func:`assemble_matrix` actually did, and why.

    Written to JSON (``to_json``) so the evidence behind "nothing was silently omitted"
    survives past the log line that produced it — the same role
    :class:`~pipelines.ingestion.fetch.FetchReport` plays for P2's collection.
    """

    window_start: date | None       # requested window, not necessarily a trading day
    window_end: date | None
    index_symbol: str
    source: str
    universe_path: str
    universe_version: str
    n_index_sessions: int           # sessions on the index's own calendar in the window
    T: int                          # sessions actually in X (rows)
    N: int                          # tickers actually in X (columns)
    q: float                        # N / T
    first_session: date | None      # actual X bounds, not the requested window
    last_session: date | None
    prior_close_date: date | None   # session immediately before window_start (D-11)
    tickers_kept: list[str] = field(default_factory=list)
    #: [{ticker, n_sessions, coverage, reason}], reason ∈ {"no_overlap", "incomplete"}
    dropped_tickers: list[dict[str, Any]] = field(default_factory=list)
    #: [{date, missing_tickers}] — should be empty given the drop rule above; kept as an
    #: explicit, checkable "zero" rather than an absent field.
    dropped_sessions: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def assert_ready_for_run(self) -> None:
        """Raise unless this alignment can feed the factor model (spec 01 §1 preconditions)."""
        if self.N == 0:
            raise ValueError("alignment produced N=0 tickers — nothing to fit")
        if self.T == 0:
            raise ValueError("alignment produced T=0 sessions — nothing to fit")
        if self.prior_close_date is None:
            raise ValueError(
                "no session found before window_start — the first in-window return would "
                "have no prior close (D-11); check the collection start date"
            )

    def assert_full_coverage(self, expected_tickers: Sequence[str]) -> None:
        """Raise if any of ``expected_tickers`` was dropped this window.

        For a frozen universe (D-12, ``list_stocks_research.txt``) a drop here means the
        file's premise — every listed ticker has full coverage in every research year — no
        longer holds against the data actually collected. That has to fail loudly rather than
        silently shrink N, or the whole point of freezing the universe (five years sharing one
        N and one q) breaks without anyone noticing.
        """
        dropped = {d["ticker"] for d in self.dropped_tickers}
        violating = sorted(set(expected_tickers) & dropped)
        if violating:
            raise ValueError(
                f"frozen-universe assumption violated — {len(violating)} ticker(s) dropped "
                f"this window despite being expected to have full coverage: {violating}. "
                "Re-run python -m pipelines.universe.file --derive-research-universe."
            )


@dataclass
class ReturnMatrix:
    """Aligned return matrix for one ticker set + window."""

    tickers: list[str]              # ordered, length N (columns of X)
    dates: list[date]               # ordered ascending, length T (rows of X)
    X: np.ndarray                   # shape (T, N)
    f: np.ndarray                   # shape (T,)
    report: AlignmentReport

    @property
    def n_tickers(self) -> int:
        return len(self.tickers)

    @property
    def n_sessions(self) -> int:
        return len(self.dates)

    def assert_rectangular(self) -> None:
        """Assert the shapes and that there are no missing cells (spec §2 pre-check)."""
        T, N = self.n_sessions, self.n_tickers
        assert self.X.shape == (T, N), f"X shape {self.X.shape} != ({T}, {N})"
        assert self.f.shape == (T,), f"f shape {self.f.shape} != ({T},)"
        assert np.all(np.isfinite(self.X)), "X contains non-finite values"
        assert np.all(np.isfinite(self.f)), "f contains non-finite values"


def assemble_matrix(
    index_returns: dict[date, float],
    ticker_returns: dict[str, dict[date, float]],
    *,
    window_start: date | None = None,
    window_end: date | None = None,
    index_symbol: str = "VNINDEX",
    source: str = SOURCE,
    universe_path: str = "<unknown>",
    universe_version: str = "<unknown>",
    prior_close_date: date | None = None,
) -> ReturnMatrix:
    """Assemble X, f from loaded per-series return dicts (pure; no I/O).

    ``index_returns``  : {date: f_t}.
    ``ticker_returns`` : {ticker: {date: x_{i,t}}}.

    Session set = index dates ∩ (dates of every *fully-covered* ticker). A ticker covering
    fewer than every index session — whether zero or merely incomplete — is excluded rather
    than allowed to shrink T for the tickers that do have full coverage. Given that rule, the
    remaining intersection is always the index's own session set; ``dropped_sessions`` in the
    returned report is therefore an explicit audit trail, not a mechanism that is expected to
    fire in normal operation. Columns follow sorted ticker order, rows follow sorted dates.

    The keyword-only metadata (``window_start``, ``universe_path``, ``prior_close_date``, …)
    has no effect on X or f — it only populates :class:`AlignmentReport` for the caller to
    inspect or persist. Omit it (as ``--mock`` does) when only the matrix itself matters.
    """
    all_tickers = sorted(ticker_returns)
    index_dates = set(index_returns)
    n_index = len(index_dates)

    kept: list[str] = []
    dropped: list[dict[str, Any]] = []
    for t in all_tickers:
        t_dates = set(ticker_returns[t])
        overlap = index_dates & t_dates
        coverage = (len(overlap) / n_index) if n_index else 0.0
        if n_index and len(overlap) == n_index:
            kept.append(t)
        else:
            reason = "no_overlap" if not overlap else "incomplete"
            dropped.append({
                "ticker": t,
                "n_sessions": len(overlap),
                "coverage": round(coverage, 4),
                "reason": reason,
            })

    common: set[date] = set(index_dates)
    for t in kept:
        common &= set(ticker_returns[t])
    dates = sorted(common)

    T, N = len(dates), len(kept)
    X = np.empty((T, N), dtype=float)
    for j, t in enumerate(kept):
        col = ticker_returns[t]
        for i, d in enumerate(dates):
            X[i, j] = col[d]
    if T:
        f = np.array([index_returns[d] for d in dates], dtype=float)
    else:
        f = np.empty((0,), dtype=float)

    dropped_session_dates = sorted(index_dates - common)
    dropped_sessions = [
        {
            "date": d,
            "missing_tickers": sorted(t for t in kept if d not in ticker_returns[t]),
        }
        for d in dropped_session_dates
    ]

    if dropped:
        logger.warning("assemble_matrix: %d ticker(s) dropped for incomplete coverage: %s",
                       len(dropped), [d["ticker"] for d in dropped][:20])
    if dropped_sessions:
        logger.warning("assemble_matrix: %d index session(s) still lost despite the drop rule.",
                       len(dropped_sessions))
    logger.info("assemble_matrix: T=%d sessions × N=%d tickers.", T, N)

    report = AlignmentReport(
        window_start=window_start,
        window_end=window_end,
        index_symbol=index_symbol,
        source=source,
        universe_path=universe_path,
        universe_version=universe_version,
        n_index_sessions=n_index,
        T=T,
        N=N,
        q=round(N / T, 4) if T else 0.0,
        first_session=dates[0] if dates else None,
        last_session=dates[-1] if dates else None,
        prior_close_date=prior_close_date,
        tickers_kept=list(kept),
        dropped_tickers=dropped,
        dropped_sessions=dropped_sessions,
    )

    return ReturnMatrix(tickers=kept, dates=dates, X=X, f=f, report=report)


# ---------------------------------------------------------------------------
# Loader — storage-agnostic
# ---------------------------------------------------------------------------


def _find_prior_close_date(
    reader: Any, index_symbol: str, window_start: date, source: str
) -> date | None:
    """Latest index session strictly before ``window_start`` (D-11's prior close).

    Bounded to a 45-day lookback — comfortably more than the longest HOSE holiday break —
    rather than an unbounded scan from the start of the table.
    """
    lookback_start = window_start - timedelta(days=45)
    bars = reader.index_bars(
        index_symbol, lookback_start, window_start - timedelta(days=1), source=source
    )
    return bars[-1][0] if bars else None


def load_return_matrix(
    tickers: list[str],
    index_symbol: str,
    start: date | None = None,
    end: date | None = None,
    source: str = SOURCE,
    reader: Any = None,
    universe_path: str = "<unknown>",
    universe_version: str = "<unknown>",
) -> ReturnMatrix:
    """Load the return series over the window from any backend, then assemble X, f.

    ``reader`` is a :class:`~pipelines.storage.ports.BarSource`; ``None`` resolves one from
    ``$DATN_STORAGE`` (local by default). It is named ``reader`` rather than ``source`` because
    ``source`` already means the data provider column in this module.

    The pre-seed below is deliberate and stays *here* rather than in the source: a ticker that
    was asked for and returned nothing must survive as an empty dict so ``assemble_matrix``
    reports it in ``dropped_tickers``. A ticker that silently vanished from the result would
    shrink N without explanation, which is exactly the kind of unexplained loss the alignment
    report exists to prevent.

    ``prior_close_date`` (D-11) is looked up here, once, via one bounded ``index_bars`` call —
    it needs I/O the pure :func:`assemble_matrix` deliberately does not do.
    """
    if reader is None:
        from pipelines.storage.factory import make_source  # noqa: PLC0415

        reader = make_source()

    ticker_returns: dict[str, dict[date, float]] = {t: {} for t in tickers}
    ticker_returns.update(reader.daily_returns(tickers, start, end, source=source))
    index_returns = reader.index_returns(index_symbol, start, end, source=source)

    prior_close_date = (
        _find_prior_close_date(reader, index_symbol, start, source) if start is not None
        else None
    )

    return assemble_matrix(
        index_returns,
        ticker_returns,
        window_start=start,
        window_end=end,
        index_symbol=index_symbol,
        source=source,
        universe_path=universe_path,
        universe_version=universe_version,
        prior_close_date=prior_close_date,
    )


# ---------------------------------------------------------------------------
# Mock + CLI
# ---------------------------------------------------------------------------


def _mock_matrix(n_tickers: int = 4, n_days: int = 30) -> ReturnMatrix:
    """Synthetic returns with one deliberately-incomplete ticker to exercise alignment."""
    import random  # noqa: PLC0415

    dates = [date.today() - timedelta(days=n_days - 1 - i) for i in range(n_days)]
    tickers = [f"T{k:02d}" for k in range(n_tickers)]
    ticker_returns: dict[str, dict[date, float]] = {}
    for k, t in enumerate(tickers):
        rng = random.Random(100 + k)
        series: dict[date, float] = {}
        for i, d in enumerate(dates):
            if k == 0 and i == n_days // 2:      # drop one session for T00
                continue
            series[d] = rng.gauss(0.0, 0.02)
        ticker_returns[t] = series
    rng = random.Random(999)
    index_returns = {d: rng.gauss(0.0, 0.01) for d in dates}
    return assemble_matrix(
        index_returns, ticker_returns,
        window_start=dates[0], window_end=dates[-1],
        universe_path="<mock>", universe_version="<mock>",
        prior_close_date=dates[0] - timedelta(days=1),
    )


def repo_relative_path(path: Any) -> str:
    """``path`` relative to ``REPO_ROOT`` as a POSIX string, or its basename if outside the repo.

    ``AlignmentReport.universe_path`` is embedded verbatim into every artifact (P4) and
    content-hashed into ``artifact_id`` — an absolute path here would make the id depend on
    which machine produced it, silently breaking the reproducibility claim the hash exists to
    make. POSIX separators keep the value identical across Windows and POSIX checkouts.
    """
    from pathlib import Path  # noqa: PLC0415

    from pipelines.common.paths import REPO_ROOT  # noqa: PLC0415

    p = Path(path).resolve()
    try:
        return p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return p.name


def _run_window(window_year: int, universe_arg: str | None, index_symbol: str,
                 report_arg: str | None, strict: bool) -> None:
    """Live path: assemble one research-year window and write the AlignmentReport to disk."""
    from pathlib import Path  # noqa: PLC0415

    from pipelines.common.paths import (  # noqa: PLC0415
        RESEARCH_UNIVERSE_FILE,
        ensure_dir,
        research_dir,
    )
    from pipelines.universe.file import resolve_universe  # noqa: PLC0415

    universe_file = Path(universe_arg) if universe_arg else RESEARCH_UNIVERSE_FILE
    uf = resolve_universe(None, universe_file)
    start, end = date(window_year, 1, 1), date(window_year, 12, 31)

    m = load_return_matrix(
        list(uf.tickers), index_symbol, start=start, end=end, source=SOURCE,
        universe_path=repo_relative_path(uf.path), universe_version=uf.version,
    )
    m.report.assert_ready_for_run()
    if strict:
        m.report.assert_full_coverage(uf.tickers)
    m.assert_rectangular()

    report_path = (
        Path(report_arg) if report_arg else research_dir() / f"alignment_{start}_{end}.json"
    )
    ensure_dir(report_path.parent)
    report_path.write_text(m.report.to_json(), encoding="utf-8")

    print(f"window    : {start} .. {end}")
    print(f"universe  : {uf.n} tickers ({uf.path})  version={uf.version}")
    print(f"T={m.report.T}  N={m.report.N}  q={m.report.q}  "
          f"dropped_tickers={len(m.report.dropped_tickers)}  "
          f"dropped_sessions={len(m.report.dropped_sessions)}")
    print(f"prior_close_date: {m.report.prior_close_date}")
    print(f"report written  : {report_path}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        prog="python -m pipelines.returns.matrix",
        description="Assemble/inspect the aligned return matrix X, f.",
    )
    parser.add_argument("--mock", action="store_true", help="Build a synthetic matrix and check.")
    parser.add_argument("--window", type=int, default=None, metavar="YEAR",
                        help="Live: assemble the YYYY-01-01..YYYY-12-31 research window.")
    parser.add_argument("--universe", type=str, default=None, metavar="PATH",
                        help="Universe file for --window (default: list_stocks_research.txt).")
    parser.add_argument("--index", type=str, default="VNINDEX", metavar="SYM")
    parser.add_argument("--report", type=str, default=None, metavar="PATH",
                        help="Write the AlignmentReport as JSON "
                             "(default: data/research/alignment_<start>_<end>.json).")
    parser.add_argument("--no-strict", action="store_true",
                        help="For --window: don't raise if a frozen-universe ticker was "
                             "dropped (default is to raise — see assert_full_coverage).")
    args = parser.parse_args()

    if args.mock:
        m = _mock_matrix()
        m.assert_rectangular()
        print(f"tickers (N={m.n_tickers}): {m.tickers}")
        print(f"sessions T={m.n_sessions}")
        print(m.report.to_json())
        print(f"X shape={m.X.shape}  f shape={m.f.shape}  finite={bool(np.all(np.isfinite(m.X)))}")
        assert m.report.dropped_tickers and m.report.dropped_tickers[0]["reason"] == "incomplete", (
            "mock fixture should exercise the incomplete-coverage drop path"
        )
        assert m.report.dropped_sessions == [], (
            "an excluded ticker must not cost the remaining tickers any session"
        )
        print("assert_rectangular + mock alignment checks: OK")
        return

    if args.window is not None:
        _run_window(args.window, args.universe, args.index, args.report,
                   strict=not args.no_strict)
        return

    parser.error("pass --mock or --window YEAR")


if __name__ == "__main__":
    main()
