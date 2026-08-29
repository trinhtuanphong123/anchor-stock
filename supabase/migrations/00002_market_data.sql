-- =============================================================================
-- 00002_market_data.sql — raw landing + typed daily bars.
--
-- Ingestion is two-pass: land the provider payload untouched, then parse it into
-- typed rows. The raw layer is the audit trail every stored number traces back
-- to; without it, "why is this close 41.2?" has no answer once the provider's
-- history moves under you.
--
-- Baseline migration 2 of 9. No production data inserted. No secrets referenced.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS staging;

-- -----------------------------------------------------------------------------
-- staging.ohlc_raw — provider payloads exactly as received.
-- Re-fetching a day overwrites the same key, so running a day twice is safe.
-- The local track writes these same record dicts as JSON Lines; that shared
-- shape is what makes the local and dashboard tracks the same pipeline.
-- -----------------------------------------------------------------------------
CREATE TABLE staging.ohlc_raw (
    symbol     text        NOT NULL,
    bar_type   text        NOT NULL
                           CONSTRAINT ohlc_raw_bar_type_check
                           CHECK (bar_type IN ('EQUITY', 'INDEX')),
    bar_date   date        NOT NULL,
    payload    jsonb       NOT NULL,            -- raw fields, uninterpreted
    provider   text        NOT NULL DEFAULT 'VCI',
    fetched_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ohlc_raw_pk PRIMARY KEY (symbol, bar_type, bar_date)
);

CREATE INDEX idx_ohlc_raw_type_date ON staging.ohlc_raw (bar_type, bar_date);

-- -----------------------------------------------------------------------------
-- daily_bars — typed equity OHLCV. The only market-data input to the model.
--
-- is_adjusted records whether the provider's close is corporate-action adjusted.
-- docs/01 §1 REQUIRES adjusted closes: an unadjusted series manufactures a fake
-- return on every ex-date, and because ex-dates are idiosyncratic the one-factor
-- model will not absorb them — they land straight in the residuals that P is
-- built from. This column is therefore nullable-by-intent: NULL means "not yet
-- verified", which is honest, and is the current state.
-- See docs/decisions/D-06-adjusted-close-semantics.md — OPEN.
-- -----------------------------------------------------------------------------
CREATE TABLE daily_bars (
    ticker      text        NOT NULL REFERENCES stocks,
    bar_date    date        NOT NULL,
    source      text        NOT NULL DEFAULT 'VCI',
    open        numeric     CHECK (open   >= 0),
    high        numeric     CHECK (high   >= 0),
    low         numeric     CHECK (low    >= 0),
    close       numeric     NOT NULL CHECK (close >= 0),
    volume      numeric     CHECK (volume >= 0),
    is_adjusted boolean,                        -- NULL = unverified; see D-6
    ingested_at timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT daily_bars_pk PRIMARY KEY (ticker, bar_date, source),
    CONSTRAINT daily_bars_high_gte_low
        CHECK (high IS NULL OR low IS NULL OR high >= low)
);

CREATE INDEX idx_daily_bars_date        ON daily_bars (bar_date);
CREATE INDEX idx_daily_bars_ticker_date ON daily_bars (ticker, bar_date DESC);

COMMENT ON COLUMN daily_bars.close IS
    'Adjusted close per docs/01 §1 — the model''s only price input. NOT NULL because a bar '
    'without a close cannot produce a return and must be dropped before upsert, not stored '
    'as a hole for a later stage to trip over.';

-- -----------------------------------------------------------------------------
-- market_index_bars — the market factor's source (VNINDEX).
-- close is NOT NULL because it IS the factor; OHLV are nullable since some index
-- feeds provide close only.
-- -----------------------------------------------------------------------------
CREATE TABLE market_index_bars (
    index_symbol text        NOT NULL,
    bar_date     date        NOT NULL,
    source       text        NOT NULL DEFAULT 'VCI',
    open         numeric     CHECK (open   >= 0),
    high         numeric     CHECK (high   >= 0),
    low          numeric     CHECK (low    >= 0),
    close        numeric     NOT NULL CHECK (close >= 0),
    volume       numeric     CHECK (volume >= 0),
    ingested_at  timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT market_index_bars_pk PRIMARY KEY (index_symbol, bar_date, source),
    CONSTRAINT market_index_bars_high_gte_low
        CHECK (high IS NULL OR low IS NULL OR high >= low)
);

CREATE INDEX idx_market_index_bars_date ON market_index_bars (bar_date);

COMMENT ON TABLE market_index_bars IS
    'Daily index OHLC. The session calendar in trading_calendar is derived from this table: '
    'a session exists iff the index printed a close.';

-- =============================================================================
-- Done. No production data inserted.
-- =============================================================================
