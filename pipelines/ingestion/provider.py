"""pipelines.ingestion.provider — the ONLY module that imports vnstock.

Every other ingestion module talks to this one through :class:`RawFetch`; none of them knows
vnstock exists. That boundary is what let ``normalize.py`` and ``quality.py`` be pure and fully
testable offline, and it is what makes the facts below containable to one file.

Three facts about the installed vnstock (4.0.4), verified by direct probing rather than taken
from documentation, drive most of this module's shape:

1. **A rate limit calls ``sys.exit()``.** ``vnai/beam/quota.py`` does
   ``sys.exit(f"Rate limit exceeded. ...")`` when the account's quota is exhausted.
   ``SystemExit`` inherits from ``BaseException``, NOT ``Exception`` — verified directly: an
   ``except Exception:`` wrapped around a rate-limited call does not catch it. The old
   ``pipelines/ingestion/daily.py:222`` guard is exactly ``except Exception``, so a rate limit
   there kills the whole worker process instead of being recorded as one failed fetch. See
   :func:`_guarded`.
2. **``history(start=...)`` returns rows before ``start``.** The VCI endpoint accepts only ``to``
   and ``countBack`` (never ``from``); vnstock computes
   ``countBack = len(pandas.bdate_range(start, end)) + 1`` and never trims the result back to
   ``start``. A 2020-01-01→2025-12-31 request returned 1568 rows starting **2019-09-26** — about
   68 rows of overshoot, roughly one per Vietnamese market holiday inside the window (business
   days ≠ trading days). ``end`` IS honoured correctly. See :meth:`VnstockProvider.fetch`.
3. **The default ``source`` changed from VCI (3.x) to KBS (4.x).** Omitting ``source=`` silently
   switches provider and, empirically, changes both the row count and the timestamp shape
   returned. ``source`` is therefore a required, validated argument here — never left to the
   library's default.

A fourth fact belongs to ``docs/decisions/D-06-adjusted-close-semantics.md``, not to this module:
the returned closes ARE corporate-action-adjusted, and the adjustment re-anchors to the present
on every new corporate action. That is why ``pipelines/ingestion/fetch.py`` re-fetches the full
window every run rather than incrementing from a high-water mark.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

__all__ = [
    "DEFAULT_SOURCE",
    "DEFAULT_THROTTLE_S",
    "VALID_SOURCES",
    "MockProvider",
    "ProviderError",
    "ProviderRateLimited",
    "ProviderUnavailable",
    "RawFetch",
    "SymbolFetchError",
    "VnstockProvider",
]

#: Stored / reported form is uppercase; the vnstock API argument is lowercased at the call site.
DEFAULT_SOURCE = "VCI"

#: The sources that actually serve OHLCV history on 4.0.4 (verified against the live provider
#: registry, which is narrower than the constructor's own validation list — dnse/binance/fmarket
#: pass __init__ and then fail later, one layer down, with a different error).
VALID_SOURCES = frozenset({"VCI", "KBS", "MSN", "FMP"})

DEFAULT_THROTTLE_S = 5.0
DEFAULT_INTERVAL = "1D"


class ProviderError(RuntimeError):
    """Base for every error this module raises. Never raised directly."""


class ProviderUnavailable(ProviderError):
    """vnstock could not be imported, or died via ``sys.exit()`` during import."""


class ProviderRateLimited(ProviderError):
    """The provider's quota was exhausted (surfaced as ``sys.exit()`` or a rate-limit exception).

    A rate limit is a property of the process, account and time window — never of one symbol.
    The caller (``fetch.py``) is expected to treat this as fatal to the whole run rather than to
    one symbol: see that module's docstring for the reasoning.
    """


class SymbolFetchError(ProviderError):
    """One symbol's fetch failed for a reason specific to it. Safe to skip and continue."""


@dataclass(frozen=True)
class RawFetch:
    """One symbol's trimmed, provider-shaped rows."""

    symbol: str
    source: str
    rows: list[dict[str, Any]]  # plain Python scalars; time/open/high/low/close/volume
    requested_start: date
    requested_end: date
    rows_before_trim: int
    trimmed_leading: int
    trimmed_trailing: int
    elapsed_s: float


# ---------------------------------------------------------------------------
# Window trim — the fix for finding 2
# ---------------------------------------------------------------------------


def _row_date(row: dict[str, Any]) -> date | None:
    t = row.get("time")
    if t is None:
        return None
    if isinstance(t, date):
        return t if not isinstance(t, datetime) else t.date()
    try:
        import pandas as pd  # noqa: PLC0415

        if pd.isna(t):
            return None
        return pd.to_datetime(t).date()
    except Exception:  # noqa: BLE001
        return None


