-- =============================================================================
-- 00005_model_artifact.sql — the frozen parameter set, loaded from a local run.
--
-- Mirrors docs/04-static-parameters.md §2 block for block. A model run is trained
-- OFFLINE on the local track and published here as an artifact; the dashboard
-- only ever APPLIES it. There is no code path from a request to the greedy
-- algorithm (docs/04 §5) — selection runs in the pipeline, on schedule.
--
-- P IS STORED. The superseded 00017 asserted "the matrices X / E / P are NOT
-- stored"; docs/04 §2 and §6 say the opposite — P[:, S] is served, full P is
-- archived, and §6 prices the full matrix at "under 100 KB" at N = 100. The spec
-- wins, and the disagreement is recorded here rather than left for someone to
-- rediscover. X and E genuinely are not stored: they are recomputable from the
-- returns and belong to a window, not to the data.
--
-- Baseline migration 5 of 9. No production data inserted. No secrets referenced.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- model_runs — one row per published artifact.
-- -----------------------------------------------------------------------------
CREATE TABLE model_runs (
    id                      bigint      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,

    -- Identity. artifact_id is content-addressed and therefore reproducible:
    -- re-training on the same data yields the same id (the digest excludes
    -- created_at and code_version). That equality is the reproducibility proof.
    artifact_id             text        NOT NULL UNIQUE,
    artifact_schema_version int         NOT NULL,
    content_sha256          text        NOT NULL
                            CONSTRAINT model_runs_sha_len CHECK (char_length(content_sha256) = 64),

    scope                   text        NOT NULL
                            CONSTRAINT model_runs_scope_check
                            CHECK (scope IN ('year', 'live')),
    scope_label             text        NOT NULL,       -- '2025' | '2026-03'
    similarity_measure      text        NOT NULL
                            CONSTRAINT model_runs_measure_check
                            CHECK (similarity_measure IN ('pearson_rho2', 'dcor2')),

    universe_version        text        NOT NULL REFERENCES universe_snapshots,
    index_symbol            text        NOT NULL,
    source                  text        NOT NULL DEFAULT 'VCI',

    -- Estimation window. prior_close_date is the (T+1)-th close and sits OUTSIDE
    -- the window: T returns need T+1 closes (docs/01 §1), so the first close of a
    -- 2021 window is the last session of 2020. Recorded explicitly so the year
    -- boundary is auditable rather than implied (docs/decisions D-11).
    window_start            date        NOT NULL,
    window_end              date        NOT NULL,
    prior_close_date        date        NOT NULL,

    n_sessions              int         NOT NULL CHECK (n_sessions > 0),   -- T
    n_tickers               int         NOT NULL CHECK (n_tickers > 0),    -- N
    q                       numeric     NOT NULL,                           -- N / T

    k                       int         NOT NULL CHECK (k > 0),
    k_max                   int         NOT NULL CHECK (k_max > 0),
    tau                     numeric     NOT NULL,

    coverage_f              numeric     NOT NULL,       -- F(S) at k
    coverage_fbar           numeric     NOT NULL,       -- F/N, the comparable number
    n_under_tau             int         NOT NULL,       -- |U_tau|

    tie_break               text        NOT NULL DEFAULT 'smallest_index',
    is_primary              boolean     NOT NULL DEFAULT false,  -- the headline run
    is_active               boolean     NOT NULL DEFAULT false,  -- served by the dashboard

    -- What the session alignment dropped, and which tickers cost the sessions.
    -- Minimum-session gates were removed; this is what replaces them. Kept as
    -- jsonb because its shape is diagnostic, never queried by the dashboard.
    alignment               jsonb,

    code_version            text,
    created_at              timestamptz NOT NULL,       -- from the artifact
    loaded_at               timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT model_runs_k_le_kmax    CHECK (k <= k_max),
    CONSTRAINT model_runs_window_order CHECK (window_start <= window_end),
    CONSTRAINT model_runs_prior_close  CHECK (prior_close_date < window_start),
    CONSTRAINT model_runs_fbar         CHECK (coverage_fbar BETWEEN 0 AND 1),

    -- dCor is a research measure. docs/01 §7 carries it for comparison in the
    -- report; docs/04 §5 keeps the dashboard on the primary method. Encoding that
    -- as a CHECK means it cannot be violated by a careless activation.
    CONSTRAINT model_runs_dcor_never_active
        CHECK (NOT is_active OR similarity_measure = 'pearson_rho2')
);

