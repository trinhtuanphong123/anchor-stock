"""pipelines.model.train — the only caller of ``pipelines.anchors.greedy``.

Orchestrates one research-year run end to end: resolve the frozen universe, align returns,
fit the factor model, build the similarity matrix, run greedy to ``k_max`` (D-9: the whole
marginal-gain curve, since nesting makes it free), assign against the *published* k-anchor
prefix, and package the result into an :class:`~pipelines.artifact.schema.Artifact`.

Two correctness traps this module exists to get right (see ``train_one_window``'s body):

1. Greedy runs to ``k_max``, but assignment — and therefore ``coverage_c``, ``a(i)`` and the
   group table — is computed on ``S[:k]`` only. ``docs/02`` §3b defines the assignment over the
   *published* set, not the candidate curve. Calling ``pipelines.anchors.greedy.assign``
   directly (rather than ``run_anchor_selection``, which assigns against every anchor greedy
   ever selected) is what keeps the two k's from being silently conflated.
2. ``RunMeta.coverage_f`` / ``coverage_fbar`` are the values *at k* — recomputed independently
   from the k-anchor assignment, not copied from the k_max curve's row at step k. The two are
   asserted equal by ``artifact.validate.v12_coverage_totals``. That assertion is bookkeeping,
   not an independent correctness check: ``F(S) = Σ_i P[i, a(i)]`` with ``a(i) = argmax_{j∈S}
   P[i,j]`` is the same mathematical quantity down both code paths, only reached by different
   arithmetic — a real catch for column-order or off-by-one bugs, not for a wrong P or a wrong
   greedy. ``pipelines.research.residuals.assert_reproduces_p`` (P12) is the check that is
   actually independent: it re-fits the factor model from re-loaded returns and confirms the
   recomputed P matches the artifact's own, so a downstream study is anchored to the same E the
   published run used.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict
from datetime import date
from pathlib import Path

from pipelines.anchors.greedy import assign, greedy, under_threshold
from pipelines.artifact import identity, validate
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
from pipelines.common.paths import REPO_ROOT, RESEARCH_UNIVERSE_FILE
from pipelines.factor.model import fit_factor_model
from pipelines.model.similarity import similarity
from pipelines.returns.matrix import SOURCE, load_return_matrix, repo_relative_path
from pipelines.universe.file import resolve_universe

DEFAULT_INDEX_SYMBOL = "VNINDEX"
DEFAULT_K = 10
DEFAULT_K_MAX = 15
DEFAULT_TAU = 0.10
DEFAULT_MEASURE = "pearson_rho2"


def _code_version() -> str | None:
    """Short git commit hash, purely informational — excluded from the digest (identity.py)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=5, check=True,
        )
        return result.stdout.strip() or None
    except Exception:  # noqa: BLE001 - provenance only, never blocks a run
        return None


