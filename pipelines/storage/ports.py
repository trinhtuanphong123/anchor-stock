"""pipelines.storage.ports — the seam between "what to compute" and "where it lands".

Two Protocols, each implemented twice: ``PostgresSink``/``PostgresSource`` in ``pg.py`` and
``LocalSink``/``LocalSource`` in ``localfs.py``. One fetch/compute path serves both tracks;
the only thing that varies is the destination.

This module imports nothing from the rest of the repo — not ``psycopg2``, not ``pyarrow``, not
even ``pipelines.common``. That is deliberate: a caller can depend on the *types* without
dragging in either backend, which is what lets ``pipelines.returns.build`` import cleanly on a
machine with no database configured.

The four constant tables at the bottom (``RECORD_KEYS``, ``CONFLICT_KEY``, ``ON_CONFLICT_KEEP``,
``PARTITION_COL``) are the machine-readable statement of the record contract. They are not
documentation: ``localfs.py --selftest`` parses the SQL in ``pipelines.common.upsert`` and
asserts they agree, so adding a column to the SQL and forgetting the local sink fails a check
instead of producing a silent divergence.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "BOOL_COLS",
    "CONFLICT_KEY",
    "DATE_COLS",
    "FLOAT_COLS",
    "INDICATOR_COLS",
    "ON_CONFLICT_KEEP",
    "PARTITION_COL",
    "RECORD_KEYS",
    "TS_COLS",
    "BarSink",
    "BarSource",
    "Dataset",
]


class Dataset(StrEnum):
    """A storage location, at the granularity the two backends actually differ on.

    ``RAW_EQUITY`` and ``RAW_INDEX`` are one Postgres table (``staging.ohlc_raw``) discriminated
    by a ``bar_type`` column, and two directories locally. Folding ``bar_type`` into the enum
    rather than carrying it as a separate argument leaves exactly one filter argument —
    ``source`` — which applies to the four typed datasets and to neither raw one. A caller can
    therefore no longer construct the meaningless combination "raw payloads from source VCI".
    """

    RAW_EQUITY = "raw_equity"
    RAW_INDEX = "raw_index"
    DAILY_BARS = "daily_bars"
    INDEX_BARS = "index_bars"
    DAILY_RETURNS = "daily_returns"
    INDEX_RETURNS = "index_returns"
    INDICATORS_DAILY = "technical_indicators_daily"

    @property
    def table(self) -> str:
        """The Postgres relation this dataset lives in."""
        if self in (Dataset.RAW_EQUITY, Dataset.RAW_INDEX):
            return "staging.ohlc_raw"
        return self.value

    @property
    def bar_type(self) -> str | None:
        """``'EQUITY'`` / ``'INDEX'`` for the raw datasets, ``None`` for the typed ones.

        This is the only place the string that ``staging.ohlc_raw``'s CHECK constrains appears.
        """
        if self is Dataset.RAW_EQUITY:
            return "EQUITY"
        if self is Dataset.RAW_INDEX:
            return "INDEX"
        return None

    @property
    def is_raw(self) -> bool:
        return self.bar_type is not None

    @property
    def has_source(self) -> bool:
        """True when the underlying table has a ``source`` column.

        ``staging.ohlc_raw`` does not: it is keyed by ``(symbol, bar_type, bar_date)`` and
        carries the provider in a separate column with a schema default. Passing ``source`` to a
        raw read is therefore a construction error, not a no-op filter.
        """
        return not self.is_raw


# ---------------------------------------------------------------------------
# Sink
# ---------------------------------------------------------------------------


@runtime_checkable
class BarSink(Protocol):
    """Where fetched bars and computed returns land.

    Contract honoured identically by both implementations:

    * Every method takes the SAME record dicts that the ``%(name)s`` placeholders in
      ``pipelines.common.upsert`` consume. A missing required key raises; an extra key is
      ignored. ``RECORD_KEYS`` states the required set per dataset.
    * Empty input is a no-op returning ``0``. No file is created, no transaction is opened.
    * The return value is the number of records **submitted**, not the number of rows that
      changed. Postgres cannot distinguish an insert from an update under ``executemany``, so
      this interface does not pretend to either.
    * Writes are **idempotent** on the dataset's conflict key. Re-submitting a record already
      present leaves the same end state as ``ON CONFLICT DO UPDATE`` — *including* the columns
      that clause declines to touch, which ``ON_CONFLICT_KEEP`` names. A blanket row-replace
      would look correct and would diverge.
    * The stored state is a pure function of the multiset of records ever written — never of
      write order, never of how many times a batch was submitted.
    * Methods **raise** on failure. They never swallow, never log-and-return-zero, never
      partially succeed in silence. Retry and quarantine policy belongs to the caller, which is
      the only layer that knows whether the run can continue.

    Note that no method takes a symbol alongside its records. That argument would permit a state
    Postgres cannot represent — ``symbol="VCB"`` next to records saying ``"FPT"`` — which the
    Postgres sink would ignore and the local sink would obey. Both derive the key from the
    record instead, so both fail on the same malformed input in the same way.
    """

    def write_raw_bars(self, records: list[dict[str, Any]]) -> int:
        """Land raw provider payloads. Conflict key ``(symbol, bar_type, bar_date)``.

        ``payload`` is a pre-serialised JSON **string**, not a dict: the Postgres statement casts
        it with ``::jsonb`` and the local sink stores the identical string. A batch may span
        several symbols; implementations group it themselves.
        """
        ...

    def write_daily_bars(self, records: list[dict[str, Any]]) -> int:
        """Typed equity bars. Conflict key ``(ticker, bar_date, source)``.

        ``close`` must be present, non-null and finite — it is the model's only price input, and
        a missing close silently deletes a session from the return series rather than raising.
        On conflict ``ingested_at`` is preserved from the incumbent row.
        """
        ...

    def write_index_bars(self, records: list[dict[str, Any]]) -> int:
        """Typed index bars. Conflict key ``(index_symbol, bar_date, source)``.

        ``close`` is the market factor itself; same non-null, finite requirement as above.
        ``ingested_at`` preserved on conflict.
        """
        ...

    def write_daily_returns(self, records: list[dict[str, Any]]) -> int:
        """Per-ticker log returns. Conflict key ``(ticker, bar_date, source)``."""
        ...

    def write_index_returns(self, records: list[dict[str, Any]]) -> int:
        """Index log returns. Conflict key ``(index_symbol, bar_date, source)``."""
        ...

    def write_indicators(self, records: list[dict[str, Any]]) -> int:
        """Display-only technical indicators. Conflict key ``(ticker, bar_date, source)``.

        Unlike every other typed dataset here, **every** non-key column is nullable and NULL is
        a meaningful value: it means "not enough history at this date" (a 200-day average on bar
        37). What is *not* permitted is NaN or infinity — ``_validate_records`` rejects both, so
        the numpy warm-up NaNs must already have become ``None`` before a record arrives here.
        """
        ...


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


@runtime_checkable
class BarSource(Protocol):
    """Where bars and returns are read from. Return types are backend-independent.

    Contract honoured identically by both implementations:

    * Every number comes back as ``float | None`` and every date as ``datetime.date`` — never
      ``Decimal``, never a numpy scalar, never a ``pandas.Timestamp``. The conversion runs
      toward float, in one place, inside ``PostgresSource``.

      The direction matters. ``Decimal`` does not survive one call downstream —
      ``compute_return_rows`` coerces it immediately — so carrying it across the port buys
      nothing. Converting the other way is worse than useless: building a ``Decimal`` from a
      float64 *invents* eighteen digits that were never measured. Narrowing discards information
      that exists; widening manufactures information that does not.
    * ``None`` means SQL NULL or a parquet null. NaN is never returned: a non-finite value is a
      write-time error, not a read-time value.
    * ``start``/``end`` and ``since``/``until`` are **inclusive** on both edges; ``None`` means
      unbounded on that edge.
    * Bar and payload reads are ordered **ascending** by date. The return-dict reads are
      unordered by construction.
    * ``source`` is a **required keyword** wherever the table has that column. There is no
      "any source" read: two sources landing the same dates would make ``prev_close`` come from
      a different price series, producing a log return that is finite, plausibly sized, and
      undetectable downstream. Requiring the argument means the bug cannot return by omission.
    * Methods **raise** on failure. A source that cannot answer says so; it does not return an
      empty result that reads as "no data". That distinction is the whole point of
      ``high_water_marks``.
    """

    def daily_bars(
        self, ticker: str, start: date | None, end: date | None, *, source: str
    ) -> list[tuple[date, float | None, float | None]]:
        """Ascending ``(bar_date, close, volume)`` for one ticker and one source.

        Feeds ``pipelines.common.returns.compute_return_rows`` directly.
        """
        ...

    def index_bars(
        self, index_symbol: str, start: date | None, end: date | None, *, source: str
    ) -> list[tuple[date, float | None]]:
        """Ascending ``(bar_date, close)`` for one index symbol and one source."""
        ...

    def daily_returns(
        self, tickers: Sequence[str], start: date | None, end: date | None, *, source: str
    ) -> dict[str, dict[date, float]]:
        """``{ticker: {bar_date: log_return}}`` for the requested tickers.

        Only tickers with at least one row appear as keys. Distinguishing "asked for and got
        nothing" from "never asked" is an alignment-reporting concern and belongs at the
        alignment site, which pre-seeds the full requested set before calling this.
        """
        ...

    def index_returns(
        self, index_symbol: str, start: date | None, end: date | None, *, source: str
    ) -> dict[date, float]:
        """``{bar_date: log_return}`` for one index symbol."""
        ...

    def raw_bars(
        self, dataset: Dataset, symbol: str, since: date | None = None, until: date | None = None
    ) -> list[tuple[date, dict[str, Any]]]:
        """Ascending ``(bar_date, payload)`` of landed raw payloads.

        ``dataset`` must be a raw one. The date is returned alongside the payload because the
        storage layer already knows it — the parse pass should not have to re-derive it from the
        payload's own ``"time"`` field.

        A payload that will not decode to a dict **raises**, naming symbol and date. Skipping it
        would put a hole in the return series that is indistinguishable from a market holiday.
        """
        ...

    def read_records(
        self, dataset: Dataset, key: str,
        start: date | None = None, end: date | None = None, *, source: str,
    ) -> list[dict[str, Any]]:
        """Full record dicts for one typed dataset and key — exactly ``RECORD_KEYS[dataset]``,
        ascending by ``bar_date``.

        The other typed reads (``daily_bars``, ``index_bars``, ``daily_returns``,
        ``index_returns``) are lossy projections — ``daily_bars`` alone drops eight of
        ``daily_bars``' eleven columns. A caller that needs to round-trip a record (P6's
        Postgres mirror, ``artifact.inspect --from-db``'s read-back check) needs this instead of
        reassembling a partial record from several of those calls.

        Typed datasets only — ``dataset.has_source`` must be true, enforced the same way every
        other typed method enforces it (:func:`require_source`). Raw payloads are already served
        by :meth:`raw_bars`.
        """
        ...

    def high_water_marks(
        self, dataset: Dataset, keys: Sequence[str], *, source: str | None = None
    ) -> dict[str, date | None]:
        """``MAX(bar_date)`` per key. Every requested key appears; ``None`` means no rows.

        Always batched — a single symbol is a one-element sequence. This replaces four
        near-identical ``MAX(bar_date)`` queries that existed separately.

        ``source`` is required for the typed datasets and must be ``None`` for the raw ones;
        the wrong combination raises ``ValueError``.

        **``None`` means "this dataset has no rows for that key" and nothing else.** It never
        means "the lookup failed" — a failure raises. The previous implementations swallowed
        exceptions and returned ``None``, which conflated two states demanding opposite actions:
        a transient database error then triggered a full multi-year refetch of every symbol
        against a throttled provider. Failing loudly is both cheaper and more honest.
        """
        ...


# ---------------------------------------------------------------------------
# The record contract, machine-readable
# ---------------------------------------------------------------------------

#: The 30 numeric indicator columns of ``technical_indicators_daily``, in DDL order.
#:
#: Named separately because it is needed twice and the two uses fail in opposite ways when they
#: disagree: ``RECORD_KEYS`` drives the INSERT column list (a mismatch raises), while
#: ``FLOAT_COLS`` drives ``localfs._arrow_schema`` (a mismatch does NOT raise — an unrecognised
#: name falls through to ``pa.string()`` and the indicator is written to parquet as text, with
#: no error at write time and none at read time either). Deriving both from one tuple removes
#: the silent half of that pair.
INDICATOR_COLS: tuple[str, ...] = (
    # trend
    "sma_20", "sma_50", "sma_200", "ema_12", "ema_26",
    # momentum
    "macd", "macd_signal", "macd_hist", "rsi_14", "stoch_k_14", "stoch_d_14",
    # volatility
    "atr_14", "bb_mid_20", "bb_upper_20", "bb_lower_20", "bb_width_20",
    "realized_vol_20d", "realized_vol_60d",
    # volume
    "obv", "volume_sma_20", "turnover_value",
    # returns (fractions, not percents — see pipelines.indicators.compute)
    "ret_1d", "ret_5d", "ret_20d", "ret_60d", "ret_252d", "ret_ytd",
    # position within the recent range
    "dist_from_sma_200_pct", "high_252d", "low_252d", "drawdown_from_252d_high",
)

#: Required keys per dataset, in the order the INSERT column list uses. Asserted against the SQL
#: in ``pipelines.common.upsert`` by ``localfs.py --selftest``.
RECORD_KEYS: dict[Dataset, tuple[str, ...]] = {
    Dataset.RAW_EQUITY: ("symbol", "bar_type", "bar_date", "payload", "fetched_at"),
    Dataset.RAW_INDEX: ("symbol", "bar_type", "bar_date", "payload", "fetched_at"),
    Dataset.DAILY_BARS: (
        "ticker", "bar_date", "source", "open", "high", "low", "close", "volume",
        "is_adjusted", "ingested_at", "updated_at",
    ),
    Dataset.INDEX_BARS: (
        "index_symbol", "bar_date", "source", "open", "high", "low", "close", "volume",
        "ingested_at", "updated_at",
    ),
    Dataset.DAILY_RETURNS: (
        "ticker", "bar_date", "source", "close", "prev_close", "log_return",
        "at_limit", "zero_volume", "computed_at",
    ),
    Dataset.INDEX_RETURNS: (
        "index_symbol", "bar_date", "source", "close", "prev_close", "log_return",
        "computed_at",
    ),
    Dataset.INDICATORS_DAILY: (
        "ticker", "bar_date", "source", *INDICATOR_COLS, "computed_at",
    ),
}

#: The ON CONFLICT tuple — the identity of a row, and the merge key for the local sink.
CONFLICT_KEY: dict[Dataset, tuple[str, ...]] = {
    Dataset.RAW_EQUITY: ("symbol", "bar_type", "bar_date"),
    Dataset.RAW_INDEX: ("symbol", "bar_type", "bar_date"),
    Dataset.DAILY_BARS: ("ticker", "bar_date", "source"),
    Dataset.INDEX_BARS: ("index_symbol", "bar_date", "source"),
    Dataset.DAILY_RETURNS: ("ticker", "bar_date", "source"),
    Dataset.INDEX_RETURNS: ("index_symbol", "bar_date", "source"),
    Dataset.INDICATORS_DAILY: ("ticker", "bar_date", "source"),
}

#: Columns the ``DO UPDATE SET`` clause deliberately omits, so an incumbent row keeps its own
#: value on conflict. Only ``ingested_at`` behaves this way: a re-ingested bar keeps the moment
#: it FIRST arrived. The local sink must replicate this, or a re-run diverges by one column.
ON_CONFLICT_KEEP: dict[Dataset, frozenset[str]] = {
    Dataset.RAW_EQUITY: frozenset(),
    Dataset.RAW_INDEX: frozenset(),
    Dataset.DAILY_BARS: frozenset({"ingested_at"}),
    Dataset.INDEX_BARS: frozenset({"ingested_at"}),
    Dataset.DAILY_RETURNS: frozenset(),
    Dataset.INDEX_RETURNS: frozenset(),
    # Nothing is preserved on conflict: a recompute replaces every column including
    # ``computed_at``. There is no "first arrival" to keep here — an indicator is derived, so
    # the only honest timestamp is the one of the computation the row currently holds.
    Dataset.INDICATORS_DAILY: frozenset(),
}

#: Column -> logical type, keyed by name because the names are globally consistent across
#: tables. The single source both backends' ``read_records`` type conversions are checked
#: against: ``FLOAT_COLS`` is what ``PostgresSource`` runs its ``Decimal -> float`` conversion
#: over (:func:`pipelines.storage.pg._f`), and what ``LocalSource``'s Arrow schema was already
#: keying off of before this lived here. One definition rather than two that could drift.
FLOAT_COLS: frozenset[str] = frozenset(
    {"open", "high", "low", "close", "volume", "prev_close", "log_return", *INDICATOR_COLS}
)
BOOL_COLS: frozenset[str] = frozenset({"is_adjusted", "at_limit", "zero_volume"})
DATE_COLS: frozenset[str] = frozenset({"bar_date"})
TS_COLS: frozenset[str] = frozenset({"ingested_at", "updated_at", "computed_at", "fetched_at"})

#: The column the local sink shards on — chosen to match the unit of work, which is one symbol.
PARTITION_COL: dict[Dataset, str] = {
    Dataset.RAW_EQUITY: "symbol",
    Dataset.RAW_INDEX: "symbol",
    Dataset.DAILY_BARS: "ticker",
    Dataset.INDEX_BARS: "index_symbol",
    Dataset.DAILY_RETURNS: "ticker",
    Dataset.INDEX_RETURNS: "index_symbol",
    Dataset.INDICATORS_DAILY: "ticker",
}


def require_source(dataset: Dataset, source: str | None) -> None:
    """Validate the ``source`` argument against the dataset. Raises ``ValueError`` on mismatch.

    Shared by both implementations so the rule is stated once: typed datasets need a source,
    raw datasets must not be given one.
    """
    if dataset.has_source and not source:
        raise ValueError(f"{dataset.value} requires an explicit source (it has a source column)")
    if not dataset.has_source and source is not None:
        raise ValueError(f"{dataset.value} has no source column; pass source=None")