-- "One active at a time" (docs/03 §8), scoped BY MEASURE rather than by scope on
-- purpose: during the 2026 warm-up the active row is the scope='year' 2025 run
-- (docs/03 §5), and the schema has to permit exactly that.
CREATE UNIQUE INDEX ux_model_runs_one_active
    ON model_runs (similarity_measure) WHERE is_active;

CREATE UNIQUE INDEX ux_model_runs_one_primary
    ON model_runs ((true)) WHERE is_primary;

CREATE INDEX idx_model_runs_scope   ON model_runs (scope, scope_label);
CREATE INDEX idx_model_runs_created ON model_runs (created_at DESC, id DESC);

-- -----------------------------------------------------------------------------
-- model_universe — the artifact's own ordered ticker list.
--
-- Deliberately separate from universe_members: that table records what the
-- universe FILE said, this one records what the RUN actually used after tickers
-- with no overlapping sessions were dropped. When they differ, the alignment
-- report explains why — and the difference is visible instead of inferred.
-- -----------------------------------------------------------------------------
CREATE TABLE model_universe (
    run_id   bigint NOT NULL REFERENCES model_runs ON DELETE CASCADE,
    position int    NOT NULL CHECK (position >= 0),
    ticker   text   NOT NULL REFERENCES stocks,

    CONSTRAINT model_universe_pk PRIMARY KEY (run_id, position),
    CONSTRAINT model_universe_ticker_uq UNIQUE (run_id, ticker)
);

-- -----------------------------------------------------------------------------
-- model_ticker_params — docs/04 §2 "per ticker i".
--
-- alpha_hat / beta_hat are what let a new session be residualised without
-- refitting; sigma_hat is what lets a live residual be expressed in
-- training-window units. Both are OUTPUTS of the run, not scratch values
-- (docs/01 §3).
-- -----------------------------------------------------------------------------
CREATE TABLE model_ticker_params (
    run_id        bigint  NOT NULL REFERENCES model_runs ON DELETE CASCADE,
    ticker        text    NOT NULL,
    position      int     NOT NULL,
    alpha_hat     numeric NOT NULL,
    beta_hat      numeric NOT NULL,
    sigma_hat     numeric NOT NULL CHECK (sigma_hat > 0),
    r2            numeric NOT NULL,                       -- factor-model R², diagnostic
    anchor_ticker text    NOT NULL,                       -- a(i)
    coverage_c    numeric NOT NULL CHECK (coverage_c BETWEEN 0 AND 1),
    is_anchor     boolean NOT NULL DEFAULT false,
    under_tau     boolean NOT NULL DEFAULT false,

    CONSTRAINT model_ticker_params_pk PRIMARY KEY (run_id, ticker),
    CONSTRAINT model_ticker_params_position_fk
        FOREIGN KEY (run_id, position) REFERENCES model_universe (run_id, position)
);

CREATE INDEX idx_mtp_anchor ON model_ticker_params (run_id, anchor_ticker);

