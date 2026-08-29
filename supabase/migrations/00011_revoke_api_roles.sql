-- =============================================================================
-- 00011_revoke_api_roles.sql — take the database off the public internet.
--
-- WHAT THIS FIXES
-- ---------------
-- Supabase ships default privileges that grant its API roles full access to
-- everything created in `public`. Measured on this project right after P7's
-- promotion, before this migration:
--
--   * RLS enabled on 0 of 26 tables (our migrations are plain SQL and never
--     enable it, so nothing filters rows);
--   * `anon` held SELECT on all 35 relations (26 tables + 9 views) AND
--     INSERT, UPDATE, DELETE, TRUNCATE on every table;
--   * `public` is a PostgREST-exposed schema.
--
-- The `anon` key is public BY DESIGN — it ships in the browser bundle. So the
-- state above meant anyone holding the project URL could not merely read the
-- frozen artifact, but TRUNCATE daily_bars. Read exposure was the finding;
-- write exposure was the actual risk.
--
-- THE DECISION (D-18 direction, chosen 2026-08-18)
-- ------------------------------------------------
-- The API roles get nothing. `services/api` connects as `postgres` over
-- DATABASE_URL and is the only read path; PostgREST and pg_graphql are not
-- part of this system's read surface. That keeps docs/04 §5's guard rail —
-- "the API reads views, not ad-hoc SQL" — meaningful: a browser that can query
-- model_ticker_params directly has walked around the guard rail entirely,
-- whatever the FastAPI layer does.
--
-- Chosen over enabling RLS with read-only policies because RLS is a row filter,
-- not an access model: it would still leave the tables reachable and would put
-- the correctness of the boundary in a policy per table, re-derived every time
-- a table is added. Revoking is one rule that holds for tables nobody has
-- written yet.
--
-- WHY A MIGRATION AND NOT A ONE-OFF
-- ---------------------------------
-- Because P8's runbook must be able to rebuild this database from nothing. A
-- privilege state fixed by hand in a dashboard is a state the runbook cannot
-- reproduce, and the next project created from these migrations would be wide
-- open again with no step that catches it.
--
-- PORTABILITY
-- -----------
-- The `anon` / `authenticated` roles do not exist on the local `datn_pg`
-- container, only on Supabase. Every statement below is therefore guarded by a
-- role-existence check, so scripts/db/apply_migrations.ps1 keeps working
-- against a plain postgres:17-alpine and this file stays a no-op there.
-- REVOKE is idempotent, so re-applying is safe.
--
-- WHAT IS DELIBERATELY NOT TOUCHED
-- --------------------------------
-- `service_role` keeps its grants. It is reachable only with the service-role
-- key, which is secret by design and must never reach apps/web; it is also what
-- the Supabase dashboard's own Table Editor uses, so revoking it would break
-- inspection tooling to close a hole that a leaked secret opens anyway. If that
-- key ever leaks, rotate it — do not rely on this file.
--
-- `staging` needs nothing: it was created by 00002, so Supabase's default
-- privileges never applied to it. Verified — anon has no USAGE on it.
--
-- No production data inserted. No secrets referenced.
-- =============================================================================

DO $$
DECLARE
    api_role text;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        -- Local container: these roles do not exist. Nothing to revoke, and the
        -- file must not fail there.
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            RAISE NOTICE 'role % absent (local track); nothing to revoke', api_role;
            CONTINUE;
        END IF;

        -- 1. Existing objects. ALL PRIVILEGES, not just SELECT: the measured
        --    state included INSERT/UPDATE/DELETE/TRUNCATE.
        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I', api_role);
        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I', api_role);
        EXECUTE format(
            'REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM %I', api_role);

        -- 2. The role's own USAGE on the schema. NOT sufficient on its own:
        --    `public` also carries the standard grant to PUBLIC (the ACL reads
        --    `=U/pg_database_owner`), which every role inherits. Revoking here
        --    only removes the explicit entry; step 2b removes the inherited one.
        EXECUTE format('REVOKE USAGE ON SCHEMA public FROM %I', api_role);

        -- 3. FUTURE objects. Without this, the next CREATE TABLE re-grants
        --    everything and the fix silently expires. `postgres` is the role
        --    this repo's migrations run as, so its defaults are the ones that
        --    govern tables we add.
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public '
            'REVOKE ALL ON TABLES FROM %I', api_role);
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public '
            'REVOKE ALL ON SEQUENCES FROM %I', api_role);
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public '
            'REVOKE ALL ON FUNCTIONS FROM %I', api_role);

        -- 4. Supabase also carries a defaults entry owned by `supabase_admin`,
        --    which applies to objects that role creates (dashboard tooling).
        --    `postgres` is usually not a member of it, so this is attempted and
        --    reported rather than assumed. A failure here is not fatal: it only
        --    covers objects this repo does not create.
        BEGIN
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public '
                'REVOKE ALL ON TABLES FROM %I', api_role);
            RAISE NOTICE 'supabase_admin defaults revoked for %', api_role;
        EXCEPTION WHEN insufficient_privilege OR undefined_object THEN
            RAISE NOTICE
                'could not alter supabase_admin defaults for % (%). Objects created BY '
                'supabase_admin in public would still be granted; this repo creates none.',
                api_role, SQLERRM;
        END;

        RAISE NOTICE 'revoked all privileges on schema public from %', api_role;
    END LOOP;

    -- 2b. The inherited grant. Measured: after step 2, `anon` still answered
    --     has_schema_privilege(...,'USAGE') = true, because PUBLIC holds USAGE
    --     on `public` and every role inherits it. Table grants alone already
    --     close the exposure, so this is defence in depth — but it is the layer
    --     that covers the one residual step 4 could not remove: a table created
    --     by supabase_admin, whose default privileges still grant anon.
    --
    --     This touches PUBLIC, not just the API roles, so the roles that
    --     legitimately need the schema are handled explicitly:
    --       * postgres      - member of pg_database_owner (owner), and holds an
    --                         explicit grant. Unaffected. This is our API's role.
    --       * service_role  - holds an explicit grant. Unaffected, deliberately.
    --       * supabase_admin- superuser, bypasses privilege checks entirely.
    --       * dashboard_user- neither superuser nor owner-member, so it WOULD
    --                         lose access. Re-granted below: it backs parts of
    --                         the Supabase Studio UI, and breaking the project's
    --                         own inspection tooling is not part of this decision.
    --     Roles deliberately left without it: anon, authenticated, authenticator
    --     (PostgREST's login role, which only SET ROLEs to the other three), and
    --     supabase_auth_admin / supabase_storage_admin, which work in `auth` and
    --     `storage` rather than `public`.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE USAGE ON SCHEMA public FROM PUBLIC;
        RAISE NOTICE 'revoked the inherited PUBLIC usage grant on schema public';

        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dashboard_user') THEN
            GRANT USAGE ON SCHEMA public TO dashboard_user;
            RAISE NOTICE 'restored schema usage for dashboard_user (Studio tooling)';
        END IF;
    END IF;
END
$$;

-- =============================================================================
-- Done. No production data inserted.
--
-- Verify with:
--   SELECT has_schema_privilege('anon', 'public', 'USAGE');   -- expected: false
--   SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
--   WHERE n.nspname = 'public' AND c.relkind IN ('r','v')
--     AND has_table_privilege('anon', c.oid, 'SELECT');
--   -- expected: 0
-- =============================================================================
