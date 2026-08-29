-- =============================================================================
-- 00006_research.sql — stability study and measure comparison.
--
-- Report-only. Nothing here is served to the dashboard; these are the tables the
-- written report quotes. Sources: docs/03 §3 (frequency table), §4 (cross-year
-- evaluation), §8 (what is published), and docs/01 §7 (dCor comparison).
--
-- Baseline migration 6 of 9. No production data inserted. No secrets referenced.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- stability_studies — the container.
--
-- k is a stored parameter, not a constant: the stability mechanisms run at the
-- PRIMARY k only (docs/03 §7 — "the stability question is whether *the* anchor
-- set is stable, and the primary k is what defines *the* set"). A second study
-- at another k is an extra row, not a schema change.
--
-- year_from/year_to and n_years are likewise stored, so that changing the span of
-- the research track (as happened when 2021 was promoted to a research year —
-- docs/decisions/D-01) does not require a migration.
-- -----------------------------------------------------------------------------
CREATE TABLE stability_studies (
    id                 bigint      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    study_label        text        NOT NULL UNIQUE,
    similarity_measure text        NOT NULL
                       CONSTRAINT stability_studies_measure_check
                       CHECK (similarity_measure IN ('pearson_rho2', 'dcor2')),
    k                  int         NOT NULL CHECK (k > 0),
    year_from          int         NOT NULL,
    year_to            int         NOT NULL,
    n_years            int         NOT NULL CHECK (n_years > 0),
    notes              text,
    created_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT stability_studies_year_order CHECK (year_from <= year_to)
);

-- -----------------------------------------------------------------------------
-- anchor_frequency — docs/03 §3.
--
-- The SHAPE of this distribution is the result, not the list. Concentrated means
-- persistent structure; flat means the method is picking up year-specific
-- artefacts and the primary set should be read with caution.
--
-- Report the TWO ENDS (how many appear in every year, how many in exactly one)
-- rather than reading each level — at five years the middle is still coarse.
-- -----------------------------------------------------------------------------
CREATE TABLE anchor_frequency (
    study_id       bigint  NOT NULL REFERENCES stability_studies ON DELETE CASCADE,
    ticker         text    NOT NULL REFERENCES stocks,
    n_years        int     NOT NULL CHECK (n_years >= 0),
    share          numeric NOT NULL CHECK (share BETWEEN 0 AND 1),
    years_selected int[]   NOT NULL,

    CONSTRAINT anchor_frequency_pk PRIMARY KEY (study_id, ticker)
);

CREATE INDEX idx_anchor_frequency_n ON anchor_frequency (study_id, n_years DESC);

COMMENT ON TABLE anchor_frequency IS
    'Year-to-year turnover of the anchor set. This is an UPPER BOUND on real instability, not '
    'a measurement of it: every run estimates on ~250 sessions, so some turnover is estimation '
    'noise and this analysis cannot separate the two (docs/03 §6). Report it as such.';

-- -----------------------------------------------------------------------------
-- cross_year_eval — docs/03 §4.
--
--   stale  = F̄(S_t)   evaluated on P_{t+1}   — what carrying last year's set delivers
--   direct = F̄(S_t+1) evaluated on P_{t+1}   — the best achievable on that year
--   ratio  = stale / direct
--
-- ratio is STORED rather than derived, because it is the figure the report quotes
-- and storing it fixes its definition (docs/03 §8).
--
-- is_forward_test marks the final pair, whose set was chosen without sight of a
-- single session of the scoring year. The earlier pairs establish the band; this
-- one is judged against it.
-- -----------------------------------------------------------------------------
CREATE TABLE cross_year_eval (
    study_id        bigint  NOT NULL REFERENCES stability_studies ON DELETE CASCADE,
    year_t          int     NOT NULL,
    year_t1         int     NOT NULL,
    run_id_t        bigint  REFERENCES model_runs ON DELETE SET NULL,
    run_id_t1       bigint  REFERENCES model_runs ON DELETE SET NULL,
    fbar_stale      numeric NOT NULL CHECK (fbar_stale  BETWEEN 0 AND 1),
    fbar_direct     numeric NOT NULL CHECK (fbar_direct BETWEEN 0 AND 1),
    ratio           numeric NOT NULL CHECK (ratio BETWEEN 0 AND 1),
    is_forward_test boolean NOT NULL DEFAULT false,

    CONSTRAINT cross_year_eval_pk PRIMARY KEY (study_id, year_t),
    CONSTRAINT cross_year_eval_consecutive CHECK (year_t1 = year_t + 1)
);

-- -----------------------------------------------------------------------------
-- measure_comparison — docs/01 §7.
--
-- Compared on RANKINGS and RESULTING ANCHOR SETS, never on absolute magnitudes:
-- dCor² and ρ² are not on the same scale and a side-by-side of raw values says
-- nothing. High Jaccard overlap says the linear measure was sufficient; low
-- overlap says nonlinear dependence is present that Pearson misses. Either
-- direction is a finding.
--
-- dcor_u_statistic_mean carries the unbiased U-statistic as a BIAS DIAGNOSTIC
-- only. The V-statistic is what feeds greedy, because it is non-negative and
-- therefore preserves the approximation guarantee; the U-statistic can go
-- negative and would void it (docs/decisions/D-05).
-- -----------------------------------------------------------------------------
CREATE TABLE measure_comparison (
    study_id                bigint  NOT NULL REFERENCES stability_studies ON DELETE CASCADE,
    year                    int     NOT NULL,
    k                       int     NOT NULL CHECK (k > 0),
    anchors_pearson         text[]  NOT NULL,
    anchors_dcor            text[]  NOT NULL,
    jaccard                 numeric NOT NULL CHECK (jaccard BETWEEN 0 AND 1),
    fbar_pearson            numeric NOT NULL,
    fbar_dcor               numeric NOT NULL,
    rank_agreement_spearman numeric CHECK (rank_agreement_spearman IS NULL
                                           OR rank_agreement_spearman BETWEEN -1 AND 1),
    dcor_u_statistic_mean   numeric,   -- bias diagnostic; never fed to greedy

    CONSTRAINT measure_comparison_pk PRIMARY KEY (study_id, year)
);

-- =============================================================================
-- Done. No production data inserted.
-- =============================================================================
