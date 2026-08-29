# services/api — FastAPI Backend

FastAPI application deployed to **Render** as a Web Service (P8, D-21). It reads Supabase as
`postgres` over `DATABASE_URL`, which after D-20 is the only path to the data.

Serves precomputed dashboard snapshots over the views in `supabase/migrations/`. No heavy
compute at request time, and no import path to `pipelines.anchors` (`docs/04` §5).

`uvicorn` must run with `services/api` as its working directory — `app/main.py` imports
`from app.health import …`, not `from services.api.app…`.

## Quick start

```bash
cd services/api
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Health check

```bash
curl http://localhost:8000/health
```

Expected response (no database configured):

```json
{"status": "ok", "service": "anchor-model-api", "database": "unconfigured", "time": "..."}
```

`/health` returns HTTP 200 whenever the process is alive; a database problem shows as
`"database": "error"` in the body, not as a non-200 status. A health check pointed at it
therefore monitors liveness only — deliberately, so a transient Supabase blip cannot
restart-loop the service.

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `DATABASE_URL` | In production | Supabase Postgres connection string. Use the **session pooler** host on port 5432: the direct `db.<ref>.supabase.co` endpoint is IPv6-only, and `db/connection.py` sets a read-only session characteristic that transaction pooling (6543) leaves to the proxy to replay rather than to this process to hold — see `render.yaml` for what was measured and why 5432 is still required. If missing outside production, `/health` reports `database: "unconfigured"`. |
| `ENV` | No | `development` (default), `test`, or `production`. `production` arms the startup guards in `runtime_guards.py`. |
| `ALLOWED_ORIGINS` | In production | Comma-separated CORS origins. Outside production it defaults to `http://localhost:3000` and `http://127.0.0.1:3000`; **in production, startup fails if it is empty.** |
| `API_DEV_FIXTURES` | No | Must stay unset/false in production — any truthy value is a fatal startup error. |

`ENVIRONMENT` is deliberately never read; `ENV` is the canonical name.

Create a `.env` file in `services/api/` or export the variables directly.
