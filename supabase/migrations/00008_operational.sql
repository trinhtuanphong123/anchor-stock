-- =============================================================================
-- 00008_operational.sql — run log and data-quality evidence.
--
-- Column names match the writers already in the codebase
-- (pipelines/common/logging.py:log_run and pipelines/common/quality.py:write_dqr),
-- so no code change is needed to start recording against this baseline.
--
-- Baseline migration 8 of 9. No production data inserted. No secrets referenced.
-- =============================================================================

-- gen_random_uuid() is built into core from PostgreSQL 13; the extension is
-- created first anyway so this file also applies cleanly on an older server.
-- It must precede the table whose DEFAULT calls the function.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------------------------------
-- pipeline_runs — one row per job execution.
--
-- The bespoke always-on scheduler was removed; local CLIs and Airflow tasks call
-- the same functions and record here. The dag_* columns are nullable because a
-- local CLI run has no DAG — they identify an Airflow execution when there is
-- one, so a failing task can be traced back without leaving the database.
-- -----------------------------------------------------------------------------
CREATE TABLE pipeline_runs (
    id            bigint      PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    job_name      text        NOT NULL,
    status        text        NOT NULL
                              CONSTRAINT pipeline_runs_status_check
                              CHECK (status IN ('started', 'succeeded', 'failed', 'skipped')),
    trigger       text        NOT NULL
                              CONSTRAINT pipeline_runs_trigger_check
                              CHECK (trigger IN ('scheduled', 'manual', 'airflow')),
    started_at    timestamptz NOT NULL DEFAULT now(),
    ended_at      timestamptz,                  -- NULL while running
    error_message text,                         -- NULL on success/skip
    metadata      jsonb,                        -- counts, ranges, run ids touched

    dag_id        text,
    dag_run_id    text,
    task_id       text
);

CREATE INDEX idx_pipeline_runs_job_started ON pipeline_runs (job_name, started_at DESC);
CREATE INDEX idx_pipeline_runs_status      ON pipeline_runs (status);
CREATE INDEX idx_pipeline_runs_dag         ON pipeline_runs (dag_id, dag_run_id);

-- -----------------------------------------------------------------------------
-- data_quality_reports — evidence, not gates.
--
-- Minimum-session thresholds were deliberately removed: a run takes whatever data
-- is available. What replaces them is *visibility* — a check writes what it found
-- here, and the run proceeds. A report row is a fact recorded, not a veto.
--
-- The alignment scope is the important one: it names which tickers cost how many
-- sessions when the return matrix was assembled, so a thin year has an
-- explanation attached rather than an unexplained small T.
-- -----------------------------------------------------------------------------
CREATE TABLE data_quality_reports (
    report_id       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id bigint      REFERENCES pipeline_runs (id) ON DELETE SET NULL,
    report_scope    text        NOT NULL,       -- 'daily_ohlcv:ticker:VCB', 'alignment:<run>'
    ref_date        date,
    check_name      text        NOT NULL,       -- 'sanity_bounds', 'duplicates', 'coverage'
    passed          boolean     NOT NULL,
    severity        text        NOT NULL DEFAULT 'info'
                                CONSTRAINT dqr_severity_check
                                CHECK (severity IN ('info', 'warning', 'error')),
    details         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT dqr_quality_check_uq
        UNIQUE (report_scope, ref_date, check_name, pipeline_run_id)
);

CREATE INDEX idx_dqr_scope_date ON data_quality_reports (report_scope, ref_date);
CREATE INDEX idx_dqr_passed     ON data_quality_reports (passed) WHERE NOT passed;

-- =============================================================================
-- Done. No production data inserted.
-- =============================================================================
