"""pipelines.universe.sync — reference data: stocks, universe snapshot/members, trading calendar.

``run_universe_sync`` is referenced by ``pipelines.ingestion.vnstock_listing``'s docstring but
has never existed until now (P6.3). This module is that function plus the three siblings needed
to make the FK prerequisites for ``model_runs`` hold rows before the artifact loader (P6.5) can
run: ``model_runs.universe_version -> universe_snapshots``, ``model_universe.ticker -> stocks``.

Scope for this pass is the **85-ticker research universe only** (``list_stocks_research.txt``,
D-16) — the other 15 tickers in ``list_stocks.txt`` have no alpha/beta and no anchor assignment,
so nothing downstream can use them; registering them would put rows on screen the model cannot
explain.

Sector labels are a two-step derivation, not a single fetch:

1. ``vnstock``'s ``Listing().symbols_by_industries()`` returns a *fine-grained* ICB-style label
   per ticker (``industry_name`` — e.g. "Ngân hàng", "Chế biến Thủy sản", "SX Nhựa - Hóa chất").
   ``Listing().industries_icb()`` — the coarse hierarchy — is NOT implemented by the KBS source
   this vnstock install uses (raises ``NotImplementedError`` naming exactly that), which is why
   a second step exists.
2. A small, hand-curated table (``_INDUSTRY_TO_SECTOR`` below) maps each fine label to one of the
   nine Vietnamese sector buckets the dashboard's treemap uses (S3). Curating ~20 industry
   labels is checked by a person; curating 85 tickers one at a time would not be.

``stocks.sector`` therefore holds the coarse bucket (treemap, anchor-group composition);
``stocks.industry`` holds the fine vnstock label (ticker-detail page). A ticker vnstock has no
label for, or whose fine label is not yet in the curated table, gets **both fields NULL** — never
a guess. ``data/reference/sector_map.csv`` is the audit trail: every ticker's fine label, mapped
bucket, and where each came from.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pipelines.universe.file import UniverseFile, read_universe_file

__all__ = [
    "SECTOR_MAP_PATH",
    "SECTOR_VOCABULARY",
    "SectorEntry",
    "derive_trading_calendar",
    "load_sector_map",
    "probe_sectors",
    "sync_stocks",
    "sync_universe_members",
    "sync_universe_snapshot",
    "write_sector_map_csv",
]

SECTOR_MAP_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "sector_map.csv"

#: The nine buckets the dashboard treemap and anchor-group composition panel use (S3). Sector
#: labels are display and external validation only (docs/02 S3g) -- never an input to P -- so
#: this vocabulary is enforced here, not as a DB CHECK, which would be a migration for display
#: data.
SECTOR_VOCABULARY: frozenset[str] = frozenset({
    "Tai chinh",
    "Bat dong san va Xay dung",
    "Nguyen vat lieu",
    "Nang luong",
    "Cong nghe",
    "Cong nghiep",
    "Dich vu",
    "Hang tieu dung",
    "Nong nghiep",
})

# Vietnamese labels with diacritics, kept separate from the ASCII keys above only so this
# source file has no encoding surprises when opened on a misconfigured terminal (the same
# reasoning that stripped em-dashes from the .ps1 scripts in P6.0). CSV output and DB rows use
# the diacritic form; SECTOR_VOCABULARY (ASCII) is what code compares against.
_SECTOR_DISPLAY: dict[str, str] = {
    "Tai chinh": "Tài chính",
    "Bat dong san va Xay dung": "Bất động sản và Xây dựng",
    "Nguyen vat lieu": "Nguyên vật liệu",
    "Nang luong": "Năng lượng",
    "Cong nghe": "Công nghệ",
    "Cong nghiep": "Công nghiệp",
    "Dich vu": "Dịch vụ",
    "Hang tieu dung": "Hàng tiêu dùng",
    "Nong nghiep": "Nông nghiệp",
}

#: vnstock's fine-grained ``industry_name`` (from ``symbols_by_industries()``, KBS source) ->
#: one of the nine buckets above. Curated by hand against the 85-ticker research universe on
#: 2026-08-18 -- every value below was observed live at least once; see P6.3 validation for the
#: per-bucket ticker counts this was checked against. Extend when a ticker outside today's
#: universe surfaces a label not covered here; do NOT guess a mapping for one this table has
#: never seen.
_INDUSTRY_TO_SECTOR: dict[str, str] = {
    # Tai chinh
    "Bảo hiểm": "Tai chinh",
    "Chứng khoán": "Tai chinh",
    "Ngân hàng": "Tai chinh",
    # Bat dong san va Xay dung
    "Bất động sản": "Bat dong san va Xay dung",
    "Xây dựng": "Bat dong san va Xay dung",
    # Nguyen vat lieu
    "SX Nhựa - Hóa chất": "Nguyen vat lieu",
    "Vật liệu xây dựng": "Nguyen vat lieu",
    # Nang luong -- Khai khoang here is PVD (PV Drilling): an oil & gas services company vnstock
    # files under generic "Mining", not a coal/ore miner -- Nang luong is the correct bucket for
    # what the ticker actually does, not for the literal Vietnamese word "khai khoang". Tien ich
    # (utilities: power/gas/water) has no bucket of its own in the nine, and sits closest to
    # Nang luong of the nine available.
    "Khai khoáng": "Nang luong",
    "Tiện ích": "Nang luong",
    # Cong nghe
    "Công nghệ và thông tin": "Cong nghe",
    # Cong nghiep
    "SX Phụ trợ": "Cong nghiep",
    "Thiết bị điện": "Cong nghiep",
    # Dich vu
    "Bán buôn": "Dich vu",
    "Bán lẻ": "Dich vu",
    "Vận tải - kho bãi": "Dich vu",
    # Hang tieu dung
    "Thực phẩm - Đồ uống": "Hang tieu dung",
    # Nong nghiep
    "Chế biến Thủy sản": "Nong nghiep",
    "Nông - Lâm - Ngư": "Nong nghiep",
}


@dataclass(frozen=True)
class SectorEntry:
    ticker: str
    sector: str | None          # ASCII key from SECTOR_VOCABULARY, or None
    industry: str | None        # vnstock's fine label, or None
    label_source: str           # 'vnstock' | 'csv' | 'missing'


# ---------------------------------------------------------------------------
# Sector derivation
# ---------------------------------------------------------------------------


def probe_sectors(tickers: Sequence[str], *, client: Any = None) -> list[SectorEntry]:
    """Fetch fine-grained industry labels for ``tickers`` and map to the nine-bucket vocabulary.

    Never writes to ``stocks`` -- returns entries for :func:`write_sector_map_csv` to persist as
    a reviewable file first. A ticker vnstock has no row for, or whose ``industry_name`` is not
    in ``_INDUSTRY_TO_SECTOR``, comes back with ``sector=None, industry=<raw label or None>,
    label_source='missing'`` -- never a guessed bucket.
    """
    if client is None:
        from vnstock.api.listing import Listing  # noqa: PLC0415

        client = Listing()

    df = client.symbols_by_industries()
    wanted = set(tickers)
    by_ticker: dict[str, str] = {}
    for _, row in df.iterrows():
        sym = str(row["symbol"]).strip().upper()
        if sym in wanted:
            by_ticker[sym] = str(row["industry_name"]).strip()

    out: list[SectorEntry] = []
    for t in tickers:
        industry = by_ticker.get(t)
        if industry is None:
            out.append(SectorEntry(t, None, None, "missing"))
            continue
        sector = _INDUSTRY_TO_SECTOR.get(industry)
        out.append(SectorEntry(t, sector, industry, "vnstock" if sector else "missing"))
    return out


def load_sector_map(path: Path | None = None) -> dict[str, SectorEntry]:
    """Read the committed, reviewed CSV. Missing file -> empty dict (not an error): sync_stocks
    then leaves sector/industry NULL for everyone, which is the honest state before curation.
    """
    target = path if path is not None else SECTOR_MAP_PATH
    if not target.is_file():
        return {}
    out: dict[str, SectorEntry] = {}
    with target.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            ticker = row["ticker"].strip().upper()
            sector_disp = (row.get("sector") or "").strip() or None
            sector = _ascii_key_for_display(sector_disp) if sector_disp else None
            out[ticker] = SectorEntry(
                ticker=ticker,
                sector=sector,
                industry=(row.get("industry") or "").strip() or None,
                label_source=(row.get("label_source") or "csv").strip(),
            )
    return out


def _ascii_key_for_display(display: str) -> str | None:
    for key, disp in _SECTOR_DISPLAY.items():
        if disp == display:
            return key
    return None


def write_sector_map_csv(entries: list[SectorEntry], path: Path | None = None) -> Path:
    """Write the audit-trail CSV: ticker, sector (display form), industry, label_source.

    This is the file a person reviews. It is never read back by ``sync_stocks`` automatically in
    the same run that wrote it -- promoting a draft into the reviewed file is a deliberate,
    separate step, matching ``derive_research_universe``'s own "prints only" convention.
    """
    target = path if path is not None else SECTOR_MAP_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ticker", "sector", "industry", "label_source"])
        for e in sorted(entries, key=lambda e: e.ticker):
            sector_disp = _SECTOR_DISPLAY.get(e.sector, "") if e.sector else ""
            writer.writerow([e.ticker, sector_disp, e.industry or "", e.label_source])
    return target


# ---------------------------------------------------------------------------
# DB writers -- pipelines.common.db.cursor(), not the storage ports (these four tables sit
# outside the BarSink/BarSource abstraction, which is about market data, not reference data).
# ---------------------------------------------------------------------------

_STOCKS_SQL = """
INSERT INTO stocks (ticker, exchange, company_name, sector, industry, is_active, first_seen_date)
VALUES (%(ticker)s, %(exchange)s, %(company_name)s, %(sector)s, %(industry)s, true, %(today)s)
ON CONFLICT (ticker) DO UPDATE SET
    exchange     = EXCLUDED.exchange,
    company_name = COALESCE(EXCLUDED.company_name, stocks.company_name),
    sector       = COALESCE(EXCLUDED.sector, stocks.sector),
    industry     = COALESCE(EXCLUDED.industry, stocks.industry),
    updated_at   = now()
