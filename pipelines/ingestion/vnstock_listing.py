"""Narrow, fail-closed VNStock listing source for production universe sync.

The adapter deliberately does one thing: obtain a listing and turn it into a fully validated,
explicit source snapshot. It has no database knowledge, does not print, and does not create a
VNStock client (or make a network request) until :meth:`VnstockListingSource.fetch` is called.

Uses ``Listing().symbols_by_exchange()``, not ``all_symbols()`` (P6.3, 2026-08-18) — verified
live against the installed vnstock 4.0.4 (KBS source): ``all_symbols()`` returns only
``symbol``/``organ_name``, no ``exchange`` column at all, which made every row fail
:func:`validate_listing_response`'s fail-closed exchange check. ``symbols_by_exchange()``
carries ``exchange`` and, filtered to ``type == 'stock'``, returns the identical row count
(1528) that ``all_symbols()`` used to — the extra rows before filtering are bonds, closed-end
funds, and futures, not equities. If a future vnstock release restores ``exchange`` to
``all_symbols()``, switching back costs one line; nothing downstream depends on which method
supplied the row.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

SOURCE_IDENTITY = "vnstock"
CANONICAL_EXCHANGES = frozenset({"HOSE", "HNX", "UPCOM"})
EXCHANGE_ALIASES = {
    "HSX": "HOSE",
    "HOSE": "HOSE",
    "HNX": "HNX",
    "UPCOM": "UPCOM",
}
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{0,9}$")
_MAX_REASON_LENGTH = 160


@dataclass(frozen=True)
class ListingRecord:
    """One normalized, accepted member of the official universe."""

    ticker: str
    exchange: str
    company_name: str
    sector: str | None = None
    industry: str | None = None


@dataclass(frozen=True)
class ListingSnapshot:
    """A source result whose completeness is explicit, never inferred by callers."""

    records: tuple[ListingRecord, ...]
    complete: bool
    reason: str = ""
    source_identity: str = SOURCE_IDENTITY
    discovered_count: int = 0

    @classmethod
    def incomplete(cls, reason: str, *, discovered_count: int = 0) -> ListingSnapshot:
        return cls(
            records=(),
            complete=False,
            reason=_bounded_reason(reason),
            discovered_count=discovered_count,
        )


class ListingSource(Protocol):
    """The narrow source boundary consumed by ``run_universe_sync``."""

    def fetch(self) -> ListingSnapshot:
        ...


def _bounded_reason(reason: str) -> str:
    return str(reason).replace("\n", " ").replace("\r", " ")[:_MAX_REASON_LENGTH]


def _text(value: Any) -> str | None:
    """Return trimmed text, treating null-like values as absent without pandas."""
    if value is None:
        return None
    try:
        if value != value:  # NaN and pandas.NA-like values
            return None
    except Exception:  # noqa: BLE001 - an opaque provider value is handled below
        pass
    text = str(value).strip()
    if text.casefold() in {"nan", "none", "null", "<na>"}:
        return None
    return text or None


def normalize_ticker(value: Any) -> str | None:
    """Normalize and conservatively validate a Vietnamese listing symbol."""
    text = _text(value)
    if text is None:
        return None
    ticker = text.upper()
    return ticker if TICKER_PATTERN.fullmatch(ticker) else None


def normalize_exchange(value: Any) -> str | None:
    """Normalize only the packet-authorized exchange aliases."""
    text = _text(value)
    if text is None:
        return None
    return EXCHANGE_ALIASES.get(text.upper())


def normalize_company_name(value: Any) -> str | None:
    """Trim and collapse whitespace while preserving the supplied display casing."""
    text = _text(value)
    return " ".join(text.split()) if text else None


def _normalize_optional(value: Any) -> str | None:
    return normalize_company_name(value)


def _row_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """Read the documented listing names case-insensitively.

    ``symbols_by_exchange()`` supplies ``symbol``, ``exchange`` and ``organ_name`` (P6.3 —
    ``all_symbols()`` no longer carries ``exchange`` on this vnstock/KBS combination; see the
    module docstring). ``ticker``/``company_name`` are accepted as already-normalized
    test/source wrappers, without relying on sector or delisting fields that have not been
    established as required provider data.
    """
    lowered = {str(key).casefold(): value for key, value in row.items()}

    def pick(*names: str) -> Any:
        for name in names:
            if name in lowered:
                return lowered[name]
        return None

    return {
        "ticker": pick("symbol", "ticker"),
        "exchange": pick("exchange"),
        "company_name": pick("organ_name", "company_name"),
        "sector": pick("sector"),
        "industry": pick("industry"),
    }


def _stable_record(existing: ListingRecord, candidate: ListingRecord) -> ListingRecord:
    """Collapse compatible duplicates independently of provider row order."""
    # These identities have already been checked by the caller.  The lexical
    # choice makes equivalent-cased display text and optional metadata stable.
    def choose(left: str | None, right: str | None) -> str | None:
        choices = [item for item in (left, right) if item]
        return min(choices, key=lambda item: (item.casefold(), item)) if choices else None

    return ListingRecord(
        ticker=existing.ticker,
        exchange=existing.exchange,
        company_name=choose(existing.company_name, candidate.company_name) or existing.company_name,
        sector=choose(existing.sector, candidate.sector),
        industry=choose(existing.industry, candidate.industry),
    )


def _rows_from_response(payload: Any) -> tuple[Iterable[Any] | None, bool, str]:
    """Extract rows and explicit response completeness from common lightweight fakes.

    The real listing dataframe has no separate response envelope; calling that documented
    full-list endpoint is the positive completeness signal.  Test and provider wrappers may
    explicitly expose ``complete=False``, ``partial`` or
    ``truncated``; each fails closed.
    """
    complete = True
    rows = payload
    if isinstance(payload, Mapping):
        if "complete" in payload:
            complete = payload["complete"] is True
        if payload.get("partial") is True or payload.get("truncated") is True:
            complete = False
        if "rows" in payload:
            rows = payload["rows"]
        else:
            return None, False, "source response is missing rows"
    else:
        if hasattr(payload, "complete"):
            complete = payload.complete is True
        if (
            getattr(payload, "partial", False) is True
            or getattr(payload, "truncated", False) is True
        ):
            complete = False
        if hasattr(payload, "rows"):
            rows = payload.rows

    if not complete:
        return None, False, "source response is explicitly partial or incomplete"
    if hasattr(rows, "to_dict"):
        try:
            rows = rows.to_dict(orient="records")
        except (TypeError, ValueError, AttributeError):
            return None, False, "source response rows cannot be read"
    if isinstance(rows, (str, bytes, Mapping)):
        return None, False, "source response rows are not a record collection"
    try:
        return list(rows), True, ""
    except TypeError:
        return None, False, "source response rows are not iterable"


def validate_listing_response(payload: Any) -> ListingSnapshot:
    """Normalize a complete all-symbols response or return an incomplete snapshot.

    Validation is intentionally all-or-nothing.  No caller receives a subset
    after malformed, unknown-exchange, conflicting, empty, or partial input.
    """
    rows, complete, reason = _rows_from_response(payload)
    if not complete or rows is None:
        return ListingSnapshot.incomplete(reason)
    if not rows:
        return ListingSnapshot.incomplete("source listing is empty")

    accepted: dict[str, ListingRecord] = {}
    discovered_count = len(rows)
    for raw in rows:
        if not isinstance(raw, Mapping):
            return ListingSnapshot.incomplete(
                "source row is not a mapping", discovered_count=discovered_count
            )
        fields = _row_fields(raw)
        ticker = normalize_ticker(fields["ticker"])
        if ticker is None:
            return ListingSnapshot.incomplete(
                "source row has malformed or missing ticker", discovered_count=discovered_count
            )
        exchange = normalize_exchange(fields["exchange"])
        if exchange is None:
            return ListingSnapshot.incomplete(
                "source row has unknown or missing exchange", discovered_count=discovered_count
            )
        company_name = normalize_company_name(fields["company_name"])
        if company_name is None:
            return ListingSnapshot.incomplete(
                "source row has missing company name", discovered_count=discovered_count
            )
        candidate = ListingRecord(
            ticker=ticker,
            exchange=exchange,
            company_name=company_name,
            sector=_normalize_optional(fields["sector"]),
            industry=_normalize_optional(fields["industry"]),
        )
        previous = accepted.get(ticker)
        if previous is not None:
            if previous.exchange != candidate.exchange or (
                previous.company_name.casefold() != candidate.company_name.casefold()
            ):
                return ListingSnapshot.incomplete(
                    "source has conflicting duplicate ticker",
                    discovered_count=discovered_count,
                )
            accepted[ticker] = _stable_record(previous, candidate)
        else:
            accepted[ticker] = candidate

    exchanges = {record.exchange for record in accepted.values()}
    if exchanges != CANONICAL_EXCHANGES:
        return ListingSnapshot.incomplete(
            "source cannot prove complete HOSE/HNX/UPCOM coverage",
            discovered_count=discovered_count,
        )
    return ListingSnapshot(
        records=tuple(sorted(accepted.values(), key=lambda record: record.ticker)),
        complete=True,
        discovered_count=discovered_count,
    )


def _default_listing_factory() -> Any:
    """Create a VNStock Listing client only when a live fetch is invoked."""
    try:
        from vnstock.api.listing import Listing  # type: ignore[import-untyped]
    except ImportError:
        from vnstock.listing import Listing  # type: ignore[import-untyped]

    return Listing()


class VnstockListingSource:
    """Production listing adapter with injectable client/factory for deterministic tests."""

    source_identity = SOURCE_IDENTITY

    def __init__(
        self,
        *,
        client: Any = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        if client is not None and client_factory is not None:
            raise ValueError("provide either client or client_factory, not both")
        self._client = client
        self._client_factory = client_factory or _default_listing_factory

    def fetch(self) -> ListingSnapshot:
        """Fetch and validate a complete listing; provider failures remain non-mutating."""
        try:
            client = self._client if self._client is not None else self._client_factory()
            payload = client.symbols_by_exchange()
            # symbols_by_exchange() spans every instrument type the exchange lists (bonds,
            # closed-end funds, futures, ...), not only equities. Filtering here, before
            # validate_listing_response ever sees the rows, is what keeps that function's
            # fail-closed exchange check meaningful — CANONICAL_EXCHANGES describes the
            # equity universe, and an unfiltered future-market row ("XHNF") would otherwise
            # trip "unknown exchange" and mark the whole snapshot incomplete for a reason
            # that has nothing to do with equity coverage.
            if hasattr(payload, "columns") and "type" in payload.columns:
                payload = payload[payload["type"] == "stock"]
        except Exception as exc:  # noqa: BLE001 - source failures must fail closed
            return ListingSnapshot.incomplete(f"source exception: {type(exc).__name__}")
        return validate_listing_response(payload)
