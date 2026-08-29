"""pipelines.storage.pg — the Postgres implementation of the storage ports.

``PostgresSink`` delegates to :mod:`pipelines.common.upsert` **verbatim**. It adds no SQL of its
own, so the ``ON CONFLICT`` behaviour the local sink replicates has exactly one definition. If a
column is added there, this file does not change — and ``localfs.py --selftest`` fails until the
contract tables in ``ports.py`` are updated to match.

``PostgresSource`` absorbs the SELECTs that were previously scattered across
``returns/build.py``, ``returns/matrix.py``, ``ingestion/staging.py``, ``common/hwm.py`` and
``ingestion/index_bars.py``. Two behaviours changed on the way in, deliberately:

**Every windowed read now filters on ``source``.** The previous ``_load_ticker_bars`` and
``_load_index_bars`` did not, even though ``(ticker, bar_date, source)`` is the primary key. A
second source landing the same dates would interleave, and ``compute_return_rows`` would take
``prev_close`` from a *different price series* — producing a log return that is finite, plausibly
sized, and invisible to every check downstream. ``source`` is a required keyword here so the
omission cannot recur.

**High-water-mark lookups no longer swallow exceptions.** Four separate ``MAX(bar_date)`` helpers
used to catch everything and return ``None``, which the callers read as "no data yet" and
answered with a full lookback. That is not graceful degradation: a one-second database blip would
turn an incremental run into a multi-year refetch of every symbol against a throttled provider.
``None`` now means one thing — no rows — and a failure raises. Retry policy belongs to the
caller, which is the only layer that knows whether the run can continue.

No connection is opened at import or at construction: :func:`pipelines.common.db.cursor` is
imported inside each method body. That property is what makes the DB-free ``--selftest`` below
possible, so it is load-bearing rather than stylistic — do not lift these imports to module level.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from typing import Any

from pipelines.common.upsert import (
    upsert_daily_bars,
    upsert_daily_returns,
    upsert_index_returns,
    upsert_market_index_bars,
    upsert_ohlc_raw,
    upsert_technical_indicators,
)
from pipelines.storage.ports import FLOAT_COLS, PARTITION_COL, RECORD_KEYS, Dataset, require_source

__all__ = ["PostgresSink", "PostgresSource"]


def _f(v: Any) -> float | None:
    """Coerce a Postgres ``numeric`` (psycopg2 gives ``Decimal``) to ``float | None``.

    The single conversion point for the whole backend. See the ``BarSource`` contract for why the
    conversion runs toward float rather than the other way.
    """
    return None if v is None else float(v)


def _window(
    col: str, clauses: list[str], params: list[Any], start: date | None, end: date | None
) -> tuple[list[str], list[Any]]:
    """Append inclusive date bounds to a WHERE clause list. ``None`` means unbounded."""
    if start is not None:
        clauses.append(f"{col} >= %s")
        params.append(start)
    if end is not None:
        clauses.append(f"{col} <= %s")
        params.append(end)
    return clauses, params


# ---------------------------------------------------------------------------
# Sink
# ---------------------------------------------------------------------------


class PostgresSink:
    """Postgres :class:`~pipelines.storage.ports.BarSink`. Pure delegation, by design."""

    def write_raw_bars(self, records: list[dict[str, Any]]) -> int:
        return upsert_ohlc_raw(records)

    def write_daily_bars(self, records: list[dict[str, Any]]) -> int:
        return upsert_daily_bars(records)

    def write_index_bars(self, records: list[dict[str, Any]]) -> int:
        return upsert_market_index_bars(records)

    def write_daily_returns(self, records: list[dict[str, Any]]) -> int:
        return upsert_daily_returns(records)

    def write_index_returns(self, records: list[dict[str, Any]]) -> int:
        return upsert_index_returns(records)

    def write_indicators(self, records: list[dict[str, Any]]) -> int:
        return upsert_technical_indicators(records)


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


class PostgresSource:
    """Postgres :class:`~pipelines.storage.ports.BarSource`."""

    def daily_bars(
        self, ticker: str, start: date | None, end: date | None, *, source: str
    ) -> list[tuple[date, float | None, float | None]]:
        from pipelines.common.db import cursor  # noqa: PLC0415

        clauses, params = _window(
            "bar_date", ["ticker = %s", "source = %s"], [ticker, source], start, end
        )
        sql = (
            "SELECT bar_date, close, volume FROM daily_bars WHERE "
            + " AND ".join(clauses)
            + " ORDER BY bar_date ASC"
        )
        with cursor() as cur:
            cur.execute(sql, params)
            return [(r[0], _f(r[1]), _f(r[2])) for r in cur.fetchall()]

    def index_bars(
        self, index_symbol: str, start: date | None, end: date | None, *, source: str
    ) -> list[tuple[date, float | None]]:
        from pipelines.common.db import cursor  # noqa: PLC0415

        clauses, params = _window(
            "bar_date", ["index_symbol = %s", "source = %s"], [index_symbol, source], start, end
        )
        sql = (
            "SELECT bar_date, close FROM market_index_bars WHERE "
            + " AND ".join(clauses)
            + " ORDER BY bar_date ASC"
        )
        with cursor() as cur:
            cur.execute(sql, params)
            return [(r[0], _f(r[1])) for r in cur.fetchall()]

    def daily_returns(
        self, tickers: Sequence[str], start: date | None, end: date | None, *, source: str
    ) -> dict[str, dict[date, float]]:
        from pipelines.common.db import cursor  # noqa: PLC0415

        if not tickers:
            return {}
        clauses, params = _window(
            "bar_date", ["ticker = ANY(%s)", "source = %s"], [list(tickers), source], start, end
        )
        sql = (
            "SELECT ticker, bar_date, log_return FROM daily_returns WHERE " + " AND ".join(clauses)
        )
        out: dict[str, dict[date, float]] = {}
        with cursor() as cur:
            cur.execute(sql, params)
            for tk, d, lr in cur.fetchall():
                out.setdefault(tk, {})[d] = float(lr)
        return out

    def index_returns(
        self, index_symbol: str, start: date | None, end: date | None, *, source: str
    ) -> dict[date, float]:
        from pipelines.common.db import cursor  # noqa: PLC0415

        clauses, params = _window(
            "bar_date", ["index_symbol = %s", "source = %s"], [index_symbol, source], start, end
        )
        sql = "SELECT bar_date, log_return FROM index_returns WHERE " + " AND ".join(clauses)
        with cursor() as cur:
            cur.execute(sql, params)
            return {d: float(lr) for d, lr in cur.fetchall()}

    def read_records(
        self, dataset: Dataset, key: str,
        start: date | None = None, end: date | None = None, *, source: str,
    ) -> list[dict[str, Any]]:
        """Full record dicts, exactly ``RECORD_KEYS[dataset]`` — see the ``BarSource`` Protocol.

        Typed datasets only (``require_source`` rejects a raw one, since raw has no ``source``
        column to filter on and is already served by :meth:`raw_bars`).
        """
        require_source(dataset, source)
        from pipelines.common.db import cursor  # noqa: PLC0415

        part_col = PARTITION_COL[dataset]
        cols = RECORD_KEYS[dataset]
        clauses, params = _window(
            "bar_date", [f"{part_col} = %s", "source = %s"], [key, source], start, end
        )
        sql = (
            f"SELECT {', '.join(cols)} FROM {dataset.table} WHERE "
            + " AND ".join(clauses)
            + " ORDER BY bar_date ASC"
        )
        with cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            rec = dict(zip(cols, row, strict=True))
            for c in FLOAT_COLS:
                if c in rec:
                    rec[c] = _f(rec[c])
            out.append(rec)
        return out

    def raw_bars(
        self, dataset: Dataset, symbol: str, since: date | None = None, until: date | None = None
    ) -> list[tuple[date, dict[str, Any]]]:
        from pipelines.common.db import cursor  # noqa: PLC0415

        if not dataset.is_raw:
            raise ValueError(f"raw_bars() needs a raw dataset, got {dataset.value}")
        clauses, params = _window(
            "bar_date",
            ["symbol = %s", "bar_type = %s"],
            [symbol, dataset.bar_type],
            since,
            until,
        )
        sql = (
            "SELECT bar_date, payload FROM staging.ohlc_raw WHERE "
            + " AND ".join(clauses)
            + " ORDER BY bar_date ASC"
        )
        out: list[tuple[date, dict[str, Any]]] = []
        with cursor() as cur:
            cur.execute(sql, params)
            for bar_date, payload in cur.fetchall():
                # psycopg2 decodes jsonb to a dict already. A non-dict here means the audit row
                # is corrupt, and skipping it would leave a hole in the return series that is
                # indistinguishable from a market holiday — so it raises.
                if not isinstance(payload, dict):
                    raise ValueError(
                        f"raw payload for {symbol} on {bar_date} is "
                        f"{type(payload).__name__}, expected dict"
                    )
                out.append((bar_date, payload))
        return out

    def high_water_marks(
        self, dataset: Dataset, keys: Sequence[str], *, source: str | None = None
    ) -> dict[str, date | None]:
        from pipelines.common.db import cursor  # noqa: PLC0415

        require_source(dataset, source)
        out: dict[str, date | None] = {k: None for k in keys}
        if not keys:
            return out

        key_col = PARTITION_COL[dataset]
        clauses = [f"{key_col} = ANY(%s)"]
        params: list[Any] = [list(keys)]
        if dataset.is_raw:
            clauses.append("bar_type = %s")
            params.append(dataset.bar_type)
        else:
            clauses.append("source = %s")
            params.append(source)

        # The table and key column come from a closed enum, never from caller input, so the
        # interpolation below has no injection surface. Every value is still a bound parameter.
        sql = (
            f"SELECT {key_col}, MAX(bar_date) FROM {dataset.table} WHERE "
            + " AND ".join(clauses)
            + f" GROUP BY {key_col}"
        )
        with cursor() as cur:
            cur.execute(sql, params)
            for key, hwm in cur.fetchall():
                if key in out:
                    out[key] = hwm
        return out


# ---------------------------------------------------------------------------
# Self-check — no database, no network
# ---------------------------------------------------------------------------


class _RecordingCursor:
    """Stands in for a psycopg2 cursor, recording statements and replaying canned rows."""

    def __init__(self, log: list[tuple[Any, Any]], queue: list[list[tuple]]) -> None:
        self.log = log
        self.queue = queue

    def execute(self, sql: Any, params: Any = None) -> None:
        self.log.append((sql, params))

    def fetchall(self) -> list[tuple]:
        return self.queue.pop(0) if self.queue else []

    def fetchone(self) -> tuple | None:
        rows = self.fetchall()
        return rows[0] if rows else None

    def __enter__(self) -> _RecordingCursor:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


def _selftest() -> int:  # noqa: PLR0915 - a linear checklist
    import contextlib
    from datetime import UTC, datetime
    from decimal import Decimal

    from pipelines.common import db as db_mod
    from pipelines.common import upsert as U
    from pipelines.storage.ports import BarSink, BarSource

    log: list[tuple[Any, Any]] = []
    queue: list[list[tuple]] = []

    @contextlib.contextmanager
    def fake_cursor():
        yield _RecordingCursor(log, queue)

    real_cursor = db_mod.cursor
    db_mod.cursor = fake_cursor  # type: ignore[assignment]

    # execute_values does its own mogrify/paginate/execute dance against a real psycopg2
    # cursor's C-level parameter binding, which _RecordingCursor cannot emulate. The sink's
    # actual promise — the same SQL object, the same record dicts, no copy or mutation — is
    # checked one layer up instead, by recording the call to execute_values itself rather than
    # its effect on a cursor.
    real_execute_values = U.execute_values
    ev_log: list[tuple[Any, Any, Any, Any]] = []

    def fake_execute_values(cur, sql, records, template=None, page_size=100, fetch=False):  # noqa: ANN001, ARG001
        ev_log.append((sql, records, template, page_size))

    U.execute_values = fake_execute_values  # type: ignore[assignment]

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

    try:
        sink, src = PostgresSink(), PostgresSource()

        check(
            "PostgresSink/PostgresSource satisfy the Protocols",
            lambda: (
                _assert(isinstance(sink, BarSink), "sink"),
                _assert(isinstance(src, BarSource), "source"),
            ),
        )

        check(
            "construction opened no connection",
            lambda: _assert(not log, f"statements ran at construction: {log}"),
        )

        # The sink must hand the caller's dicts, unmodified, to the exact SQL object in
        # upsert.py — identity, not string equality, so a copied-and-edited constant fails.
        # It must also page at 500 — the whole point of P15's B1.
        def _verbatim() -> None:
            ev_log.clear()
            ts = datetime(2025, 1, 2, tzinfo=UTC)
            rec = {
                "ticker": "VCB", "bar_date": date(2025, 1, 2), "source": "VCI",
                "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0,
                "is_adjusted": False, "ingested_at": ts, "updated_at": ts,
            }
            n = sink.write_daily_bars([rec])
            _assert(n == 1, f"returned {n}")
            sql, records, template, page_size = ev_log[-1]
            _assert(sql is U._DAILY_BARS_SQL, "sink used SQL that is not upsert.py's constant")
            _assert(template is U._DAILY_BARS_TEMPLATE,
                    "sink used a template that is not upsert.py's constant")
            _assert(records[0] is rec, "sink copied or mutated the record dict")
            _assert(page_size == 500, f"page_size={page_size}, expected 500")

        check("sink delegates verbatim to upsert.py's own SQL object, batched at 500", _verbatim)

        def _empty_noop() -> None:
            log.clear()
            ev_log.clear()
            for fn in (sink.write_raw_bars, sink.write_daily_bars, sink.write_index_bars,
                       sink.write_daily_returns, sink.write_index_returns,
                       sink.write_indicators):
                _assert(fn([]) == 0, f"{fn.__name__} on empty input")
            _assert(not log and not ev_log, f"empty input still executed: {log} {ev_log}")

        check("empty input is a no-op that opens nothing", _empty_noop)

        def _decimal_to_float() -> None:
            log.clear()
            queue.append([(date(2025, 1, 2), Decimal("12.3400"), Decimal("1000000"))])
            got = src.daily_bars("VCB", None, None, source="VCI")
            _assert(got == [(date(2025, 1, 2), 12.34, 1000000.0)], f"{got}")
            _, c, v = got[0]
            _assert(type(c) is float and type(v) is float, "Decimal leaked through")

        check("Decimal becomes float at the read boundary", _decimal_to_float)

        # The regression guard for the missing-source-filter bug.
        def _source_filter() -> None:
            log.clear()
            queue.extend([[], [], [], []])
            src.daily_bars("VCB", None, None, source="VCI")
            src.index_bars("VNINDEX", None, None, source="VCI")
            src.daily_returns(["VCB"], None, None, source="VCI")
            src.index_returns("VNINDEX", None, None, source="VCI")
            for sql, params in log:
                _assert("source = %s" in sql, f"no source filter in: {sql}")
                _assert("VCI" in params, f"source value not bound in: {params}")

        check("every typed read filters on source", _source_filter)

        def _window_bounds() -> None:
            log.clear()
            queue.append([])
            src.daily_bars("VCB", date(2025, 1, 1), date(2025, 12, 31), source="VCI")
            sql, params = log[-1]
            _assert("bar_date >= %s" in sql and "bar_date <= %s" in sql, sql)
            _assert(params == ["VCB", "VCI", date(2025, 1, 1), date(2025, 12, 31)], f"{params}")

        check("date bounds are inclusive and bound as parameters", _window_bounds)

        def _hwm() -> None:
            log.clear()
            queue.append([("VCB", date(2025, 1, 3))])
            got = src.high_water_marks(Dataset.DAILY_BARS, ["VCB", "NOSUCH"], source="VCI")
            _assert(got == {"VCB": date(2025, 1, 3), "NOSUCH": None}, f"{got}")
            sql, params = log[-1]
            _assert("MAX(bar_date)" in sql and "GROUP BY ticker" in sql, sql)
            _assert("source = %s" in sql, sql)

            log.clear()
            queue.append([("VCB", date(2025, 1, 3))])
            src.high_water_marks(Dataset.RAW_EQUITY, ["VCB"])
            sql, params = log[-1]
            _assert("staging.ohlc_raw" in sql, sql)
            _assert("bar_type = %s" in sql and "source" not in sql, sql)
            _assert("EQUITY" in params, f"{params}")

        check("one batched HWM query per dataset, pre-seeded, correctly keyed", _hwm)

        def _source_validation() -> None:
            _assert_raises(
                lambda: src.high_water_marks(Dataset.RAW_EQUITY, ["VCB"], source="VCI"),
                ValueError, "source on a raw dataset",
            )
            _assert_raises(
                lambda: src.high_water_marks(Dataset.DAILY_BARS, ["VCB"]),
                ValueError, "missing source on a typed dataset",
            )

        check("source/dataset mismatch raises rather than silently ignoring", _source_validation)

        # read_records: full record, Decimal->float on exactly FLOAT_COLS, keys == RECORD_KEYS
        # in order (P6.4 — this is what the Postgres mirror and artifact.inspect --from-db
        # round-trip a whole row through).
        def _read_records() -> None:
            log.clear()
            ts = datetime(2025, 1, 2, tzinfo=UTC)
            queue.append([(
                "VCB", date(2025, 1, 2), "VCI", Decimal("90.0"), Decimal("91.5"),
                Decimal("89.5"), Decimal("90.5"), Decimal("1000000"), False, ts, ts,
            )])
            recs = src.read_records(Dataset.DAILY_BARS, "VCB", source="VCI")
            _assert(len(recs) == 1, f"{recs}")
            rec = recs[0]
            _assert(tuple(rec.keys()) == RECORD_KEYS[Dataset.DAILY_BARS],
                    f"{rec.keys()} != {RECORD_KEYS[Dataset.DAILY_BARS]}")
            _assert(type(rec["close"]) is float and rec["close"] == 90.5,
                    f"Decimal leaked through close: {rec['close']!r}")
            _assert(type(rec["volume"]) is float, f"Decimal leaked through volume: {rec}")
            _assert(rec["is_adjusted"] is False, "bool not passed through unchanged")
            _assert(rec["ingested_at"] == ts, "timestamp not passed through unchanged")
            sql, params = log[-1]
            _assert(sql.startswith("SELECT " + ", ".join(RECORD_KEYS[Dataset.DAILY_BARS])), sql)
            _assert("source = %s" in sql and "ORDER BY bar_date ASC" in sql, sql)
            _assert(params == ["VCB", "VCI"], f"{params}")

            _assert_raises(
                lambda: src.read_records(Dataset.RAW_EQUITY, "VCB", source="VCI"),
                ValueError, "read_records on a raw dataset",
            )

        check("read_records: exactly RECORD_KEYS[dataset], Decimal->float, source filtered",
              _read_records)

        def _bad_payload() -> None:
            log.clear()
            queue.append([(date(2025, 1, 2), "not-a-dict")])
            _assert_raises(
                lambda: src.raw_bars(Dataset.RAW_EQUITY, "VCB"),
                ValueError, "undecodable raw payload",
            )
            _assert_raises(
                lambda: src.raw_bars(Dataset.DAILY_BARS, "VCB"),
                ValueError, "raw_bars on a typed dataset",
            )

        check("a corrupt raw payload raises instead of being skipped", _bad_payload)

    finally:
        db_mod.cursor = real_cursor  # type: ignore[assignment]
        U.execute_values = real_execute_values  # type: ignore[assignment]

    print()
    if failed:
        print(f"pg selftest: {passed} passed, {len(failed)} FAILED")
        return 1
    print(f"pg selftest: {passed} passed, 0 failed")
    return 0


def _assert(cond: bool, what: str) -> None:
    if not cond:
        raise AssertionError(what)


def _assert_raises(fn, exc_type: type[BaseException], what: str) -> None:
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__} for {what}, nothing raised")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.storage.pg",
        description="Postgres storage backend; --selftest uses a fake cursor and needs no DB.",
    )
    parser.add_argument("--selftest", action="store_true", help="Run the contract checks.")
    args = parser.parse_args(argv)
    if not args.selftest:
        parser.error("--selftest is the only mode; this module is a library otherwise.")
    return _selftest()


if __name__ == "__main__":
    sys.exit(main())