def _trim_to_window(
    rows: list[dict[str, Any]], start: date, end: date
) -> tuple[list[dict[str, Any]], int, int]:
    """Drop rows outside ``[start, end]``. Returns ``(kept, n_leading, n_trailing)``.

    Trimming here, not later, is deliberate: the overshoot is not information, it is an artifact
    of an endpoint that only accepts ``to`` + ``countBack``, and its size depends on the holiday
    count inside the window — leaving it in would make the raw store's content a function of
    something nobody asked about. Two runs with different ``--start`` values would then land
    different amounts of history under the same ``(symbol, bar_type, bar_date)`` key.
    """
    dated = [(row, _row_date(row)) for row in rows]
    n_leading = sum(1 for _, d in dated if d is not None and d < start)
    n_trailing = sum(1 for _, d in dated if d is not None and d > end)
    kept = [row for row, d in dated if d is not None and start <= d <= end]
    return kept, n_leading, n_trailing


def _to_scalar(v: Any) -> Any:
    """Unwrap a numpy/pandas scalar to a plain Python one; leave everything else untouched."""
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:  # noqa: BLE001
            return v
    return v


def _rows_from_dataframe(df: Any) -> list[dict[str, Any]]:
    records = df.to_dict(orient="records")
    return [{k: _to_scalar(v) for k, v in rec.items()} for rec in records]


# ---------------------------------------------------------------------------
# Rate-limit / retry-unwrap guard — the fix for findings 1 and the tenacity wrap
# ---------------------------------------------------------------------------

_RATE_LIMIT_MARKERS = ("ratelimitexceeded", "rate limit", "429", "quota")


def _unwrap_retry(exc: BaseException) -> BaseException:
    """``tenacity.RetryError`` -> the original exception it wraps.

    Duck-typed; does not import tenacity. ``Quote.history`` is wrapped in
    ``@retry(stop=stop_after_attempt(3), ...)``, which re-wraps any ``Exception`` subclass raised
    by the provider into a ``RetryError`` after exhausting its attempts — so ``except ValueError``
    around a call to ``history()`` may not match the ORIGINAL error type. This must run before
    any type/message inspection of ``exc``.
    """
    last_attempt = getattr(exc, "last_attempt", None)
    if last_attempt is not None and hasattr(last_attempt, "exception"):
        try:
            inner = last_attempt.exception()
        except Exception:  # noqa: BLE001
            return exc
        if inner is not None:
            return inner
    return exc


