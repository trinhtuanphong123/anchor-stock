-- =============================================================================
-- 00001_reference.sql — reference data: tickers, universe versions, calendar.
--
-- Baseline migration 1 of 9 for the anchor model. The superseded pre-anchor set
-- (Leiden clustering, behavior windows, dashboard snapshots) lives in _archive/
-- and is not applied: it could not be applied, because its 00012 granted on
-- eleven tables no migration created. See docs/00-project-status.md §3.
--
-- Applied to an empty database, so every statement is a plain CREATE.
-- No production data inserted. No secrets referenced.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- stocks — ticker master.
-- Metadata is enriched from the provider listing when available; unknown fields
-- stay NULL rather than being fabricated, because sector labels are used as
-- EXTERNAL VALIDATION of the anchor groups (docs/02 §3g) and an invented sector
-- would make that validation circular.
-- -----------------------------------------------------------------------------
CREATE TABLE stocks (
    ticker          text        PRIMARY KEY,
    exchange        text,                       -- HOSE / HNX / UPCOM
    company_name    text,
    sector          text,
    industry        text,
    icb_code        text,
    listed_date     date,
    is_active       boolean     NOT NULL DEFAULT true,
    first_seen_date date,
    last_seen_date  date,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_stocks_sector   ON stocks (sector);
CREATE INDEX idx_stocks_exchange ON stocks (exchange);

COMMENT ON TABLE stocks IS
    'Ticker master. Sector/industry are external validation only — they never enter the '
    'similarity matrix or the selection objective (docs/02 §3g).';

-- -----------------------------------------------------------------------------
-- universe_snapshots — one row per distinct content of list_stocks.txt.
--
-- universe_version is CONTENT-ADDRESSED: it is derived from a SHA-256 over the
-- normalised (uppercased, deduplicated, ascending) ticker list. Two runs share a
-- version if and only if they ran on the same set. Nothing has to remember to
-- bump a counter, and one version can never mean two different sets.
-- -----------------------------------------------------------------------------
CREATE TABLE universe_snapshots (
    universe_version text        PRIMARY KEY,   -- 'u' || left(sha256, 8)
    sha256           text        NOT NULL,
    n_tickers        int         NOT NULL CHECK (n_tickers > 0),
    source_file      text,                      -- provenance, e.g. 'list_stocks.txt'
    note             text,
    created_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT universe_snapshots_sha_len CHECK (char_length(sha256) = 64)
);

-- -----------------------------------------------------------------------------
-- universe_members — the ORDERED universe.
--
-- `position` is the load-bearing column. Every vector and matrix downstream is
-- stored positionally (docs/04 §2: "the universe list fixes ordering ... a
-- reordered universe silently misaligns everything"). Making position an
-- explicit, uniquely-constrained column is the durable form of that rule: the
-- ordering is a stored fact that can be checked, not a convention that has to be
-- remembered by every writer.
--
-- Positions are 0-based to match the numpy arrays they index.
-- -----------------------------------------------------------------------------
CREATE TABLE universe_members (
    universe_version text NOT NULL REFERENCES universe_snapshots ON DELETE CASCADE,
    ticker           text NOT NULL REFERENCES stocks,
    position         int  NOT NULL CHECK (position >= 0),

    CONSTRAINT universe_members_pk PRIMARY KEY (universe_version, ticker),
    CONSTRAINT universe_members_position_uq UNIQUE (universe_version, position)
);

CREATE INDEX idx_universe_members_ticker ON universe_members (ticker);

-- -----------------------------------------------------------------------------
-- trading_calendar — which dates are sessions, and their dense ordering.
--
-- Derived from market_index_bars: a session exists if and only if the index
-- printed a close. That makes the calendar a consequence of observed data rather
-- than an assumption maintained by hand, which matters because minimum-session
-- gates were deliberately removed — "take whatever data is available".
--
-- session_seq is a dense rank over trading days, so "the trailing W sessions"
-- becomes a subtraction rather than a window function. NULL on non-trading days.
-- -----------------------------------------------------------------------------
CREATE TABLE trading_calendar (
    cal_date       date        PRIMARY KEY,
    is_trading_day boolean     NOT NULL,
    day_type       text        NOT NULL DEFAULT 'trading'
                               CONSTRAINT trading_calendar_day_type_check
                               CHECK (day_type IN ('trading', 'weekend', 'holiday',
                                                   'manual_closure')),
    session_seq    bigint,                      -- dense rank; NULL when not a session
    note           text,
    created_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT trading_calendar_seq_iff_trading
        CHECK ((session_seq IS NOT NULL) = is_trading_day)
);

CREATE INDEX idx_trading_calendar_trading ON trading_calendar (is_trading_day);
CREATE UNIQUE INDEX ux_trading_calendar_session_seq
    ON trading_calendar (session_seq) WHERE session_seq IS NOT NULL;

-- =============================================================================
-- Done. No production data inserted.
-- =============================================================================
