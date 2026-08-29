# anchor-stock

Anchor-ticker selection for the Vietnamese equity market (HOSE). A small set of **anchor**
tickers is chosen to represent a ~100-ticker universe by maximising a coverage objective over a
residual-similarity matrix, and the result is served as a dashboard.

```
adjusted closes → log returns → one-factor OLS on VNINDEX → residuals E
    → P = corr(E) ∘ corr(E)        (ρ², non-negative)
    → greedy submodular maximisation of  F(S) = Σ_i max_{j∈S} P_ij
    → anchor set S, assignment a(i), coverage c_i, marginal-gain curve Δ
```

**Read [`AGENTS.md`](AGENTS.md) before changing anything** — it carries the orientation, the
invariants that are easy to break silently, and the working rules. The authoritative
specification is `docs/01`–`docs/04`; where code and spec disagree, the spec wins.

## Shape

| Path | What it is |
|---|---|
| `pipelines/` | Library of callable steps — ingestion, returns, factor model, greedy, artifacts |
| `services/api/` | FastAPI read layer over Supabase. Deployed to Render (`render.yaml`) |
| `apps/web/` | Next.js dashboard, statically exported. Deployed to Render (`render.yaml`) |
| `supabase/migrations/` | Schema baseline, `00001`–`00013` |
| `docs/` | Specs, decision records, plans, runbook — tracked (D-29) |

## Running the checks

Everything below runs offline. No database, no network, no credentials.

```bash
ruff check .
python scripts/check_locks.py
PYTHONPATH=services/api python -m unittest discover -s services/api/tests -t services/api/tests
npm --prefix apps/web ci && npm --prefix apps/web run test
python -m pipelines.anchors.greedy
```

CI runs all of these plus the full pipeline self-check matrix — see `.github/workflows/ci.yml`.
The `services/api` suite is stdlib `unittest`, not pytest, deliberately; `AGENTS.md` §Verification
explains why that is load-bearing rather than stylistic.

## Rebuilding the data

`docs/RUNBOOK.md` rebuilds the database from empty. It is honest about which of its steps are
scripted and which are still by hand — read §0 and §5 before starting, not after.

## What is not here

The research track — `pipelines/research/` (the A–G method studies), `data/research/`, and nine of
the ten artifacts — lives in the author's working copy, not in this repository. Documents under
`docs/` cite it and those citations point outside; no code depends on it. The reasoning is in
[D-29](docs/decisions/D-29-private-repository-carries-system-and-documents.md).
