"""API runtime guards — focused tests.

Standard-library ``unittest`` only (no pytest, no new dependency). Exercises the
production runtime guards, the CORS origin contract, the health field contract,
and read-only / import safety at the real settings/application boundaries — not
duplicate helper predicates.

CORS header behavior is asserted through a tiny dependency-free ASGI harness
(``httpx``/``TestClient`` is intentionally not a project dependency): OPTIONS
preflights short-circuit in the CORS middleware before routing, and dev ``/health``
GETs never open a DB connection (no ``DATABASE_URL``), so no test touches a database.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

# Force a clean, non-production test process so importing the API package never
# trips the production guards on an ambient ENV=production (real assertions below
# pass explicit environments to resolve_runtime / create_app).
os.environ["ENV"] = "test"

# services/api makes ``app.*`` importable (matches the uvicorn cwd).
API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app import config  # noqa: E402
from app.config import load_runtime_settings  # noqa: E402
from app.db import connection  # noqa: E402
from app.health import health_check  # noqa: E402
from app.main import create_app  # noqa: E402
from app.runtime_guards import (  # noqa: E402
    DEV_DEFAULT_ORIGINS,
    RuntimeConfigError,
    is_overbroad_origin_regex,
    is_truthy_fixture,
    normalize_mode,
    parse_allowed_origin_regex,
    parse_allowed_origins,
    resolve_runtime,
)


def _prod_env(**overrides):
    """A valid baseline production environment; override individual keys per case."""
    env = {
        "ENV": "production",
        "DATABASE_URL": "postgresql://user:pass@db.internal:5432/anchor",
        "ALLOWED_ORIGINS": "https://app.example.invalid",
        "API_DEV_FIXTURES": "0",
    }
    env.update(overrides)
    return env


async def _call_asgi(app, method, path, headers):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 80),
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)

    status = None
    resp_headers: dict[str, str] = {}
    body = b""
    for message in messages:
        if message["type"] == "http.response.start":
            status = message["status"]
            for key, value in message.get("headers", []):
                resp_headers[key.decode("latin-1").lower()] = value.decode("latin-1")
        elif message["type"] == "http.response.body":
            body += message.get("body", b"") or b""
    return status, resp_headers, body


def call_asgi(app, method, path, headers):
    return asyncio.run(_call_asgi(app, method, path, headers))


class RuntimeModeTests(unittest.TestCase):
    def test_01_production_activates_guards(self):
        cfg = resolve_runtime(_prod_env())
        self.assertEqual(cfg.mode, "production")
        self.assertTrue(cfg.is_production)
        # Guards are active: an otherwise-valid production env with fixtures on fails.
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(API_DEV_FIXTURES="1"))

    def test_02_uppercase_and_whitespace_normalize(self):
        self.assertEqual(normalize_mode("  Production "), "production")
        self.assertEqual(normalize_mode(" TEST "), "test")
        self.assertTrue(resolve_runtime(_prod_env(ENV="  PRODUCTION ")).is_production)

    def test_03_development_is_non_production(self):
        cfg = resolve_runtime({"ENV": "development"})
        self.assertEqual(cfg.mode, "development")
        self.assertFalse(cfg.is_production)

    def test_04_test_is_non_production(self):
        cfg = resolve_runtime({"ENV": "test"})
        self.assertEqual(cfg.mode, "test")
        self.assertFalse(cfg.is_production)

    def test_05_missing_env_is_safe_non_production(self):
        self.assertEqual(normalize_mode(None), "development")
        cfg = resolve_runtime({})
        self.assertFalse(cfg.is_production)
        self.assertEqual(cfg.allowed_origins, DEV_DEFAULT_ORIGINS)

    def test_06_blank_env_is_safe_non_production(self):
        self.assertEqual(normalize_mode("   "), "development")
        self.assertFalse(resolve_runtime({"ENV": "  "}).is_production)

    def test_07_unknown_env_fails(self):
        with self.assertRaises(RuntimeConfigError):
            normalize_mode("staging")
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime({"ENV": "staging"})

    def test_08_environment_variable_is_ignored(self):
        # ENVIRONMENT must not be read; only ENV drives mode.
        cfg = resolve_runtime({"ENVIRONMENT": "production"})
        self.assertFalse(cfg.is_production)
        self.assertEqual(cfg.mode, "development")


class DatabaseGuardTests(unittest.TestCase):
    def test_09_production_missing_database_url_fails(self):
        env = _prod_env()
        del env["DATABASE_URL"]
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(env)

    def test_10_production_blank_database_url_fails(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(DATABASE_URL=""))

    def test_11_production_whitespace_database_url_fails(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(DATABASE_URL="   "))

    def test_12_valid_production_url_accepted_without_connection(self):
        cfg = resolve_runtime(_prod_env())
        self.assertTrue(cfg.is_production)
        self.assertEqual(cfg.database_url, "postgresql://user:pass@db.internal:5432/anchor")

    def test_13_error_text_hides_credentials_and_url(self):
        env = _prod_env(DATABASE_URL="postgresql://admin:SuperSecret123@")  # malformed: no host
        with self.assertRaises(RuntimeConfigError) as ctx:
            resolve_runtime(env)
        msg = str(ctx.exception)
        self.assertNotIn("SuperSecret123", msg)
        self.assertNotIn("admin", msg)
        self.assertNotIn("postgresql://", msg)

    # --- Blocker 2: DATABASE_URL port validation -------------------------------

    def test_13a_non_integer_port_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(DATABASE_URL="postgresql://host:notaport/db"))

    def test_13b_zero_port_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(DATABASE_URL="postgresql://host:0/db"))

    def test_13c_out_of_range_port_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(DATABASE_URL="postgresql://host:65536/db"))

    def test_13d_valid_port_accepted(self):
        cfg = resolve_runtime(_prod_env(DATABASE_URL="postgresql://host:5432/db"))
        self.assertTrue(cfg.is_production)
        self.assertEqual(cfg.database_url, "postgresql://host:5432/db")

    def test_13e_malformed_ipv6_bracket_rejected_safely(self):
        # A bracketed IPv6 host with a bad port must raise the bounded config error,
        # never an unhandled ValueError.
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(DATABASE_URL="postgresql://[::1]:notaport/db"))

    def test_13f_port_error_text_hides_url(self):
        with self.assertRaises(RuntimeConfigError) as ctx:
            resolve_runtime(_prod_env(DATABASE_URL="postgresql://svc:TopSecret@host:notaport/db"))
        msg = str(ctx.exception)
        self.assertNotIn("TopSecret", msg)
        self.assertNotIn("notaport", msg)
        self.assertNotIn("postgresql://", msg)


class FixtureGuardTests(unittest.TestCase):
    def test_14_production_fixtures_1_fails(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(API_DEV_FIXTURES="1"))

    def test_15_production_fixtures_true_fails(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(API_DEV_FIXTURES="true"))

    def test_16_production_fixtures_yes_fails(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(API_DEV_FIXTURES="yes"))

    def test_17_production_fixtures_on_fails(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(API_DEV_FIXTURES="on"))

    def test_18_truthy_case_whitespace_variants_fail(self):
        for value in (" TRUE ", "On", " YeS", "1 "):
            self.assertTrue(is_truthy_fixture(value))
            with self.assertRaises(RuntimeConfigError):
                resolve_runtime(_prod_env(API_DEV_FIXTURES=value))

    def test_19_production_falsy_remains_disabled(self):
        for value in ("0", "false", "off", "no", ""):
            cfg = resolve_runtime(_prod_env(API_DEV_FIXTURES=value))
            self.assertFalse(cfg.dev_fixtures_enabled)

    def test_20_development_fixture_mode_available(self):
        cfg = resolve_runtime({"ENV": "development", "API_DEV_FIXTURES": "1"})
        self.assertTrue(cfg.dev_fixtures_enabled)

    def test_21_test_fixture_mode_available(self):
        cfg = resolve_runtime({"ENV": "test", "API_DEV_FIXTURES": "1"})
        self.assertTrue(cfg.dev_fixtures_enabled)


class OriginParsingTests(unittest.TestCase):
    def test_22_production_missing_origins_fails(self):
        env = _prod_env()
        del env["ALLOWED_ORIGINS"]
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(env)

    def test_23_production_blank_origins_fail(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(ALLOWED_ORIGINS="   "))

    def test_24_valid_comma_separated_origins_parse(self):
        self.assertEqual(
            parse_allowed_origins("https://a.example, https://b.example"),
            ["https://a.example", "https://b.example"],
        )

    def test_25_whitespace_trimmed(self):
        self.assertEqual(parse_allowed_origins("  https://a.example  "), ["https://a.example"])
        # A trailing slash normalizes to the browser Origin form (no slash).
        self.assertEqual(parse_allowed_origins("https://a.example/"), ["https://a.example"])

    def test_26_empty_list_entry_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            parse_allowed_origins("https://a.example,,https://b.example")

    def test_27_malformed_origin_rejected(self):
        for value in ("http://", "not a url", "https://"):
            with self.assertRaises(RuntimeConfigError):
                parse_allowed_origins(value)

    def test_28_relative_origin_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            parse_allowed_origins("/api/overview")

    def test_29_unsupported_scheme_rejected(self):
        for value in ("ftp://host", "ws://host", "file:///x"):
            with self.assertRaises(RuntimeConfigError):
                parse_allowed_origins(value)

    def test_30_origin_path_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            parse_allowed_origins("https://a.example/app")

    def test_31_origin_query_or_fragment_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            parse_allowed_origins("https://a.example?x=1")
        with self.assertRaises(RuntimeConfigError):
            parse_allowed_origins("https://a.example#frag")

    def test_32_wildcard_with_credentials_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime({"ENV": "development", "ALLOWED_ORIGINS": "*"},
                cors_allow_credentials=True)
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(ALLOWED_ORIGINS="*"), cors_allow_credentials=True)

    def test_33_production_has_no_localhost_default(self):
        cfg = resolve_runtime(_prod_env(ALLOWED_ORIGINS="https://app.example.invalid"))
        self.assertEqual(cfg.allowed_origins, ("https://app.example.invalid",))
        self.assertNotIn("http://localhost:3000", cfg.allowed_origins)

    def test_34_development_retains_localhost_defaults(self):
        cfg = resolve_runtime({"ENV": "development"})
        self.assertEqual(cfg.allowed_origins, DEV_DEFAULT_ORIGINS)

    # --- Blocker 3: CORS origin port validation --------------------------------

    def test_34a_non_integer_origin_port_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            parse_allowed_origins("https://app.example:notaport")

    def test_34b_zero_origin_port_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            parse_allowed_origins("https://app.example:0")

    def test_34c_out_of_range_origin_port_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            parse_allowed_origins("https://app.example:65536")

    def test_34d_valid_origin_ports_accepted(self):
        self.assertEqual(parse_allowed_origins("https://app.example:443"),
            ["https://app.example:443"])
        self.assertEqual(parse_allowed_origins("http://localhost:3000"), ["http://localhost:3000"])

    def test_34e_invalid_origin_port_fails_production_construction(self):
        # An invalid origin port must fail while resolving settings for the app —
        # before any CORS middleware is created with it. Both the pure resolver and
        # the construction-boundary loader reject it.
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(ALLOWED_ORIGINS="https://app.example:notaport"))
        with self.assertRaises(RuntimeConfigError):
            load_runtime_settings(
                {
                    "ENV": "production",
                    "DATABASE_URL": "postgresql://u:p@h:5432/d",
                    "ALLOWED_ORIGINS": "https://app.example:0",
                    "API_DEV_FIXTURES": "0",
                }
            )


class CorsBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev_app = create_app(resolve_runtime({"ENV": "development"}))
        cls.prod_app = create_app(resolve_runtime(_prod_env(ALLOWED_ORIGINS="https://app.example.invalid")))

    def test_35_allowed_origin_receives_matching_header(self):
        with mock.patch.object(config.settings, "database_url", None):
            status, headers, _ = call_asgi(
                self.dev_app, "GET", "/health", {"origin": "http://localhost:3000"}
            )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("access-control-allow-origin"), "http://localhost:3000")

    def test_36_foreign_origin_receives_no_matching_header(self):
        with mock.patch.object(config.settings, "database_url", None):
            _, headers, _ = call_asgi(
                self.dev_app, "GET", "/health", {"origin": "http://evil.invalid"}
            )
        self.assertNotEqual(headers.get("access-control-allow-origin"), "http://evil.invalid")
        self.assertNotIn("access-control-allow-origin", headers)

    def test_37_foreign_origin_needs_no_custom_rejection_status(self):
        with mock.patch.object(config.settings, "database_url", None):
            status, _, _ = call_asgi(
                self.dev_app, "GET", "/health", {"origin": "http://evil.invalid"}
            )
        # A simple cross-origin GET is not blocked server-side; the browser enforces it.
        self.assertEqual(status, 200)

    def test_38_preflight_for_allowed_production_origin_works(self):
        # OPTIONS preflight short-circuits in the CORS middleware (no routing, no DB).
        status, headers, _ = call_asgi(
            self.prod_app,
            "OPTIONS",
            "/api/overview",
            {
                "origin": "https://app.example.invalid",
                "access-control-request-method": "GET",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            headers.get("access-control-allow-origin"), "https://app.example.invalid"
        )

    def test_39_credentials_behavior_preserved(self):
        # Current contract: credentials are NOT enabled; the header must be absent.
        with mock.patch.object(config.settings, "database_url", None):
            _, headers, _ = call_asgi(
                self.dev_app, "GET", "/health", {"origin": "http://localhost:3000"}
            )
        self.assertNotEqual(headers.get("access-control-allow-credentials"), "true")


class OriginRegexTests(unittest.TestCase):
    """P14-G3 — ALLOWED_ORIGIN_REGEX, which exists for Netlify's deploy previews.

    A preview build is served from a fresh origin every deploy
    (``https://<hash>--<site>.netlify.app``), so an exact-match ``ALLOWED_ORIGINS``
    list cannot admit it and every preview renders ``api_not_configured`` on every
    panel. These assert that the pattern admits previews without admitting the web.
    """

    # A realistically-scoped Netlify preview pattern: this site, any deploy hash.
    PREVIEW_PATTERN = r"https://[0-9a-z]+--anchor-model-web\.netlify\.app"
    PREVIEW_ORIGIN = "https://deadbeef01--anchor-model-web.netlify.app"

    def test_73_regex_alone_satisfies_production(self):
        env = _prod_env(ALLOWED_ORIGIN_REGEX=self.PREVIEW_PATTERN)
        del env["ALLOWED_ORIGINS"]
        cfg = resolve_runtime(env)
        self.assertEqual(cfg.allowed_origins, ())
        self.assertEqual(cfg.allowed_origin_regex, self.PREVIEW_PATTERN)

    def test_74_production_with_neither_origin_input_still_fails(self):
        env = _prod_env()
        del env["ALLOWED_ORIGINS"]
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(env)
        # A blank pattern is not a configuration either.
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(ALLOWED_ORIGINS="", ALLOWED_ORIGIN_REGEX="   "))

    def test_75_uncompilable_regex_rejected(self):
        with self.assertRaises(RuntimeConfigError):
            parse_allowed_origin_regex("https://[unclosed")
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(_prod_env(ALLOWED_ORIGIN_REGEX="*(bad"))

    def test_76_absent_or_blank_regex_is_none(self):
        self.assertIsNone(parse_allowed_origin_regex(None))
        self.assertIsNone(parse_allowed_origin_regex("   "))
        self.assertIsNone(resolve_runtime(_prod_env()).allowed_origin_regex)

    def test_77_overbroad_regex_rejected_in_production(self):
        for pattern in (".*", ".+", "https://.*", "http://.*", "[a-z:/.]*"):
            with self.subTest(pattern=pattern):
                self.assertTrue(is_overbroad_origin_regex(pattern))
                with self.assertRaises(RuntimeConfigError):
                    resolve_runtime(_prod_env(ALLOWED_ORIGIN_REGEX=pattern))

    def test_78_overbroad_regex_rejected_with_credentials_outside_production(self):
        with self.assertRaises(RuntimeConfigError):
            resolve_runtime(
                {"ENV": "development", "ALLOWED_ORIGIN_REGEX": ".*"},
                cors_allow_credentials=True,
            )

    def test_79_scoped_regex_is_not_overbroad(self):
        # The guard must not fire on the pattern it exists to permit.
        self.assertFalse(is_overbroad_origin_regex(self.PREVIEW_PATTERN))
        cfg = resolve_runtime(_prod_env(ALLOWED_ORIGIN_REGEX=self.PREVIEW_PATTERN))
        self.assertEqual(cfg.allowed_origin_regex, self.PREVIEW_PATTERN)

    def test_80_list_and_regex_coexist(self):
        cfg = resolve_runtime(
            _prod_env(
                ALLOWED_ORIGINS="https://app.example.invalid",
                ALLOWED_ORIGIN_REGEX=self.PREVIEW_PATTERN,
            )
        )
        self.assertEqual(cfg.allowed_origins, ("https://app.example.invalid",))
        self.assertEqual(cfg.allowed_origin_regex, self.PREVIEW_PATTERN)

    def test_81_error_text_does_not_echo_the_pattern(self):
        with self.assertRaises(RuntimeConfigError) as caught:
            resolve_runtime(_prod_env(ALLOWED_ORIGIN_REGEX="https://(secret-site.*"))
        self.assertNotIn("secret-site", str(caught.exception))

    def test_82_load_runtime_settings_reads_the_regex_from_the_environment(self):
        cfg = load_runtime_settings(
            {
                "ENV": "production",
                "DATABASE_URL": "postgresql://u:p@h:5432/d",
                "ALLOWED_ORIGINS": "",
                "ALLOWED_ORIGIN_REGEX": self.PREVIEW_PATTERN,
                "API_DEV_FIXTURES": "0",
            }
        )
        self.assertEqual(cfg.allowed_origin_regex, self.PREVIEW_PATTERN)

    # --- Behaviour at the middleware, not just at the resolver -----------------

    def _preview_app(self):
        env = _prod_env(ALLOWED_ORIGIN_REGEX=self.PREVIEW_PATTERN)
        del env["ALLOWED_ORIGINS"]
        return create_app(resolve_runtime(env))

    def _preflight(self, app, origin):
        return call_asgi(
            app,
            "OPTIONS",
            "/api/overview",
            {"origin": origin, "access-control-request-method": "GET"},
        )

    def test_83_a_preview_origin_is_admitted(self):
        status, headers, _ = self._preflight(self._preview_app(), self.PREVIEW_ORIGIN)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("access-control-allow-origin"), self.PREVIEW_ORIGIN)

    def test_84_a_foreign_origin_is_still_refused(self):
        _, headers, _ = self._preflight(self._preview_app(), "https://evil.invalid")
        self.assertNotIn("access-control-allow-origin", headers)

    def test_85_the_pattern_is_anchored_at_both_ends(self):
        # Starlette matches with fullmatch; a suffix-extended lookalike must not pass.
        # This is the attack a `search`-based match would let through.
        app = self._preview_app()
        for origin in (
            self.PREVIEW_ORIGIN + ".evil.invalid",
            "https://evil.invalid/" + self.PREVIEW_ORIGIN,
            "http://deadbeef01--anchor-model-web.netlify.app",
        ):
            with self.subTest(origin=origin):
                _, headers, _ = self._preflight(app, origin)
                self.assertNotIn("access-control-allow-origin", headers)


class HealthContractTests(unittest.TestCase):
    def _health_body(self):
        with mock.patch.object(config.settings, "database_url", None):
            return asyncio.run(health_check())

    def test_40_health_contains_database(self):
        self.assertIn("database", self._health_body())

    def test_41_health_does_not_expose_db(self):
        self.assertNotIn("db", self._health_body())

    def test_42_health_output_has_no_secrets(self):
        body = self._health_body()
        for value in body.values():
            if isinstance(value, str):
                self.assertNotIn("://", value)
                self.assertNotIn("password", value.lower())

    def test_43_health_shape_matches_contract(self):
        body = self._health_body()
        self.assertEqual(body.get("status"), "ok")
        for field in ("status", "database", "time"):
            self.assertIn(field, body)


def _db_url():
    """Patch in a syntactically valid URL so the pool builds without a real database."""
    return mock.patch.object(config.settings, "database_url", "postgresql://u:p@h:5432/d")


def _fake_conn():
    """A stand-in psycopg2 connection realistic enough for the pool to accept it back.

    ``closed`` and ``info.transaction_status`` are what ``_putconn`` inspects to decide between
    pooling, rolling back, and discarding — a bare ``MagicMock`` reads as "already closed" and is
    silently dropped, which would make retention tests pass for the wrong reason.

    ``readonly`` starts unset and is flipped by ``set_session``, mirroring psycopg2's own local
    record of the session characteristic.
    """
    import psycopg2  # noqa: PLC0415

    conn = mock.MagicMock()
    conn.closed = False
    conn.readonly = None
    conn.info.transaction_status = psycopg2.extensions.TRANSACTION_STATUS_IDLE

    def set_session(readonly=None, **_kwargs):
        if readonly is not None:
            conn.readonly = readonly

    conn.set_session.side_effect = set_session
    return conn


def _cursor_of(conn):
    """The cursor object ``read_cursor``'s ``with conn.cursor(...) as cur`` actually yields."""
    return conn.cursor.return_value.__enter__.return_value


async def _drive_lifespan(app):
    """Run the ASGI lifespan protocol (startup then shutdown) and return what the app sent."""
    events = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    sent: list[dict] = []

    async def receive():
        return events.pop(0)

    async def send(message):
        sent.append(message)

    await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)
    return sent


