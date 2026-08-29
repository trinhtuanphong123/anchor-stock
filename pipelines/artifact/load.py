"""pipelines.artifact.load — write one on-disk artifact into Postgres (P6.5).

Mirrors ``supabase/migrations/00005_model_artifact.sql`` table for table, in FK order, inside
one transaction:

    model_runs -> model_universe -> model_ticker_params -> model_anchors
               -> model_similarity_anchor -> model_similarity_full -> model_groups

Three refusals happen **before** that transaction opens, so a rejected artifact never leaves a
partial write behind:

1. ``artifact.validate.validate_all`` — V1-V14. A manifest that fails its own correctness
   contract is refused before the database is touched at all.
2. The artifact's ``universe_version`` must already be registered in ``universe_snapshots``
   (``pipelines.universe.sync``, P6.3) — otherwise the FK on ``model_runs.universe_version``
   would fail with a raw constraint-violation message naming a column, not a fix.
3. Every ticker in the artifact's universe must already be in ``stocks``, for the same reason
   applied to ``model_universe.ticker`` / ``model_ticker_params.anchor_ticker`` /
   ``model_groups.anchor_ticker``.

Idempotency is a fourth, related check, but not a refusal: an ``artifact_id`` already present
with an equal ``content_sha256`` is a no-op (the same principle as
``io.write_artifact``'s own idempotency check — a content-identical re-run changes nothing). An
``artifact_id`` present with a *different* ``content_sha256`` raises
:class:`~pipelines.artifact.io.ArtifactCollisionError` — the same class ``io.py`` raises for the
identical situation on disk, because it is the identical situation: an id that no longer means
one thing.

``is_active`` is always ``false`` on load (D-8) — activation is a separate, deliberate act; see
``pipelines.artifact.activate``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipelines.artifact import validate as V
from pipelines.artifact.io import ArtifactCollisionError, find_artifacts, read_artifact
from pipelines.artifact.schema import Artifact

__all__ = ["ArtifactLoadError", "LoadResult", "load_artifact"]


class ArtifactLoadError(RuntimeError):
    """A named prerequisite is missing. Never a raw FK-violation message."""


@dataclass
class LoadResult:
    artifact_id: str
    inserted: bool                    # False -> idempotent no-op, content already matched
    run_id: int | None = None
    n_universe: int = 0
    n_ticker_params: int = 0
    n_anchors: int = 0
    n_similarity_anchor: int = 0
    n_groups: int = 0
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Preflight — all read-only, all before the write transaction opens
# ---------------------------------------------------------------------------


def _check_universe_registered(universe_version: str, *, cur: Any) -> None:
    cur.execute("SELECT 1 FROM universe_snapshots WHERE universe_version = %s", (universe_version,))
    if cur.fetchone() is None:
        raise ArtifactLoadError(
            f"universe_version {universe_version!r} is not registered in universe_snapshots — "
            f"run pipelines.universe.sync first"
        )


def _check_tickers_known(tickers: list[str], *, cur: Any) -> None:
    cur.execute("SELECT ticker FROM stocks WHERE ticker = ANY(%s)", (tickers,))
    known = {row[0] for row in cur.fetchall()}
    missing = sorted(set(tickers) - known)
    if missing:
        raise ArtifactLoadError(
            f"{len(missing)} universe ticker(s) absent from stocks: "
            f"{', '.join(missing[:10])}"
            + (f" (and {len(missing) - 10} more)" if len(missing) > 10 else "")
            + " — run pipelines.universe.sync first"
        )


def _existing_content_sha256(artifact_id: str, *, cur: Any) -> str | None:
    cur.execute("SELECT content_sha256 FROM model_runs WHERE artifact_id = %s", (artifact_id,))
    row = cur.fetchone()
    return row[0] if row is not None else None


# ---------------------------------------------------------------------------
# The write, in FK order
# ---------------------------------------------------------------------------


def _insert_model_run(a: Artifact, *, cur: Any) -> int:
    r = a.run
    cur.execute(
        """
        INSERT INTO model_runs (
            artifact_id, artifact_schema_version, content_sha256,
            scope, scope_label, similarity_measure,
            universe_version, index_symbol, source,
            window_start, window_end, prior_close_date,
            n_sessions, n_tickers, q,
            k, k_max, tau,
            coverage_f, coverage_fbar, n_under_tau,
            tie_break, is_primary, is_active,
            alignment, code_version, created_at
        ) VALUES (
            %(artifact_id)s, %(artifact_schema_version)s, %(content_sha256)s,
            %(scope)s, %(scope_label)s, %(similarity_measure)s,
            %(universe_version)s, %(index_symbol)s, %(source)s,
            %(window_start)s, %(window_end)s, %(prior_close_date)s,
            %(n_sessions)s, %(n_tickers)s, %(q)s,
            %(k)s, %(k_max)s, %(tau)s,
            %(coverage_f)s, %(coverage_fbar)s, %(n_under_tau)s,
            %(tie_break)s, %(is_primary)s, false,
            %(alignment)s::jsonb, %(code_version)s, %(created_at)s
        )
        RETURNING id
        """,
        {
            "artifact_id": r.artifact_id, "artifact_schema_version": r.artifact_schema_version,
            "content_sha256": r.content_sha256,
            "scope": r.scope, "scope_label": r.scope_label,
            "similarity_measure": r.similarity_measure,
            "universe_version": r.universe_version, "index_symbol": r.index_symbol,
            "source": r.source,
            "window_start": r.window_start, "window_end": r.window_end,
            "prior_close_date": r.prior_close_date,
            "n_sessions": r.n_sessions, "n_tickers": r.n_tickers, "q": r.q,
            "k": r.k, "k_max": r.k_max, "tau": r.tau,
            "coverage_f": r.coverage_f, "coverage_fbar": r.coverage_fbar,
            "n_under_tau": r.n_under_tau,
            "tie_break": r.tie_break, "is_primary": r.is_primary,
            "alignment": json.dumps(r.alignment), "code_version": r.code_version,
            "created_at": r.created_at,
        },
    )
    return cur.fetchone()[0]


def _insert_model_universe(a: Artifact, run_id: int, *, cur: Any) -> int:
    rows = [{"run_id": run_id, "position": u.position, "ticker": u.ticker} for u in a.universe]
    cur.executemany(
        "INSERT INTO model_universe (run_id, position, ticker) "
        "VALUES (%(run_id)s, %(position)s, %(ticker)s)",
        rows,
    )
    return len(rows)


def _insert_model_ticker_params(a: Artifact, run_id: int, *, cur: Any) -> int:
    rows = [
        {
            "run_id": run_id, "ticker": t.ticker, "position": t.position,
            "alpha_hat": t.alpha_hat, "beta_hat": t.beta_hat, "sigma_hat": t.sigma_hat,
            "r2": t.r2, "anchor_ticker": t.anchor_ticker, "coverage_c": t.coverage_c,
            "is_anchor": t.is_anchor, "under_tau": t.under_tau,
        }
        for t in a.ticker_params
    ]
    cur.executemany(
        """
        INSERT INTO model_ticker_params (
            run_id, ticker, position, alpha_hat, beta_hat, sigma_hat, r2,
            anchor_ticker, coverage_c, is_anchor, under_tau
        ) VALUES (
            %(run_id)s, %(ticker)s, %(position)s, %(alpha_hat)s, %(beta_hat)s, %(sigma_hat)s,
            %(r2)s, %(anchor_ticker)s, %(coverage_c)s, %(is_anchor)s, %(under_tau)s
        )
        """,
        rows,
    )
    return len(rows)


def _insert_model_anchors(a: Artifact, run_id: int, *, cur: Any) -> int:
    rows = [
        {
            "run_id": run_id, "step_k": s.step_k, "anchor_ticker": s.anchor_ticker,
            "position": s.position, "marginal_gain": s.marginal_gain,
            "coverage_f": s.coverage_f, "coverage_fbar": s.coverage_fbar,
            "in_published_set": s.in_published_set,
        }
        for s in a.anchors
    ]
    cur.executemany(
        """
        INSERT INTO model_anchors (
            run_id, step_k, anchor_ticker, position, marginal_gain,
            coverage_f, coverage_fbar, in_published_set
        ) VALUES (
            %(run_id)s, %(step_k)s, %(anchor_ticker)s, %(position)s, %(marginal_gain)s,
            %(coverage_f)s, %(coverage_fbar)s, %(in_published_set)s
        )
        """,
        rows,
    )
    return len(rows)


def _insert_model_similarity_anchor(a: Artifact, run_id: int, *, cur: Any) -> int:
    from pipelines.artifact.io import anchor_columns  # noqa: PLC0415

    rows = [
        {"run_id": run_id, "ticker": r["ticker"], "anchor_ticker": r["anchor_ticker"],
         "rho2": r["rho2"]}
        for r in anchor_columns(a)
    ]
    cur.executemany(
        "INSERT INTO model_similarity_anchor (run_id, ticker, anchor_ticker, rho2) "
        "VALUES (%(run_id)s, %(ticker)s, %(anchor_ticker)s, %(rho2)s)",
        rows,
    )
    return len(rows)


def _insert_model_similarity_full(a: Artifact, run_id: int, *, cur: Any) -> None:
    n = a.P.shape[0]
    # Row-major in model_universe.position order — P is already indexed by position, and
    # model_universe was just written in that same order, so a plain C-order ravel matches the
    # DDL's stated ordering with nothing further to coordinate.
    values = a.P.ravel(order="C").tolist()
    cur.execute(
        "INSERT INTO model_similarity_full (run_id, n, values, p_sha256) "
        "VALUES (%(run_id)s, %(n)s, %(values)s, %(p_sha256)s)",
        {"run_id": run_id, "n": n, "values": values, "p_sha256": a.run.p_sha256},
    )


def _insert_model_groups(a: Artifact, run_id: int, *, cur: Any) -> int:
    rows = [
        {
            "run_id": run_id, "anchor_ticker": g.anchor_ticker, "size": g.size,
            "f_j": g.f_j, "rho2_mean": g.rho2_mean, "rho2_min": g.rho2_min,
            "sector_composition": json.dumps(g.sector_composition),
        }
        for g in a.groups
    ]
    cur.executemany(
        """
        INSERT INTO model_groups (
            run_id, anchor_ticker, size, f_j, rho2_mean, rho2_min, sector_composition
        ) VALUES (
            %(run_id)s, %(anchor_ticker)s, %(size)s, %(f_j)s, %(rho2_mean)s, %(rho2_min)s,
            %(sector_composition)s::jsonb
        )
        """,
        rows,
    )
    return len(rows)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def load_artifact(artifact: Artifact, *, source_dir: Path | None = None) -> LoadResult:
    """Validate, preflight-check, and write ``artifact`` to Postgres. See the module docstring
    for the full ordering and what each refusal means.
    """
    V.validate_all(artifact, source_dir=source_dir)

    from pipelines.common.db import cursor  # noqa: PLC0415

    universe_version = artifact.run.universe_version
    tickers = [u.ticker for u in artifact.universe]

    with cursor() as cur:
        _check_universe_registered(universe_version, cur=cur)
        _check_tickers_known(tickers, cur=cur)
        existing = _existing_content_sha256(artifact.run.artifact_id, cur=cur)

    if existing is not None:
        if existing == artifact.run.content_sha256:
            return LoadResult(artifact_id=artifact.run.artifact_id, inserted=False)
        raise ArtifactCollisionError(
            f"artifact_id {artifact.run.artifact_id!r} already exists in model_runs with "
            f"content_sha256={existing!r}, but the artifact being loaded has "
            f"{artifact.run.content_sha256!r} — same id, different content"
        )

    with cursor() as cur:
        run_id = _insert_model_run(artifact, cur=cur)
        n_universe = _insert_model_universe(artifact, run_id, cur=cur)
        n_params = _insert_model_ticker_params(artifact, run_id, cur=cur)
        n_anchors = _insert_model_anchors(artifact, run_id, cur=cur)
        n_sim_anchor = _insert_model_similarity_anchor(artifact, run_id, cur=cur)
        _insert_model_similarity_full(artifact, run_id, cur=cur)
        n_groups = _insert_model_groups(artifact, run_id, cur=cur)

    return LoadResult(
        artifact_id=artifact.run.artifact_id, inserted=True, run_id=run_id,
        n_universe=n_universe, n_ticker_params=n_params, n_anchors=n_anchors,
        n_similarity_anchor=n_sim_anchor, n_groups=n_groups,
    )


# ---------------------------------------------------------------------------
# Self-check — no database. Fakes pipelines.common.db.cursor exactly like
# pipelines.storage.pg._selftest does, so the transaction shape and refusal ordering are
# checked without touching a server.
# ---------------------------------------------------------------------------


def _selftest() -> int:  # noqa: PLR0915
    import contextlib

    from pipelines.artifact.inspect import build_fixture_artifact

    passed = 0
    failed: list[str] = []

    def check(label: str, fn) -> None:  # noqa: ANN001
        nonlocal passed
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed.append(label)
            print(f"  FAIL  {label}\n          {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"  PASS  {label}")

    class _Cursor:
        """Records statements; replays canned fetchone()/fetchall() results in call order."""

        def __init__(self, log: list[tuple[Any, Any]], answers: list[Any]) -> None:
            self.log = log
            self.answers = answers
            self._last: Any = None

        def execute(self, sql: Any, params: Any = None) -> None:
            self.log.append((sql, params))
            self._last = self.answers.pop(0) if self.answers else None

        def executemany(self, sql: Any, records: Any) -> None:
            self.log.append((sql, records))

        def fetchone(self) -> Any:
            return self._last

        def fetchall(self) -> Any:
            return self._last if self._last is not None else []

        def __enter__(self) -> _Cursor:
            return self

        def __exit__(self, *exc: Any) -> bool:
            return False

    def fake_db(answers: list[Any]) -> tuple[list[tuple[Any, Any]], Any]:
        log: list[tuple[Any, Any]] = []

        @contextlib.contextmanager
        def fake_cursor():
            yield _Cursor(log, answers)

        return log, fake_cursor

    import pipelines.common.db as db_mod

    real_cursor = db_mod.cursor
    fixture = build_fixture_artifact(k=2, k_max=4, tau=0.5)

    def _invalid_artifact_never_opens_transaction() -> None:
        import copy

        broken = copy.deepcopy(fixture)
        broken.run.n_tickers = fixture.run.n_tickers + 1  # V5 will reject this
        log, fake = fake_db([])
        db_mod.cursor = fake
        try:
            _assert_raises(lambda: load_artifact(broken), V.ValidationError, "V5 dimensions")
            _assert(log == [], f"a statement ran despite the artifact being invalid: {log}")
        finally:
            db_mod.cursor = real_cursor

    check("an invalid artifact is rejected before any statement runs",
          _invalid_artifact_never_opens_transaction)

    def _unregistered_universe_named() -> None:
        # preflight cursor: universe_snapshots lookup -> None (not registered)
        log, fake = fake_db([None])
        db_mod.cursor = fake
        try:
            _assert_raises(lambda: load_artifact(fixture), ArtifactLoadError,
                            "unregistered universe_version")
        finally:
            db_mod.cursor = real_cursor

    check("an unregistered universe_version is refused by name, not a raw FK error",
          _unregistered_universe_named)

    def _missing_tickers_named() -> None:
        # universe_snapshots -> found; stocks lookup -> only the first ticker known
        first = fixture.universe[0].ticker
        log, fake = fake_db([(1,), [(first,)]])
        db_mod.cursor = fake
        try:
            with_error = None
            try:
                load_artifact(fixture)
            except ArtifactLoadError as exc:
                with_error = exc
            _assert(with_error is not None, "expected ArtifactLoadError")
            _assert("absent from stocks" in str(with_error), str(with_error))
        finally:
            db_mod.cursor = real_cursor

    check("tickers missing from stocks are named, not a raw FK error", _missing_tickers_named)

    def _idempotent_reload_is_noop() -> None:
        all_tickers = [(u.ticker,) for u in fixture.universe]
        # universe_snapshots -> found; stocks -> all known; model_runs lookup -> same content_sha256
        log, fake = fake_db([(1,), all_tickers, (fixture.run.content_sha256,)])
        db_mod.cursor = fake
        try:
            result = load_artifact(fixture)
            _assert(result.inserted is False, result)
            _assert(not any("INSERT INTO model_runs" in str(sql) for sql, _ in log), log)
        finally:
            db_mod.cursor = real_cursor

    check("re-loading an already-present, content-identical artifact is a no-op",
          _idempotent_reload_is_noop)

    def _content_collision_raises() -> None:
        all_tickers = [(u.ticker,) for u in fixture.universe]
        log, fake = fake_db([(1,), all_tickers, ("a-different-sha256-entirely",)])
        db_mod.cursor = fake
        try:
            _assert_raises(lambda: load_artifact(fixture), ArtifactCollisionError,
                            "same id, different content")
        finally:
            db_mod.cursor = real_cursor

    check("same artifact_id with different content raises ArtifactCollisionError",
          _content_collision_raises)

    def _full_write_shape() -> None:
        all_tickers = [(u.ticker,) for u in fixture.universe]
        # preflight: universe found, tickers known, no existing artifact_id
        # write: model_runs INSERT ... RETURNING id -> (7,)
        log, fake = fake_db([(1,), all_tickers, None, (7,)])
        db_mod.cursor = fake
        try:
            result = load_artifact(fixture)
            _assert(result.inserted is True and result.run_id == 7, result)
            _assert(result.n_universe == len(fixture.universe), result)
            _assert(result.n_ticker_params == len(fixture.ticker_params), result)
            _assert(result.n_anchors == len(fixture.anchors), result)
            _assert(result.n_groups == len(fixture.groups), result)
            tables_hit = [str(sql) for sql, _ in log if "INSERT INTO" in str(sql)]
            expected = ["model_runs", "model_universe", "model_ticker_params", "model_anchors",
                        "model_similarity_anchor", "model_similarity_full", "model_groups"]
            for name in expected:
                _assert(any(name in t for t in tables_hit), f"{name} was never inserted into")
            # is_active is hard-coded false in the SQL's VALUES clause, never taken from the
            # artifact (D-8) — literally after the is_primary placeholder, matching the column
            # order (tie_break, is_primary, is_active). A caught real bug (P6.6): this used to
            # read "%(tie_break)s, false, %(is_primary)s" — false landed in is_primary's slot
            # and the artifact's own is_primary value leaked into is_active instead.
            run_sql, run_params = log[3]
            _assert("%(tie_break)s, %(is_primary)s, false" in run_sql,
                    "is_active is not hard-coded false in the VALUES clause, in column order")
            _assert("is_active" not in run_params, "is_active must not be a bound parameter")
        finally:
            db_mod.cursor = real_cursor

    check("a fresh load writes all seven tables, in FK order, is_active hard-coded false",
          _full_write_shape)

    print()
    if failed:
        print(f"artifact.load selftest: {passed} passed, {len(failed)} FAILED")
        return 1
    print(f"artifact.load selftest: {passed} passed, 0 failed")
    return 0


def _assert(cond: bool, what: object) -> None:
    if not cond:
        raise AssertionError(str(what))


def _assert_raises(fn, exc_type: type[BaseException], what: str) -> None:
    try:
        fn()
    except exc_type:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__} for {what}, got {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"expected {exc_type.__name__} for {what}, nothing raised")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.artifact.load",
        description="Load an on-disk artifact into Postgres (inactive). --selftest needs no DB.",
    )
    parser.add_argument("target", nargs="?", default=None,
                         help="artifact_id or path. With --all-on-disk, ignored.")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--all-on-disk", action="store_true",
                         help="Load every artifact found under data/artifacts/.")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    targets: list[str]
    if args.all_on_disk:
        targets = [artifact_id for _, _, artifact_id in find_artifacts()]
        if not targets:
            print("no artifacts found under data/artifacts/", file=sys.stderr)
            return 1
    elif args.target:
        targets = [args.target]
    else:
        parser.error("give an artifact_id/path, or pass --all-on-disk")
        return 2

    failed = False
    for t in targets:
        artifact = read_artifact(t)
        try:
            result = load_artifact(artifact)
        except (ArtifactLoadError, ArtifactCollisionError, V.ValidationError) as exc:
            print(f"{t}: FAILED — {exc}", file=sys.stderr)
            failed = True
            continue
        state = "inserted" if result.inserted else "no-op (already present)"
        print(f"{t}: {state}  run_id={result.run_id}  "
              f"universe={result.n_universe} params={result.n_ticker_params} "
              f"anchors={result.n_anchors} sim_anchor={result.n_similarity_anchor} "
              f"groups={result.n_groups}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
