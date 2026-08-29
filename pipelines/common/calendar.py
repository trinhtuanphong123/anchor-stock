"""pipelines.common.calendar — trading-calendar gate.

Primary source: ``trading_calendar`` table (when DB is configured).
Fallback:       Mon–Fri weekday heuristic (never crashes the worker).

Usage::

    from pipelines.common.calendar import is_trading_day

    if not is_trading_day():
        logger.info("Non-trading day — skipping")
        return
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta

logger = logging.getLogger(__name__)

# Emit the fallback warning at most once per process lifetime.
_fallback_warned: bool = False


def is_trading_day(check_date: date | None = None) -> bool:
    """Return True if *check_date* is a trading day.

    Queries ``trading_calendar.is_trading_day`` via the database.
    Falls back silently to a Mon–Fri weekday heuristic when:
    - ``DATABASE_URL`` is not configured, or
    - the DB is unreachable, or
    - *check_date* is not yet present in the calendar.

    Args:
        check_date: Date to test.  Defaults to ``date.today()``.

    Returns:
        ``True``  — authoritative trading day, or weekday when calendar absent.
        ``False`` — authoritative non-trading day, or weekend when calendar absent.
    """
    global _fallback_warned

    if check_date is None:
        check_date = date.today()

    # ------------------------------------------------------------------
    # Attempt authoritative DB lookup first
    # ------------------------------------------------------------------
    try:
        from pipelines.common.db import cursor  # noqa: PLC0415

        with cursor() as cur:
            cur.execute(
                "SELECT is_trading_day FROM trading_calendar WHERE cal_date = %s",
                (check_date,),
            )
            row = cur.fetchone()
            if row is not None:
                return bool(row[0])
            # Date exists in DB but not in calendar yet — fall through.
            logger.debug(
                "calendar: %s not found in trading_calendar; using weekday fallback",
                check_date,
            )
    except Exception:  # noqa: BLE001
        if not _fallback_warned:
            logger.warning(
                "calendar: trading_calendar unavailable (DB not configured or unreachable). "
                "Using Mon–Fri weekday heuristic.  Set DATABASE_URL for authoritative dates."
            )
            _fallback_warned = True

    # ------------------------------------------------------------------
    # Fallback: Mon(0)–Fri(4) = tentative trading; Sat(5)–Sun(6) = non-trading
    # ------------------------------------------------------------------
    return check_date.weekday() < 5


# HOSE trading session window (UTC boundaries).
# Morning session:   09:00–11:30 ICT = 02:00–04:30 UTC
# Afternoon session: 13:00–15:00 ICT = 06:00–08:00 UTC
# Gate window spans both sessions plus the lunch break (04:30–06:00 UTC);
# running during the lunch break is harmless — no new bars are traded then.
# Close matches the documented HOSE session end: 15:00 ICT = 08:00 UTC.
# Use --force to bypass this gate for manual re-runs after close.
_SESSION_OPEN_UTC: time = time(2, 0)  # 09:00 ICT — HOSE morning session open
_SESSION_CLOSE_UTC: time = time(8, 0) # 15:00 ICT — documented HOSE session close

# Emit the fallback warning at most once per process lifetime.
_trading_hours_fallback_warned: bool = False


def is_trading_hours(
    check_date: date | None = None,
    now_utc: datetime | None = None,
) -> bool:
    """Return True if now_utc falls within the trading session window for check_date.

    Used to gate the hourly 5-minute intraday refresh (DEC-006, DEC-008).
    The window is the *outer* boundary: it covers both the HOSE morning session
    (09:00–11:30 ICT) and the afternoon session (13:00–15:00 ICT) plus the
    lunch break, because running during the break is harmless.

    Tries to read session_open / session_close from trading_calendar (assumed
    to be stored in ICT = UTC+7, consistent with SESSION_CLOSE_UTC's derivation
    in daily_incremental.py).  Falls back to module-level constants when the DB
    is unavailable or the date is not yet in the calendar.

    Args:
        check_date: Date whose session boundaries to use (default: today).
        now_utc:    Current UTC datetime (default: datetime.now(timezone.utc)).
                    Injectable for testing.

    Returns:
        True  — now_utc is inside the trading session window.
        False — now_utc is before the open or after the close.
    """
    global _trading_hours_fallback_warned

    if check_date is None:
        check_date = date.today()
    if now_utc is None:
        now_utc = datetime.now(UTC)

    # Strip tz for comparison against naive time constants
    now_time_utc_naive = now_utc.replace(tzinfo=None).time()

    open_utc = _SESSION_OPEN_UTC
    close_utc = _SESSION_CLOSE_UTC

    # Attempt to read session_open / session_close from trading_calendar.
    # Assume stored in ICT (UTC+7); subtract 7 hours to get UTC.
    try:
        from pipelines.common.db import cursor  # noqa: PLC0415

        with cursor() as cur:
            cur.execute(
                "SELECT session_open, session_close "
                "FROM trading_calendar WHERE cal_date = %s",
                (check_date,),
            )
            row = cur.fetchone()
            if row and row[0] is not None and row[1] is not None:
                ict_offset = timedelta(hours=7)
                open_dt_utc = datetime.combine(check_date, row[0]) - ict_offset
                close_dt_utc = datetime.combine(check_date, row[1]) - ict_offset
                open_utc = open_dt_utc.time()
                close_utc = close_dt_utc.time()
    except Exception:  # noqa: BLE001
        if not _trading_hours_fallback_warned:
            logger.warning(
                "calendar: trading_calendar session times unavailable. "
                "Using hardcoded UTC constants for is_trading_hours."
            )
            _trading_hours_fallback_warned = True

    return open_utc <= now_time_utc_naive < close_utc
