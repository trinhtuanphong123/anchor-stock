"""Production runtime guards for the anchor-model API.

Pure, side-effect-free configuration validation invoked once at application
construction. It reads only the interim canonical ``ENV`` runtime-mode input
(never ``ENVIRONMENT``) and, when ``ENV=production``, fails fast — before the API
serves any request — on an absent/blank/malformed ``DATABASE_URL``, a truthy
``API_DEV_FIXTURES``, missing/invalid ``ALLOWED_ORIGINS``/``ALLOWED_ORIGIN_REGEX``,
or a wildcard origin combined with credentials.

Boundaries: validation NEVER opens a database connection, and no error text or
log includes the database URL, credentials, tokens, SQL, or a stack trace. This
module has no import-time side effects.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

# Accepted normalized runtime modes. ``production`` is the only mode that enables
# production guards; a missing/blank ENV normalizes to the safe ``development``.
VALID_MODES = ("development", "test", "production")

# Truthy forms for API_DEV_FIXTURES (case-insensitive, trimmed). This is the
# single canonical definition; db.connection consumes it too.
_TRUTHY_FIXTURE_VALUES = ("1", "true", "yes", "on")

# Committed local-development CORS default (only used outside production).
DEV_DEFAULT_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")

_ALLOWED_ORIGIN_SCHEMES = ("http", "https")
_WILDCARD = "*"

# Probe origins used to detect an ALLOWED_ORIGIN_REGEX that admits anything at all.
# ``.invalid`` is reserved by RFC 2606 and can never be a real deployment origin, so a
# pattern matching either of these matches effectively every origin. Both schemes are
# probed because ``https://.*`` is as over-broad as ``.*`` and would slip a single probe.
#
# The hostname is deliberately lowercase letters only — no digit, no hyphen. The probe can
# only be matched by characters it actually contains, so a narrow alphabet is what lets a
# character-class wildcard like ``[a-z:/.]*`` be caught. Adding a hyphen here would quietly
# shrink the set of sloppy patterns this detects.
_OVERBROAD_PROBE_ORIGINS = (
    "https://overbroadprobe.invalid",
    "http://overbroadprobe.invalid",
)


class RuntimeConfigError(Exception):
    """Fatal, secret-safe startup configuration error.

    Raised before the API serves requests. The message is bounded and must never
    contain a database URL, credentials, tokens, SQL, or a stack trace.
    """


@dataclass(frozen=True)
class RuntimeConfig:
    """Immutable resolved runtime configuration (the canonical settings view)."""

    mode: str
    is_production: bool
    database_url: str | None
    dev_fixtures_enabled: bool
    allowed_origins: tuple[str, ...]
    allowed_origin_regex: str | None
    cors_allow_credentials: bool


def normalize_mode(raw: str | None) -> str:
    """Trim + lowercase ENV. Blank/missing → ``development``; unknown → error.

    A missing ENV must not silently mean production; it retains the committed safe
    development behavior. Any unrecognized non-empty value is a configuration error.
    """
    mode = (raw or "").strip().lower()
    if mode == "":
        return "development"
    if mode not in VALID_MODES:
        raise RuntimeConfigError(
            "ENV must be one of development, test, or production."
        )
    return mode


def is_truthy_fixture(raw: str | None) -> bool:
    """True when API_DEV_FIXTURES is a recognized truthy value (trimmed, lowercased)."""
    return (raw or "").strip().lower() in _TRUTHY_FIXTURE_VALUES


def _extract_port(parts, error_message: str) -> int | None:
    """Return the parsed port (``None`` if omitted) or raise a bounded error.

    ``urllib.parse.SplitResult.port`` raises ``ValueError`` for a non-integer or
    out-of-range (>65535) port; a parsed ``0`` is likewise rejected. The raw value
    is never echoed. Also traps malformed bracketed-host/IPv6 syntax safely.
    """
    try:
        port = parts.port
    except ValueError:
        raise RuntimeConfigError(error_message) from None
    if port is not None and not (1 <= port <= 65535):
        raise RuntimeConfigError(error_message)
    return port


def _validate_database_url(raw: str | None) -> str:
    """Structurally validate a production DATABASE_URL without connecting.

    Requires a non-blank value with a PostgreSQL scheme, a host, and — when
    present — a valid ``1..65535`` port. Never echoes the value or credentials in
    the error text and never opens a connection.
    """
    value = (raw or "").strip()
    if value == "":
        raise RuntimeConfigError(
            "DATABASE_URL is required in production but is missing or blank."
        )
    invalid = "DATABASE_URL is not a valid PostgreSQL connection URL."
    try:
        parts = urlsplit(value)
        hostname = parts.hostname  # can raise ValueError on malformed IPv6 brackets
    except ValueError:
        raise RuntimeConfigError(invalid) from None
    if parts.scheme not in ("postgresql", "postgres") or not hostname:
        raise RuntimeConfigError(invalid)
    _extract_port(parts, "DATABASE_URL has an invalid or out-of-range port.")
    return value


def _normalize_origin(origin: str) -> str:
    """Validate and normalize a single CORS origin (never echoes the raw value).

    Accepts ``*`` (wildcard) or an absolute http/https origin with a host, an
    optional valid ``1..65535`` port, and no user info, path, query, or fragment;
    normalizes to ``scheme://host[:port]`` (trailing slash dropped) so it matches
    the browser ``Origin`` header exactly.
    """
    raw = origin.strip()
    if raw == "":
        raise RuntimeConfigError("ALLOWED_ORIGINS contains an empty origin entry.")
    if raw == _WILDCARD:
        return _WILDCARD
    malformed = "ALLOWED_ORIGINS must contain absolute http/https origins."
    try:
        parts = urlsplit(raw)
        hostname = parts.hostname  # can raise ValueError on malformed IPv6 brackets
    except ValueError:
        raise RuntimeConfigError(malformed) from None
    if parts.scheme not in _ALLOWED_ORIGIN_SCHEMES or not parts.netloc or not hostname:
        raise RuntimeConfigError(malformed)
    if parts.username or parts.password:
        raise RuntimeConfigError("ALLOWED_ORIGINS origins must not contain user info.")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise RuntimeConfigError(
            "ALLOWED_ORIGINS origins must not contain a path, query, or fragment."
        )
    _extract_port(parts, "ALLOWED_ORIGINS contains an origin with an invalid port.")
    return f"{parts.scheme}://{parts.netloc}"


def parse_allowed_origins(raw: str | None) -> list[str]:
    """Parse a comma-separated ALLOWED_ORIGINS list into normalized origins.

    An empty/blank input yields ``[]``; malformed or empty entries raise.
    """
    value = (raw or "").strip()
    if value == "":
        return []
    return [_normalize_origin(chunk) for chunk in value.split(",")]


def parse_allowed_origin_regex(raw: str | None) -> str | None:
    """Validate ALLOWED_ORIGIN_REGEX and return it, or ``None`` when unset.

    **Why this exists.** ``ALLOWED_ORIGINS`` is an exact-match list, and a host that
    issues a fresh origin per deploy preview — ``https://<hash>--<site>.netlify.app``
    — can never be enumerated in one. Without a pattern every preview build renders
    ``api_not_configured`` on every panel, which reads as a broken deployment rather
    than as the CORS refusal it is.

    Only compilation is checked here; ``is_overbroad_origin_regex`` applies the
    breadth guard, because that one is conditional on mode and credentials.

    The pattern is never echoed in the error text. It is not a secret, but this
    module's contract is bounded messages that do not repeat their input, and one
    exception invites the next.
    """
    value = (raw or "").strip()
    if value == "":
        return None
    try:
        re.compile(value)
    except re.error:
        raise RuntimeConfigError(
            "ALLOWED_ORIGIN_REGEX is not a valid regular expression."
        ) from None
    return value


def is_overbroad_origin_regex(pattern: str) -> bool:
    """True when the pattern admits an origin no deployment could legitimately want.

    Matched with ``fullmatch`` because that is what Starlette's ``CORSMiddleware``
    uses (starlette 1.3.1, pinned in ``requirements-api.lock``) — testing with
    ``search`` here would reject patterns the middleware treats as anchored.

    **What this catches and what it does not.** It catches the total wildcards —
    ``.*``, ``.+``, ``https://.*`` — which are the shapes a hurried pattern actually
    takes. It does NOT catch a pattern that is broad *within* a shared domain:
    ``https://.*\\.netlify\\.app`` admits every site on netlify.app, including other
    people's. No probe can distinguish that from a legitimate wildcard subdomain, so
    scoping the pattern to the deployment's own site name stays the operator's job.
    """
    compiled = re.compile(pattern)
    return any(compiled.fullmatch(probe) for probe in _OVERBROAD_PROBE_ORIGINS)


def resolve_runtime(
    env: Mapping[str, str | None],
    *,
    cors_allow_credentials: bool = False,
) -> RuntimeConfig:
    """Resolve + validate the runtime configuration for the given environment.

    Reads only ``ENV``, ``DATABASE_URL``, ``API_DEV_FIXTURES``, ``ALLOWED_ORIGINS``
    and ``ALLOWED_ORIGIN_REGEX``. In production it fails fast on missing/invalid
    database URL, enabled fixtures, missing/invalid origins, an over-broad origin
    pattern, and wildcard-with-credentials. Outside production it retains the
    committed localhost default when no origins are configured. Opens no connection
    and echoes no secret.

    **Either origin input satisfies production.** A deployment that serves only
    preview builds has no fixed origin to list, so requiring the list specifically
    would force a placeholder entry that means nothing. What production forbids is
    configuring *neither*.
    """
    mode = normalize_mode(env.get("ENV"))
    is_production = mode == "production"
    raw_database_url = env.get("DATABASE_URL")
    fixtures_enabled = is_truthy_fixture(env.get("API_DEV_FIXTURES"))
    raw_origins = env.get("ALLOWED_ORIGINS")
    origin_regex = parse_allowed_origin_regex(env.get("ALLOWED_ORIGIN_REGEX"))

    if is_production:
        _validate_database_url(raw_database_url)
        if fixtures_enabled:
            raise RuntimeConfigError(
                "API_DEV_FIXTURES must be disabled in production."
            )
        origins = parse_allowed_origins(raw_origins)
        if not origins and origin_regex is None:
            raise RuntimeConfigError(
                "ALLOWED_ORIGINS or ALLOWED_ORIGIN_REGEX must be explicitly "
                "configured in production."
            )
    else:
        origins = parse_allowed_origins(raw_origins) or list(DEV_DEFAULT_ORIGINS)

    if _WILDCARD in origins and cors_allow_credentials:
        raise RuntimeConfigError(
            "A wildcard ALLOWED_ORIGINS cannot be combined with CORS credentials."
        )

    # An over-broad PATTERN is refused where a literal ``*`` would be accepted, and the
    # asymmetry is deliberate: ``ALLOWED_ORIGINS=*`` is a legible declaration that someone
    # meant to open the API, whereas a regex that happens to match everything is what a
    # mistyped pattern looks like. Anyone who genuinely wants open CORS still has the
    # wildcard. Enforced in production, and wherever credentials are on — the same two
    # places the wildcard rule already cares about.
    if origin_regex is not None and (is_production or cors_allow_credentials):
        if is_overbroad_origin_regex(origin_regex):
            raise RuntimeConfigError(
                "ALLOWED_ORIGIN_REGEX matches arbitrary origins; scope it to the "
                "deployment's own hostnames, or set ALLOWED_ORIGINS=* deliberately."
            )

    database_url = (raw_database_url or "").strip() or None
    return RuntimeConfig(
        mode=mode,
        is_production=is_production,
        database_url=database_url,
        dev_fixtures_enabled=fixtures_enabled,
        allowed_origins=tuple(origins),
        allowed_origin_regex=origin_regex,
        cors_allow_credentials=cors_allow_credentials,
    )
