"""pipelines.artifact.validate — V1-V14, the artifact's correctness contract.

Referenced by the migration plan's validation table since P0 and defined nowhere until now.
Each check maps to either a CHECK constraint in ``supabase/migrations/00005_model_artifact.sql``
or an identity from ``docs/02`` (the algorithm's output contract) — the cross-reference is in
each function's docstring, so a failure names the rule it broke rather than just "invalid".

V9 and V13 are the load-bearing pair: both **recompute from the stored matrix P** rather than
trusting a stored scalar, so a manifest that disagrees with its own P cannot pass. Every other
check is a self-consistency check among the manifest's own fields.

Every function takes ``(artifact, *, source_dir=None)`` for a uniform call signature — most
ignore ``source_dir``; only V3 uses it, to also confirm the artifact's directory name matches
its own id. Each function returns ``None`` on success and raises :class:`ValidationError`
(naming the check) on failure — the same "assert, don't return a bool" idiom as
``pipelines.factor.model.assert_similarity`` and ``pipelines.anchors.greedy.assert_identities``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from pipelines.artifact import identity
from pipelines.artifact.schema import ARTIFACT_SCHEMA_VERSION, Artifact

_TOL = 1e-8
_REL_TOL = 1e-6


class ValidationError(AssertionError):
    """A specific V-rule failed. The message names which one."""


def v1_schema_version(a: Artifact, *, source_dir: Path | None = None) -> None:
    """artifact_schema_version is one this code knows (migration 00005's version column)."""
    if a.run.artifact_schema_version != ARTIFACT_SCHEMA_VERSION:
        raise ValidationError(
            f"V1: artifact_schema_version={a.run.artifact_schema_version!r} != "
            f"{ARTIFACT_SCHEMA_VERSION!r} this code knows"
        )


def v2_content_digest(a: Artifact, *, source_dir: Path | None = None) -> None:
    """Recomputing the digest reproduces content_sha256, 64 hex chars."""
    if len(a.run.content_sha256) != 64:
        raise ValidationError(
            f"V2: content_sha256 is {len(a.run.content_sha256)} chars, expected 64"
        )
    if not identity.verify_content_sha256(a):
        raise ValidationError(
            f"V2: recomputed content_sha256 != stored ({a.run.content_sha256})"
        )


def v3_artifact_id(a: Artifact, *, source_dir: Path | None = None) -> None:
    """artifact_id is the agreed prefix of content_sha256, and (if known) the directory name."""
    expected = identity.artifact_id_from_digest(a.run.content_sha256)
    if a.run.artifact_id != expected:
        raise ValidationError(f"V3: artifact_id={a.run.artifact_id!r} != {expected!r}")
    if source_dir is not None and source_dir.name != a.run.artifact_id:
        raise ValidationError(
            f"V3: directory name {source_dir.name!r} != artifact_id {a.run.artifact_id!r}"
        )


def v4_universe_positions(a: Artifact, *, source_dir: Path | None = None) -> None:
    """Universe positions are exactly 0..N-1; tickers unique; order is ascending by ticker.

    Column order is what the greedy tie-break (smallest index) depends on (docs/04 §2).
    """
    n = len(a.universe)
    positions = sorted(u.position for u in a.universe)
    if positions != list(range(n)):
        raise ValidationError(f"V4: universe positions are not exactly 0..{n - 1}: {positions}")
    tickers = [u.ticker for u in a.universe]
    if len(set(tickers)) != n:
        raise ValidationError("V4: duplicate tickers in universe")
    ordered = [u.ticker for u in sorted(a.universe, key=lambda u: u.position)]
    if ordered != sorted(ordered):
        raise ValidationError(f"V4: universe not ticker-ascending by position: {ordered}")


def v5_dimensions(a: Artifact, *, source_dir: Path | None = None) -> None:
    """n_tickers == len(universe) == P.shape; n_sessions > 0; q == N/T."""
    n, t = a.run.n_tickers, a.run.n_sessions
    if n != len(a.universe):
        raise ValidationError(f"V5: n_tickers={n} != len(universe)={len(a.universe)}")
    if tuple(a.P.shape) != (n, n):
        raise ValidationError(f"V5: P.shape={a.P.shape} != ({n}, {n})")
    if t <= 0:
        raise ValidationError(f"V5: n_sessions={t} <= 0")
    expected_q = n / t
    if abs(a.run.q - expected_q) > _REL_TOL * max(1.0, abs(expected_q)):
        raise ValidationError(f"V5: q={a.run.q} != N/T={expected_q}")


def v6_window(a: Artifact, *, source_dir: Path | None = None) -> None:
    """window_start <= window_end; prior_close_date < window_start (D-11)."""
    r = a.run
    if r.window_start > r.window_end:
        raise ValidationError(f"V6: window_start {r.window_start} > window_end {r.window_end}")
    if r.prior_close_date >= r.window_start:
        raise ValidationError(
            f"V6: prior_close_date {r.prior_close_date} not before window_start "
            f"{r.window_start} (D-11)"
        )


def v7_k_bounds(a: Artifact, *, source_dir: Path | None = None) -> None:
    """0 < k <= k_max <= N (migration: model_runs_k_le_kmax, k/k_max CHECK > 0)."""
    r = a.run
    if not (0 < r.k <= r.k_max <= r.n_tickers):
        raise ValidationError(
            f"V7: expected 0 < k({r.k}) <= k_max({r.k_max}) <= N({r.n_tickers})"
        )


def v8_ticker_params(a: Artifact, *, source_dir: Path | None = None) -> None:
    """One TickerParams per position, no gaps; sigma_hat > 0; r2 in [0,1]; alpha/beta finite."""
    n = a.run.n_tickers
    positions = sorted(tp.position for tp in a.ticker_params)
    if positions != list(range(n)):
        raise ValidationError(f"V8: ticker_params positions are not exactly 0..{n - 1}")
    for tp in a.ticker_params:
        if not (np.isfinite(tp.sigma_hat) and tp.sigma_hat > 0):
            raise ValidationError(f"V8: sigma_hat<=0 or non-finite for {tp.ticker}: {tp.sigma_hat}")
        if not (0.0 <= tp.r2 <= 1.0):
            raise ValidationError(f"V8: r2 out of [0,1] for {tp.ticker}: {tp.r2}")
        if not (np.isfinite(tp.alpha_hat) and np.isfinite(tp.beta_hat)):
            raise ValidationError(f"V8: alpha_hat/beta_hat not finite for {tp.ticker}")


def v9_coverage_matches_p(a: Artifact, *, source_dir: Path | None = None) -> None:
    """coverage_c in [0,1] and equals P[i, position(a(i))], recomputed from the stored P."""
    for tp in a.ticker_params:
        if not (0.0 <= tp.coverage_c <= 1.0):
            raise ValidationError(f"V9: coverage_c out of [0,1] for {tp.ticker}: {tp.coverage_c}")
        j = a.position_of(tp.anchor_ticker)
        actual = float(a.P[tp.position, j])
        if abs(actual - tp.coverage_c) > _REL_TOL * max(1.0, abs(actual)):
            raise ValidationError(
                f"V9: coverage_c for {tp.ticker} = {tp.coverage_c} != P[i,a(i)] = {actual}"
            )


def v10_anchor_steps(a: Artifact, *, source_dir: Path | None = None) -> None:
    """step_k covers 1..k_max contiguously; anchors unique; in_published_set <=> step_k<=k."""
    k, k_max = a.run.k, a.run.k_max
    steps = sorted(s.step_k for s in a.anchors)
    if steps != list(range(1, k_max + 1)):
        raise ValidationError(f"V10: step_k does not cover 1..{k_max} contiguously: {steps}")
    tickers = [s.anchor_ticker for s in a.anchors]
    if len(set(tickers)) != len(tickers):
        raise ValidationError("V10: anchor tickers are not unique across steps")
    for s in a.anchors:
        expected = s.step_k <= k
        if s.in_published_set != expected:
            raise ValidationError(
                f"V10: step {s.step_k} in_published_set={s.in_published_set} != "
                f"(step_k<=k)={expected}"
            )


def v11_marginal_gain_monotone(a: Artifact, *, source_dir: Path | None = None) -> None:
    """marginal_gain >= 0 and non-increasing across steps — submodularity made visible.

    A violation means P was mutated between greedy rounds (docs/02 §3e, migration comment on
    model_anchors.marginal_gain).
    """
    ordered = sorted(a.anchors, key=lambda s: s.step_k)
    prev: float | None = None
    for s in ordered:
        if s.marginal_gain < -_TOL:
            raise ValidationError(
                f"V11: negative marginal_gain at step {s.step_k}: {s.marginal_gain}"
            )
        if prev is not None and s.marginal_gain > prev + _TOL:
            raise ValidationError(
                f"V11: marginal_gain increased at step {s.step_k}: {s.marginal_gain} > {prev}"
            )
        prev = s.marginal_gain


def v12_coverage_totals(a: Artifact, *, source_dir: Path | None = None) -> None:
    """coverage_f == sum(coverage_c); coverage_fbar == F/N in [0,1]; both match the curve at k."""
    r = a.run
    f_sum = sum(tp.coverage_c for tp in a.ticker_params)
    if abs(r.coverage_f - f_sum) > _REL_TOL * max(1.0, abs(f_sum)):
        raise ValidationError(f"V12: coverage_f={r.coverage_f} != sum(coverage_c)={f_sum}")
    expected_fbar = (r.coverage_f / r.n_tickers) if r.n_tickers else 0.0
    if abs(r.coverage_fbar - expected_fbar) > _REL_TOL * max(1.0, abs(expected_fbar)):
        raise ValidationError(f"V12: coverage_fbar={r.coverage_fbar} != F/N={expected_fbar}")
    if not (0.0 <= r.coverage_fbar <= 1.0 + _TOL):
        raise ValidationError(f"V12: coverage_fbar out of [0,1]: {r.coverage_fbar}")
    at_k = [s for s in a.anchors if s.step_k == r.k]
    if not at_k:
        raise ValidationError(f"V12: no anchor step at step_k=k={r.k}")
    row = at_k[0]
    if abs(row.coverage_f - r.coverage_f) > _REL_TOL * max(1.0, abs(r.coverage_f)):
        raise ValidationError(
            f"V12: curve row F at k ({row.coverage_f}) != run.coverage_f ({r.coverage_f})"
        )
    if abs(row.coverage_fbar - r.coverage_fbar) > _REL_TOL * max(1.0, abs(r.coverage_fbar)):
        raise ValidationError(
            f"V12: curve row Fbar at k ({row.coverage_fbar}) != run.coverage_fbar "
            f"({r.coverage_fbar})"
        )


def v13_similarity_matrix(a: Artifact, *, source_dir: Path | None = None) -> None:
    """P symmetric, unit diagonal, [0,1]; p_sha256 matches the sha256 of the stored P."""
    P = a.P
    n = a.run.n_tickers
    if tuple(P.shape) != (n, n):
        raise ValidationError(f"V13: P.shape={P.shape} != ({n}, {n})")
    if not np.allclose(P, P.T, atol=1e-8):
        raise ValidationError("V13: P is not symmetric")
    if not np.all(np.abs(np.diag(P) - 1.0) <= 1e-6):
        raise ValidationError("V13: diag(P) != 1")
    if not (np.all(P >= -_TOL) and np.all(P <= 1.0 + _TOL)):
        raise ValidationError("V13: P outside [0, 1]")
    recomputed = identity.compute_p_sha256(P)
    if recomputed != a.run.p_sha256:
        raise ValidationError(f"V13: recomputed p_sha256 {recomputed} != stored {a.run.p_sha256}")


def v14_assignment_identities(a: Artifact, *, source_dir: Path | None = None) -> None:
    """is_anchor <=> ticker in S; a(j)=j for anchors; a(i) in S; under_tau <=> c_i<tau."""
    published = {s.anchor_ticker for s in a.anchors if s.in_published_set}
    tau = a.run.tau
    n_under = 0
    for tp in a.ticker_params:
        expected_is_anchor = tp.ticker in published
        if tp.is_anchor != expected_is_anchor:
            raise ValidationError(
                f"V14: is_anchor for {tp.ticker} = {tp.is_anchor} != "
                f"(ticker in S)={expected_is_anchor}"
            )
        if tp.is_anchor and tp.anchor_ticker != tp.ticker:
            raise ValidationError(
                f"V14: anchor {tp.ticker} assigned to {tp.anchor_ticker}, expected itself"
            )
        if tp.anchor_ticker not in published:
            raise ValidationError(
                f"V14: {tp.ticker}'s anchor {tp.anchor_ticker} not in published S"
            )
        expected_under = tp.coverage_c < tau
        if tp.under_tau != expected_under:
            raise ValidationError(
                f"V14: under_tau for {tp.ticker} = {tp.under_tau} != "
                f"(coverage_c<tau)={expected_under}"
            )
        n_under += int(tp.under_tau)
    if n_under != a.run.n_under_tau:
        raise ValidationError(f"V14: n_under_tau={a.run.n_under_tau} != actual count {n_under}")


CheckFn = Callable[..., None]

#: Ordered so V1-V3 (identity) fail fast before V4-V14 (content) do real work.
CHECKS: list[tuple[str, str, CheckFn]] = [
    ("V1", "artifact_schema_version is known", v1_schema_version),
    ("V2", "content_sha256 reproduces from content", v2_content_digest),
    ("V3", "artifact_id matches content_sha256 (and directory name)", v3_artifact_id),
    ("V4", "universe positions 0..N-1, unique, ascending", v4_universe_positions),
    ("V5", "N/T/q dimensions agree with P", v5_dimensions),
    ("V6", "window ordering and prior_close_date (D-11)", v6_window),
    ("V7", "0 < k <= k_max <= N", v7_k_bounds),
    ("V8", "per-ticker params complete, sigma_hat>0, r2 in [0,1]", v8_ticker_params),
    ("V9", "coverage_c matches P[i,a(i)]", v9_coverage_matches_p),
    ("V10", "anchor steps contiguous, in_published_set correct", v10_anchor_steps),
    ("V11", "marginal_gain >= 0, non-increasing", v11_marginal_gain_monotone),
    ("V12", "F/Fbar totals match the curve at k", v12_coverage_totals),
    ("V13", "P symmetric/unit-diag/[0,1], p_sha256 matches", v13_similarity_matrix),
    ("V14", "assignment identities, under_tau, n_under_tau", v14_assignment_identities),
]


def validate_all(artifact: Artifact, *, source_dir: Path | None = None) -> None:
    """Run V1-V14 in order; raise on the first failure. Used before writing (train.py)."""
    for _check_id, _label, fn in CHECKS:
        fn(artifact, source_dir=source_dir)
