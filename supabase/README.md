# supabase — database schema

Baseline migrations for the anchor model. Applied to an **empty** database, so every statement
is a plain `CREATE`; there is no migration path from the previous schema.

## Files

| File | Contents |
|---|---|
| `00001_reference.sql` | `stocks`, `universe_snapshots`, `universe_members`, `trading_calendar` |
| `00002_market_data.sql` | `staging.ohlc_raw`, `daily_bars`, `market_index_bars` |
| `00003_returns.sql` | `daily_returns`, `index_returns` |
| `00004_indicators.sql` | `technical_indicators_daily` — display only, never a model input |
| `00005_model_artifact.sql` | The frozen parameter set: `model_runs` and its six child tables |
| `00006_research.sql` | Stability study and measure comparison — report only |
| `00007_live_monitors.sql` | The daily apply path and its four monitors |
| `00008_operational.sql` | `pipeline_runs`, `data_quality_reports` |
| `00009_views.sql` | The read surface (`v_*`) the API and dashboard are limited to |

`_archive/` holds the 13 superseded pre-anchor migrations. They are **not** applied and could
not be: `00012` granted privileges on eleven tables that no migration on disk creates, so the
old set could never be applied to an empty database. They are kept as a record of what was
tried. See [`docs/00-project-status.md`](../docs/00-project-status.md) §3.

## Two things worth knowing before reading the schema

**Position is a stored fact, not a convention.** `universe_members.position` and
`model_universe.position` pin the ordering that every stored vector and matrix depends on. A
reordered universe silently misaligns everything, so the ordering is constrained in the
database rather than remembered by each writer.

**`P` is stored.** The superseded `00017` asserted the similarity matrix was not stored;
[`docs/04`](../docs/04-static-parameters.md) §2 and §6 say the opposite and price the full
matrix at under 100 KB. The spec wins. `X` and `E` genuinely are not stored — they are
recomputable from the returns and belong to a window, not to the data.

## Applying

```bash
python -m pipelines.common.db --check-schema-files
```

Then apply the files in numeric order with `supabase db push`, or individually with `psql -f`.

**Not yet verified against a live server.** The migrations pass a static structural check (FK,
index and view targets all resolve; no duplicate definitions; creation order valid), but have
not been applied to a real database. That check cannot catch a type error, a bad `CHECK`
expression, or a reserved-word collision — only applying them can.