-- -----------------------------------------------------------------------------
-- model_anchors — the ordered anchor set and the full marginal-gain curve.
--
-- Stored to k_max, not to k. Greedy is nested, so the run to k_max CONTAINS the
-- run to every smaller k and the extra rows are free (docs/02 §5). The elbow
-- argument for the chosen k is far stronger when the curve extends past it.
-- in_published_set marks the prefix that was actually published.
-- -----------------------------------------------------------------------------
CREATE TABLE model_anchors (
    run_id           bigint  NOT NULL REFERENCES model_runs ON DELETE CASCADE,
    step_k           int     NOT NULL CHECK (step_k > 0),  -- 1..k_max, selection order
    anchor_ticker    text    NOT NULL,
    position         int     NOT NULL,
    marginal_gain    numeric NOT NULL CHECK (marginal_gain >= 0),  -- Δ_step, non-increasing
    coverage_f       numeric NOT NULL,
    coverage_fbar    numeric NOT NULL,
    in_published_set boolean NOT NULL,                     -- step_k <= k

    CONSTRAINT model_anchors_pk PRIMARY KEY (run_id, step_k),
    CONSTRAINT model_anchors_ticker_uq UNIQUE (run_id, anchor_ticker)
);

COMMENT ON COLUMN model_anchors.marginal_gain IS
    'Δ_step. Non-increasing across steps — that is submodularity made visible, and a violation '
    'means P was mutated between rounds.';

-- -----------------------------------------------------------------------------
-- model_similarity_anchor — P[:, S], the slice the dashboard reads.
-- N*k rows per run (1,000 at N=100, k=10). Assignment, coverage and the
-- assignment-challenge monitor all read anchor columns only (docs/04 §6).
-- -----------------------------------------------------------------------------
CREATE TABLE model_similarity_anchor (
    run_id        bigint  NOT NULL REFERENCES model_runs ON DELETE CASCADE,
    ticker        text    NOT NULL,
    anchor_ticker text    NOT NULL,
    rho2          numeric NOT NULL CHECK (rho2 BETWEEN 0 AND 1),

    CONSTRAINT model_similarity_anchor_pk PRIMARY KEY (run_id, ticker, anchor_ticker)
);

CREATE INDEX idx_msa_anchor ON model_similarity_anchor (run_id, anchor_ticker);

-- -----------------------------------------------------------------------------
-- model_similarity_full — the archived N×N matrix.
--
-- Flattened row-major in model_universe.position order. float8[] rather than
-- bytea: both round-trip exactly (Postgres float8 is IEEE-754 double), but an
-- array is inspectable in a SQL editor and serialisable by PostgREST, and for a
-- thesis artefact someone will want to poke at, inspectability wins.
-- ~90 KB per run at N = 100 (docs/decisions D-4).
-- -----------------------------------------------------------------------------
CREATE TABLE model_similarity_full (
    run_id   bigint   PRIMARY KEY REFERENCES model_runs ON DELETE CASCADE,
    n        int      NOT NULL CHECK (n > 0),
    ordering text     NOT NULL DEFAULT 'model_universe.position ASC, row-major',
    values   float8[] NOT NULL,
    p_sha256 text     NOT NULL,      -- sha256 of the canonical P.npy bytes

    CONSTRAINT model_similarity_full_len CHECK (array_length(values, 1) = n * n)
);

-- -----------------------------------------------------------------------------
-- model_groups — the group table (docs/02 §3g).
--
-- sector_composition is the one deliberate jsonb here: its key set is whichever
-- sectors appear in that group, it varies per group, and it is EXTERNAL
-- VALIDATION only — rendered, never read by code. Sector labels never enter P.
-- -----------------------------------------------------------------------------
CREATE TABLE model_groups (
    run_id             bigint  NOT NULL REFERENCES model_runs ON DELETE CASCADE,
    anchor_ticker      text    NOT NULL,
    size               int     NOT NULL CHECK (size > 0),   -- |C_j|
    f_j                numeric NOT NULL,                    -- Σ_{i∈C_j} c_i
    rho2_mean          numeric NOT NULL,
    rho2_min           numeric NOT NULL,
    sector_composition jsonb   NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT model_groups_pk PRIMARY KEY (run_id, anchor_ticker)
);

-- =============================================================================
-- Done. No production data inserted.
-- =============================================================================
