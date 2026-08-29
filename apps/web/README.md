# apps/web — Frontend Dashboard

Next.js application published as a **Render Static Site** (P8, D-21). `next.config.ts` sets
`output: 'export'`, so `npm run build` emits a static `out/` directory rather than a server —
which is why it costs no instance-hours and never sleeps.

Reads precomputed snapshots from the FastAPI backend API. It holds no credentials of any kind;
per D-20, the Supabase service-role key must never reach this package.

## Quick start

```bash
cd apps/web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the dashboard shell.

## Build & lint

```bash
npm run lint
npm run build
```

## Environment variables

Create a `.env.local` file (or copy from `.env.example`):

| Variable | Required | Description |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | For any deployed build | FastAPI backend URL (e.g. `http://localhost:8000`). |

Only `NEXT_PUBLIC_*` variables are exposed to the browser. No secrets are included.

**Two things about this variable that are easy to get wrong.**

It is **inlined at build time**, not read at runtime — `lib/api.ts` reads it as a literal
`process.env.NEXT_PUBLIC_API_BASE_URL` member expression precisely so Next can substitute it
into the bundle. Changing it on the host after a successful build does nothing until a rebuild.

And **mock fallback only happens in local mode.** `next build` sets `NODE_ENV=production`, which
`classifyRuntimeMode` classifies as production-like, and a production-like build with no base
URL renders an `api_not_configured` error rather than mock data. That is deliberate — a
misconfigured deployment should look broken, not look real — but it means the variable is
mandatory for anything you deploy.

## Connecting to the backend

1. Start the FastAPI backend: `cd services/api && uvicorn app.main:app --port 8000`
2. Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` in `.env.local`
3. Start the frontend: `npm run dev`
4. The health card will show live backend status.
