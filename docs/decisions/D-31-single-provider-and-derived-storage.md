# D-31 — Back to one provider; the derived tables become views

**Status:** Decided, 2026-08-30 (P15). Supersedes [[D-30]] in *provider* (Netlify → Render); D-21's
static-hosting reasoning is retained unchanged for the third time. Also decides the P15 data-tier
reshape and the baseline-migration edit — bundled here rather than split into three records
because all three were argued and applied together, against the same clean infrastructure, in the
same pass.
**Affects:** `render.yaml` (both services, one file again); `netlify.toml` (deleted);
`supabase/migrations/00003_returns.sql`, `00004_indicators.sql`, `00013_market_home_views.sql`;
`pipelines/common/db.py` (`REQUIRED_TABLES`); `apps/web/src/lib/api.ts`
(`validateApiBaseUrl`/`joinApiUrl`).
**Related:** [[D-21]] (Render topology, static over web service), [[D-30]] (the Netlify split this
reverses), [[D-14]] (the asymmetric-mirror precedent P15 extends to returns), [[D-20]] (why `00011`
revoking `anon`/`authenticated` is load-bearing here too).

## Context

P15 rebuilds the deployment from nothing, on clean infrastructure: two stale Render services
pointed at the predecessor repository, an empty target Supabase project in Singapore
(`qhbfjgheeyckefcwtmcq`) sitting next to a full one in Sydney (`dxklhenmyzdzitgnmuwc`), and zero
Netlify projects — `netlify.toml` had been describing a site that never existed.

**The reader is one person, presenting.** That is the sizing input the rest of this record follows
from: the thing to optimise is the latency of one page load, not throughput, and every historical
argument for a second provider or a second server has to be re-weighed against that, not against
a product with traffic.

## Part 1 — One provider again

D-30's own record marked the Netlify choice **OPEN**: "why Netlify rather than Render's own Static
Site is not recorded, because it is not known," and named the evidence that would close it — one
sentence naming a property Netlify has that Render Static does not. That sentence was never
written. Meanwhile the split cost a real thing: a cross-reference that could only be closed by
hand, twice, after each side's first deploy — the site had to be *built* with the API's URL and
the API had to be *configured* with the site's origin before CORS would admit it.

**Alternatives.** (a) Leave it split, write the missing justification. Rejected — six months on,
still no reason exists; inventing one to keep a working setup is not what the OPEN marker is for.
(b) Collapse to one Render Static Site, restoring D-30's rejected alternative (a). Chosen.

**Decision: (b).** `render.yaml` declares both services again — `anchor-model-api` (Web Service)
and `anchor-model-web` (Static Site) — and `netlify.toml` is deleted. D-21's argument for a static
host over a second web service is unchanged by any of this: a Web Service serving static files can
spin down, a Static Site cannot, and that is still true regardless of which provider runs it.

**The cross-reference loop shrinks, not just moves.** The static site's `routes` rewrite
(`/api/* → https://anchor-model-api.onrender.com/api/*`) makes the browser call only its own
origin, so `apps/web` builds with a fixed `NEXT_PUBLIC_API_BASE_URL=/` that names no service and
needs no value filled in after either deploy. `apps/web/src/lib/api.ts`'s `validateApiBaseUrl` was
extended to accept a root-relative value as "same origin" (normalized to `""`); `joinApiUrl`
already resolved an empty base to a bare path and needed no change. `ALLOWED_ORIGINS` on the API
stays configured, `sync: false`, as the fallback — **whether a Render Static Site's rewrite can
proxy to another Render service's `*.onrender.com` host is not verified as this record is written**,
and Validation row 11 of the P15 plan is where that gets proved or disproved. If it does not hold,
the browser falls back to a real cross-origin call and CORS is what admits it.

**Cold start is fixed differently than D-21 left it.** D-21 shipped the API on Render's free plan
and relied on an UptimeRobot ping switched on before a demonstration. P15 buys `plan: starter`
instead — not for capacity (measured RSS is 65–74 MB against a 512 MB ceiling on both plans) but
for *not sleeping*, which is the one thing free cannot do and a presentation cannot work around.

## Part 2 — The derived tables become views, and eight tables are dropped

**The sizing that decided this.** Before P15, three tiers of data sat in the same schema at very
different weights:

| Tier | Rows | Size | Reproducible? |
|---|---|---|---|
| Source of record (`daily_bars`, `market_index_bars`, `stocks`, …) | 123k | 32 MB | No — only by refetching |
| Frozen model output (`model_*`) | 1.1k | 4 MB | Must not be — `docs/04` §5 forbids a request path reaching greedy |
| Derived (`daily_returns`, `index_returns`, `technical_indicators_daily`) | 243k | 112 MB | Yes — a pure function of tier 1 |

Tier 3 was 67% of the rows and 76% of the bytes, carrying no information tier 1 did not already
have.

