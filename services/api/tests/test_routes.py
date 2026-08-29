"""P8/P9 — read-route contract tests for /api/model/active and /api/market/*.

Same idiom as ``test_runtime_guards.py``: standard-library ``unittest`` only, and the same
dependency-free ASGI harness, because ``httpx``/``TestClient`` is deliberately not a project
dependency. The harness here adds a query string, which the one next door does not support —
``/api/market/movers`` cannot be exercised without one.

**No test opens a database.** ``fetch_one``/``fetch_all`` are patched in the route modules'
namespaces, so what is under test is the serialisation contract and the request validation, not
psycopg2. The SQL those fakes capture is asserted on directly — that is how the ORDER BY and the
parameter binding get checked without a server.

What these assert, and why each one exists:

* ``Decimal`` never reaches the wire as anything but a JSON number, at a width that does not
  destroy a fraction (``as_float``'s 3-decimal default would round ret_1d to 0.1%).
* NULL stays ``null``. An absent index or an uncomputed indicator is not zero — a zero here
  would be a claim the data does not make.
* Whole-number columns stay integers, so a share count does not arrive as ``1.23e9``.
* An invalid ``direction`` or ``limit`` produces the 400 envelope, not a 500 — and never
  reaches the SQL string.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest import mock

# Keep the import below out of production mode; the guards are exercised next door.
os.environ["ENV"] = "test"

# services/api makes ``app.*`` importable (matches the uvicorn cwd).
API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.main import create_app  # noqa: E402
from app.runtime_guards import resolve_runtime  # noqa: E402

# ---------------------------------------------------------------------------
# ASGI harness — as in test_runtime_guards.py, plus a query string.
# ---------------------------------------------------------------------------


async def _call_asgi(app, method, path, headers=None, query=""):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query.encode("latin-1"),
        "root_path": "",
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in (headers or {}).items()
        ],
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
    body = b""
    for message in messages:
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            body += message.get("body", b"") or b""
    return status, body


def call_json(app, path, query=""):
    """Issue a GET and return ``(status, parsed_body)``."""
    status, body = asyncio.run(_call_asgi(app, "GET", path, query=query))
    return status, json.loads(body) if body else None


def _app():
    """A non-production app with an injected config, so no env is read and no DB is touched."""
    return create_app(
        resolve_runtime(
            {
                "ENV": "test",
                "DATABASE_URL": "postgresql://u:p@h:5432/d",
                "ALLOWED_ORIGINS": "https://app.example.invalid",
                "API_DEV_FIXTURES": "0",
            }
        )
    )


# ---------------------------------------------------------------------------
# Fixture rows — deliberately carry Decimal, None and large integers, because
# those are the three things the serialisers exist to handle.
# ---------------------------------------------------------------------------

ACTIVE_RUN_ROW = {
    "run_id": 1,
    "artifact_id": "ae2010a4ad426",
    "scope": "year",
    "scope_label": "2025",
    "similarity_measure": "pearson_rho2",
    "universe_version": "u27ba69c4",
    "index_symbol": "VNINDEX",
    "window_start": date(2025, 1, 2),
    "window_end": date(2025, 12, 31),
    "prior_close_date": date(2024, 12, 31),
    "n_sessions": 249,
    "n_tickers": 85,
    "q": Decimal("0.3413654"),
    "k": 10,
    "k_max": 15,
    "tau": Decimal("0.10"),
    "coverage_f": Decimal("22.3745821"),
    "coverage_fbar": Decimal("0.2632304"),
    "n_under_tau": 38,
    "is_primary": True,
    "created_at": datetime(2026, 8, 17, 9, 30, tzinfo=UTC),
    "loaded_at": datetime(2026, 8, 18, 11, 5, tzinfo=UTC),
    "latest_session": date(2026, 8, 18),
}

OVERVIEW_ROW = {
    "session_date": date(2026, 8, 18),
    "n_tickers": 85,
    "n_with_return": 84,
    "total_turnover": Decimal("1234567890.55"),
    "total_volume": Decimal("9876543210"),
    "advancers": 40,
    "decliners": 30,
    "unchanged": 14,
    "index_symbol": "VNINDEX",
    "index_close": Decimal("1284.37"),
    "index_ret_1d": Decimal("0.0071234"),
}

SECTOR_ROW = {
    "sector": "Ngân hàng",
    "n_tickers": 12,
    "n_with_return": 11,
    "mean_ret_1d": Decimal("0.0123456"),
    "total_turnover": Decimal("987654321.99"),
    "total_volume": Decimal("5432100000"),
}

MOVER_ROW = {
    "ticker": "VCB",
    "company_name": "Ngân hàng TMCP Ngoại thương Việt Nam",
    "sector": "Ngân hàng",
    "bar_date": date(2026, 8, 18),
    "close_price": Decimal("92.40"),
    "volume": 1234567,
    "turnover_value": Decimal("114074590.80"),
    "ret_1d": Decimal("0.0712349"),
    "ret_5d": None,
    "ret_20d": Decimal("-0.0234567"),
    "ret_60d": Decimal("0.1834500"),
    # NULL on purpose: a ticker with fewer than 253 loaded sessions has every shorter return
    # and no 1Y one, which is the case NULLS LAST exists to keep out of the top of the table.
    "ret_252d": None,
}

INDEX_BAR_ROW = {
    "index_symbol": "VNINDEX",
    "bar_date": date(2026, 8, 18),
    "open": Decimal("1820.55"),
    "high": Decimal("1841.20"),
    "low": Decimal("1818.03"),
    "close": Decimal("1832.12"),
    "volume": 987654321,
    "ret_1d": Decimal("0.0031420"),
}


class ModelActiveTests(unittest.TestCase):
    def test_serialises_dates_ratios_and_timestamps(self):
        with mock.patch("app.routes.model.fetch_one", return_value=dict(ACTIVE_RUN_ROW)):
            status, body = call_json(_app(), "/api/model/active")

        self.assertEqual(status, 200)
        self.assertEqual(body["window_start"], "2025-01-02")
        self.assertEqual(body["window_end"], "2025-12-31")
        self.assertEqual(body["prior_close_date"], "2024-12-31")
        self.assertEqual(body["created_at"], "2026-08-17T09:30:00Z")

        # The whole point of the endpoint: the window and the prices disagree, and both
        # dates are on the wire so the screen can say so rather than imply they match.
        self.assertEqual(body["latest_session"], "2026-08-18")
        self.assertNotEqual(body["latest_session"], body["window_end"])

        # Ratios keep more than three decimals. as_float's default would give 0.263.
        self.assertEqual(body["coverage_fbar"], 0.26323)
        self.assertEqual(body["q"], 0.341365)
        self.assertIsInstance(body["coverage_fbar"], float)

        # Counts stay integers.
        for key in ("run_id", "n_sessions", "n_tickers", "k", "k_max", "n_under_tau"):
            self.assertIsInstance(body[key], int, key)
        self.assertIs(body["is_primary"], True)

    def test_no_active_run_is_503_not_404(self):
        # Nothing activated is "the system is not ready", not "you asked for a missing thing".
        with mock.patch("app.routes.model.fetch_one", return_value=None):
            status, body = call_json(_app(), "/api/model/active")

        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "no_data")


class MarketOverviewTests(unittest.TestCase):
    def test_decimals_become_numbers_and_volume_stays_integral(self):
        with mock.patch("app.routes.market.fetch_one", return_value=dict(OVERVIEW_ROW)):
            status, body = call_json(_app(), "/api/market/overview")

        self.assertEqual(status, 200)
        self.assertEqual(body["session_date"], "2026-08-18")
        self.assertEqual(body["total_turnover"], 1234567890.55)

        # A share count is exact. As a float this would be 9.87654321e9 and would start
        # losing digits past 2^53.
        self.assertIsInstance(body["total_volume"], int)
        self.assertEqual(body["total_volume"], 9876543210)

        # Index move keeps its precision: 0.007 at the default width, 0.007123 here.
        self.assertEqual(body["index_ret_1d"], 0.007123)

    def test_breadth_counts_are_not_presented_as_a_partition(self):
        with mock.patch("app.routes.market.fetch_one", return_value=dict(OVERVIEW_ROW)):
            _, body = call_json(_app(), "/api/market/overview")

        # 40 + 30 + 14 = 84, not 85. A ticker whose first session is today has a NULL ret_1d
        # and is counted in none of the three. n_with_return is what explains the gap, so it
        # must be on the wire beside them.
        self.assertEqual(
            body["advancers"] + body["decliners"] + body["unchanged"],
            body["n_with_return"],
        )
        self.assertLess(body["n_with_return"], body["n_tickers"])

    def test_absent_index_serialises_as_null_never_zero(self):
        row = dict(OVERVIEW_ROW, index_symbol=None, index_close=None, index_ret_1d=None)
        with mock.patch("app.routes.market.fetch_one", return_value=row):
            status, body = call_json(_app(), "/api/market/overview")

        self.assertEqual(status, 200)
        # With no active run the index half is NULL. Rendering 0 would assert the index
        # closed flat, which is a claim the data does not make.
        self.assertIsNone(body["index_symbol"])
        self.assertIsNone(body["index_close"])
        self.assertIsNone(body["index_ret_1d"])

    def test_empty_database_is_detected_on_the_value_not_the_row_count(self):
        # v_market_overview's aggregates are scalar subqueries, so it returns a row even
        # against an empty daily_bars — with a NULL session_date.
        row = dict(OVERVIEW_ROW, session_date=None)
        with mock.patch("app.routes.market.fetch_one", return_value=row):
            status, body = call_json(_app(), "/api/market/overview")

        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "no_data")


class MarketSectorsTests(unittest.TestCase):
    def test_decimals_become_numbers_and_volume_stays_integral(self):
        with mock.patch("app.routes.market.fetch_all", return_value=[dict(SECTOR_ROW)]):
            status, body = call_json(_app(), "/api/market/sectors")

        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        row = body["sectors"][0]
        self.assertEqual(row["sector"], "Ngân hàng")
        self.assertEqual(row["mean_ret_1d"], 0.012346)
        self.assertEqual(row["total_turnover"], 987654321.99)
        self.assertIsInstance(row["total_volume"], int)
        self.assertEqual(row["total_volume"], 5432100000)

    def test_null_sector_and_null_mean_pass_through(self):
        # A sector with no assigned name, and/or zero tickers holding a return today
        # (n_with_return == 0), must serialise as null — not "Khác", not 0.0.
        row = dict(SECTOR_ROW, sector=None, n_with_return=0, mean_ret_1d=None)
        with mock.patch("app.routes.market.fetch_all", return_value=[row]):
            status, body = call_json(_app(), "/api/market/sectors")

        self.assertEqual(status, 200)
        out = body["sectors"][0]
        self.assertIsNone(out["sector"])
        self.assertIsNone(out["mean_ret_1d"])
        self.assertEqual(out["n_with_return"], 0)

    def test_empty_result_is_200_with_empty_list(self):
        # No indicators computed yet is a legitimate state (00010's own header says so),
        # not an error — an empty treemap, not a 503.
        with mock.patch("app.routes.market.fetch_all", return_value=[]):
            status, body = call_json(_app(), "/api/market/sectors")

        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["sectors"], [])

    def test_ordered_by_turnover_desc_nulls_last_then_sector(self):
        captured = {}

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            return [dict(SECTOR_ROW)]

        with mock.patch("app.routes.market.fetch_all", side_effect=fake_fetch_all):
            call_json(_app(), "/api/market/sectors")

        self.assertIn("total_turnover DESC NULLS LAST", captured["sql"])
        self.assertIn("sector ASC", captured["sql"])


class MarketMoversTests(unittest.TestCase):
    def _capture(self, path, query):
        """Run the route with a fake fetch_all, returning (status, body, sql, params)."""
        captured = {}

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return [dict(MOVER_ROW)]

        with mock.patch("app.routes.market.fetch_all", side_effect=fake_fetch_all):
            status, body = call_json(_app(), path, query=query)
        return status, body, captured.get("sql"), captured.get("params")

    def test_direction_down_orders_ascending_with_nulls_last(self):
        status, body, sql, params = self._capture("/api/market/movers", "direction=down&limit=5")

        self.assertEqual(status, 200)
        self.assertEqual(body["direction"], "down")
        self.assertEqual(body["limit"], 5)

        # Postgres defaults DESC to NULLS FIRST, so both branches say it explicitly.
        self.assertIn("ASC NULLS LAST", sql)
        self.assertNotIn("DESC", sql)
        # Deterministic ordering: same data, same response.
        self.assertIn("t.ticker ASC", sql)
        # limit is bound, never formatted into the string.
        self.assertEqual(params, (5,))
        self.assertNotIn("5", sql.split("LIMIT")[-1].strip().rstrip(";").replace("%s", ""))

    def test_direction_up_orders_descending_with_nulls_last(self):
        status, body, sql, params = self._capture("/api/market/movers", "direction=up")

        self.assertEqual(status, 200)
        self.assertIn("DESC NULLS LAST", sql)
        self.assertEqual(body["limit"], 10, "default limit")
        self.assertEqual(params, (10,))

    def test_rows_keep_precision_nulls_and_integral_volume(self):
        _, body, _, _ = self._capture("/api/market/movers", "direction=up")
        row = body["movers"][0]

        # 0.071 at as_float's default width; 0.071235 here.
        self.assertEqual(row["ret_1d"], 0.071235)
        self.assertEqual(row["ret_20d"], -0.023457)
        # An uncomputed indicator during warm-up is null, not 0.
        self.assertIsNone(row["ret_5d"])
        self.assertIsInstance(row["volume"], int)
        # Per-ticker date is exposed so a delisted ticker shows as stale rather than
        # being silently ranked beside today's movers.
        self.assertEqual(row["bar_date"], "2026-08-18")

    def test_invalid_direction_is_400_and_never_reaches_the_sql(self):
        captured = {}

        def fake_fetch_all(sql, params=None):  # pragma: no cover - must not run
            captured["sql"] = sql
            return []

        with mock.patch("app.routes.market.fetch_all", side_effect=fake_fetch_all):
            status, body = call_json(_app(), "/api/market/movers", query="direction=sideways")

        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "invalid_params")
        # Rejected by validation before the handler body — the value never touched SQL.
        self.assertNotIn("sql", captured)

    def test_out_of_range_limit_is_400(self):
        for query in ("direction=up&limit=0", "direction=up&limit=101", "direction=up&limit=abc"):
            with self.subTest(query=query):
                with mock.patch("app.routes.market.fetch_all", return_value=[]):
                    status, body = call_json(_app(), "/api/market/movers", query=query)
                self.assertEqual(status, 400)
                self.assertEqual(body["error"]["code"], "invalid_params")

    def test_each_horizon_ranks_and_filters_on_its_own_column(self):
        """The mapping from a display label to a schema column, asserted once per horizon.

        This is the test that would have caught the mistake the route is shaped to avoid:
        filtering on ret_1d while ordering by ret_252d admits every short-history ticker into
        the 1Y table on the strength of a one-day move.
        """
        expected = {
            "1d": "ret_1d", "5d": "ret_5d", "1m": "ret_20d",
            "3m": "ret_60d", "1y": "ret_252d",
        }
        for horizon, column in expected.items():
            with self.subTest(horizon=horizon):
                status, body, sql, _ = self._capture(
                    "/api/market/movers", f"horizon={horizon}&direction=up"
                )
                self.assertEqual(status, 200)
                self.assertEqual(body["horizon"], horizon)
                self.assertIn(f"t.{column} DESC NULLS LAST", sql)
                # Ordered and filtered on the SAME column — the whole point.
                self.assertIn(f"WHERE t.{column} IS NOT NULL", sql)
                # No other horizon's column may appear in either clause.
                for other in set(expected.values()) - {column}:
                    self.assertNotIn(f"t.{other} DESC", sql)
                    self.assertNotIn(f"WHERE t.{other}", sql)

    def test_default_horizon_is_1d(self):
        _, body, sql, _ = self._capture("/api/market/movers", "direction=up")
        self.assertEqual(body["horizon"], "1d")
        self.assertIn("t.ret_1d DESC NULLS LAST", sql)

    def test_invalid_horizon_is_400_and_never_reaches_the_sql(self):
        captured = {}

        def fake_fetch_all(sql, params=None):  # pragma: no cover - must not run
            captured["sql"] = sql
            return []

        with mock.patch("app.routes.market.fetch_all", side_effect=fake_fetch_all):
            status, body = call_json(_app(), "/api/market/movers", query="horizon=6m")

        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "invalid_params")
        self.assertNotIn("sql", captured)

    def test_every_row_carries_all_five_horizons(self):
        """The table shows four context columns beside the ranked one, from a single request."""
        _, body, _, _ = self._capture("/api/market/movers", "horizon=3m&direction=up")
        row = body["movers"][0]
        for field in ("ret_1d", "ret_5d", "ret_20d", "ret_60d", "ret_252d"):
            self.assertIn(field, row)
        self.assertEqual(row["ret_60d"], 0.18345)
        # An uncomputed 1Y return is null, never 0 — a 0 would claim the stock was flat.
        self.assertIsNone(row["ret_252d"])


class MarketLiquidityTests(unittest.TestCase):
    def _capture(self, query=""):
        captured = {}

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return [dict(MOVER_ROW)]

        with (
            mock.patch("app.routes.market.fetch_all", side_effect=fake_fetch_all),
            mock.patch(
                "app.routes.market.fetch_one",
                return_value={"session_date": date(2026, 8, 18)},
            ),
        ):
            status, body = call_json(_app(), "/api/market/liquidity", query=query)
        return status, body, captured.get("sql"), captured.get("params")

    def test_orders_by_turnover_desc_nulls_last_then_ticker(self):
        status, body, sql, params = self._capture("limit=5")

        self.assertEqual(status, 200)
        self.assertIn("t.turnover_value DESC NULLS LAST", sql)
        self.assertIn("t.ticker ASC", sql)
        self.assertEqual(params, (5,))
        self.assertEqual(body["limit"], 5)

    def test_reads_the_same_view_as_movers(self):
        """Not an implementation detail: it is why the two tables cannot disagree about a row."""
        _, _, sql, _ = self._capture()
        self.assertIn("FROM v_top_movers", sql)
        # No direction and no NOT NULL filter — "least traded" is not a question the screen asks.
        self.assertNotIn("WHERE", sql)

    def test_publishes_the_session_it_ranked_beside_each_row_s_own_date(self):
        _, body, _, _ = self._capture()
        self.assertEqual(body["session_date"], "2026-08-18")
        # Per-row date too, so a delisted ticker's last turnover is visibly stale rather than
        # sitting unmarked in a table captioned "today".
        self.assertEqual(body["stocks"][0]["bar_date"], "2026-08-18")

    def test_turnover_keeps_precision_and_volume_stays_integral(self):
        _, body, _, _ = self._capture()
        row = body["stocks"][0]
        self.assertEqual(row["turnover_value"], 114074590.8)
        self.assertIsInstance(row["volume"], int)

    def test_out_of_range_limit_is_400(self):
        for query in ("limit=0", "limit=101"):
            with self.subTest(query=query):
                with mock.patch("app.routes.market.fetch_all", return_value=[]):
                    status, body = call_json(_app(), "/api/market/liquidity", query=query)
                self.assertEqual(status, 400)
                self.assertEqual(body["error"]["code"], "invalid_params")


class MarketIndexHistoryTests(unittest.TestCase):
    def _capture(self, query=""):
        captured = {}

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return [dict(INDEX_BAR_ROW)]

        with mock.patch("app.routes.market.fetch_all", side_effect=fake_fetch_all):
            status, body = call_json(_app(), "/api/market/index-history", query=query)
        return status, body, captured.get("sql"), captured.get("params")

    def test_fixed_ranges_bind_a_session_count_never_a_date(self):
        """1M/3M/6M/1Y are session counts, matching the movers horizons on the same screen."""
        for rng, sessions in (("1m", 20), ("3m", 60), ("6m", 126), ("1y", 252)):
            with self.subTest(range=rng):
                status, body, sql, params = self._capture(f"range={rng}")
                self.assertEqual(status, 200)
                self.assertEqual(body["range"], rng)
                self.assertEqual(params, (sessions,))
                # Bound, never formatted into the string.
                self.assertIn("LIMIT %s", sql)

    def test_tail_ranges_return_ascending_for_the_chart(self):
        """DESC picks the most recent N; the chart needs them back in drawing order."""
        _, _, sql, _ = self._capture("range=3m")
        self.assertIn("ORDER BY bar_date DESC", sql)
        self.assertTrue(sql.rstrip().endswith("ORDER BY t.bar_date ASC"))

    def test_ytd_anchors_to_the_latest_session_not_the_wall_clock(self):
        _, _, sql, params = self._capture("range=ytd")
        self.assertIn("date_trunc('year'", sql)
        self.assertIn("SELECT max(bar_date) FROM v_index_history", sql)
        self.assertIsNone(params, "YTD takes no bound parameter")
        self.assertNotIn("now()", sql)
        self.assertNotIn("current_date", sql)

    def test_all_has_no_window(self):
        _, _, sql, params = self._capture("range=all")
        self.assertNotIn("LIMIT", sql)
        self.assertNotIn("WHERE", sql)
        self.assertIsNone(params)

    def test_default_range_is_1y(self):
        _, body, _, params = self._capture()
        self.assertEqual(body["range"], "1y")
        self.assertEqual(params, (252,))

    def test_symbol_is_read_off_the_data_never_taken_from_the_caller(self):
        _, body, sql, _ = self._capture("range=1m")
        self.assertEqual(body["index_symbol"], "VNINDEX")
        # The view resolves it through v_active_model_run; the route names no symbol at all.
        self.assertNotIn("VNINDEX", sql)

    def test_bars_keep_precision_and_null_first_return(self):
        _, body, _, _ = self._capture("range=1m")
        bar = body["bars"][0]
        self.assertEqual(bar["bar_date"], "2026-08-18")
        self.assertEqual(bar["close"], 1832.12)
        self.assertEqual(bar["ret_1d"], 0.003142)
        self.assertIsInstance(bar["volume"], int)

        # The series' first session has no previous close. A fabricated 0 there would draw a
        # flat first step the market never had.
        first_session = dict(INDEX_BAR_ROW, ret_1d=None)
        with mock.patch("app.routes.market.fetch_all", return_value=[first_session]):
            _, body = call_json(_app(), "/api/market/index-history", query="range=all")
        self.assertIsNone(body["bars"][0]["ret_1d"])

    def test_no_active_run_is_503_not_an_empty_chart(self):
        """Same code /api/model/active gives for the same condition — see its own test.

        A line with no points and a line the database cannot name are different failures, and
        503 is this API's answer for the second: the data is not loaded, not absent.
        """
        with mock.patch("app.routes.market.fetch_all", return_value=[]):
            status, body = call_json(_app(), "/api/market/index-history", query="range=1y")
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "no_data")

    def test_invalid_range_is_400_and_never_reaches_the_sql(self):
        captured = {}

        def fake_fetch_all(sql, params=None):  # pragma: no cover - must not run
            captured["sql"] = sql
            return []

        with mock.patch("app.routes.market.fetch_all", side_effect=fake_fetch_all):
            status, body = call_json(
                _app(), "/api/market/index-history", query="range=10y"
            )

        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "invalid_params")
        self.assertNotIn("sql", captured)


TICKER_LIST_ROW = {
    "position": 1,
    "ticker": "VIC",
    "company_name": "Tập đoàn Vingroup",
    "sector": "Bất động sản và Xây dựng",
    "industry": "Bất động sản",
    "anchor_ticker": "VIC",
    "coverage_c": Decimal("1.0000000"),
    "is_anchor": True,
    "under_tau": False,
    "bar_date": date(2026, 8, 18),
    "ret_1d": Decimal("0.0123456"),
}

# One row shaped exactly like _DETAIL_SQL's column list -- a three-way join's worth of fixture,
# deliberately including Decimal, a large integral obv, and a fractional volume_sma_20.
TICKER_DETAIL_ROW = {
    "position": 3,
    "ticker": "PDR",
    "company_name": "Bất động sản Phát Đạt",
    "sector": "Bất động sản và Xây dựng",
    "industry": "Bất động sản",
    "anchor_ticker": "PDR",
    "coverage_c": Decimal("1.0000000"),
    "is_anchor": True,
    "under_tau": False,
    "alpha_hat": Decimal("0.0004123"),
    "beta_hat": Decimal("1.2345678"),
    "sigma_hat": Decimal("0.0234567"),
    "r2": Decimal("0.4123456"),
    "bar_date": date(2026, 8, 18),
    "open": Decimal("24.50"),
    "high": Decimal("25.10"),
    "low": Decimal("24.30"),
    "close": Decimal("24.95"),
    "volume": Decimal("3456789"),
    "sma_20": Decimal("23.8765"),
    "sma_50": Decimal("22.1234"),
    "sma_200": Decimal("20.5678"),
    "ema_12": Decimal("24.1122"),
    "ema_26": Decimal("23.4455"),
    "macd": Decimal("0.6667"),
    "macd_signal": Decimal("0.5123"),
    "macd_hist": Decimal("0.1544"),
    "rsi_14": Decimal("62.3456"),
    "stoch_k_14": Decimal("71.2345"),
    "stoch_d_14": Decimal("68.1234"),
    "atr_14": Decimal("0.8901"),
    "bb_mid_20": Decimal("23.8765"),
    "bb_upper_20": Decimal("25.2345"),
    "bb_lower_20": Decimal("22.5185"),
    "bb_width_20": Decimal("0.1138"),
    "realized_vol_20d": Decimal("0.2891234"),
    "realized_vol_60d": Decimal("0.3123456"),
    "obv": Decimal("123456789012"),
    "volume_sma_20": Decimal("2987654.5"),
    "turnover_value": Decimal("86234567.55"),
    "ret_1d": Decimal("0.0181818"),
    "ret_5d": Decimal("0.0523456"),
    "ret_20d": None,
    "ret_60d": Decimal("-0.0123456"),
    "ret_ytd": Decimal("0.3456789"),
    "dist_from_sma_200_pct": Decimal("0.2131234"),
    "high_252d": Decimal("28.90"),
    "low_252d": Decimal("18.20"),
    "drawdown_from_252d_high": Decimal("-0.1366782"),
}


class TickerListTests(unittest.TestCase):
    def test_ordered_by_position_returns_all_fields(self):
        with mock.patch("app.routes.tickers.fetch_all", return_value=[dict(TICKER_LIST_ROW)]):
            status, body = call_json(_app(), "/api/tickers")

        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        row = body["tickers"][0]
        self.assertEqual(row["ticker"], "VIC")
        self.assertEqual(row["position"], 1)
        self.assertEqual(row["coverage_c"], 1.0)
        self.assertIs(row["is_anchor"], True)
        self.assertEqual(row["ret_1d"], 0.012346)
        self.assertEqual(row["bar_date"], "2026-08-18")

    def test_order_by_clause_is_position_asc(self):
        captured = {}

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            return []

        with mock.patch("app.routes.tickers.fetch_all", side_effect=fake_fetch_all):
            call_json(_app(), "/api/tickers")

        self.assertIn("a.position ASC", captured["sql"])

    def test_empty_universe_is_200_with_empty_list(self):
        with mock.patch("app.routes.tickers.fetch_all", return_value=[]):
            status, body = call_json(_app(), "/api/tickers")

        self.assertEqual(status, 200)
        self.assertEqual(body, {"count": 0, "tickers": []})


class TickerDetailTests(unittest.TestCase):
    def test_serialises_three_blocks(self):
        with mock.patch("app.routes.tickers.fetch_one", return_value=dict(TICKER_DETAIL_ROW)):
            status, body = call_json(_app(), "/api/tickers/PDR")

        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"identity", "assignment", "latest"})

        self.assertEqual(body["identity"]["ticker"], "PDR")
        self.assertEqual(body["identity"]["sector"], "Bất động sản và Xây dựng")

        self.assertEqual(body["assignment"]["position"], 3)
        self.assertIs(body["assignment"]["is_anchor"], True)
        self.assertEqual(body["assignment"]["beta_hat"], 1.234568)

        # A share count is exact -- as a float this would start losing digits.
        self.assertIsInstance(body["latest"]["volume"], int)
        self.assertEqual(body["latest"]["volume"], 3456789)
        # obv is a cumulative sum of integral volumes -- stays an exact int, not a float.
        self.assertIsInstance(body["latest"]["obv"], int)
        self.assertEqual(body["latest"]["obv"], 123456789012)
        # An uncomputed trailing return during warm-up is null, not 0.
        self.assertIsNone(body["latest"]["ret_20d"])
        # RSI/Stochastic are bounded [0, 100] -- not a fraction, so no 6-digit rounding.
        self.assertEqual(body["latest"]["rsi_14"], 62.35)
        # bb_width_20, dist_from_sma_200_pct and drawdown_from_252d_high are ratios (P7 S2),
        # despite reading like percents or prices by name.
        self.assertEqual(body["latest"]["bb_width_20"], 0.1138)
        self.assertEqual(body["latest"]["drawdown_from_252d_high"], -0.136678)

    def test_unknown_ticker_is_404(self):
        with mock.patch("app.routes.tickers.fetch_one", return_value=None):
            status, body = call_json(_app(), "/api/tickers/ZZZZ")

        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "not_found")

    def test_ticker_param_normalised_to_uppercase(self):
        captured = {}

        def fake_fetch_one(sql, params=None):
            captured["params"] = params
            return dict(TICKER_DETAIL_ROW)

        with mock.patch("app.routes.tickers.fetch_one", side_effect=fake_fetch_one):
            call_json(_app(), "/api/tickers/pdr")

        self.assertEqual(captured["params"], ("PDR",))

    def test_no_bar_match_leaves_latest_columns_null(self):
        # A member whose indicators have not been computed yet: the LEFT JOINs still return the
        # identity/assignment half, but every latest-block column is NULL. Must not become 0.
        row = dict(TICKER_DETAIL_ROW)
        for key in row:
            if key not in ("position", "ticker", "company_name", "sector", "industry",
                           "anchor_ticker", "coverage_c", "is_anchor", "under_tau",
                           "alpha_hat", "beta_hat", "sigma_hat", "r2"):
                row[key] = None

        with mock.patch("app.routes.tickers.fetch_one", return_value=row):
            status, body = call_json(_app(), "/api/tickers/PDR")

        self.assertEqual(status, 200)
        for key, value in body["latest"].items():
            if key == "bar_date":
                continue
            self.assertIsNone(value, key)


BAR_ROW = {
    "bar_date": date(2026, 8, 18),
    "open": Decimal("24.50"),
    "high": Decimal("25.10"),
    "low": Decimal("24.30"),
    "close": Decimal("24.95"),
    "volume": Decimal("3456789"),
    "is_adjusted": True,
}

INDICATOR_SERIES_ROW = {
    "bar_date": date(2026, 8, 18),
    "close": Decimal("24.95"),
    "volume": Decimal("3456789"),
    "sma_20": Decimal("23.8765"),
    "sma_50": Decimal("22.1234"),
    "sma_200": Decimal("20.5678"),
    "ema_12": Decimal("24.1122"),
    "ema_26": Decimal("23.4455"),
    "macd": Decimal("0.6667"),
    "macd_signal": Decimal("0.5123"),
    "macd_hist": Decimal("0.1544"),
    "rsi_14": Decimal("62.3456"),
    "stoch_k_14": Decimal("71.2345"),
    "stoch_d_14": Decimal("68.1234"),
    "atr_14": Decimal("0.8901"),
    "bb_mid_20": Decimal("23.8765"),
    "bb_upper_20": Decimal("25.2345"),
    "bb_lower_20": Decimal("22.5185"),
    "bb_width_20": Decimal("0.1138"),
    "realized_vol_20d": Decimal("0.2891234"),
    "realized_vol_60d": Decimal("0.3123456"),
    "obv": Decimal("123456789012"),
    "volume_sma_20": Decimal("2987654.5"),
    "turnover_value": Decimal("86234567.55"),
    "ret_1d": Decimal("0.0181818"),
    "ret_5d": Decimal("0.0523456"),
    "ret_20d": None,
    "ret_60d": Decimal("-0.0123456"),
    "ret_ytd": Decimal("0.3456789"),
    "dist_from_sma_200_pct": Decimal("0.2131234"),
    "high_252d": Decimal("28.90"),
    "low_252d": Decimal("18.20"),
    "drawdown_from_252d_high": Decimal("-0.1366782"),
}


def _capture_series(path, query, *, fetch_all_return, fetch_one_return=None):
    """Run a series route with faked fetch_all/fetch_one, returning (status, body, captured)."""
    captured = {}

    def fake_fetch_all(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return fetch_all_return

    def fake_fetch_one(sql, params=None):
        captured["exists_sql"] = sql
        captured["exists_params"] = params
        return fetch_one_return

    with mock.patch("app.routes.tickers.fetch_all", side_effect=fake_fetch_all), mock.patch(
        "app.routes.tickers.fetch_one", side_effect=fake_fetch_one
    ):
        status, body = call_json(_app(), path, query=query)
    return status, body, captured


class TickerHistoryTests(unittest.TestCase):
    def test_default_window_uses_252_and_null_bounds(self):
        status, body, captured = _capture_series(
            "/api/tickers/PDR/history", "", fetch_all_return=[dict(BAR_ROW)]
        )

        self.assertEqual(status, 200)
        self.assertEqual(body["ticker"], "PDR")
        self.assertEqual(body["count"], 1)
        # ticker, from, from, to, to, limit
        self.assertEqual(captured["params"], ("PDR", None, None, None, None, 252))

    def test_explicit_range_uses_max_rows_not_default_window(self):
        _, _, captured = _capture_series(
            "/api/tickers/PDR/history",
            "from=2026-01-01&to=2026-03-01",
            fetch_all_return=[dict(BAR_ROW)],
        )

        self.assertEqual(
            captured["params"],
            ("PDR", date(2026, 1, 1), date(2026, 1, 1), date(2026, 3, 1), date(2026, 3, 1), 2000),
        )

    def test_from_after_to_is_400_and_never_reaches_sql(self):
        status, body, captured = _capture_series(
            "/api/tickers/PDR/history",
            "from=2026-06-01&to=2026-01-01",
            fetch_all_return=[dict(BAR_ROW)],
        )

        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "invalid_params")
        self.assertNotIn("sql", captured)

    def test_bars_serialise_ohlcv_and_is_adjusted(self):
        _, body, _ = _capture_series(
            "/api/tickers/PDR/history", "", fetch_all_return=[dict(BAR_ROW)]
        )
        row = body["bars"][0]
        self.assertEqual(row["bar_date"], "2026-08-18")
        self.assertEqual(row["close"], 24.95)
        self.assertIsInstance(row["volume"], int)
        self.assertIs(row["is_adjusted"], True)

    def test_unknown_ticker_with_no_rows_is_404(self):
        status, body, _ = _capture_series(
            "/api/tickers/ZZZZ/history", "", fetch_all_return=[], fetch_one_return=None
        )
        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "not_found")

    def test_known_ticker_with_no_rows_in_range_is_200_empty(self):
        # A typo must not look like a quiet market: distinguishing this from the 404 above is
        # the entire point of the existence check.
        status, body, _ = _capture_series(
            "/api/tickers/PDR/history",
            "from=2020-01-01&to=2020-01-05",
            fetch_all_return=[],
            fetch_one_return={"?column?": 1},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ticker": "PDR", "count": 0, "bars": []})


class TickerIndicatorsTests(unittest.TestCase):
    def test_default_window_and_ordering(self):
        status, body, captured = _capture_series(
            "/api/tickers/PDR/indicators", "", fetch_all_return=[dict(INDICATOR_SERIES_ROW)]
        )

        self.assertEqual(status, 200)
        self.assertEqual(captured["params"][-1], 252)
        row = body["indicators"][0]
        self.assertEqual(row["bar_date"], "2026-08-18")
        # close/volume duplicated from daily_bars -- each series response is self-sufficient.
        self.assertEqual(row["close"], 24.95)
        self.assertIsInstance(row["volume"], int)

    def test_obv_stays_exact_int_and_null_return_passes_through(self):
        _, body, _ = _capture_series(
            "/api/tickers/PDR/indicators", "", fetch_all_return=[dict(INDICATOR_SERIES_ROW)]
        )
        row = body["indicators"][0]
        self.assertIsInstance(row["obv"], int)
        self.assertEqual(row["obv"], 123456789012)
        self.assertIsNone(row["ret_20d"])

    def test_oscillators_and_ratios_use_their_own_width(self):
        _, body, _ = _capture_series(
            "/api/tickers/PDR/indicators", "", fetch_all_return=[dict(INDICATOR_SERIES_ROW)]
        )
        row = body["indicators"][0]
        self.assertEqual(row["rsi_14"], 62.35)
        self.assertEqual(row["bb_width_20"], 0.1138)
        self.assertEqual(row["drawdown_from_252d_high"], -0.136678)

    def test_from_after_to_is_400(self):
        status, body, _ = _capture_series(
            "/api/tickers/PDR/indicators",
            "from=2026-06-01&to=2026-01-01",
            fetch_all_return=[dict(INDICATOR_SERIES_ROW)],
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["error"]["code"], "invalid_params")

    def test_unknown_ticker_is_404(self):
        status, body, _ = _capture_series(
            "/api/tickers/ZZZZ/indicators", "", fetch_all_return=[], fetch_one_return=None
        )
        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "not_found")


ANALYSIS_ROW = {
    "bar_date": date(2026, 8, 18),
    "close": Decimal("24.95"),
    "volume": Decimal("3456789"),
    "sma_20": Decimal("23.8765"),
    "sma_50": Decimal("22.1234"),
    "sma_200": Decimal("20.5678"),
    "rsi_14": Decimal("62.3456"),
    "macd_hist": Decimal("0.1544"),
    "bb_upper_20": Decimal("25.2345"),
    "bb_lower_20": Decimal("22.5185"),
    "bb_mid_20": Decimal("23.8765"),
    "volume_sma_20": Decimal("2987654.5"),
    "drawdown_from_252d_high": Decimal("-0.1366782"),
    "ret_5d": Decimal("0.0523456"),
    "ret_20d": None,
    "ret_60d": Decimal("-0.0123456"),
    "ret_ytd": Decimal("0.3456789"),
}


class TickerAnalysisTests(unittest.TestCase):
    def test_full_row_serialises_statements_and_price_basis(self):
        with mock.patch("app.routes.tickers.fetch_one", return_value=dict(ANALYSIS_ROW)):
            status, body = call_json(_app(), "/api/tickers/PDR/analysis")

        self.assertEqual(status, 200)
        self.assertEqual(body["ticker"], "PDR")
        self.assertEqual(body["bar_date"], "2026-08-18")
        self.assertEqual(body["price_basis"], "adjusted")
        self.assertEqual(len(body["statements"]), 12, "13 rules minus ret_20d (NULL)")
        codes = {s["code"] for s in body["statements"]}
        self.assertNotIn("ret_20d", codes)
        skipped_codes = {s["code"] for s in body["skipped"]}
        self.assertEqual(skipped_codes, {"ret_20d"})

    def test_unknown_ticker_is_404(self):
        with mock.patch("app.routes.tickers.fetch_one", return_value=None):
            status, body = call_json(_app(), "/api/tickers/ZZZZ/analysis")

        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "not_found")

    def test_known_ticker_with_no_indicators_yet_is_200_all_skipped(self):
        # v_latest_indicators returns no row: the ticker itself is real, it just has no
        # indicator history computed. This is a fact worth reporting, not a 503.
        captured = {}

        def fake_fetch_one(sql, params=None):
            if "stocks" in sql:
                captured["exists_sql"] = sql
                return {"?column?": 1}
            return None

        with mock.patch("app.routes.tickers.fetch_one", side_effect=fake_fetch_one):
            status, body = call_json(_app(), "/api/tickers/PDR/analysis")

        self.assertEqual(status, 200)
        self.assertEqual(body["statements"], [])
        self.assertEqual(len(body["skipped"]), 13)
        self.assertIsNone(body["bar_date"])
        self.assertIn("exists_sql", captured)

    def test_ticker_param_normalised_to_uppercase(self):
        captured = {}

        def fake_fetch_one(sql, params=None):
            captured["params"] = params
            return dict(ANALYSIS_ROW)

        with mock.patch("app.routes.tickers.fetch_one", side_effect=fake_fetch_one):
            call_json(_app(), "/api/tickers/pdr/analysis")

        self.assertEqual(captured["params"], ("PDR",))


ANCHOR_ROW = {
    "step_k": 1,
    "anchor_ticker": "VIC",
    "position": 5,
    "marginal_gain": Decimal("5.800375824479027"),
    "coverage_f": Decimal("5.800375824479027"),
    "coverage_fbar": Decimal("0.0682397"),
    "in_published_set": True,
    "size": 12,
    "f_j": Decimal("5.8003758"),
    "rho2_mean": Decimal("0.3456789"),
    "rho2_min": Decimal("0.1123456"),
    "sector_composition": {"Bất động sản và Xây dựng": 8, "Tài chính": 4},
    "company_name": "Tập đoàn Vingroup",
    "sector": "Bất động sản và Xây dựng",
}

# step_k=11 > k=10: selected but never published. model_groups has no row for it, so every
# group-shaped column is a real NULL -- not a join bug (00012's own COMMENT ON VIEW says so).
UNPUBLISHED_ANCHOR_ROW = {
    "step_k": 11,
    "anchor_ticker": "VCG",
    "position": 40,
    "marginal_gain": Decimal("1.1478179368951837"),
    "coverage_f": Decimal("34.5"),
    "coverage_fbar": Decimal("0.4059"),
    "in_published_set": False,
    "size": None,
    "f_j": None,
    "rho2_mean": None,
    "rho2_min": None,
    "sector_composition": None,
    "company_name": "Tổng công ty CP XNK và Xây dựng Việt Nam",
    "sector": "Bất động sản và Xây dựng",
}

MEMBER_ROW = {
    "member_ticker": "IDI",
    "company_name": "CTCP Đầu tư và Phát triển Đa Quốc Gia",
    "sector": "Nông nghiệp",
    "position": 30,
    "coverage_c": Decimal("0.8234567"),
    "is_anchor": False,
    "under_tau": False,
    "indicator_date": date(2026, 8, 18),
    "ret_1d": Decimal("-0.0042493"),
    "ret_5d": Decimal("0.0123456"),
    "ret_20d": None,
    "turnover_value": Decimal("12345678.90"),
    "rsi_14": Decimal("55.1234"),
    "dist_from_sma_200_pct": Decimal("0.0567890"),
    "drawdown_from_252d_high": Decimal("-0.1123456"),
}


class AnchorListTests(unittest.TestCase):
    def test_returns_all_fields(self):
        with mock.patch("app.routes.anchors.fetch_all", return_value=[dict(ANCHOR_ROW)]):
            status, body = call_json(_app(), "/api/anchors")

        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        row = body["anchors"][0]
        self.assertEqual(row["anchor_ticker"], "VIC")
        self.assertEqual(row["step_k"], 1)
        self.assertIs(row["in_published_set"], True)
        self.assertEqual(row["marginal_gain"], 5.800376)
        self.assertEqual(row["rho2_mean"], 0.345679)
        self.assertEqual(row["sector_composition"], {"Bất động sản và Xây dựng": 8, "Tài chính": 4})

    def test_ordered_by_step_k_asc(self):
        captured = {}

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            return []

        with mock.patch("app.routes.anchors.fetch_all", side_effect=fake_fetch_all):
            call_json(_app(), "/api/anchors")

        self.assertIn("step_k ASC", captured["sql"])

    def test_unpublished_anchor_has_null_group_fields(self):
        with mock.patch(
            "app.routes.anchors.fetch_all", return_value=[dict(UNPUBLISHED_ANCHOR_ROW)]
        ):
            status, body = call_json(_app(), "/api/anchors")

        self.assertEqual(status, 200)
        row = body["anchors"][0]
        self.assertIs(row["in_published_set"], False)
        for key in ("size", "f_j", "rho2_mean", "rho2_min", "sector_composition"):
            self.assertIsNone(row[key], key)
        # marginal_gain and coverage_f are still real -- selection happened, just unpublished.
        self.assertIsNotNone(row["marginal_gain"])


class AnchorDetailTests(unittest.TestCase):
    def test_serialises_anchor_and_members(self):
        with mock.patch(
            "app.routes.anchors.fetch_one", return_value=dict(ANCHOR_ROW)
        ), mock.patch("app.routes.anchors.fetch_all", return_value=[dict(MEMBER_ROW)]):
            status, body = call_json(_app(), "/api/anchors/VIC")

        self.assertEqual(status, 200)
        self.assertEqual(body["anchor"]["anchor_ticker"], "VIC")
        self.assertEqual(len(body["members"]), 1)
        member = body["members"][0]
        self.assertEqual(member["ticker"], "IDI")
        self.assertEqual(member["coverage_c"], 0.823457)
        self.assertIsNone(member["ret_20d"])
        self.assertEqual(member["indicator_date"], "2026-08-18")

    def test_unknown_anchor_is_404(self):
        with mock.patch("app.routes.anchors.fetch_one", return_value=None):
            status, body = call_json(_app(), "/api/anchors/ZZZZ")

        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "not_found")

    def test_anchor_param_normalised_to_uppercase(self):
        captured = {}

        def fake_fetch_one(sql, params=None):
            captured["params"] = params
            return dict(ANCHOR_ROW)

        with mock.patch(
            "app.routes.anchors.fetch_one", side_effect=fake_fetch_one
        ), mock.patch("app.routes.anchors.fetch_all", return_value=[]):
            call_json(_app(), "/api/anchors/vic")

        self.assertEqual(captured["params"], ("VIC",))

    def test_members_ordered_by_coverage_c_desc(self):
        captured = {}

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            return []

        with mock.patch(
            "app.routes.anchors.fetch_one", return_value=dict(ANCHOR_ROW)
        ), mock.patch("app.routes.anchors.fetch_all", side_effect=fake_fetch_all):
            call_json(_app(), "/api/anchors/VIC")

        self.assertIn("coverage_c DESC", captured["sql"])
        self.assertIn("member_ticker ASC", captured["sql"])

    def test_unpublished_anchor_has_empty_members(self):
        # Selected at step_k=11 but never published: a real row here, no group assigned to it
        # in model_ticker_params, so the members query legitimately returns zero rows.
        with mock.patch(
            "app.routes.anchors.fetch_one", return_value=dict(UNPUBLISHED_ANCHOR_ROW)
        ), mock.patch("app.routes.anchors.fetch_all", return_value=[]):
            status, body = call_json(_app(), "/api/anchors/VCG")

        self.assertEqual(status, 200)
        self.assertEqual(body["members"], [])
        self.assertIsNone(body["anchor"]["size"])


class NoPathToGreedyTests(unittest.TestCase):
    def test_api_does_not_import_pipelines(self):
        """docs/04 §5, made checkable rather than trusted (D-18).

        The serving plane reads stored rows. If a route ever imports pipelines.anchors, a
        request has a path to the greedy algorithm and the static-parameter design is gone.
        """
        leaked = sorted(m for m in sys.modules if m == "pipelines" or m.startswith("pipelines."))
        self.assertEqual(leaked, [], f"services/api imported {leaked}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
