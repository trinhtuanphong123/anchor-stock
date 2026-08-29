"""API — FastAPI application entry point.

Read-only serving plane. It serves precomputed outputs only and never runs a model: the
anchor selection lives in ``pipelines`` and runs on a schedule, so there is no code path from
a request to the greedy algorithm (spec ``docs/04-static-parameters.md`` §5).

Routes, as of P9: ``/health``, ``/api/model/active``, ``/api/market/*`` (overview, sectors,
movers), ``/api/tickers/*`` (list, detail, history, indicators, analysis) and ``/api/anchors/*``
(D-18). ``/api/pipeline/status``, once planned here, was dropped in P9 (S1) — no consumer screen
exists, and ``/api/model/active`` already publishes freshness. The old Leiden-era routes were
archived separately (P8).

Every route reads a view (or, for ``/api/tickers/{t}/history``, ``/indicators`` and
``/analysis``, the two base tables ``00009_views.sql`` sanctions directly) and serialises it. The
one exception that computes anything is ``/api/tickers/{t}/analysis``'s narrative, and that logic
lives entirely in ``app.narrative``, not here. No route may import ``pipelines.anchors`` — that
is what keeps the "no path from a request to greedy" guard rail checkable by inspection rather
than by trust.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.connection import close_pool
from app.health import router as health_router
from app.routes._errors import register_exception_handlers
from app.routes.anchors import router as anchors_router
from app.routes.market import router as market_router
from app.routes.model import router as model_router
from app.routes.tickers import router as tickers_router
from app.runtime_guards import RuntimeConfig


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncGenerator[None]:
    """Shutdown only — startup deliberately does nothing.

    The connection pool is built by the first query, never at boot: ``test_45``/``test_46``/
    ``test_54`` assert that runtime validation and ``create_app()`` open no connection, and
    production startup depends on that staying true. Warming the pool here would break all three
    and would make a database outage a boot failure instead of a 503.

    On the way down, ``close_pool()`` hands the connections back rather than leaving the Supabase
    pooler to time them out. It is a no-op when no query ever ran.
    """
    yield
    close_pool()


def create_app(runtime_config: RuntimeConfig | None = None) -> FastAPI:
    """Construct the FastAPI app from freshly-resolved runtime configuration.

    When no ``runtime_config`` is injected, settings are resolved from the CURRENT
    environment at each call via ``load_runtime_settings()`` — never a module-level
    cache — so the production guards run against the live ``ENV`` (a process that
    imported under development and later sets ``ENV=production`` cannot bypass them).
    Tests may inject an immutable ``RuntimeConfig``. CORS uses only the validated
    allowed origins — in production these are supplied explicitly (no localhost
    default), and a wildcard is never combined with credentials.
    """
    if runtime_config is None:
        from app.config import load_runtime_settings  # noqa: PLC0415

        runtime_config = load_runtime_settings()

    app = FastAPI(
        title="Anchor Model API",
        description="Representative-ticker selection for the Vietnamese equity market.",
        version="0.2.0",
        lifespan=_lifespan,
    )

    # CORS — read-only browser access limited to the validated allowed origins, plus the
    # optional validated pattern for hosts that mint a fresh origin per deploy preview.
    # Starlette applies the pattern with `fullmatch`, so it is anchored at both ends.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_config.allowed_origins),
        allow_origin_regex=runtime_config.allowed_origin_regex,
        allow_credentials=runtime_config.cors_allow_credentials,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(model_router)
    app.include_router(market_router)
    app.include_router(tickers_router)
    app.include_router(anchors_router)

    # Stable error envelope for all failures.
    register_exception_handlers(app)
    return app


app = create_app()
