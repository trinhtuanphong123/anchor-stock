"""P15/C1+C2 — GZipMiddleware and the Cache-Control header wired in app.main.

Same idiom as test_routes.py: standard-library unittest only, no database, no httpx. The ASGI
harness here is a superset of test_routes.py's ``_call_asgi`` — it also returns response
headers, which those tests never needed and this one exists specifically to check.
"""

from __future__ import annotations

import asyncio
import gzip
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ["ENV"] = "test"

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.main import create_app  # noqa: E402
from app.runtime_guards import resolve_runtime  # noqa: E402


async def _call_asgi(app, method, path, headers=None):
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
    response_headers: dict[str, str] = {}
    body = b""
    for message in messages:
        if message["type"] == "http.response.start":
            status = message["status"]
            response_headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in message.get("headers", [])
            }
        elif message["type"] == "http.response.body":
            body += message.get("body", b"") or b""
    return status, response_headers, body


def call(app, path, headers=None):
    return asyncio.run(_call_asgi(app, "GET", path, headers=headers))


def _app():
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


#: 30 rows is comfortably past GZipMiddleware's default 500-byte minimum_size, and past what
#: any single ticker-list row could compress to nothing.
_MANY_TICKERS = [
    {
        "position": i, "ticker": f"T{i:03d}", "company_name": f"Company {i}",
        "sector": "Industrials", "industry": "Industrials", "anchor_ticker": f"T{i:03d}",
        "coverage_c": 0.5, "is_anchor": False, "under_tau": False,
        "bar_date": None, "ret_1d": 0.01,
    }
    for i in range(30)
]


class GZipMiddlewareTests(unittest.TestCase):
    def test_a_large_response_is_gzipped_when_the_client_accepts_it(self):
        with mock.patch("app.routes.tickers.fetch_all", return_value=list(_MANY_TICKERS)):
            status, headers, body = call(
                _app(), "/api/tickers", headers={"Accept-Encoding": "gzip"},
            )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("content-encoding"), "gzip")
        # The wire body is the gzip stream; decompressing it recovers the JSON.
        decompressed = gzip.decompress(body)
        self.assertIn(b'"count":30', decompressed)

    def test_no_accept_encoding_header_means_no_gzip(self):
        with mock.patch("app.routes.tickers.fetch_all", return_value=list(_MANY_TICKERS)):
            status, headers, body = call(_app(), "/api/tickers")
        self.assertEqual(status, 200)
        self.assertNotIn("content-encoding", headers)
        self.assertIn(b'"count":30', body)


class CacheControlHeaderTests(unittest.TestCase):
    def test_api_200_gets_a_60_second_cache_control_header(self):
        with mock.patch("app.routes.tickers.fetch_all", return_value=list(_MANY_TICKERS)):
            status, headers, _ = call(_app(), "/api/tickers")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("cache-control"), "public, max-age=60")

    def test_health_is_never_cache_controlled(self):
        # /health must always reflect live connectivity — caching it would let a stale "ok"
        # survive an outage for up to a minute.
        _, headers, _ = call(_app(), "/health")
        self.assertNotIn("cache-control", headers)

    def test_an_error_response_is_not_cache_controlled(self):
        with mock.patch("app.routes.model.fetch_one", return_value=None):
            status, headers, _ = call(_app(), "/api/model/active")
        self.assertEqual(status, 503)
        self.assertNotIn("cache-control", headers)


if __name__ == "__main__":
    unittest.main()
