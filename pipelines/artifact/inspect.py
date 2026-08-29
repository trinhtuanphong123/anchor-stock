"""pipelines.artifact.inspect — run V1-V14 against a real or synthetic artifact.

CLI:

    python -m pipelines.artifact.inspect <artifact_id_or_path>
    python -m pipelines.artifact.inspect --selftest

``--selftest`` needs no network or database: it builds a synthetic artifact from
``pipelines.anchors.greedy``'s own block-structured fixture (the same one ``greedy.py --mock``
uses), confirms it passes all fourteen checks, then — for every check — deliberately violates
exactly the one thing that check exists to catch and confirms it raises. This is the same
behavioural standard the P0 schema guard rails were held to: each rule proven to refuse what it
claims to, not just listed.
"""

from __future__ import annotations

import copy
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from pipelines.anchors.greedy import assign, greedy, under_threshold
from pipelines.artifact import identity
from pipelines.artifact import io as aio
from pipelines.artifact.schema import (
    ARTIFACT_SCHEMA_VERSION,
    AnchorStep,
    Artifact,
    Group,
    RunMeta,
    TickerParams,
    UniverseEntry,
)
from pipelines.artifact.validate import CHECKS, ValidationError

# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def run_checks(artifact: Artifact, *, source_dir: Path | None = None) -> tuple[int, int]:
    """Print PASS/FAIL for every check in :data:`CHECKS`. Returns ``(passed, failed)``."""
    passed = 0
    failed = 0
    for check_id, label, fn in CHECKS:
        try:
            fn(artifact, source_dir=source_dir)
        except Exception as exc:  # noqa: BLE001 - the point is to report, not propagate
            failed += 1
            print(f"  FAIL  {check_id}  {label}\n          {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"  PASS  {check_id}  {label}")
    return passed, failed


# ---------------------------------------------------------------------------
# Synthetic fixture (block-structured P, same shape as anchors/greedy.py's own --mock)
# ---------------------------------------------------------------------------


def _mock_p(
    blocks: tuple[int, ...] = (3, 3), within: float = 0.7, cross: float = 0.05
) -> np.ndarray:
    n = sum(blocks)
    P = np.full((n, n), cross, dtype=float)
    idx = 0
    for b in blocks:
        P[idx:idx + b, idx:idx + b] = within
        idx += b
    np.fill_diagonal(P, 1.0)
    return P


def build_fixture_artifact(k: int = 2, k_max: int = 4, tau: float = 0.5) -> Artifact:
    """A genuinely correct, greedy-derived artifact — exercises the real selection code, not a
    hand-typed stand-in for it.
    """
    P = _mock_p()
    n = P.shape[0]
    tickers = [chr(ord("A") + i) for i in range(n)]   # already ascending: A, B, C, D, E, F

    g = greedy(P, k_max)
    asn = assign(P, g.anchors[:k])
    published = set(g.anchors[:k])
    under = set(under_threshold(asn.best_rho2, tau))

    universe = [UniverseEntry(position=i, ticker=tickers[i]) for i in range(n)]

    ticker_params = [
        TickerParams(
            ticker=tickers[i],
            position=i,
            alpha_hat=0.0,
            beta_hat=1.0,
            sigma_hat=0.01,
            r2=0.5,
            anchor_ticker=tickers[int(asn.assignment[i])],
            coverage_c=float(asn.best_rho2[i]),
            is_anchor=(i in published),
            under_tau=(i in under),
        )
        for i in range(n)
    ]

    anchors = [
        AnchorStep(
            step_k=row["k"],
            anchor_ticker=tickers[row["anchor"]],
            position=row["anchor"],
            marginal_gain=row["marginal_gain"],
            coverage_f=row["F"],
            coverage_fbar=row["Fbar"],
            in_published_set=(row["k"] <= k),
        )
        for row in g.coverage_curve
    ]

    groups = []
    for j in sorted(asn.clusters):
        members = asn.clusters[j]
        rho2s = [float(asn.best_rho2[i]) for i in members]
        groups.append(Group(
            anchor_ticker=tickers[j],
            size=len(members),
            f_j=asn.F_j[j],
            rho2_mean=asn.rho2_mean_j[j],
            rho2_min=min(rho2s) if rho2s else 0.0,
        ))

    at_k = next(row for row in g.coverage_curve if row["k"] == k)

    run = RunMeta(
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
        scope="year",
        scope_label="9999",
        similarity_measure="pearson_rho2",
        universe_version="utest0000",
        index_symbol="VNINDEX",
        source="VCI",
        window_start=date(9999, 1, 1),
        window_end=date(9999, 12, 31),
        prior_close_date=date(9998, 12, 31),
        n_sessions=250,
        n_tickers=n,
        q=n / 250,
        k=k,
        k_max=k_max,
        tau=tau,
        coverage_f=at_k["F"],
        coverage_fbar=at_k["Fbar"],
        n_under_tau=len(under),
        alignment={"note": "synthetic fixture, not a real alignment report"},
        created_at=datetime.now(UTC).isoformat(),
    )

    artifact = Artifact(run=run, universe=universe, ticker_params=ticker_params,
                        anchors=anchors, groups=groups, P=P)
    identity.seal(artifact)
    return artifact


# ---------------------------------------------------------------------------
# --selftest
# ---------------------------------------------------------------------------


def _violate(base: Artifact, mutate: Any) -> Artifact:
    """Deep-copy ``base`` (hashes/ids stay as the clean copy recorded) and apply ``mutate``."""
    corrupt = copy.deepcopy(base)
    mutate(corrupt)
    return corrupt


# ---------------------------------------------------------------------------
# --from-db — read an artifact back out of Postgres and compare it to disk (P6.6)
#
# This is what proves pipelines.artifact.load's write LOSSLESS rather than merely plausible.
# P is compared exactly (float8 is IEEE-754 double both sides — see D-4), not within a
# tolerance; a mismatch there means the load or the read has a real bug, not rounding.
# ---------------------------------------------------------------------------


def read_artifact_from_db(artifact_id: str) -> Artifact:
    """Rebuild an :class:`Artifact` from ``model_runs`` and its six child tables.

    Every ``numeric`` column crosses the seam via ``float()`` at the point of construction — the
    same convention ``pipelines.storage.pg`` uses — so nothing downstream ever sees a
    ``Decimal``. ``float8[]`` values (``model_similarity_full.values``) already come back as
    ``float`` from psycopg2, needing no conversion.

    **``extra_float_digits`` is set explicitly, and the exact comparison above depends on it.**
    psycopg2 receives ``float8`` as *text*, so how many digits the server prints decides whether a
    double survives the trip. PostgreSQL 12+ defaults to ``1`` — the shortest representation that
    round-trips exactly — but a pooler may override it, and Supabase's does: measured on
    2026-08-29, a session through the Supavisor pooler reports ``extra_float_digits = 0``, which
    prints 15 significant digits and quietly drops the last bits.

    That is not hypothetical. Against the local container this check passed with ``P`` exact
    (P6.5); against Supabase it failed with ``max abs diff = 4.996e-16`` — about two ULP, the
    signature of a formatting loss rather than a data one. Re-reading the same rows at
    ``extra_float_digits`` 1, 2 and 3 all returned ``P`` **bit-for-bit identical**, which is what
    identifies the cause. The stored bytes were never wrong; the read was.

    So the setting is pinned here rather than trusted, and ``3`` is used rather than ``1`` because
    it is the maximum and cannot under-print on any server version. Without this line the check
    reports a false FAIL on the deployment that actually matters — the worst kind, because it
    accuses the loader of a bug that is not there.
    """
    from pipelines.common.db import cursor  # noqa: PLC0415

    with cursor() as cur:
        cur.execute("SET extra_float_digits = 3")
        cur.execute(
            """
            SELECT artifact_id, artifact_schema_version, content_sha256,
                   scope, scope_label, similarity_measure,
                   universe_version, index_symbol, source,
                   window_start, window_end, prior_close_date,
                   n_sessions, n_tickers, q,
                   k, k_max, tau,
                   coverage_f, coverage_fbar, n_under_tau,
                   tie_break, is_primary, is_active,
                   alignment, code_version, created_at,
                   id
            FROM model_runs WHERE artifact_id = %s
            """,
            (artifact_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise LookupError(f"artifact_id {artifact_id!r} not found in model_runs")
        (art_id, schema_v, content_sha, scope, scope_label, measure, univ_v, idx_sym, source,
         w_start, w_end, prior_close, n_sess, n_tick, q, k, k_max, tau, cov_f, cov_fbar,
         n_under_tau, tie_break, is_primary, is_active, alignment, code_version,
         created_at, run_id) = row

        run = RunMeta(
            artifact_schema_version=schema_v,
            scope=scope, scope_label=scope_label, similarity_measure=measure,
            universe_version=univ_v, index_symbol=idx_sym, source=source,
            window_start=w_start, window_end=w_end, prior_close_date=prior_close,
            n_sessions=n_sess, n_tickers=n_tick, q=float(q),
            k=k, k_max=k_max, tau=float(tau),
            coverage_f=float(cov_f), coverage_fbar=float(cov_fbar), n_under_tau=n_under_tau,
            alignment=alignment, artifact_id=art_id, content_sha256=content_sha,
            tie_break=tie_break, is_primary=is_primary, is_active=is_active,
            code_version=code_version, created_at=created_at.isoformat(),
        )

        cur.execute(
            "SELECT position, ticker FROM model_universe WHERE run_id = %s ORDER BY position",
            (run_id,),
        )
        universe = [UniverseEntry(position=p, ticker=t) for p, t in cur.fetchall()]

        cur.execute(
            """
            SELECT ticker, position, alpha_hat, beta_hat, sigma_hat, r2,
                   anchor_ticker, coverage_c, is_anchor, under_tau
            FROM model_ticker_params WHERE run_id = %s ORDER BY position
            """,
            (run_id,),
        )
        ticker_params = [
            TickerParams(
                ticker=t, position=p, alpha_hat=float(a), beta_hat=float(b),
                sigma_hat=float(s), r2=float(r2), anchor_ticker=at,
                coverage_c=float(c), is_anchor=ia, under_tau=ut,
            )
            for t, p, a, b, s, r2, at, c, ia, ut in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT step_k, anchor_ticker, position, marginal_gain,
                   coverage_f, coverage_fbar, in_published_set
            FROM model_anchors WHERE run_id = %s ORDER BY step_k
            """,
            (run_id,),
        )
        anchors = [
            AnchorStep(
                step_k=sk, anchor_ticker=at, position=p, marginal_gain=float(mg),
                coverage_f=float(f), coverage_fbar=float(fb), in_published_set=ip,
            )
            for sk, at, p, mg, f, fb, ip in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT anchor_ticker, size, f_j, rho2_mean, rho2_min, sector_composition
            FROM model_groups WHERE run_id = %s ORDER BY anchor_ticker
            """,
            (run_id,),
        )
        groups = [
            Group(
                anchor_ticker=at, size=sz, f_j=float(fj), rho2_mean=float(rm),
                rho2_min=float(rmin), sector_composition=sc or {},
            )
            for at, sz, fj, rm, rmin, sc in cur.fetchall()
        ]

        cur.execute(
            "SELECT n, values, p_sha256 FROM model_similarity_full WHERE run_id = %s", (run_id,)
        )
        n, values, p_sha256 = cur.fetchone()
        P = np.array(values, dtype=np.float64).reshape(n, n)

    # p_sha256 is logically a model_similarity_full column (see schema.py's RunMeta docstring
    # on why identity.seal() writes it there); RunMeta only has the field so both sides of a
    # comparison read the same shape without a special case.
    run.p_sha256 = p_sha256

    return Artifact(run=run, universe=universe, ticker_params=ticker_params,
                     anchors=anchors, groups=groups, P=P)


#: RunMeta fields allowed to differ between disk and DB, and why.
_RUN_FIELDS_EXCLUDED_FROM_COMPARE: frozenset[str] = frozenset({
    # DB-only state: load.py always writes is_active=false (D-8); activate.py may have since
    # flipped it. The on-disk artifact never records activation at all.
    "is_active",
})


def compare_artifacts(disk: Artifact, db: Artifact) -> list[str]:
    """Field-for-field equality, disk vs. DB. Empty list == identical (``is_active`` excepted).

    ``P`` is compared with ``np.array_equal`` — exact, not ``np.allclose`` — because ``float8``
    is IEEE-754 double on both sides (D-4) and a mismatch here is a real bug, not float noise.
    """
    mismatches: list[str] = []

    d_run, b_run = disk.run.to_dict(), db.run.to_dict()
    for field_name in sorted(set(d_run) - _RUN_FIELDS_EXCLUDED_FROM_COMPARE):
        dv, bv = d_run[field_name], b_run.get(field_name)
        if field_name == "created_at":
            # Compare as instants, not strings: a timestamptz round-trip may reformat the
            # offset (+00:00 vs +0000) without changing the moment in time.
            if datetime.fromisoformat(dv) != datetime.fromisoformat(bv):
                mismatches.append(f"run.created_at: disk={dv!r} db={bv!r}")
            continue
        if dv != bv:
            mismatches.append(f"run.{field_name}: disk={dv!r} db={bv!r}")

    if [u.ticker for u in disk.universe] != [u.ticker for u in db.universe]:
        mismatches.append("universe: ticker order differs")
    elif [u.position for u in disk.universe] != [u.position for u in db.universe]:
        mismatches.append("universe: positions differ")

    if len(disk.ticker_params) != len(db.ticker_params):
        mismatches.append(
            f"ticker_params: {len(disk.ticker_params)} vs {len(db.ticker_params)} rows"
        )
    else:
        d_by_ticker = {t.ticker: t for t in disk.ticker_params}
        for t in db.ticker_params:
            if t.ticker not in d_by_ticker:
                mismatches.append(f"ticker_params: {t.ticker} on disk missing from db")
                continue
            if d_by_ticker[t.ticker] != t:
                mismatches.append(f"ticker_params[{t.ticker}]: disk={d_by_ticker[t.ticker]} db={t}")

    if disk.anchors != db.anchors:
        mismatches.append(f"anchors: disk={disk.anchors} != db={db.anchors}")

    if len(disk.groups) != len(db.groups):
        mismatches.append(f"groups: {len(disk.groups)} vs {len(db.groups)} rows")
    else:
        d_by_anchor = {g.anchor_ticker: g for g in disk.groups}
        for g in db.groups:
            if d_by_anchor.get(g.anchor_ticker) != g:
                mismatches.append(
                    f"groups[{g.anchor_ticker}]: disk={d_by_anchor.get(g.anchor_ticker)} db={g}"
                )

    if disk.P.shape != db.P.shape:
        mismatches.append(f"P: shape disk={disk.P.shape} != db={db.P.shape}")
    elif not np.array_equal(disk.P, db.P):
        max_abs_diff = float(np.max(np.abs(disk.P - db.P)))
        mismatches.append(f"P: not exactly equal, max abs diff={max_abs_diff!r}")

    return mismatches


def run_from_db_check(artifact_id: str) -> bool:
    """``python -m pipelines.artifact.inspect --from-db <id>``. Prints and returns pass/fail."""
    disk = aio.read_artifact(artifact_id)
    db = read_artifact_from_db(artifact_id)
    mismatches = compare_artifacts(disk, db)
    if mismatches:
        print(f"  FAIL  {len(mismatches)} mismatch(es):")
        for m in mismatches:
            print(f"          {m}")
        return False
    print(f"  PASS  disk and db are field-for-field identical for {artifact_id} "
          f"(is_active excepted)")
    return True


def _selftest() -> int:
    passed = 0
    failed: list[str] = []

    def check(label: str, fn) -> None:
        nonlocal passed
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - the point is to report, not propagate
            failed.append(f"{label}: {type(exc).__name__}: {exc}")
            print(f"  FAIL  {label}\n          {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"  PASS  {label}")

    good = build_fixture_artifact()

    def _clean_passes_all() -> None:
        p, f = run_checks(good)
        assert f == 0, f"clean fixture failed {f} check(s)"
        assert p == len(CHECKS), f"expected {len(CHECKS)} checks, ran {p}"

    check("clean fixture passes all 14 checks", _clean_passes_all)

    # One deliberate violation per check, each targeting exactly the rule it names.
    violations: list[tuple[str, Any, Any]] = [
        ("V1", lambda a: setattr(a.run, "artifact_schema_version", 999),
         "artifact.validate.v1_schema_version"),
        ("V2", lambda a: setattr(a.run, "content_sha256",
                                 ("0" if a.run.content_sha256[0] != "0" else "1")
                                 + a.run.content_sha256[1:]),
         "artifact.validate.v2_content_digest"),
        ("V3", lambda a: setattr(a.run, "artifact_id", "a" + "0" * 12),
         "artifact.validate.v3_artifact_id"),
        ("V4", lambda a: setattr(a.universe[1], "position", a.universe[0].position),
         "artifact.validate.v4_universe_positions"),
        ("V5", lambda a: setattr(a.run, "n_tickers", a.run.n_tickers + 1),
         "artifact.validate.v5_dimensions"),
        ("V6", lambda a: setattr(a.run, "prior_close_date", a.run.window_start),
         "artifact.validate.v6_window"),
        ("V7", lambda a: setattr(a.run, "k", a.run.k_max + 1),
         "artifact.validate.v7_k_bounds"),
        ("V8", lambda a: setattr(a.ticker_params[0], "sigma_hat", 0.0),
         "artifact.validate.v8_ticker_params"),
        ("V9", lambda a: setattr(a.ticker_params[0], "coverage_c", 0.42),
         "artifact.validate.v9_coverage_matches_p"),
        ("V10", lambda a: setattr(
            a.anchors[0], "in_published_set", not a.anchors[0].in_published_set),
         "artifact.validate.v10_anchor_steps"),
        ("V11", lambda a: setattr(
            a.anchors[-1], "marginal_gain", a.anchors[0].marginal_gain + 1.0),
         "artifact.validate.v11_marginal_gain_monotone"),
        ("V12", lambda a: setattr(a.run, "coverage_f", a.run.coverage_f + 1.0),
         "artifact.validate.v12_coverage_totals"),
        ("V13", lambda a: a.P.__setitem__((0, 1), a.P[0, 1] + 0.3),
         "artifact.validate.v13_similarity_matrix"),
        ("V14", lambda a: setattr(
            a.ticker_params[0], "under_tau", not a.ticker_params[0].under_tau),
         "artifact.validate.v14_assignment_identities"),
    ]

    check_by_id = {cid: fn for cid, _label, fn in CHECKS}

    for check_id, mutate, target_name in violations:
        def _one_violation(check_id=check_id, mutate=mutate, target_name=target_name) -> None:
            bad = _violate(good, mutate)
            try:
                check_by_id[check_id](bad, source_dir=None)
            except ValidationError:
                return
            raise AssertionError(f"{target_name} did not catch its deliberate violation")

        check(f"{check_id} catches its deliberate violation", _one_violation)

    # io round-trip: write, idempotent rewrite, and a genuine on-disk collision.
    def _io_round_trip() -> None:
        import shutil
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="datn_artifact_"))
        try:
            fixture = build_fixture_artifact()
            out_dir = aio.write_artifact(fixture, root=tmp)
            assert out_dir.name == fixture.run.artifact_id

            reloaded = aio.read_artifact(fixture.run.artifact_id, root=tmp)
            assert reloaded.run.artifact_id == fixture.run.artifact_id
            assert np.array_equal(reloaded.P, fixture.P)

            # idempotent: identical content, same id, must not raise
            aio.write_artifact(build_fixture_artifact(), root=tmp)

            # corrupt the on-disk manifest under the same id, then try to write the real
            # content again — the id now disagrees with what's on disk, must raise
            (out_dir / aio.MANIFEST_NAME).write_text('{"run": {"corrupt": true}}',
                                                      encoding="utf-8")
            try:
                aio.write_artifact(build_fixture_artifact(), root=tmp)
            except aio.ArtifactCollisionError:
                pass
            else:
                raise AssertionError("write_artifact did not detect the on-disk corruption")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    check("write/read round-trip, idempotent rewrite, collision detection", _io_round_trip)

    print(f"\nartifact.inspect selftest: {passed} passed, {len(failed)} failed")
    return 0 if not failed else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m pipelines.artifact.inspect",
        description="Run V1-V14 against a real artifact, or --selftest against a synthetic one.",
    )
    parser.add_argument("target", nargs="?", default=None,
                        help="artifact_id (resolved under data/artifacts/) or a directory path.")
    parser.add_argument("--selftest", action="store_true",
                        help="Build a synthetic artifact and exercise every check + violation.")
    parser.add_argument("--from-db", metavar="ARTIFACT_ID", default=None,
                        help="Read this artifact back out of Postgres and compare it, field "
                             "for field, against the same artifact_id on disk (P6.6).")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.from_db:
        return 0 if run_from_db_check(args.from_db) else 1

    if not args.target:
        parser.error("pass an artifact_id/path, --from-db ARTIFACT_ID, or --selftest")

    from pipelines.common.paths import artifact_dir

    p = Path(args.target)
    source_dir = p if p.is_dir() else artifact_dir(args.target)

    artifact = aio.read_artifact(args.target)
    print(f"artifact_id : {artifact.run.artifact_id}")
    print(f"scope       : {artifact.run.scope} / {artifact.run.scope_label}")
    print(f"N={artifact.run.n_tickers}  T={artifact.run.n_sessions}  "
          f"k={artifact.run.k}  k_max={artifact.run.k_max}")
    passed, failed = run_checks(artifact, source_dir=source_dir)
    print(f"\n{passed} passed, {failed} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
