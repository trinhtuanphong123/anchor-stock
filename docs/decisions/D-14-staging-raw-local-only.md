# D-14 — `staging.ohlc_raw` is local-track only

**Status:** Decided, 2026-08-18 (recorded retroactively — the choice was made and acted on in P6)
**Affects:** `pipelines/storage/mirror.py` (`MIRRORED` deliberately excludes the raw datasets);
`supabase/migrations/00002_market_data.sql` (`staging.ohlc_raw`, applied and empty);
`pipelines/storage/localfs.py`'s "four asymmetries" docstring.

## Context

P0 gave the pipeline a raw landing zone: every provider payload is stored verbatim before it is
parsed, so a parse bug can be re-run against the bytes actually received rather than against a
refetch that may return different data. Locally that is `data/raw/{EQUITY,INDEX}/<SYM>.jsonl.gz`;
in Postgres it is `staging.ohlc_raw`, keyed `(symbol, bar_type, bar_date)`.

P6 mirrored the local track into Postgres. The question was whether raw payloads should cross
too.

## Alternatives

**(a) Mirror raw as well.** Restores the audit trail on the database side. Costs: ~139k JSON
payloads of provider text in a database nothing serving reads; a second read path in
`mirror.py` (raw goes through `raw_bars()`, not the generic `read_records()`); and it forces
resolution of the `provider` divergence below rather than allowing it to be documented.

**(b) Raw stays local; Postgres holds only typed data.** Chosen.

## Decision

`staging.ohlc_raw` is a **local-track artefact**. `MIRRORED` in `pipelines/storage/mirror.py`
lists only typed datasets, and `mirror.py`'s fake sink asserts in its selftest that
`write_raw_bars` is never called. The Postgres table stays applied and empty, for the same
reason the `live_*` tables do ([[D-13]]): the schema is specified, and deleting it would put the
schema at odds with the specification.

## Why

The audit trail's purpose is *re-parsing*, and re-parsing happens on the machine that trains the
model. The dashboard never re-parses anything — it reads typed rows. Copying the payloads into
Postgres would satisfy a symmetry that nothing needs at the cost of a second read path across
the storage seam, in a module whose entire value is that it has exactly one.

## The divergence this decision contains

`staging.ohlc_raw` has a `provider` column filled by a **schema default**, which no record dict
supplies. The local JSONL files therefore have no counterpart to it: a local raw record and a
Postgres raw row differ by one column.

This was found in P6 (as "latent bug #5"). It is **documented rather than fixed**, and this
record is where it is documented. Fixing it means adding `provider` to the raw record dicts,
which means rewriting 101 local raw shards — for a column that, under this decision, nothing
will ever read, because the rows it belongs to are never written to Postgres at all.

The divergence is therefore **contained by this decision**, not merely tolerated: it can only
become visible if `staging.ohlc_raw` starts receiving rows, and that is precisely the change
that would reverse this record. Whoever makes it inherits the column as the first thing to fix.

P6 verified the containment directly: `staging.ohlc_raw` held 0 rows after the mirror.
