# pipelines — anchor model data and modelling steps

A **library of callable functions**, not a service. Local CLIs and (later) Airflow tasks call
the same entry points; nothing here starts a scheduler or owns a process lifecycle. That is
deliberate — everything an Airflow task will run is first exercised by a one-line local
command, so a DAG failure is always reproducible outside Airflow.

The method is specified in [`docs/01`](../docs/01-data-pipeline.md) through
[`docs/04`](../docs/04-static-parameters.md). Where code and spec disagree, the spec wins.

## Packages

| Package | Owns |
|---|---|
| `common/` | DB connection, upserts, log-return maths, quality reporting, path resolution |
| `universe/` | Reading the investable universe from `list_stocks.txt` and hashing it into a version |
| `ingestion/` | Fetching daily bars from the provider, landing the raw payload, normalising it |
| `returns/` | Persisting log-return series; assembling the aligned matrices `X` (T×N) and `f` (T) |
| `factor/` | One-factor OLS per ticker; residuals; the ρ² similarity matrix `P` |
| `anchors/` | The greedy submodular selection and the assignment readout |

Planned, not yet written: `storage/` (the local-vs-Postgres sink seam), `model/` (training,
dCor², apply), `artifact/` (the frozen parameter set and its validation), `indicators/`,
`research/`.

## Two tracks, one code path

The local train track and the dashboard track differ **only in where bytes land**. Throttled
fetch, raw-record construction, normalisation and quality checks are identical; the seam sits
at the write boundary (`storage/ports.py`) and is mirrored at the read boundary. A local raw
file is a line-serialisation of a `staging.ohlc_raw` row — same shape, different medium.

## Running things

Every module follows the same idiom: a `main()` reachable as `python -m pipelines.<module>`,
usually with `--mock` or `--selftest` so it needs neither network nor database.

```bash
python -m pipelines.universe.file --check
```

```bash
python -m pipelines.returns.matrix --mock
```

```bash
python -m pipelines.factor.model
```

```bash
python -m pipelines.anchors.greedy
```

```bash
python -m pipelines.common.db --check-schema-files
```

There is no test runner and no CI. These self-checks are the verification story; extend the
idiom rather than replacing it, and never report a command as passing when it does not exist.