def _looks_rate_limited(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".casefold()
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def _guarded(fn: Callable[[], Any], *, symbol: str) -> Any:
    """Call ``fn()``, translating vnstock/vnai's failure modes into this module's exceptions.

    Order is load-bearing:

    1. ``SystemExit`` is caught FIRST, before the generic ``Exception`` clause — because it is a
       ``BaseException`` and an ``except Exception:`` below it would never see it. This is
       finding 1, made structurally impossible to get backwards.
    2. ``KeyboardInterrupt`` is re-raised unconditionally — an operator's Ctrl-C must never be
       reinterpreted as a symbol failure.
    3. Anything else is unwrapped past a possible ``RetryError`` before its type or message is
       inspected, then classified as a rate limit or an ordinary per-symbol failure.
    """
    try:
        return fn()
    except SystemExit as exc:
        raise ProviderRateLimited(
            f"{symbol}: vnai terminated the process (rate limit): {exc}"
        ) from exc
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001
        orig = _unwrap_retry(exc)
        if _looks_rate_limited(orig):
            raise ProviderRateLimited(f"{symbol}: {type(orig).__name__}: {orig}") from orig
        raise SymbolFetchError(f"{symbol}: {type(orig).__name__}: {orig}") from orig


# ---------------------------------------------------------------------------
# Import, once per process
# ---------------------------------------------------------------------------

_quote_cls: type | None = None


def _ensure_quote() -> type:
    """Import ``vnstock.Quote`` once. Raises :class:`ProviderUnavailable` on any failure.

    ``vnai`` (vnstock's telemetry/quota dependency) can itself call ``sys.exit()`` during its
    import-time quota check, so ``SystemExit`` is caught here too, not only inside ``fetch()``.
    Import-time stdout banners are best-effort suppressed; ``vnai`` also writes directly to file
    descriptor 1 in places ``redirect_stdout`` cannot intercept — accepted, not fixed.
    """
    global _quote_cls
    if _quote_cls is not None:
        return _quote_cls
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            from vnstock import Quote  # noqa: PLC0415
    except SystemExit as exc:
        raise ProviderUnavailable(f"vnai exited during import: {exc}") from exc
    except ImportError as exc:
        raise ProviderUnavailable(f"vnstock is not importable: {exc}") from exc
    _quote_cls = Quote
    return Quote


def available() -> bool:
    """True if vnstock can be imported right now. Never raises."""
    try:
        _ensure_quote()
    except ProviderUnavailable:
        return False
    return True


# ---------------------------------------------------------------------------
# Real provider
# ---------------------------------------------------------------------------


class VnstockProvider:
    """Fetches one symbol's daily history through vnstock, trimmed and throttled.

    ``source`` is validated at construction — a typo fails immediately, not at symbol 47 of 101
    — and is NEVER omitted from the vnstock call, because 4.0.4 silently defaults to KBS
    (finding 3) rather than the VCI the rest of this pipeline assumes.
    """

    def __init__(
        self,
        *,
        source: str = DEFAULT_SOURCE,
        throttle_s: float = DEFAULT_THROTTLE_S,
        interval: str = DEFAULT_INTERVAL,
        time_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        source_u = source.strip().upper()
        if source_u not in VALID_SOURCES:
            raise ValueError(f"unknown source {source!r}; expected one of {sorted(VALID_SOURCES)}")
        self.source = source_u
        self.throttle_s = float(throttle_s)
        self.interval = interval
        self._time_fn = time_fn
        self._sleep_fn = sleep_fn
        self._last_call: float | None = None

    def _throttle(self) -> None:
        """Sleep only as much as still needed since the last call. First call never sleeps."""
        if self._last_call is None:
            return
        wait = self.throttle_s - (self._time_fn() - self._last_call)
        if wait > 0:
            self._sleep_fn(wait)

    def fetch(self, symbol: str, start: date, end: date) -> RawFetch:
        self._throttle()
        Quote = _ensure_quote()  # noqa: N806

        def _call() -> Any:
            q = Quote(source=self.source.lower(), symbol=symbol)
            return q.history(
                symbol=symbol, start=start.isoformat(), end=end.isoformat(),
                interval=self.interval,
            )

        t0 = self._time_fn()
        df = _guarded(_call, symbol=symbol)
        elapsed = self._time_fn() - t0
        self._last_call = self._time_fn()

        rows = [] if df is None or getattr(df, "empty", False) else _rows_from_dataframe(df)
        n_before = len(rows)
        kept, n_leading, n_trailing = _trim_to_window(rows, start, end)

        return RawFetch(
            symbol=symbol, source=self.source, rows=kept,
            requested_start=start, requested_end=end,
            rows_before_trim=n_before, trimmed_leading=n_leading, trimmed_trailing=n_trailing,
            elapsed_s=elapsed,
        )


# ---------------------------------------------------------------------------
# Mock provider — same interface, no vnstock import, deterministic, fault-injectable
# ---------------------------------------------------------------------------

_TRADING_WEEKDAYS = frozenset({0, 1, 2, 3, 4})


def _weekdays(start: date, end: date) -> list[date]:
    out = []
    d = start
    one = date.resolution
    while d <= end:
        if d.weekday() in _TRADING_WEEKDAYS:
            out.append(d)
        d = d + one
    return out


@dataclass
class MockProvider:
    """Deterministic synthetic history, generated at the SAME layer as the real provider.

    Emits raw, provider-shaped rows (``time`` as an ISO string, plain OHLCV) so that
    ``--mock`` on the caller exercises normalize and quality exactly as the real path does. The
    old code's two mock generators sat at different layers — ``daily._generate_mock_bars``
    emitted already-typed records and bypassed normalize entirely, while
    ``index_bars._generate_mock_raw_rows`` emitted raw rows through the full path. This adopts
    the index layer for both bar kinds.

    ``faults`` maps a symbol to an injected defect, for testing row-level quarantine and status
    handling with no network: ``"nan_close"``, ``"zero_price"``, ``"dup_date"``, ``"no_rows"``,
    ``"overshoot"``, ``"all_bad"``, ``"rate_limit"``, ``"fetch_error"``.
    """

    source: str = DEFAULT_SOURCE
    seed: int = 20201201
    faults: dict[str, str] = field(default_factory=dict)
    base_price: dict[str, float] = field(default_factory=dict)

    def fetch(self, symbol: str, start: date, end: date) -> RawFetch:
        fault = self.faults.get(symbol)
        if fault == "rate_limit":
            raise ProviderRateLimited(f"{symbol}: injected rate limit")
        if fault == "fetch_error":
            raise SymbolFetchError(f"{symbol}: injected fetch error")
        if fault == "no_rows":
            return RawFetch(symbol, self.source, [], start, end, 0, 0, 0, 0.001)

        dates = _weekdays(start, end)
        base = self.base_price.get(symbol, 10.0 + (abs(hash((self.seed, symbol))) % 90))
        rows: list[dict[str, Any]] = []
        price = base
        for i, d in enumerate(dates):
            drift = ((abs(hash((self.seed, symbol, i))) % 2001) - 1000) / 100_000.0
            price = max(0.01, price * (1.0 + drift))
            close = round(price, 2)
            rows.append({
                "time": d.isoformat(), "open": round(close * 0.995, 2),
                "high": round(close * 1.01, 2), "low": round(close * 0.99, 2),
                "close": close, "volume": 1_000_000 + (i * 137) % 500_000,
            })

        n_before = len(rows)
        n_leading = n_trailing = 0

        if fault == "nan_close" and rows:
            rows[len(rows) // 2]["close"] = float("nan")
        elif fault == "zero_price" and rows:
            rows[len(rows) // 2]["close"] = 0.0
        elif fault == "dup_date" and len(rows) >= 2:
            rows[1] = dict(rows[0])
        elif fault == "overshoot":
            extra = [{
                "time": (start - date.resolution * (20 - k)).isoformat(),
                "open": base, "high": base, "low": base, "close": base, "volume": 1,
            } for k in range(20)]
            rows = extra + rows
            n_before = len(rows)
            kept, n_leading, n_trailing = _trim_to_window(rows, start, end)
            return RawFetch(symbol, self.source, kept, start, end,
                            n_before, n_leading, n_trailing, 0.001)
        elif fault == "all_bad":
            for r in rows:
                r["close"] = 0.0

        return RawFetch(symbol, self.source, rows, start, end,
                        n_before, n_leading, n_trailing, 0.001)


# ---------------------------------------------------------------------------
# Self-check — offline
# ---------------------------------------------------------------------------


def _selftest() -> int:  # noqa: PLR0915
    passed = 0
    failed: list[str] = []

    def check(label: str, fn) -> None:
        nonlocal passed
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed.append(label)
            print(f"  FAIL  {label}\n          {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"  PASS  {label}")

    def _trim_edges() -> None:
        rows = [
            {"time": "2024-12-20"}, {"time": "2024-12-30"},
            {"time": "2025-01-02"}, {"time": "2025-01-10"},
            {"time": "2025-02-01"},
        ]
        kept, n_lead, n_trail = _trim_to_window(rows, date(2025, 1, 1), date(2025, 1, 31))
        assert n_lead == 2, n_lead
        assert n_trail == 1, n_trail
        assert [r["time"] for r in kept] == ["2025-01-02", "2025-01-10"], kept

    check("window trim drops leading and trailing overshoot correctly", _trim_edges)

    def _systemexit_becomes_rate_limited() -> None:
        def boom():
            sys.exit("Rate limit exceeded. Process terminated.")
        try:
            _guarded(boom, symbol="VCB")
        except ProviderRateLimited:
            pass
        else:
            raise AssertionError("expected ProviderRateLimited")

    check(
        "SystemExit from the provider becomes ProviderRateLimited",
        _systemexit_becomes_rate_limited,
    )

    def _bare_except_exception_does_not_catch_it() -> None:
        # The exact regression this module exists to prevent: daily.py:222 used
        # `except Exception`, which a SystemExit sails straight past.
        def boom():
            sys.exit("Rate limit exceeded.")
        caught_as_exception = False
        try:
            boom()
        except Exception:  # noqa: BLE001
            caught_as_exception = True
        except SystemExit:
            pass
        assert caught_as_exception is False, (
            "except Exception caught a SystemExit — the regression this module guards against"
        )

    check(
        "except Exception provably does NOT catch SystemExit (the daily.py:222 bug)",
        _bare_except_exception_does_not_catch_it,
    )

    def _retry_error_unwrapped() -> None:
        class _FakeAttempt:
            def exception(self):
                return ValueError("boom from the real provider")

        class _FakeRetryError(Exception):
            last_attempt = _FakeAttempt()

        def boom():
            raise _FakeRetryError("retries exhausted")

        try:
            _guarded(boom, symbol="VCB")
        except SymbolFetchError as exc:
            assert "ValueError" in str(exc), str(exc)
            assert isinstance(exc.__cause__, ValueError), exc.__cause__
        else:
            raise AssertionError("expected SymbolFetchError")

    check(
        "RetryError is unwrapped to the original exception before classification",
        _retry_error_unwrapped,
    )

    def _keyboard_interrupt_propagates() -> None:
        def boom():
            raise KeyboardInterrupt
        try:
            _guarded(boom, symbol="VCB")
        except KeyboardInterrupt:
            return
        raise AssertionError("KeyboardInterrupt must propagate uncaught")

    check(
        "KeyboardInterrupt propagates rather than becoming a symbol failure",
        _keyboard_interrupt_propagates,
    )

    def _throttle_arithmetic() -> None:
        clock = {"t": 0.0}
        slept: list[float] = []
        p = VnstockProvider(
            source="VCI", throttle_s=5.0,
            time_fn=lambda: clock["t"], sleep_fn=lambda s: slept.append(s),
        )
        p._throttle()  # first call: no history yet
        assert slept == [], slept
        p._last_call = 0.0
        clock["t"] = 2.0
        p._throttle()
        assert slept == [3.0], slept

    check("throttle sleeps only the remaining time; first call never sleeps", _throttle_arithmetic)

    def _source_validation() -> None:
        try:
            VnstockProvider(source="tcbs")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for an invalid/removed source")
        p = VnstockProvider(source="vci")
        assert p.source == "VCI", p.source  # stored uppercase
        assert DEFAULT_SOURCE == "VCI", "default must not silently become KBS"

    check(
        "invalid source rejected at construction; stored form is uppercase VCI",
        _source_validation,
    )

    def _mock_respects_window() -> None:
        mp = MockProvider(seed=1)
        rf = mp.fetch("VCB", date(2025, 1, 1), date(2025, 1, 31))
        assert rf.rows, "expected some weekday rows in January"
        dates = [date.fromisoformat(r["time"]) for r in rf.rows]
        assert all(date(2025, 1, 1) <= d <= date(2025, 1, 31) for d in dates), dates
        assert all(d.weekday() < 5 for d in dates), dates

    check("MockProvider emits only in-window weekdays", _mock_respects_window)

    def _mock_faults() -> None:
        start, end = date(2025, 1, 1), date(2025, 1, 31)

        rf = MockProvider(faults={"NANC": "nan_close"}).fetch("NANC", start, end)
        assert any(isinstance(r["close"], float) and r["close"] != r["close"] for r in rf.rows), (
            "expected a NaN close row for the nan_close fault"
        )

        rf2 = MockProvider(faults={"MTY": "no_rows"}).fetch("MTY", start, end)
        assert rf2.rows == [], rf2.rows

        rf3 = MockProvider(faults={"OVER": "overshoot"}).fetch("OVER", start, end)
        assert rf3.trimmed_leading == 20, rf3.trimmed_leading
        assert all(date.fromisoformat(r["time"]) >= start for r in rf3.rows), rf3.rows

        try:
            MockProvider(faults={"RL": "rate_limit"}).fetch("RL", start, end)
        except ProviderRateLimited:
            pass
        else:
            raise AssertionError("expected ProviderRateLimited from the rate_limit fault")

    check("fault injection produces the documented row shapes", _mock_faults)

    def _available_is_boolean_never_raises() -> None:
        result = available()
        assert isinstance(result, bool), result

    check("available() returns a bool and never raises", _available_is_boolean_never_raises)

    print()
    if failed:
        print(f"provider selftest: {passed} passed, {len(failed)} FAILED")
        return 1
    print(f"provider selftest: {passed} passed, 0 failed")
    return 0


def _probe(symbol: str, start: date, end: date, source: str) -> int:
    """One real network call, for manual verification against the live API."""
    p = VnstockProvider(source=source, throttle_s=0.0)
    rf = p.fetch(symbol, start, end)
    print(f"symbol={rf.symbol} source={rf.source} elapsed={rf.elapsed_s:.2f}s")
    print(f"requested: [{rf.requested_start} .. {rf.requested_end}]")
    print(f"rows_before_trim={rf.rows_before_trim} trimmed_leading={rf.trimmed_leading} "
          f"trimmed_trailing={rf.trimmed_trailing} kept={len(rf.rows)}")
    if rf.rows:
        print(f"first={rf.rows[0]}")
        print(f"last={rf.rows[-1]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.ingestion.provider",
        description="vnstock coupling point; --selftest is offline, --probe hits the real API.",
    )
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--probe", metavar="SYMBOL", default=None)
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end", default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    args = parser.parse_args(argv)

    if args.probe:
        if not args.start or not args.end:
            parser.error("--probe requires --start and --end")
        return _probe(
            args.probe, date.fromisoformat(args.start), date.fromisoformat(args.end), args.source
        )
    if not args.selftest:
        parser.error("pass --selftest (offline) or --probe SYMBOL --start .. --end .. (live)")
    return _selftest()


if __name__ == "__main__":
    sys.exit(main())