**`daily_returns` / `index_returns` become VIEWs** over `daily_bars` / `market_index_bars`
(`supabase/migrations/00003_returns.sql`). This is not only a space saving — it retires a whole
class of bug a view cannot have. In P6.4 a fetch once succeeded while the returns rebuild was
*missed*, leaving a silent hole at the 2025/2026 boundary that only a boundary check caught. A
derived relation cannot fall behind the table it is derived from.

The one place this costs something is stated in the migration's own header rather than discovered
later: Postgres computes in `float8`, matching `pipelines/common/returns.py`'s Python float64
exactly on keys, `prev_close`, `at_limit` and `zero_volume`, but 0.2–0.45% of `log_return` values
differ from the old stored table by exactly 1 ULP — a `libm` difference between the Windows machine
that computed the table and Postgres's own `ln()`, not a divergence the view introduces. Measured
against the Sydney database before it was deleted, not assumed; see the migration file for the
isolated cause. Nothing the deployed system reads is on that path — no route selects from either
relation, and artifacts are loaded from disk, never retrained from a request.

**This extends, not breaks, an existing asymmetry.** `pipelines/storage/ports.py`'s `BarSink`
keeps writing both datasets on the **local** track (the research archive); the Postgres mirror does
not, because there is nothing left for it to write. D-14 already established exactly this shape for
`staging.ohlc_raw` — local writes it, Postgres does not — and `pipelines/storage/mirror.py`'s
`MIRRORED` tuple now excludes `DAILY_RETURNS`/`INDEX_RETURNS` on the same grounds, with a fake-sink
guard (mirroring D-14's `write_raw_bars` guard) asserting the Postgres path is never asked to write
them.

**Eight tables with no writer are dropped.** `00006_research` and `00007_live_monitors` held zero
rows and nothing in this repository — the research track that would have written them
(`pipelines/research/`) is not carried in this repository at all (D-29). Moved to
`supabase/migrations/_archive/`, numbers `00006`/`00007` left as a gap rather than renumbering the
rest, which would rewrite history to hide that something was withdrawn. One consequence this
forced and was not anticipated in the P15 plan: `v_active_group_health` LEFT JOINed onto
`live_coverage_monitor` and lost the seven drift columns that join supplied — they were NULL on
every row forever, a permanent state the LEFT JOIN dressed up as "no data yet." The group's real
figures from `model_groups` remain; the seven columns are gone, not nulled.

**The 31 indicator columns become `double precision`.** They were `numeric`, which forced a
`float64 → numeric → Decimal → float` round trip on every write and read
(`pipelines/storage/pg.py`'s `_f()` existed specifically to undo it). `double precision` is what
the values already were before Postgres received them; every `CHECK` constraint is preserved.
Measured effect: ~94 MB → ~30 MB for this table alone. `technical_indicators_daily` stays a table,
not a view — unlike returns it does not have a comparably cheap live-computable form — but its
`COMMENT ON TABLE` now says plainly that it is a cache, derived entirely from `daily_bars`, and
rebuildable with `pipelines.indicators.build`.

## Part 3 — Editing the baseline migrations in place

`00003`/`00004`/`00009`/`00012`/`00013` were edited directly rather than patched with a new
migration on top. **This is defensible only because it was checked, not assumed:**
`supabase_migrations.schema_migrations` was empty on *both* Supabase projects before P15 — Sydney's
schema had been applied by hand, same as Singapore's was about to be — so there was no recorded
migration history anywhere to preserve. Once `apply_migration` ran the eleven files against
Singapore and `schema_migrations` gained its 11 rows, that door closed: every change from here
forward is a new migration, never an edit to `00001`–`00013`.

## Consequences

**`docs/RUNBOOK.md` lost its two biggest caveats.** "Supabase's schema is applied by hand, with no
recorded procedure" is gone — replaced by the same `apply_migration` sequence this record used.
"`--storage pg` against Supabase is NOT a routine step" (the ten-hour `executemany` warning) is gone
— `pipelines/common/upsert.py`'s six `upsert_*` functions now submit through
`psycopg2.extras.execute_values` (`page_size=500`), a separate but simultaneous P15 change (B1) that
this rebuild depended on to be practical at all: reloading 120k+ rows through the old per-row path
was the thing blocking the rebuild from happening.

**A second Supabase region stopped being a cost.** Render's Singapore region and Supabase's new
project are now the same region (`ap-southeast-1`), where before (Sydney, `ap-southeast-2`) every
query paid an extra network leg — measured at ~450 ms/request at steady state before this record.

## Verified

`docs/plans/active/p15-deployment-rebuild.md` carries the row-by-row Validation table this record's
claims are checked against, including the row that matters most for a defence — no cold start
after 30 minutes idle — and the row that had to run before the Sydney project could be deleted: the
returns views cross-checked row-for-row against the old stored tables.
