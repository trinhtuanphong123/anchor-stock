"""Application settings loaded from environment variables.

All database fields are optional so the service starts even when
DB env vars are not configured.  Never expose raw connection strings
or secrets through API responses.

The interim canonical runtime-mode input is ``ENV`` (never ``ENVIRONMENT``).
Runtime settings are resolved **at application construction** via
:func:`load_runtime_settings` (see ``app.main.create_app``), NOT frozen at module
import — so each ``create_app()`` re-reads the current environment and re-runs the
production guards. Importing this module opens no database connection and
snapshots no runtime mode.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic_settings import BaseSettings

from app.runtime_guards import RuntimeConfig, resolve_runtime


class Settings(BaseSettings):
    """Minimal configuration — health metadata plus the runtime-guard inputs."""

    # Database (optional — missing → health reports "unconfigured")
    database_url: str | None = None

    # Service metadata
    service_name: str = "anchor-model-api"

    # Runtime-guard inputs. `env` is the ONLY runtime-mode variable;
    # `ENVIRONMENT` is intentionally not read.
    env: str = "development"
    api_dev_fixtures: str = ""
    allowed_origins: str = ""
    # Exact-match origins cannot enumerate a host that mints a fresh origin per deploy
    # preview; this is the pattern that admits them. Either input satisfies production.
    allowed_origin_regex: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton for request-time health/DB-URL/service-name reads (db.connection,
# health). It does NOT drive app construction or the production guards — those are
# resolved fresh per create_app() via load_runtime_settings().
settings = Settings()


def load_runtime_settings(environ: Mapping[str, str] | None = None) -> RuntimeConfig:
    """Resolve and validate the runtime configuration from the CURRENT environment.

    Called at application construction (never cached at module import), so each
    ``create_app()`` sees the current ``ENV``/``DATABASE_URL``/``API_DEV_FIXTURES``/
    ``ALLOWED_ORIGINS`` and re-runs the production guards (fail-fast,
    secret-safe, no DB connection). Pass an explicit ``environ`` mapping to inject
    immutable settings in tests; otherwise a fresh ``Settings()`` reads the live
    environment. ``ENVIRONMENT`` is never read.
    """
    if environ is None:
        source = Settings()  # fresh read of the current environment (+ .env)
        resolved_env = {
            "ENV": source.env,
            "DATABASE_URL": source.database_url,
            "API_DEV_FIXTURES": source.api_dev_fixtures,
            "ALLOWED_ORIGINS": source.allowed_origins,
            "ALLOWED_ORIGIN_REGEX": source.allowed_origin_regex,
        }
    else:
        resolved_env = {
            key: environ.get(key)
            for key in (
                "ENV",
                "DATABASE_URL",
                "API_DEV_FIXTURES",
                "ALLOWED_ORIGINS",
                "ALLOWED_ORIGIN_REGEX",
            )
        }
    return resolve_runtime(resolved_env)