class DbAndImportSafetyTests(unittest.TestCase):
    def setUp(self):
        # The pool is a process-wide singleton created on first use; reset it so no test
        # inherits another's pool (or its fake connection) and so these tests never create one
        # they are not asserting against.
        connection.close_pool()

    def tearDown(self):
        connection.close_pool()

    def test_44_api_db_cursor_is_read_only(self):
        fake_conn = mock.MagicMock()
        with mock.patch.object(config.settings, "database_url", "postgresql://u:p@h:5432/d"):
            with mock.patch("psycopg2.connect", return_value=fake_conn) as connect:
                with connection.read_cursor():
                    pass
        connect.assert_called_once()
        fake_conn.set_session.assert_called_once_with(readonly=True)

    def test_54_pool_is_lazy_no_connection_before_first_use(self):
        # App construction must neither open a connection nor so much as build the pool object
        # (extends test_46: the lazy pool is created only when a query actually runs, and the
        # lifespan's startup half deliberately does nothing).
        connection._POOL = None
        with mock.patch(
            "psycopg2.connect",
            side_effect=AssertionError("must not connect before first use"),
        ):
            app = create_app(resolve_runtime({"ENV": "development"}))
        self.assertEqual(app.title, "Anchor Model API")
        self.assertIsNone(connection._POOL)

    def test_55_pool_reuses_one_connection_across_sequential_checkouts(self):
        # Five sequential checkouts share ONE connection: the pool is built on first use and the
        # connection goes back into it each time instead of being closed.
        fake_conn = _fake_conn()
        with _db_url(), mock.patch("psycopg2.connect", return_value=fake_conn) as connect:
            for _ in range(5):
                with connection.read_cursor():
                    pass
        connect.assert_called_once()
        self.assertFalse(fake_conn.close.called, "a pooled connection must not be closed")

    def test_56_pool_retains_every_connection_it_opens(self):
        # THE regression test for this change. The uncommitted patch this replaced used
        # psycopg2's ThreadedConnectionPool(1, 10), where `minconn` is a RETENTION CEILING rather
        # than a growth floor: it kept exactly one connection and closed the rest. Over five page
        # loads of four parallel requests it opened 16 connections and discarded 15.
        #
        # The property asserted here is the one that matters and is independent of any pool
        # implementation: grow to the observed concurrent peak, then stop handshaking.
        conns = []

        def factory(*_a, **_k):
            conns.append(_fake_conn())
            return conns[-1]

        def one_checkout():
            with connection.read_cursor():
                time.sleep(0.02)  # hold it, so the four in a round really do overlap

        with _db_url(), mock.patch("psycopg2.connect", side_effect=factory) as connect:
            for _ in range(5):  # five page loads
                threads = [threading.Thread(target=one_checkout) for _ in range(4)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

        self.assertEqual(
            connect.call_count, 4,
            "the pool must grow to the concurrent peak and then stop handshaking",
        )
        self.assertEqual(
            [c for c in conns if c.close.called], [],
            "no connection may be closed and re-opened while the pool is alive",
        )

    def test_57_concurrent_first_use_creates_exactly_one_pool(self):
        # Uvicorn runs sync endpoints in a threadpool, so several requests can reach an unbuilt
        # pool at once. Unguarded, each built its own: six concurrent cold-start requests produced
        # six pools, five orphaned, and five connections that were neither pooled nor closed —
        # silently, because the orphans' PoolError was swallowed on return.
        pools = []
        real_new_pool = connection._new_pool

        def tracing_new_pool(url):
            # The delay is what makes this test deterministic rather than a coin flip. The race
            # lives between "is _POOL None?" and the assignment, and building the pool opens no
            # connection, so without a pause here that window is a few microseconds and an
            # unlocked build would usually still look fine. Verified in both directions: with the
            # lock removed this fails; with it, it passes.
            time.sleep(0.03)
            pool = real_new_pool(url)
            pools.append(pool)
            return pool

        conns = []

        def factory(*_a, **_k):
            conns.append(_fake_conn())
            return conns[-1]

        errors = []

        def one_checkout():
            try:
                with connection.read_cursor():
                    pass
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

        with _db_url(), \
                mock.patch.object(connection, "_new_pool", tracing_new_pool), \
                mock.patch("psycopg2.connect", side_effect=factory):
            threads = [threading.Thread(target=one_checkout) for _ in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(pools), 1, "exactly one pool may ever be constructed")
        pooled = set(pools[0]._idle)
        self.assertTrue(
            all(c in pooled or c.close.called for c in conns),
            "every connection must end up pooled or closed — never orphaned",
        )

    def test_58_readonly_is_asserted_once_per_connection(self):
        # SET SESSION CHARACTERISTICS is a property of the session, and a pooled session now
        # outlives its request. Setting it per checkout was a wasted round trip to Sydney on
        # every request; the guarantee is unchanged because the setting persists.
        fake_conn = _fake_conn()
        with _db_url(), mock.patch("psycopg2.connect", return_value=fake_conn):
            for _ in range(4):
                with connection.read_cursor():
                    pass
        fake_conn.set_session.assert_called_once_with(readonly=True)
        self.assertIs(fake_conn.readonly, True)

    def test_59_readonly_failure_is_fatal_in_production(self):
        # services/api connects as `postgres` (D-20), so set_session is the only write barrier at
        # this layer. While its failure was swallowed, anything that stopped the statement from
        # taking effect degraded silently to a read-write superuser session. In production it
        # must refuse to serve instead.
        fake_conn = _fake_conn()
        fake_conn.set_session.side_effect = RuntimeError("not supported by this pooler")
        with _db_url(), mock.patch.dict(os.environ, {"ENV": "production"}), \
                mock.patch("psycopg2.connect", return_value=fake_conn):
            with self.assertRaises(connection.DatabaseUnavailable):
                with connection.read_cursor():
                    self.fail("must not reach the query with the guarantee unestablished")
        self.assertTrue(fake_conn.close.called, "an unusable session must not go back in the pool")

    def test_60_readonly_failure_is_tolerated_outside_production(self):
        # Local work must not require a stand-in connection that implements set_session.
        fake_conn = _fake_conn()
        fake_conn.set_session.side_effect = RuntimeError("not supported")
        reached = False
        with _db_url(), mock.patch.dict(os.environ, {"ENV": "development"}), \
                mock.patch("psycopg2.connect", return_value=fake_conn):
            with connection.read_cursor():
                reached = True
        self.assertTrue(reached)

    def test_72_readonly_is_fatal_on_the_live_env_not_an_imported_snapshot(self):
        # The hole F4 left open. `config.settings` is snapshotted at import, and app/config.py
        # says so itself: that singleton "does NOT drive app construction or the production
        # guards", which create_app() re-resolves per call precisely so a process that imported
        # under development and later set ENV=production cannot bypass them (test_52).
        #
        # Deciding whether a missing write barrier stops the request IS one of those guards.
        # Read from the snapshot, this exact sequence turned the production refusal back into a
        # non-production warning -- silently, on the one connection-layer barrier that stops this
        # service writing as `postgres`. The mode must come from the live environment.
        fake_conn = _fake_conn()
        fake_conn.set_session.side_effect = RuntimeError("not supported by this pooler")
        with _db_url(), \
                mock.patch.object(config.settings, "env", "development"), \
                mock.patch.dict(os.environ, {"ENV": "production"}), \
                mock.patch("psycopg2.connect", return_value=fake_conn):
            with self.assertRaises(connection.DatabaseUnavailable):
                with connection.read_cursor():
                    self.fail("a stale import-time ENV must not downgrade the write barrier")
        self.assertTrue(fake_conn.close.called)

    def test_61_dead_pooled_connection_is_retried_once(self):
        # The failure pooling introduces and per-request connecting could not: a connection idle
        # in the pool that the server has already dropped looks healthy until `execute` runs.
        # Before this, that surfaced as a 500.
        import psycopg2  # noqa: PLC0415

        dead, live = _fake_conn(), _fake_conn()
        _cursor_of(dead).execute.side_effect = psycopg2.OperationalError("server closed")
        _cursor_of(live).fetchall.return_value = [{"ticker": "VCB"}]

        with _db_url(), mock.patch("psycopg2.connect", side_effect=[dead, live]) as connect:
            rows = connection.fetch_all("SELECT 1")

        self.assertEqual(rows, [{"ticker": "VCB"}])
        self.assertEqual(connect.call_count, 2)
        self.assertTrue(dead.close.called, "the dead connection must be closed, not pooled")
        self.assertFalse(live.close.called)

    def test_62_a_bad_statement_is_not_retried(self):
        # ProgrammingError is a sibling of OperationalError under DatabaseError. Retrying
        # malformed SQL would just produce the same failure twice.
        import psycopg2  # noqa: PLC0415

        conn = _fake_conn()
        _cursor_of(conn).execute.side_effect = psycopg2.ProgrammingError("syntax error")
        with _db_url(), mock.patch("psycopg2.connect", return_value=conn) as connect:
            with self.assertRaises(psycopg2.ProgrammingError):
                connection.fetch_one("SELECT bogus")
        connect.assert_called_once()

    def test_63_two_consecutive_connection_failures_become_unavailable(self):
        # Exactly two attempts, then the "system is not ready" envelope (503) — never an
        # unbounded retry loop and never an unhandled 500.
        import psycopg2  # noqa: PLC0415

        first, second = _fake_conn(), _fake_conn()
        for c in (first, second):
            _cursor_of(c).execute.side_effect = psycopg2.OperationalError("server closed")
        with _db_url(), mock.patch("psycopg2.connect", side_effect=[first, second]) as connect:
            with self.assertRaises(connection.DatabaseUnavailable):
                connection.fetch_all("SELECT 1")
        self.assertEqual(connect.call_count, 2)

    def test_64_pool_exhaustion_is_503_not_a_hang(self):
        # Past the ceiling the pool raises rather than blocks, and that becomes 503 immediately.
        # D-21 records this deployment has no connection-count pressure, so back-pressure is
        # cheaper than a queue nobody needs.
        with _db_url(), mock.patch("psycopg2.connect", side_effect=lambda *a, **k: _fake_conn()):
            with connection.read_cursor():
                pass  # build the pool
            pool = connection._POOL
            held = [pool.getconn() for _ in range(connection._POOL_MAX)]
            try:
                with self.assertRaises(connection.DatabaseUnavailable):
                    with connection.read_cursor():
                        self.fail("must not hand out a connection past the ceiling")
            finally:
                for c in held:
                    pool.putconn(c)

    def test_67_connections_are_opened_outside_the_pool_lock(self):
        # The reason this pool is hand-written instead of psycopg2's. `ThreadedConnectionPool`
        # holds one lock across `_getconn`, which calls `psycopg2.connect()` inside it, so
        # concurrent first requests pay their handshakes END TO END. Measured against the real
        # Supabase pooler (a ~955 ms handshake to Sydney): the first page load took 8,647 ms with
        # that pool against 1,557 ms with no pool at all — a five-fold regression on exactly the
        # load a reader of a spun-down free instance sees. This pool locks bookkeeping only.
        #
        # A timing assertion, deliberately: the property IS temporal, and no structural check
        # would catch a future refactor that moved connect() back inside the lock. The margin is
        # wide (4 x 150 ms serialised would be 600 ms; the bar is 350 ms).
        handshake = 0.15

        def slow_factory(*_a, **_k):
            time.sleep(handshake)
            return _fake_conn()

        def one_checkout():
            with connection.read_cursor():
                pass

        with _db_url(), mock.patch("psycopg2.connect", side_effect=slow_factory):
            threads = [threading.Thread(target=one_checkout) for _ in range(4)]
            start = time.perf_counter()
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            elapsed = time.perf_counter() - start

        self.assertLess(
            elapsed, handshake * 2.33,
            "four concurrent first checkouts took %.0f ms: handshakes are being serialised, "
            "which is the psycopg2 pool behaviour this implementation exists to avoid"
            % (elapsed * 1000),
        )

    def test_68_an_open_transaction_is_reset_before_the_connection_is_pooled(self):
        # A connection handed back mid-transaction sits idle-in-transaction on the server,
        # holding a snapshot open. The reset happens OUTSIDE the pool lock (it is a round trip),
        # but it must still happen — an early draft of this pool skipped it and looked much
        # faster for exactly that wrong reason.
        import psycopg2  # noqa: PLC0415

        conn = _fake_conn()
        conn.info.transaction_status = psycopg2.extensions.TRANSACTION_STATUS_INTRANS
        with _db_url(), mock.patch("psycopg2.connect", return_value=conn):
            with connection.read_cursor():
                pass
        conn.rollback.assert_called_once()
        self.assertIn(conn, connection._POOL._idle, "the reset connection must still be pooled")

    def test_69_pooled_connections_enable_tcp_keepalives(self):
        # Only a pool can be hurt by a silently-dropped idle socket, because only a pool keeps
        # one. Render's Singapore egress reaches Supabase's Sydney pooler across the public
        # internet, and a middlebox that drops an idle flow without a FIN leaves `execute`
        # blocking on TCP retransmission for the kernel's timeout (~15 min on Linux) while it
        # holds a Uvicorn threadpool slot. `connect_timeout` is already spent and the server's
        # `statement_timeout` never starts, because the server never sees the query. Keepalives
        # are the only guard that applies, and they turn the hang into an error `_execute`
        # retries.
        factory = mock.patch("psycopg2.connect", side_effect=lambda *a, **k: _fake_conn())
        with _db_url(), factory as connect:
            with connection.read_cursor():
                pass
        kwargs = connect.call_args.kwargs
        self.assertEqual(kwargs.get("keepalives"), 1, "idle pooled sockets must be probed")
        for key in ("keepalives_idle", "keepalives_interval", "keepalives_count"):
            self.assertIsInstance(kwargs.get(key), int, f"{key} must be set explicitly")
        # The detection budget must stay well inside a request's patience, not the kernel's.
        budget = (
            kwargs["keepalives_idle"]
            + kwargs["keepalives_interval"] * kwargs["keepalives_count"]
        )
        self.assertLessEqual(budget, 120, "a dead peer must surface in ~a minute, not ~15")
        self.assertEqual(kwargs.get("connect_timeout"), connection._CONNECT_TIMEOUT)

    def test_70_a_dead_connection_retires_its_idle_siblings(self):
        # `_execute` retries ONCE. Every connection in the pool was opened to the same pooler at
        # the same time, so whatever killed one has very likely killed the rest — and a ticker
        # screen fires four requests in parallel. Handing the retry a second stale connection
        # answers 503 for a database that is perfectly healthy. The first proved-dead connection
        # must therefore retire the idle set, not just itself.
        import psycopg2  # noqa: PLC0415

        conns = []

        def factory(*_a, **_k):
            conns.append(_fake_conn())
            return conns[-1]

        def one_checkout():
            with connection.read_cursor():
                time.sleep(0.02)

        with _db_url(), mock.patch("psycopg2.connect", side_effect=factory) as connect:
            # A page load grows the pool to four, exactly as test_56 measures.
            threads = [threading.Thread(target=one_checkout) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(connect.call_count, 4)

            # The pooler goes away underneath all four while they sit idle.
            stale = list(conns)
            for c in stale:
                _cursor_of(c).execute.side_effect = psycopg2.OperationalError("server closed")

            rows = connection.fetch_all("SELECT 1")

        self.assertEqual(rows, [], "the retry must be served, not turned into a 503")
        self.assertEqual(
            connect.call_count, 5,
            "exactly one fresh connection: the retry must not spend itself on a second stale one",
        )
        for c in stale:
            self.assertTrue(c.close.called, "every stale sibling must be retired, not re-served")

    def test_71_a_dead_connection_is_not_reported_as_a_read_only_failure(self):
        # `_ensure_read_only` runs before the query, so a connection that dies between the
        # handshake and `set_session` fails THERE. Converting that to DatabaseUnavailable would
        # answer 503 while logging "could not set the connection read-only" — pointing a reader
        # at the write barrier for what is a dropped socket, and skipping the retry that would
        # have served the request. Fail-closed is unaffected: test_59 still holds for a
        # set_session that fails for its own reasons.
        import psycopg2  # noqa: PLC0415

        dead, live = _fake_conn(), _fake_conn()
        dead.set_session.side_effect = psycopg2.OperationalError("server closed the connection")
        _cursor_of(live).fetchall.return_value = [{"ticker": "VCB"}]

        with _db_url(), mock.patch.dict(os.environ, {"ENV": "production"}), \
                mock.patch("psycopg2.connect", side_effect=[dead, live]) as connect:
            rows = connection.fetch_all("SELECT 1")

        self.assertEqual(rows, [{"ticker": "VCB"}])
        self.assertEqual(connect.call_count, 2)
        self.assertTrue(dead.close.called, "a connection proved dead must not go back in the pool")

    def test_66_application_shutdown_closes_the_pool(self):
        # Drives the real ASGI lifespan protocol against the constructed app, so this proves the
        # WIRING, not just that close_pool() works when called directly. Startup must still open
        # nothing — that is test_54's half of the same contract.
        app = create_app(resolve_runtime({"ENV": "development"}))
        with _db_url(), mock.patch("psycopg2.connect", side_effect=lambda *a, **k: _fake_conn()):
            with connection.read_cursor():
                pass
            self.assertIsNotNone(connection._POOL)
            sent = asyncio.run(_drive_lifespan(app))
        self.assertEqual(
            [m["type"] for m in sent],
            ["lifespan.startup.complete", "lifespan.shutdown.complete"],
        )
        self.assertIsNone(connection._POOL, "shutdown must release the pool")

    def test_65_close_pool_is_idempotent_and_resets_state(self):
        with _db_url(), mock.patch("psycopg2.connect", side_effect=lambda *a, **k: _fake_conn()):
            with connection.read_cursor():
                pass
            self.assertIsNotNone(connection._POOL)
            connection.close_pool()
            self.assertIsNone(connection._POOL)
            connection.close_pool()  # second call must not raise
            with connection.read_cursor():
                pass  # and the next query rebuilds it
            self.assertIsNotNone(connection._POOL)

    def test_45_startup_validation_opens_no_connection(self):
        with mock.patch("psycopg2.connect",
            side_effect=AssertionError("no connect during validation")):
            cfg = resolve_runtime(_prod_env())
        self.assertTrue(cfg.is_production)

    def test_46_app_construction_opens_no_connection(self):
        with mock.patch("psycopg2.connect",
            side_effect=AssertionError("no connect on construction")):
            app = create_app(resolve_runtime({"ENV": "development"}))
        self.assertEqual(app.title, "Anchor Model API")

    def test_47_production_config_errors_are_bounded(self):
        bad_envs = [
            _prod_env(DATABASE_URL=""),
            _prod_env(API_DEV_FIXTURES="1"),
            {"ENV": "production", "DATABASE_URL": "postgresql://u:p@h/d"},  # no origins
            {"ENV": "staging"},
        ]
        for env in bad_envs:
            with self.assertRaises(RuntimeConfigError) as ctx:
                resolve_runtime(env)
            msg = str(ctx.exception)
            self.assertLess(len(msg), 200)
            self.assertNotIn("\n", msg)
            self.assertNotIn("Traceback", msg)

    def test_48_no_raw_trace_or_credentials_in_error(self):
        with self.assertRaises(RuntimeConfigError) as ctx:
            resolve_runtime(_prod_env(DATABASE_URL="postgresql://svc:TopSecret@:5432/db"))
        msg = str(ctx.exception)
        self.assertNotIn("TopSecret", msg)
        self.assertNotIn("Traceback", msg)


class ImportOrderRegressionTests(unittest.TestCase):
    """Blocker 1: runtime settings resolve at construction, not module import.

    ``app.config``/``app.runtime_guards``/``app.main`` were already imported (at
    module load, under a non-production ENV). A fresh ``create_app()`` must resolve
    the CURRENT environment and re-run the production guards — a development import
    followed by ``ENV=production`` cannot bypass them, and no module-level cache
    controls later construction. Fresh construction itself is the fix (no
    ``importlib.reload``).
    """

    def test_49_fresh_create_app_applies_current_production_env(self):
        # Forward: switch to production with bad config, then construct fresh → fail.
        with mock.patch.dict(
            os.environ,
            {
                "ENV": "production",
                "DATABASE_URL": "",  # blank in production
                "ALLOWED_ORIGINS": "https://app.example.invalid",
                "API_DEV_FIXTURES": "0",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeConfigError):
                create_app()

    def test_50_fresh_create_app_valid_production_uses_production_cors(self):
        # Reverse: valid production env → construct fresh → production CORS origins.
        with mock.patch.dict(
            os.environ,
            {
                "ENV": "production",
                "DATABASE_URL": "postgresql://u:p@db.invalid:5432/app",
                "ALLOWED_ORIGINS": "https://app.example.invalid",
                "API_DEV_FIXTURES": "0",
            },
            clear=False,
        ):
            with mock.patch("psycopg2.connect", side_effect=AssertionError("no connect")):
                app = create_app()
            status, headers, _ = call_asgi(
                app,
                "OPTIONS",
                "/api/overview",
                {"origin": "https://app.example.invalid", "access-control-request-method": "GET"},
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                headers.get("access-control-allow-origin"), "https://app.example.invalid"
            )
            _, foreign_headers, _ = call_asgi(
                app,
                "OPTIONS",
                "/api/overview",
                {"origin": "http://localhost:3000", "access-control-request-method": "GET"},
            )
            self.assertNotEqual(
                foreign_headers.get("access-control-allow-origin"), "http://localhost:3000"
            )

    def test_51_fresh_create_app_development_uses_localhost_defaults(self):
        with mock.patch.dict(os.environ, {"ENV": "development", "ALLOWED_ORIGINS": ""},
            clear=False):
            cfg = load_runtime_settings()
            self.assertFalse(cfg.is_production)
            self.assertEqual(cfg.allowed_origins, DEV_DEFAULT_ORIGINS)
            with mock.patch("psycopg2.connect", side_effect=AssertionError("no connect")):
                app = create_app()
            self.assertEqual(app.title, "Anchor Model API")

    def test_52_no_stale_module_level_runtime_cache(self):
        # The removed import-time cache must not exist; construction goes through a
        # callable that re-reads the environment.
        for attr in ("runtime", "RUNTIME", "RUNTIME_MODE", "IS_PRODUCTION"):
            self.assertFalse(hasattr(config, attr), f"stale module-level {attr!r} must not exist")
        self.assertTrue(callable(load_runtime_settings))

    def test_53_injected_settings_are_used_verbatim(self):
        # Explicitly injected immutable settings ignore the ambient environment.
        injected = resolve_runtime(
            {
                "ENV": "production",
                "DATABASE_URL": "postgresql://u:p@h:5432/d",
                "ALLOWED_ORIGINS": "https://injected.example.invalid",
                "API_DEV_FIXTURES": "0",
            }
        )
        with mock.patch.dict(os.environ, {"ENV": "development"}, clear=False):
            with mock.patch("psycopg2.connect", side_effect=AssertionError("no connect")):
                app = create_app(injected)
            _, headers, _ = call_asgi(
                app,
                "OPTIONS",
                "/api/overview",
                {"origin": "https://injected.example.invalid",
                    "access-control-request-method": "GET"},
            )
            self.assertEqual(
                headers.get("access-control-allow-origin"), "https://injected.example.invalid"
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
