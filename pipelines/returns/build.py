"""pipelines.returns.build — build & persist log-return series (anchor model).

Reads the raw bars and writes the derived log-return series the factor model
consumes:

    daily_bars        → daily_returns   x_{i,t} = ln(P_t / P_{t-1}) + flags
    market_index_bars → index_returns   f_t     = ln(I_t / I_{t-1})

This is the algorithm-specific data prep, kept separate from the dashboard feature
set. It does NOT assemble the aligned X / f matrix — that is done per run for a
given universe + window by the factor-model step. Here we persist the per-series
returns (universe-independent), idempotently, so runs read them by (ticker, date).

Leakage / honesty
-----------------
Each return uses only the current and previous session's close (right-edge). The
first session of a series has no return and is not stored. at_limit / zero_volume
are recorded, never used to exclude (spec 01-data-pipeline §1.4).

Environment variables (live mode only)
---------------------------------------
    DATABASE_URL  Supabase Postgres connection string (never logged).
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pipelines.common.returns import (
    DEFAULT_LIMIT_BAND,
    compute_index_return_rows,
    compute_return_rows,
)

logger = logging.getLogger(__name__)

SOURCE: str = "VCI"
DEFAULT_INDEX_SYMBOL: str = "VNINDEX"
MOCK_DEFAULT_TICKERS: list[str] = ["VCB", "FPT", "HPG"]

# Mock series depth (trading days) per series.
_MOCK_DEPTH: int = 40


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class BuildReturnsResult:
    """Aggregate outcome of one returns-build run."""

    tickers_attempted: int = 0
    tickers_succeeded: int = 0
    tickers_failed: int = 0
    index_symbols_attempted: int = 0
    index_symbols_succeeded: int = 0
    ticker_return_rows: int = 0     # rows written/validated for daily_returns
    index_return_rows: int = 0      # rows written/validated for index_returns
    at_limit_count: int = 0
    zero_volume_count: int = 0
    live: bool = True               # False in mock mode (no DB writes)
    errors: list[str] = field(default_factory=list)

    @property
    def overall_status(self) -> str:
        if self.tickers_attempted > 0 and self.tickers_failed == self.tickers_attempted:
            return "failed"
        return "succeeded"


# ---------------------------------------------------------------------------
# Mock generator
# ---------------------------------------------------------------------------


def _mock_series(seed: int, base: float, depth: int) -> list[tuple[date, float, float]]:
    """Deterministic synthetic (date, close, volume) walk ending today."""
    rng = random.Random(seed)
    today = date.today()
    dates = [today - timedelta(days=depth - 1 - i) for i in range(depth)]
    out: list[tuple[date, float, float]] = []
    level = base
    for d in dates:
        level *= 1.0 + rng.gauss(0.0005, 0.012)
        vol = 0.0 if rng.random() < 0.05 else round(max(0.0, rng.gauss(1_000_000, 250_000)), 0)
        out.append((d, round(level, 2), vol))
    return out


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_build_returns(
    tickers: list[str],
    index_symbols: list[str],
    start_date: date | None = None,
    end_date: date | None = None,
    mock: bool = False,
    pipeline_run_id: int | None = None,  # noqa: ARG001 - accepted for parity
    band: float = DEFAULT_LIMIT_BAND,
    reader: Any = None,
    writer: Any = None,
) -> BuildReturnsResult:
    """Compute and (live) persist log returns for tickers + index symbols.

    ``reader`` / ``writer`` are a :class:`~pipelines.storage.ports.BarSource` and
    :class:`~pipelines.storage.ports.BarSink`; ``None`` resolves them from ``$DATN_STORAGE``
    (local by default). They are named reader/writer rather than source/sink because ``source``
    already means the provider column written into every record here.

    Mock: synthetic bars, no storage at all. Mock data is *generated*, not *read*, so it is
    deliberately not routed through a third backend — that would conflate "where does this come
    from" with "where does it go", and make ``--mock`` require a writable data root.
    """
    result = BuildReturnsResult(
        tickers_attempted=len(tickers),
        index_symbols_attempted=len(index_symbols),
        live=not mock,
    )
    computed_at = datetime.now(UTC)

    if not mock:
        from pipelines.storage.factory import make_sink, make_source  # noqa: PLC0415

        reader = reader if reader is not None else make_source()
        writer = writer if writer is not None else make_sink()

    # ---- equity returns ----
    for i, ticker in enumerate(tickers):
        try:
            if mock:
                bars = _mock_series(seed=1000 + i, base=10.0 + i, depth=_MOCK_DEPTH)
            else:
                bars = reader.daily_bars(ticker, start_date, end_date, source=SOURCE)
        except Exception as exc:  # noqa: BLE001
            result.tickers_failed += 1
            result.errors.append(f"{ticker}: load failed: {type(exc).__name__}")
            continue

        rows = compute_return_rows(bars, band=band)
        for r in rows:
            r.update({"ticker": ticker, "source": SOURCE, "computed_at": computed_at})
        result.at_limit_count += sum(1 for r in rows if r["at_limit"])
        result.zero_volume_count += sum(1 for r in rows if r["zero_volume"])

        if not mock and rows:
            try:
                writer.write_daily_returns(rows)
            except Exception as exc:  # noqa: BLE001
                result.tickers_failed += 1
                result.errors.append(f"{ticker}: write failed: {type(exc).__name__}")
                continue

        result.ticker_return_rows += len(rows)
        result.tickers_succeeded += 1
        logger.info("[%s] %d return rows.", ticker, len(rows))

    # ---- index returns ----
    for j, sym in enumerate(index_symbols):
        try:
            if mock:
                synth = _mock_series(seed=9000 + j, base=1200.0, depth=_MOCK_DEPTH)
                mbars = [(d, c) for (d, c, _v) in synth]
            else:
                mbars = reader.index_bars(sym, start_date, end_date, source=SOURCE)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"{sym}: index load failed: {type(exc).__name__}")
            continue

        irows = compute_index_return_rows(mbars)
        for r in irows:
            r.update({"index_symbol": sym, "source": SOURCE, "computed_at": computed_at})

        if not mock and irows:
            try:
                writer.write_index_returns(irows)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{sym}: index write failed: {type(exc).__name__}")
                continue

        result.index_return_rows += len(irows)
        result.index_symbols_succeeded += 1
        logger.info("[%s] %d index return rows.", sym, len(irows))

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resolve_tickers(arg_tickers: str | None, mock: bool) -> list[str]:
    """Explicit ``--tickers`` first, else ``list_stocks.txt``. Never a silent database fallback.

    The mock branch comes first so ``--mock`` never requires the universe file to exist.

    Note what changed: explicitly-passed tickers are now sorted, deduplicated and validated, so
    a typo raises instead of quietly fetching a symbol that does not exist — and column order
    becomes a property of the ticker *set* rather than of the argument string, which is what the
    greedy tie-break downstream depends on.
    """
    if mock and not arg_tickers:
        return list(MOCK_DEFAULT_TICKERS)

    from pipelines.universe.file import resolve_universe  # noqa: PLC0415

    return list(resolve_universe(arg_tickers).tickers)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.returns.build",
        description=(
            "Build & persist log-return series (daily_returns + index_returns) from "
            "daily_bars + market_index_bars. Anchor-model data prep."
        ),
    )
    parser.add_argument("--mock", action="store_true", help="Synthetic data; no DB.")
    parser.add_argument("--once", action="store_true", help="Run once (default; accepted).")
    parser.add_argument("--tickers", type=str, default=None, metavar="LIST",
                        help="Comma/space tickers. Default: mock set, or active universe (live).")
    parser.add_argument("--index", type=str, default=DEFAULT_INDEX_SYMBOL, metavar="SYM",
                        help=f"Comma-separated index symbols (default {DEFAULT_INDEX_SYMBOL}).")
    parser.add_argument("--start", type=str, default=None, metavar="YYYY-MM-DD",
                        help="Start date (inclusive). Default: full history.")
    parser.add_argument("--end", type=str, default=None, metavar="YYYY-MM-DD",
                        help="End date (inclusive). Default: through latest.")
    args = parser.parse_args()

    def _parse(s: str | None) -> date | None:
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except ValueError:
            logger.error("Invalid date %r (expected YYYY-MM-DD).", s)
            sys.exit(2)

    tickers = _resolve_tickers(args.tickers, args.mock)
    index_symbols = [s.strip().upper() for s in args.index.replace(",", " ").split() if s.strip()]

    logger.info("=== build_returns starting (tickers=%d index=%s mock=%s) ===",
                len(tickers), index_symbols, args.mock)
    result = run_build_returns(
        tickers, index_symbols, start_date=_parse(args.start), end_date=_parse(args.end),
        mock=args.mock,
    )
    logger.info(
        "build_returns %s — tickers=%d/%d ticker_rows=%d | index=%d/%d index_rows=%d "
        "| at_limit=%d zero_volume=%d live=%s",
        result.overall_status, result.tickers_succeeded, result.tickers_attempted,
        result.ticker_return_rows, result.index_symbols_succeeded,
        result.index_symbols_attempted, result.index_return_rows,
        result.at_limit_count, result.zero_volume_count, result.live,
    )
    sys.exit(0 if result.overall_status == "succeeded" else 1)


if __name__ == "__main__":
    main()
