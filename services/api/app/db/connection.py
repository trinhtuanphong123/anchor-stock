"""services.api.app.db.connection — read-only DB access for the API layer.

This module is the ONLY place the API opens database connections. It is
strictly read-only (``SET TRANSACTION READ ONLY``) and never performs writes or
schema operations. Credentials come from ``settings.database_url`` (server-side
env only); the URL is never logged or returned.

Connections live in a process-wide pool, created on the first query and never at import or app
construction. What a pool changes, stated here rather than left to be discovered — every item
below exists because keeping a socket open with nothing travelling over it is a state
per-request connecting never had:

* a session now outlives the request that opened it, so the read-only characteristic is set once
  per connection instead of once per checkout (:func:`_ensure_read_only`);
* a pooled connection can be dead before it is used, so reads retry exactly once
  (:func:`_execute`) — and because a pooled connection's siblings share its fate, the first one
  proved dead retires the whole idle set (:meth:`_ConnectionPool.discard_idle`), or the single
  retry would be spent on a second corpse;
* a dropped socket does not always announce itself, so every connection carries TCP keepalives
  (:data:`_CONNECT_KWARGS`) — otherwise a black-holed flow blocks on kernel retransmission for
  minutes with no timeout in this process able to stop it;
* the pool has a hard ceiling and fails fast past it — 503, not a queue.

Three signal exceptions are raised to the route layer, which maps them to the
stable error envelope (DEC-011):

* ``DatabaseUnavailable`` — no ``DATABASE_URL`` and dev fixtures are off (-> 503).
* ``NoData``              — no valid precomputed rows exist yet (-> 503).
* ``NotFound``            — an explicitly-requested resource does not exist (-> 404).

Dev fixtures (``API_DEV_FIXTURES``) are an opt-in, server-side flag used only
when no ``DATABASE_URL`` is configured; they never touch production tables.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import deque
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any

logger = logging.getLogger(__name__)


class DatabaseUnavailable(Exception):
    """No live database configured and dev fixtures are disabled."""


class NoData(Exception):
    """A query found no valid precomputed rows yet."""


class NotFound(Exception):
    """An explicitly-requested resource (a ticker, an anchor, a run_id) does not exist."""


_CONNECT_TIMEOUT = 5  # seconds

# Passed to every ``psycopg2.connect`` this module makes. ``connect_timeout`` bounds the
# handshake; the keepalives bound a failure that only a POOL can have, because only a pool keeps
# a socket open with nothing travelling over it.
#
# Measured against the real Supabase session pooler: after ``pg_terminate_backend`` killed a
# pooled connection, ``conn.closed`` still read 0 — psycopg2 learns nothing until the next
# statement. When the peer's FIN/RST arrives that is harmless, because the next ``execute``
# fails at once and :func:`_execute` retries (measured end to end: 1,365 ms, served correctly).
# The dangerous case is when nothing arrives — a NAT or load balancer between Render's Singapore
# egress and Supabase's Sydney pooler dropping an idle flow without telling either end. Then
# ``execute`` blocks on TCP retransmission for the kernel's own timeout, ~15 minutes on Linux at
# the default ``tcp_retries2``, holding a Uvicorn threadpool slot the whole time. Neither guard
# already in place applies: ``connect_timeout`` is spent (the socket is open) and the server's
# ``statement_timeout`` (2 min here) never starts, because the server never receives the query.
#
# libpq's keepalives turn that hang into an errno the retry can act on: probes start after 30 s
# of silence and give up after 3 misses 10 s apart, so a black-holed connection surfaces as an
# ``OperationalError`` in about a minute instead of a quarter of an hour.
_CONNECT_KWARGS = {
    "connect_timeout": _CONNECT_TIMEOUT,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}

# How many connections may be open at once. See `_ConnectionPool` for the sizing argument and
# for the measurements behind this whole design.
_POOL_MAX = 8

# Created lazily on first use, never at import or app construction: test_45/test_46/test_54 pin
# that validation and `create_app()` open no connection, and production startup depends on it.
_POOL = None

# Guards creation of the singleton only — NOT the pool's own bookkeeping, which has its own lock.
# Without it, concurrent first requests each see `_POOL is None` and each build a pool; measured
# on the earlier psycopg2-based version, six concurrent cold-start requests produced six pools,
# five orphaned, and five connections neither pooled nor closed — silently, because returning a
# connection to a pool that never issued it raised into the `finally` that swallowed it. Uvicorn
# runs sync endpoints in a threadpool, so this is reachable on every cold start.
_POOL_LOCK = threading.Lock()


class PoolError(Exception):
    """The pool cannot supply a connection: exhausted, or already closed."""


class _ConnectionPool:
    """A small pool that does every network operation OUTSIDE its lock.

    **Why not `psycopg2.pool.ThreadedConnectionPool`.** It was tried, and measured against the
    real Supabase session pooler (ap-southeast-2, a ~955 ms handshake from here) at 9 page loads
    of 4 concurrent requests — the ticker screen's actual shape:

    ========================================  ========  ==========  ===========
    shape                                     handshk   1st load    loads 2-9
    ========================================  ========  ==========  ===========
    no pool (one connect per request)               36     1330 ms      1338 ms
    ThreadedConnectionPool                           4     8647 ms       903 ms
    this pool                                        4     1652 ms       482 ms
    ========================================  ========  ==========  ===========

    `ThreadedConnectionPool.getconn` holds one lock across the whole of `_getconn`, and
    `_getconn` calls `psycopg2.connect()` while holding it. So every handshake is serialised:
    four concurrent first requests pay four handshakes end to end instead of one. `putconn` holds
    the same lock across its `rollback()`, serialising a second round trip per request. That made
    the first page load roughly five times slower than connecting per request — the load a reader
    of a spun-down free instance actually sees.

    Here the lock protects bookkeeping only — a deque of idle connections and a lease count.
    Connecting and rolling back happen outside it, so concurrent requests do that work in
    parallel, exactly as the unpooled code already did.

    **What the first load still costs, and why.** Measured by alternating cold loads six times
    each: 1330 ms unpooled against 1652 ms pooled, +321 ms. That is not serialisation — it is the
    `rollback()` this pool must issue to return a connection in a reusable state, which closing a
    connection does not need. It is repaid on the very next page load, which saves ~856 ms.
    Removing it is what `autocommit` would buy (measured: 1st load 1363 ms, later loads 161 ms),
    and that is deliberately a separate decision: it drops the shared snapshot across the two
    queries `anchor_detail` issues.

    Sizing: `maxsize` counts *handlers in flight*, not queries. Within a handler the queries run
    in sequence and each `read_cursor()` returns its connection before the next opens one. The
    ticker screen fires four routes in parallel (P10.5) plus the provenance strip, so five is the
    realistic peak for one viewer; the default leaves room for two. Past the ceiling `getconn`
    raises rather than blocks — D-21 records that this deployment has no connection-count
    pressure, so back-pressure is cheaper than a queue nobody needs.
    """

    def __init__(self, url: str, maxsize: int) -> None:
        self._url = url
        self._max = maxsize
        self._idle: deque = deque()
        self._lock = threading.Lock()
        self._leased = 0  # handed out OR currently being opened — both occupy a slot
        self._closed = False

    def getconn(self):
        """Return a pooled connection, or open one. Raises :class:`PoolError` past the ceiling."""
        with self._lock:
            if self._closed:
                raise PoolError("connection pool is closed")
            while self._idle:
                conn = self._idle.pop()
                if not conn.closed:
                    self._leased += 1
                    return conn
                # Closed while idle (server hung up, or close_pool raced us): drop and look on.
            if self._leased >= self._max:
                raise PoolError("connection pool exhausted")
            self._leased += 1  # reserve the slot before releasing the lock

        import psycopg2  # noqa: PLC0415

        try:
            return psycopg2.connect(self._url, **_CONNECT_KWARGS)
        except Exception:
            with self._lock:
                self._leased -= 1  # the reservation must not outlive the failure
            raise

    def putconn(self, conn, close: bool = False) -> None:
        """Return a connection. ``close=True`` retires it instead of pooling it."""
        drop = close or conn.closed
        if not drop:
            # Reset before taking the lock: a rollback is a round trip, and holding the lock
            # across it is precisely what made psycopg2's pool slow.
            try:
                from psycopg2.extensions import TRANSACTION_STATUS_IDLE  # noqa: PLC0415

                if conn.info.transaction_status != TRANSACTION_STATUS_IDLE:
                    conn.rollback()
            except Exception:  # noqa: BLE001 - a connection that will not reset is not reusable
                drop = True
        with self._lock:
            self._leased -= 1
            if drop or self._closed:
                dead = conn
            else:
                self._idle.append(conn)
                dead = None
        if dead is not None:
            try:
                dead.close()
            except Exception:  # noqa: BLE001
                pass

    def discard_idle(self) -> None:
        """Retire every currently-idle connection, keeping the pool open for new ones.

        Called when a checked-out connection turns out to be dead. Every connection in this pool
        was opened to the same host through the same Supabase pooler, so whatever ended one — the
        pooler restarting, an idle-flow timeout in the middle, a failover — has almost certainly
        ended its siblings too. Left in place, they are handed to the next callers in turn, and
        :func:`_execute` only retries ONCE: a page load of four parallel requests against four
        stale connections would spend the retry on a second stale one and answer 503.

        Discarding them costs at most ``_POOL_MAX`` handshakes that a rare event was going to
        force anyway, and only when a connection has *already* been proved dead. It is never
        reached in normal operation.
        """
        with self._lock:
            idle, self._idle = list(self._idle), deque()
        for conn in idle:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        if idle:
            logger.info(
                "discarded %d idle pooled connection(s) after a connection failure", len(idle)
            )

    def closeall(self) -> None:
        """Close every idle connection and refuse further checkouts. Idempotent."""
        with self._lock:
            self._closed = True
            idle, self._idle = list(self._idle), deque()
        for conn in idle:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def _new_pool(url: str) -> _ConnectionPool:
    """Build the process pool. Separate from the class so tests can substitute a shape."""
    return _ConnectionPool(url, _POOL_MAX)


def _get_pool():
    """Return the process-wide connection pool, creating it on first use.

    Read-only pool for a strictly read-only service (DEC-011). Created only from
    ``read_cursor()`` so nothing connects at import or app startup. Raises
    :class:`DatabaseUnavailable` when there is no URL or no driver — the same contract the old
    per-call ``psycopg2.connect`` had.

    Double-checked: the hot path never touches the lock, and creation happens exactly once.
    """
    global _POOL
    pool = _POOL
    if pool is not None:
        return pool
    from app.config import settings  # noqa: PLC0415

    url = settings.database_url
    if not url:
        raise DatabaseUnavailable()
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = _new_pool(url)
        return _POOL


def close_pool() -> None:
    """Close every pooled connection and reset the pool. Safe to call more than once.

    Wired to the application's shutdown (``app.main``) so a terminating process hands its
    connections back instead of leaving the pooler to time them out. Never called at startup —
    the pool does not exist until the first query.
    """
    global _POOL
    with _POOL_LOCK:
        pool, _POOL = _POOL, None
    if pool is None:
        return
    try:
        pool.closeall()
    except Exception:  # noqa: BLE001 - shutdown must not raise
        logger.warning("failed to close the connection pool cleanly", exc_info=True)


def _read_only_is_mandatory() -> bool:
    """True when a failure to set a connection read-only must stop the request.

    `services/api` connects as ``postgres`` (D-20 revoked the API roles' grants), so
    ``set_session(readonly=True)`` is the only write barrier at the connection layer. While its
    failure was swallowed, anything that stopped the statement from taking effect degraded
    silently to a read-write superuser session. In production that is fatal.

    Outside production it stays a warning: not every stand-in connection supports `set_session`,
    and local work must not require one that does.

    **The mode is read from the live environment, not from the imported ``settings`` singleton.**
    `app.config` says so itself: that singleton is snapshotted at import and "does NOT drive app
    construction or the production guards", which `create_app()` re-resolves per call so that a
    process which imported under development and later set ``ENV=production`` cannot bypass them.
    This function is one of those guards — the one that decides whether a missing write barrier
    stops the request — so reading the snapshot would have let exactly that sequence turn the
    refusal back into a warning, silently, which is the failure mode this check exists to end.
    A fresh read costs one ``Settings()`` construction per *connection* (the caller short-circuits
    once ``conn.readonly`` is set), not per request.
    """
    from app.config import Settings  # noqa: PLC0415
    from app.runtime_guards import RuntimeConfigError, normalize_mode  # noqa: PLC0415

    try:
        return normalize_mode(Settings().env) == "production"
    except RuntimeConfigError:
        # An unrecognised ENV cannot reach here (create_app refuses it), but if it ever did, the
        # strict branch is the safe one.
        return True


def _ensure_read_only(conn) -> None:
    """Assert the read-only session characteristic, skipping the round trip when already set.

    ``SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`` is a property of the *session*, and
    a pooled session now outlives the request that created it — so this is issued once per
    connection rather than once per checkout. `conn.readonly` is psycopg2's own local record of
    that state and costs nothing to read.

    If a future psycopg2 stopped reflecting it, the check simply never short-circuits and every
    checkout re-issues the statement, which is exactly today's behaviour. The optimisation can
    fail; the guarantee cannot.
    """
    if conn.readonly is True:
        return
    try:
        conn.set_session(readonly=True)
    except _connection_errors():
        # The connection died, the guarantee did not. Let it through unchanged so `_execute`
        # retries on a fresh connection; converting it here would answer 503 while logging
        # "could not set the connection read-only", which points a reader at the write barrier
        # for what is a dropped socket. Fail-closed is preserved either way: if the retry also
        # cannot set the characteristic, the branch below still refuses to serve.
        raise
    except Exception as exc:  # noqa: BLE001 - not every backend supports it
        if _read_only_is_mandatory():
            logger.error("could not set the connection read-only; refusing to serve")
            raise DatabaseUnavailable() from exc
        logger.warning("could not set the connection read-only; continuing (non-production)")


def dev_fixtures_enabled() -> bool:
    """True when the opt-in dev-fixture flag is set (server-side env only).

    Uses the single canonical truthy definition; production startup
    already fails fast when this flag is truthy, so this path is dev/test only.
    """
    from app.runtime_guards import is_truthy_fixture  # noqa: PLC0415

    return is_truthy_fixture(os.environ.get("API_DEV_FIXTURES"))


def live_db_configured() -> bool:
    """True when a real database URL is configured."""
    from app.config import settings  # noqa: PLC0415

    return bool(settings.database_url)


def _connection_errors() -> tuple[type[BaseException], ...]:
    """The psycopg2 errors that mean *this connection* is finished, not *this query* is wrong.

    ``ProgrammingError`` — a bad statement — is a sibling under ``DatabaseError`` and is
    deliberately absent: retrying malformed SQL only produces the same failure twice.
    """
    try:
        import psycopg2  # noqa: PLC0415
    except ImportError:  # pragma: no cover - environment-dependent
        return ()
    return (psycopg2.OperationalError, psycopg2.InterfaceError)


@contextmanager
def read_cursor() -> Generator[Any]:
    """Yield a read-only ``RealDictCursor`` borrowed from the process connection pool.

    On a clean exit the connection returns to the pool, rolled back to a pristine state and
    reusable. If the body raises a *connection-level* error the connection is closed instead of
    pooled: a session the server has already dropped must not be handed to the next request.
    Callers that want that retried go through :func:`_execute`.

    Lazily imports psycopg2 so the service still boots if the driver is absent (the health
    endpoint reports ``unconfigured``/``error`` separately). Raises :class:`DatabaseUnavailable`
    when there is no URL, no driver, the read-only guarantee could not be established in
    production, or the pool is exhausted — all ``_POOL_MAX`` connections busy, where the pool
    fails fast rather than blocking.
    """
    try:
        from psycopg2.extras import RealDictCursor  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise DatabaseUnavailable() from exc

    # Hold the pool that issued this connection. Re-resolving it in `finally` could return a
    # different object and return the connection to a pool that never owned it.
    pool = _get_pool()
    try:
        conn = pool.getconn()
    except Exception as exc:  # noqa: BLE001 - PoolError or a failed lazy connect
        raise DatabaseUnavailable() from exc

    discard = False
    try:
        try:
            _ensure_read_only(conn)
        except Exception:
            discard = True  # a session that cannot be made read-only is not reusable
            raise
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
    except _connection_errors():
        discard = True
        # This connection is gone, and its siblings were opened to the same pooler at the same
        # time. Retire them too rather than feed them to the retry one at a time.
        pool.discard_idle()
        raise
    finally:
        try:
            pool.putconn(conn, close=discard)
        except Exception:  # noqa: BLE001 - returning a connection must not mask the real error
            logger.warning("failed to return a connection to the pool", exc_info=True)


def _execute(
    sql: str,
    params: Sequence[Any] | None,
    reduce: Callable[[Any], Any],
) -> Any:
    """Run one read query, retrying once if the pooled connection turned out to be dead.

    Pooling introduces a failure the per-request connect could not have: a connection idle in the
    pool that the server (Supavisor, or the network) has since dropped is handed out looking
    healthy, and only `execute` discovers otherwise. Without this, that surfaced as a 500.

    **The retry is safe because this service is strictly read-only (DEC-011).** Every statement
    it issues is a SELECT against a view, so re-running one is idempotent by construction. That
    is a precondition, not a coincidence — a service that wrote could not do this.

    Exactly two attempts. The second failure becomes :class:`DatabaseUnavailable` (503, the
    "system is not ready" envelope) rather than an unhandled 500.
    """
    last: BaseException | None = None
    for _ in range(2):
        try:
            with read_cursor() as cur:
                cur.execute(sql, tuple(params or ()))
                return reduce(cur)
        except _connection_errors() as exc:
            # read_cursor has already closed the bad connection rather than pooling it.
            last = exc
            logger.warning("pooled connection failed mid-query; retrying once", exc_info=True)
    raise DatabaseUnavailable() from last


def fetch_all(sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    """Run a read query and return all rows as dicts (empty list if none)."""
    return _execute(sql, params, lambda cur: [dict(r) for r in cur.fetchall()])


def fetch_one(sql: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
    """Run a read query and return the first row as a dict, or None."""

    def first(cur: Any) -> dict[str, Any] | None:
        row = cur.fetchone()
        return dict(row) if row else None

    return _execute(sql, params, first)


# ---------------------------------------------------------------------------
# Serialization helpers (DB cell -> ISO-8601 UTC string)
# ---------------------------------------------------------------------------


def iso_date(value: Any) -> str | None:
    """``date``/``datetime`` -> ``YYYY-MM-DD`` (None passes through)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def iso_ts(value: Any) -> str | None:
    """``timestamptz``/``datetime`` -> ``YYYY-MM-DDTHH:MM:SSZ`` (UTC)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=UTC)
        return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def as_float(value: Any, ndigits: int = 3) -> float | None:
    """Numeric -> rounded float (None if NULL or non-numeric)."""
    if value is None:
        return None
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return None


def today() -> date:
    """Current local date (kept centralized for testability)."""
    return date.today()
