"""pipelines.universe.file — read the investable universe from ``list_stocks.txt``.

The universe is a *file*, not a database query. That matters for two reasons.

**A fresh install is unambiguous.** The previous design resolved the universe from
``stocks.is_active``, which meant the answer to "which tickers?" depended on what ingestion had
already written — and was empty before the first run. A file has the same answer on a bare
checkout as it does in production.

**The version is the content.** ``universe_version`` is a hash of the normalised ticker list,
so two runs share a version if and only if they ran on the same set. Nothing has to remember to
bump a counter, and a version can never silently mean two different sets.

Normalisation, in order: strip comments (``#``) and blank lines, uppercase, drop duplicates,
**sort ascending**. Sorting is not cosmetic — ``assemble_matrix`` orders columns by ticker and
the greedy tie-break is smallest index, so column order has to be a property of the content
rather than of how the file was typed. Line order carries no meaning by design.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pipelines.common.paths import UNIVERSE_FILE

# Research-track defaults (docs/03 §2). Kept local rather than imported from
# pipelines.returns.* to keep this module the dependency-free foundation it already is.
_RESEARCH_INDEX_SYMBOL = "VNINDEX"
_RESEARCH_SOURCE = "VCI"

#: A ticker is 3–10 characters of uppercase letters and digits. HOSE equities are all 3
#: letters; the wider pattern leaves room for index symbols without loosening it to "anything".
TICKER_RE = re.compile(r"^[A-Z0-9]{3,10}$")

_COMMENT = "#"


class UniverseFileError(ValueError):
    """The universe file is missing, empty, or contains a malformed ticker."""


@dataclass(frozen=True)
class UniverseFile:
    """A resolved universe: the tickers, plus the identity of that exact set."""

    path: Path
    tickers: tuple[str, ...]
    sha256: str
    version: str

    @property
    def n(self) -> int:
        return len(self.tickers)

    def __len__(self) -> int:
        return len(self.tickers)

    def __contains__(self, ticker: object) -> bool:
        return isinstance(ticker, str) and ticker.strip().upper() in self.tickers

    def position(self, ticker: str) -> int:
        """Index of ``ticker`` in the ordered universe. Raises ``KeyError`` if absent.

        Positions are what artifacts store instead of symbols, so that a reordered universe
        fails validation rather than passing quietly.
        """
        try:
            return self.tickers.index(ticker.strip().upper())
        except ValueError as exc:
            raise KeyError(ticker) from exc


def normalise_tickers(raw_lines: list[str]) -> tuple[str, ...]:
    """Turn raw file lines into the canonical ordered ticker tuple.

    Raises ``UniverseFileError`` naming the offending line number if any entry is malformed —
    a typo in this file would otherwise surface much later as an unexplained empty series.
    """
    seen: set[str] = set()
    bad: list[str] = []

    for lineno, line in enumerate(raw_lines, start=1):
        text = line.split(_COMMENT, 1)[0].strip()
        if not text:
            continue
        token = text.upper()
        if not TICKER_RE.match(token):
            bad.append(f"line {lineno}: {text!r}")
            continue
        seen.add(token)

    if bad:
        raise UniverseFileError(
            "malformed ticker entries — " + "; ".join(bad[:10])
            + (f" (and {len(bad) - 10} more)" if len(bad) > 10 else "")
        )
    return tuple(sorted(seen))


def universe_digest(tickers: tuple[str, ...]) -> str:
    """SHA-256 over the normalised ticker list.

    Hashed from the *normalised* list rather than the raw bytes, so reformatting the file —
    reordering lines, editing a comment, changing the trailing newline — leaves the version
    alone. Only the set of tickers moves it.
    """
    payload = "\n".join(tickers).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_universe_file(path: Path | str | None = None) -> UniverseFile:
    """Read and normalise the universe file. ``None`` uses the repo default."""
    target = Path(path) if path is not None else UNIVERSE_FILE
    if not target.is_file():
        raise UniverseFileError(f"universe file not found: {target}")

    tickers = normalise_tickers(target.read_text(encoding="utf-8").splitlines())
    if not tickers:
        raise UniverseFileError(f"universe file contains no tickers: {target}")

    digest = universe_digest(tickers)
    return UniverseFile(
        path=target.resolve(),
        tickers=tickers,
        sha256=digest,
        version=f"u{digest[:8]}",
    )


def resolve_universe(
    explicit: str | None = None, universe_file: Path | str | None = None
) -> UniverseFile:
    """Resolve which tickers to run on: explicit list first, else the file.

    There is deliberately **no** fallback to the database. A silent fallback is what made the
    old design ambiguous — a run could quietly use a different universe than the one the
    operator thought they had specified.
    """
    if explicit:
        tickers = normalise_tickers(explicit.replace(",", " ").split())
        if not tickers:
            raise UniverseFileError(f"--tickers given but resolved to nothing: {explicit!r}")
        digest = universe_digest(tickers)
        return UniverseFile(
            path=Path("<explicit>"),
            tickers=tickers,
            sha256=digest,
            version=f"u{digest[:8]}",
        )
    return read_universe_file(universe_file)


# ---------------------------------------------------------------------------
# Research-universe derivation (D-12) — a one-off query, not a per-run step
# ---------------------------------------------------------------------------


def derive_research_universe(
    tickers: Sequence[str],
    years: Sequence[int],
    *,
    index_symbol: str = _RESEARCH_INDEX_SYMBOL,
    source: str = _RESEARCH_SOURCE,
    reader: Any = None,
) -> tuple[tuple[str, ...], dict[str, list[int]]]:
    """Which tickers have a return on every session of every given year, and why the rest don't.

    A pure query over a :class:`~pipelines.storage.ports.BarSource` — no file is written here.
    The CLI below only prints the result; promoting it into ``list_stocks_research.txt`` is a
    deliberate, separate, manual step, so the frozen research universe never silently drifts
    when more data lands (see that file's own header).

    Returns ``(kept, excluded)`` where ``kept`` is sorted ascending and ``excluded`` maps each
    dropped ticker to the list of years it cost a session in.
    """
    if reader is None:
        from pipelines.storage.factory import make_source  # noqa: PLC0415

        reader = make_source()

    missing_years: dict[str, list[int]] = {t: [] for t in tickers}
    for year in years:
        start, end = date(year, 1, 1), date(year, 12, 31)
        index_dates = set(reader.index_returns(index_symbol, start, end, source=source))
        ticker_returns = reader.daily_returns(list(tickers), start, end, source=source)
        for t in tickers:
            covered = len(index_dates & set(ticker_returns.get(t, {})))
            if covered < len(index_dates):
                missing_years[t].append(year)

    kept = tuple(sorted(t for t in tickers if not missing_years[t]))
    excluded = {t: yrs for t, yrs in missing_years.items() if yrs}
    return kept, excluded


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """``python -m pipelines.universe.file --check`` — read, normalise, and report."""
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.universe.file",
        description="Read and validate the universe file; print its version and contents.",
    )
    parser.add_argument("--check", action="store_true", help="Validate and summarise.")
    parser.add_argument("--file", default=None, metavar="PATH", help="Override the file path.")
    parser.add_argument("--list", action="store_true", help="Print every ticker, one per line.")
    parser.add_argument(
        "--derive-research-universe", action="store_true",
        help=(
            "Query storage (live data) for per-ticker session coverage across --years; print "
            "the subset with a return on every session of every year, plus why each excluded "
            "ticker was cut. Prints only — promoting the result into "
            "list_stocks_research.txt is a manual step (D-12)."
        ),
    )
    parser.add_argument(
        "--years", type=str, default="2021-2025", metavar="START-END",
        help="Inclusive year range for --derive-research-universe (default 2021-2025).",
    )
    args = parser.parse_args(argv)

    if args.derive_research_universe:
        try:
            uf = read_universe_file(args.file)
            start_y, end_y = (int(x) for x in args.years.split("-", 1))
            years = list(range(start_y, end_y + 1))
            kept, excluded = derive_research_universe(uf.tickers, years)
        except (UniverseFileError, ValueError) as exc:
            print(f"derive-research-universe FAILED — {exc}", file=sys.stderr)
            return 1
        print(f"years    : {years[0]}-{years[-1]}")
        print(f"input    : {uf.n} tickers ({uf.path})")
        print(f"kept     : {len(kept)} (full coverage every year)")
        print(f"excluded : {len(excluded)}")
        for t in sorted(excluded):
            print(f"  {t}: missing session(s) in {excluded[t]}")
        print()
        print(", ".join(kept))
        return 0

    try:
        uf = read_universe_file(args.file)
    except UniverseFileError as exc:
        print(f"universe FAILED — {exc}", file=sys.stderr)
        return 1

    print(f"path    : {uf.path}")
    print(f"tickers : {uf.n}")
    print(f"sha256  : {uf.sha256}")
    print(f"version : {uf.version}")
    if args.list:
        for t in uf.tickers:
            print(t)
    else:
        head = ", ".join(uf.tickers[:12])
        print(f"first 12: {head}{' …' if uf.n > 12 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