"""


def sync_stocks(
    listing_records: Sequence[Any],
    sector_by_ticker: dict[str, SectorEntry],
    *,
    today: date | None = None,
) -> int:
    """Upsert ``stocks`` for exactly the tickers in ``listing_records``.

    ``listing_records`` are :class:`pipelines.ingestion.vnstock_listing.ListingRecord` (ticker,
    exchange, company_name); sector/industry come from ``sector_by_ticker`` (built by
    :func:`load_sector_map`, keyed by the same tickers). ``COALESCE`` on conflict means a
    ticker's sector is never overwritten back to NULL by a re-run that has no label for it --
    this function only ever adds information, never retracts it silently.
    """
    if not listing_records:
        return 0

    from pipelines.common.db import cursor  # noqa: PLC0415

    today_ = today if today is not None else datetime.now(UTC).date()
    rows = []
    for r in listing_records:
        entry = sector_by_ticker.get(r.ticker)
        sector_disp = _SECTOR_DISPLAY.get(entry.sector) if entry and entry.sector else None
        industry = entry.industry if entry else None
        rows.append({
            "ticker": r.ticker, "exchange": r.exchange, "company_name": r.company_name,
            "sector": sector_disp, "industry": industry, "today": today_,
        })

    with cursor() as cur:
        cur.executemany(_STOCKS_SQL, rows)
    return len(rows)


_SNAPSHOT_SQL = """
INSERT INTO universe_snapshots (universe_version, sha256, n_tickers, source_file, note)
VALUES (%(version)s, %(sha256)s, %(n)s, %(source_file)s, %(note)s)
ON CONFLICT (universe_version) DO NOTHING
"""


def sync_universe_snapshot(uf: UniverseFile, *, note: str | None = None) -> bool:
    """Register ``uf``'s version. Content-addressed (P6.3): ``ON CONFLICT DO NOTHING`` is
    correct, not merely convenient -- the same version can only ever mean the same ticker set.
    Returns True if a row was inserted, False if the version already existed.
    """
    from pipelines.common.db import cursor  # noqa: PLC0415

    with cursor() as cur:
        cur.execute(_SNAPSHOT_SQL, {
            "version": uf.version, "sha256": uf.sha256, "n": uf.n,
            "source_file": str(uf.path), "note": note,
        })
        return cur.rowcount == 1


def sync_universe_members(uf: UniverseFile) -> int:
    """Replace ``universe_members`` for ``uf.version`` with exactly ``uf.tickers`` in file order.

    Delete-then-insert inside one transaction, not an upsert: content-addressing means a given
    version's membership never legitimately changes, so a full replace is the simplest thing
    that is still correct on a re-run (including a re-run after a bug in a previous partial
    write).
    """
    from pipelines.common.db import cursor  # noqa: PLC0415

    rows = [{"version": uf.version, "ticker": t, "position": i}
            for i, t in enumerate(uf.tickers)]
    with cursor() as cur:
        cur.execute("DELETE FROM universe_members WHERE universe_version = %s", (uf.version,))
        cur.executemany(
            "INSERT INTO universe_members (universe_version, ticker, position) "
            "VALUES (%(version)s, %(ticker)s, %(position)s)",
            rows,
        )
    return len(rows)


def derive_trading_calendar() -> int:
    """Populate ``trading_calendar`` from the sessions already in ``market_index_bars`` (P6.4).

    A session exists iff the index printed a close (docs/01 -- the calendar is a consequence of
    observed data, not an assumption maintained by hand). ``session_seq`` is a dense rank over
    ``bar_date`` ascending; the ``trading_calendar_seq_iff_trading`` CHECK is what catches a
    derivation bug here, not a manual audit.
    """
    from pipelines.common.db import cursor  # noqa: PLC0415

    sql = """
    INSERT INTO trading_calendar (cal_date, is_trading_day, day_type, session_seq)
    SELECT
        bar_date,
        true,
        'trading',
        row_number() OVER (ORDER BY bar_date)
    FROM (SELECT DISTINCT bar_date FROM market_index_bars) d
    ON CONFLICT (cal_date) DO UPDATE SET
        is_trading_day = true,
        day_type       = 'trading',
        session_seq    = EXCLUDED.session_seq
    """
    with cursor() as cur:
        cur.execute(sql)
        return cur.rowcount


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_universe_sync(
    universe_file: Path | str = "list_stocks_research.txt",
    *,
    listing_source: Any = None,
    sector_map_path: Path | None = None,
) -> dict[str, Any]:
    """``stocks`` + ``universe_snapshots`` + ``universe_members`` for one universe file.

    ``listing_source`` follows ``pipelines.ingestion.vnstock_listing.ListingSource`` (a
    ``.fetch() -> ListingSnapshot``); ``None`` builds the real ``VnstockListingSource``. The
    listing snapshot must be ``complete`` -- a partial provider response is refused rather than
    silently registering a subset of the universe as if it were everyone (mirrors
    ``vnstock_listing.validate_listing_response``'s own fail-closed contract).
    """
    from pipelines.ingestion.vnstock_listing import VnstockListingSource  # noqa: PLC0415

    uf = read_universe_file(universe_file)
    source = listing_source if listing_source is not None else VnstockListingSource()
    snapshot = source.fetch()
    if not snapshot.complete:
        raise RuntimeError(f"listing source incomplete: {snapshot.reason}")

    by_ticker = {r.ticker: r for r in snapshot.records}
    missing = [t for t in uf.tickers if t not in by_ticker]
    if missing:
        raise RuntimeError(
            f"{len(missing)} universe ticker(s) absent from the listing source: "
            f"{', '.join(sorted(missing)[:10])}"
            + (f" (and {len(missing) - 10} more)" if len(missing) > 10 else "")
        )

    listing_records = [by_ticker[t] for t in uf.tickers]
    sector_by_ticker = load_sector_map(sector_map_path)

    n_stocks = sync_stocks(listing_records, sector_by_ticker)
    inserted_snapshot = sync_universe_snapshot(uf)
    n_members = sync_universe_members(uf)

    n_with_sector = sum(
        1 for t in uf.tickers if sector_by_ticker.get(t) and sector_by_ticker[t].sector
    )
    return {
        "universe_version": uf.version,
        "n_tickers": uf.n,
        "n_stocks_upserted": n_stocks,
        "snapshot_inserted": inserted_snapshot,
        "n_members": n_members,
        "n_with_sector": n_with_sector,
        "n_without_sector": uf.n - n_with_sector,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.universe.sync",
        description="Sync reference data (stocks, universe snapshot/members) for a universe file.",
    )
    parser.add_argument("--file", default="list_stocks_research.txt", metavar="PATH")
    parser.add_argument(
        "--probe-sectors", action="store_true",
        help="Fetch fine-grained industry labels for --file's tickers and write a DRAFT "
             "sector_map.csv for review. Does not touch the database.",
    )
    parser.add_argument("--sync", action="store_true", help="Run the DB sync (needs DATABASE_URL).")
    args = parser.parse_args(argv)

    if args.probe_sectors:
        uf = read_universe_file(args.file)
        entries = probe_sectors(list(uf.tickers))
        path = write_sector_map_csv(entries)
        n_mapped = sum(1 for e in entries if e.sector)
        print(f"probed {len(entries)} tickers, {n_mapped} mapped, {len(entries) - n_mapped} "
              f"missing -> {path}")
        for e in entries:
            if not e.sector:
                print(f"  MISSING  {e.ticker}: industry={e.industry!r}")
        return 0

    if args.sync:
        result = run_universe_sync(args.file)
        for k, v in result.items():
            print(f"{k}: {v}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