def train_one_window(
    window_year: int,
    *,
    universe_file: Path | str | None = None,
    index_symbol: str = DEFAULT_INDEX_SYMBOL,
    k: int = DEFAULT_K,
    k_max: int = DEFAULT_K_MAX,
    tau: float = DEFAULT_TAU,
    measure: str = DEFAULT_MEASURE,
    is_primary: bool = False,
) -> Artifact:
    """Build one sealed, validated (but not yet written) Artifact for a research year."""
    from datetime import UTC, datetime  # noqa: PLC0415

    uf = resolve_universe(None, universe_file or RESEARCH_UNIVERSE_FILE)
    start, end = date(window_year, 1, 1), date(window_year, 12, 31)

    m = load_return_matrix(
        list(uf.tickers), index_symbol, start=start, end=end, source=SOURCE,
        universe_path=repo_relative_path(uf.path), universe_version=uf.version,
    )
    m.report.assert_ready_for_run()
    m.report.assert_full_coverage(uf.tickers)
    m.assert_rectangular()

    fit = fit_factor_model(m.X, m.f)
    P = similarity(fit.residuals, measure)

    # Greedy to k_max — the whole curve, nested and therefore free (D-9).
    g = greedy(P, k_max)
    # Assignment on the PUBLISHED prefix only (docs/02 §3b) — not run_anchor_selection(), which
    # would assign against every one of the k_max anchors greedy selected.
    published_anchors = g.anchors[:k]
    asn = assign(P, published_anchors)
    under = set(under_threshold(asn.best_rho2, tau))
    published_positions = set(published_anchors)

    F = float(asn.best_rho2.sum())
    N = m.report.N
    Fbar = (F / N) if N else 0.0

    universe = [UniverseEntry(position=i, ticker=t) for i, t in enumerate(m.tickers)]

    ticker_params = [
        TickerParams(
            ticker=m.tickers[i],
            position=i,
            alpha_hat=float(fit.alpha[i]),
            beta_hat=float(fit.beta[i]),
            sigma_hat=float(fit.sigma[i]),
            r2=float(fit.r2[i]),
            anchor_ticker=m.tickers[int(asn.assignment[i])],
            coverage_c=float(asn.best_rho2[i]),
            is_anchor=(i in published_positions),
            under_tau=(i in under),
        )
        for i in range(N)
    ]

    anchors = [
        AnchorStep(
            step_k=row["k"],
            anchor_ticker=m.tickers[row["anchor"]],
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
            anchor_ticker=m.tickers[j],
            size=len(members),
            f_j=asn.F_j[j],
            rho2_mean=asn.rho2_mean_j[j],
            rho2_min=min(rho2s) if rho2s else 0.0,
        ))

    run = RunMeta(
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
        scope="year",
        scope_label=str(window_year),
        similarity_measure=measure,
        universe_version=uf.version,
        index_symbol=index_symbol,
        source=SOURCE,
        window_start=m.report.first_session,
        window_end=m.report.last_session,
        prior_close_date=m.report.prior_close_date,
        n_sessions=m.report.T,
        n_tickers=N,
        # Exact N/T, not m.report.q — AlignmentReport rounds q to 4dp for human-readable JSON;
        # the artifact needs the precise value V5 can verify without a rounding tolerance.
        q=(N / m.report.T) if m.report.T else 0.0,
        k=k,
        k_max=k_max,
        tau=tau,
        coverage_f=F,
        coverage_fbar=Fbar,
        n_under_tau=len(under),
        alignment=asdict(m.report),
        is_primary=is_primary,
        code_version=_code_version(),
        created_at=datetime.now(UTC).isoformat(),
    )

    artifact = Artifact(run=run, universe=universe, ticker_params=ticker_params,
                        anchors=anchors, groups=groups, P=P)
    # Sealed here, not left to write_artifact, so --dry-run (which never calls write_artifact)
    # still returns an artifact with a real artifact_id/content_sha256 to validate and print.
    return identity.seal(artifact)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m pipelines.model.train",
        description="Train and publish one artifact per --window year (docs/04 §2).",
    )
    parser.add_argument("--window", type=int, nargs="+", required=True, metavar="YEAR",
                        help="One or more research years, e.g. --window 2021 2022 2023 2024 2025.")
    parser.add_argument("--universe", type=str, default=None, metavar="PATH",
                        help="Universe file (default: list_stocks_research.txt).")
    parser.add_argument("--index", type=str, default=DEFAULT_INDEX_SYMBOL, metavar="SYM")
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--k-max", type=int, default=DEFAULT_K_MAX)
    parser.add_argument("--tau", type=float, default=DEFAULT_TAU)
    parser.add_argument("--measure", type=str, default=DEFAULT_MEASURE,
                        choices=("pearson_rho2", "dcor2"))
    parser.add_argument("--primary", type=int, default=None, metavar="YEAR",
                        help="Mark this --window year's artifact is_primary=true.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build and validate (V1-V14) without writing to data/artifacts/.")
    args = parser.parse_args(argv)

    failures = 0
    for year in args.window:
        print(f"=== {year} ===")
        artifact = train_one_window(
            year,
            universe_file=args.universe,
            index_symbol=args.index,
            k=args.k, k_max=args.k_max, tau=args.tau,
            measure=args.measure,
            is_primary=(args.primary == year),
        )
        try:
            validate.validate_all(artifact)
        except validate.ValidationError as exc:
            failures += 1
            print(f"  VALIDATION FAILED: {exc}")
            continue

        print(f"  artifact_id : {artifact.run.artifact_id}")
        print(f"  N={artifact.run.n_tickers}  T={artifact.run.n_sessions}  "
              f"q={artifact.run.q}  k={artifact.run.k}  k_max={artifact.run.k_max}")
        print(f"  F={artifact.run.coverage_f:.4f}  Fbar={artifact.run.coverage_fbar:.4f}  "
              f"n_under_tau={artifact.run.n_under_tau}  is_primary={artifact.run.is_primary}")

        if args.dry_run:
            print("  (dry-run — not written)")
        else:
            out_dir = aio.write_artifact(artifact)
            print(f"  written to  : {out_dir}")

    print(f"\n{len(args.window) - failures}/{len(args.window)} window(s) succeeded")
    return 0 if not failures else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
