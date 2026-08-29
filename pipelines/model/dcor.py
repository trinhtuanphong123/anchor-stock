"""pipelines.model.dcor — squared distance correlation (docs/01 §7, D-5).

The second similarity measure carried for comparison against Pearson-ρ². Only this module
changes what feeds greedy relative to ``pipelines.factor.model.residual_similarity`` — "only
§4 changes" (docs/01 §7): the same residual matrix E from the same factor-model fit is the
input to both measures.

Two estimators, both computed, only one ever reaching greedy:

- **V-statistic** (Székely, Rizzo & Bakirov 2007): double-centering. Biased upward under
  independence, but **always non-negative** — a theorem, not an accident of the data. This is
  what feeds greedy (:func:`residual_dcor2`). Non-negativity is what supplies **normalisation**
  of the coverage objective (docs/01 §4, docs/02 §1) — monotonicity and submodularity hold for
  any real P, so a negative similarity does not make the problem non-monotone; it makes F
  un-normalised (F(∅)=0 can exceed F of a small non-empty set), and normalisation is what the
  (1−1/e) guarantee actually requires. See :func:`residual_dcor2_u` for the same point stated
  from the U-statistic side.
- **U-statistic** (Székely & Rizzo 2013, U-centering): unbiased under independence, but **can
  go negative** by construction — that is how it buys unbiasedness. Computed only as a bias
  diagnostic (:func:`residual_dcor2_u`), reported alongside the V-statistic in
  ``measure_comparison``, never fed to greedy. See ``docs/decisions/D-05``.

The matmul route (both estimators): flatten each column's centred T×T distance matrix into one
row of an (N, T²) matrix M, then a single ``M @ M.T`` recovers every pairwise dCov² at once —
the Frobenius inner product of two T×T matrices is exactly the dot product of their flattened
forms. At N=100, T=250 that is ~42 MB and ~450M FLOPs: one BLAS call, no chunking needed.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from pipelines.factor.model import assert_similarity


def _pairwise_abs_distance(col: np.ndarray) -> np.ndarray:
    """a_ij = |col_i − col_j|, the T×T distance matrix for one residual column."""
    return np.abs(col[:, None] - col[None, :])


def _double_center(D: np.ndarray) -> np.ndarray:
    """V-statistic (biased) double-centering of a T×T distance matrix."""
    row_mean = D.mean(axis=1, keepdims=True)
    col_mean = D.mean(axis=0, keepdims=True)
    grand_mean = D.mean()
    return D - row_mean - col_mean + grand_mean


def _u_center(D: np.ndarray) -> np.ndarray:
    """U-statistic (unbiased) centering (Székely & Rizzo 2013). Needs T > 3.

    ``D`` is symmetric (it is a distance matrix), so its row sums equal its column sums —
    the same ``row_sum`` vector centres both axes.
    """
    T = D.shape[0]
    row_sum = D.sum(axis=1)
    total = D.sum()
    A = (
        D
        - row_sum[:, None] / (T - 2)
        - row_sum[None, :] / (T - 2)
        + total / ((T - 1) * (T - 2))
    )
    np.fill_diagonal(A, 0.0)
    return A


def _dcov2_matrix(E: np.ndarray, center_fn: Callable[[np.ndarray], np.ndarray],
                   denom: float) -> np.ndarray:
    """Every pairwise dCov² via one matmul.

    ``<A_i, A_j>_F = flatten(A_i) . flatten(A_j)`` — stacking the N flattened, centred distance
    matrices as rows of ``M`` (N, T²) turns the whole N×N table of Frobenius inner products into
    one ``M @ M.T``.
    """
    T, N = E.shape
    M = np.empty((N, T * T), dtype=float)
    for i in range(N):
        M[i] = center_fn(_pairwise_abs_distance(E[:, i])).ravel()
    G = (M @ M.T) / denom
    return 0.5 * (G + G.T)  # exact symmetry, floating-point hygiene only


def _v_to_correlation(dcov2: np.ndarray) -> np.ndarray:
    """V-statistic dCor²: always in [0,1] (Cauchy-Schwarz + non-negativity), diagonal → 1.

    A constant residual column has zero distance variance (all pairwise distances are 0); it is
    set to 0 off-diagonal and the diagonal is forced to exactly 1 — the same handling
    ``pipelines.factor.model.residual_similarity`` gives a constant column under Pearson.
    """
    diag = np.maximum(np.diag(dcov2), 0.0)  # non-negative by theorem; clip is float hygiene
    safe = np.outer(diag > 0, diag > 0)
    denom = np.sqrt(np.outer(diag, diag))
    with np.errstate(divide="ignore", invalid="ignore"):
        R = np.where(safe, dcov2 / denom, 0.0)
    R = np.nan_to_num(R, nan=0.0, posinf=0.0, neginf=0.0)
    R = 0.5 * (R + R.T)
    R = np.clip(R, 0.0, 1.0)
    np.fill_diagonal(R, 1.0)
    return R


def _u_to_correlation(dcov2_u: np.ndarray) -> np.ndarray:
    """U-statistic dCor² (Székely & Rizzo 2013): sign-preserving, can be negative.

    Diagnostic only — no clipping to [0,1], no forced unit diagonal. Bounding it would hide
    exactly the bias/sign behaviour D-5 exists to show.
    """
    diag = np.diag(dcov2_u)
    denom_sq = np.outer(diag, diag)
    safe = denom_sq > 0
    with np.errstate(divide="ignore", invalid="ignore"):
        R = np.where(safe, dcov2_u / np.sqrt(np.where(safe, denom_sq, 1.0)), 0.0)
    R = np.nan_to_num(R, nan=0.0, posinf=0.0, neginf=0.0)
    return 0.5 * (R + R.T)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def residual_dcor2(E: np.ndarray) -> np.ndarray:
    """P = dCor²(i,j), V-statistic — feeds greedy (D-5).

    Symmetric, unit diagonal, values in [0,1] — the same contract as
    ``pipelines.factor.model.residual_similarity``, so the two measures are drop-in
    interchangeable (docs/01 §7: "only §4 changes").
    """
    E = np.asarray(E, dtype=float)
    N = E.shape[1] if E.ndim == 2 else 0
    if N == 0:
        return np.zeros((0, 0), dtype=float)
    if N == 1:
        return np.ones((1, 1), dtype=float)
    dcov2 = _dcov2_matrix(E, _double_center, float(E.shape[0] ** 2))
    return _v_to_correlation(dcov2)


def residual_dcor2_u(E: np.ndarray) -> np.ndarray:
    """P_u = dCor²_U(i,j), U-statistic — bias diagnostic ONLY (D-5). Never fed to greedy.

    Can take negative values by construction — that is how it achieves unbiasedness under
    independence. Monotonicity and submodularity of the coverage objective hold for any real
    P (docs/01 §4, docs/02 §1); what a negative entry breaks is **normalisation** — F(∅)=0 can
    then exceed F of a small non-empty set — and normalisation is what the (1−1/e)
    approximation guarantee (Nemhauser–Wolsey–Fisher) actually requires. Feeding this to
    greedy would therefore void the guarantee, not the objective's shape.
    """
    E = np.asarray(E, dtype=float)
    N = E.shape[1] if E.ndim == 2 else 0
    if N == 0:
        return np.zeros((0, 0), dtype=float)
    if N == 1:
        return np.ones((1, 1), dtype=float)
    T = E.shape[0]
    if T <= 3:
        raise ValueError(f"T={T} too short for the U-statistic (needs T>3)")
    dcov2_u = _dcov2_matrix(E, _u_center, float(T * (T - 3)))
    return _u_to_correlation(dcov2_u)


# ---------------------------------------------------------------------------
# CLI smoke (synthetic, no I/O) — matmul-vs-naive, identities, the bias itself
# ---------------------------------------------------------------------------


def _naive_dcov2_pair(u: np.ndarray, v: np.ndarray) -> float:
    """dCov²(u,v), V-statistic, without batching — the reference this module checks against."""
    T = u.shape[0]
    Au = _double_center(_pairwise_abs_distance(u))
    Av = _double_center(_pairwise_abs_distance(v))
    return float(np.sum(Au * Av)) / (T * T)


def main() -> None:
    rng = np.random.default_rng(42)
    T, N = 40, 8
    E = rng.normal(size=(T, N))

    # 1. matmul route vs a naive double loop.
    batched = _dcov2_matrix(E, _double_center, float(T * T))
    naive = np.array([[_naive_dcov2_pair(E[:, i], E[:, j]) for j in range(N)]
                      for i in range(N)])
    max_err = float(np.max(np.abs(batched - naive)))
    print(f"matmul vs naive dCov^2 (N={N}, T={T}): max abs err = {max_err:.2e}")
    assert max_err < 1e-10, f"matmul route diverges from the naive reference: {max_err:.2e}"

    # 2. symmetry, unit diagonal, [0,1] — same contract as Pearson's residual_similarity.
    P = residual_dcor2(E)
    assert_similarity(P)
    print(f"P: shape={P.shape} symmetric+unit-diag+bounded OK  "
          f"mean_offdiag={P[~np.eye(N, dtype=bool)].mean():.4f}")

    # 3. a perfectly dependent pair (identical columns) has dCor^2 = 1.
    u = rng.normal(size=T)
    P_dep = residual_dcor2(np.column_stack([u, u]))
    print(f"dCor^2(u,u) = {P_dep[0, 1]:.6f}  (expected 1.0)")
    assert abs(P_dep[0, 1] - 1.0) < 1e-8, "identical columns should give dCor^2 = 1"

    # 4. the V/U bias made visible: on independent columns, V sits above U (D-5).
    Pv, Pu = residual_dcor2(E), residual_dcor2_u(E)
    mask = ~np.eye(N, dtype=bool)
    v_mean, u_mean = float(Pv[mask].mean()), float(Pu[mask].mean())
    print(f"independent columns: V-statistic mean={v_mean:.4f}  U-statistic mean={u_mean:.4f}  "
          f"(V should sit visibly above U)")
    assert v_mean > u_mean, "V-statistic's upward bias vs the U-statistic is not visible"

    print("dcor selftest: OK")


if __name__ == "__main__":
    main()
