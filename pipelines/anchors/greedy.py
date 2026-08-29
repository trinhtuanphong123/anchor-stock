"""pipelines.anchors.greedy — greedy anchor selection + assignment (spec §3).

Pure numpy, no I/O, deterministic. Given the similarity matrix P (N×N of ρ²),
choose k anchors that maximise coverage

    F(S) = Σ_i max_{j∈S} ρ²(i,j)                          (§3.1)

by the greedy algorithm, whose (1 − 1/e) guarantee follows from F being normalised,
monotone and submodular (§3.2). All three are needed, and only the first depends on P:
monotonicity and submodularity hold for any real matrix, while P ≥ 0 is what gives
F(∅) = 0 with F never negative. Then assign each ticker to its single best anchor and apply
the post-hoc acceptance threshold τ.

Reproducibility (§3.3)
----------------------
Candidates are visited in ascending index order with a strict ``>``, so the first
candidate achieving the maximum wins — ``np.argmax`` returns exactly that
smallest-index maximiser. Given the same P, k, τ the output is identical every
run; the algorithm touches no DB, clock, or environment (§3.7).

Nesting (§3.3)
--------------
Greedy is nested: one run to k yields the whole coverage curve for k = 1..k. F(S)
and the marginal gain are recorded after every round.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class GreedyResult:
    anchors: list[int]                 # selected indices, in selection order (len k)
    coverage: np.ndarray               # (N,) c[i] = max_{j∈S} P[i,j]
    marginal_gains: list[float]        # marginal gain per round
    coverage_curve: list[dict[str, Any]]  # per round: k, anchor, marginal_gain, F, Fbar


@dataclass
class Assignment:
    assignment: np.ndarray             # (N,) a(i) = anchor index explaining i best
    best_rho2: np.ndarray              # (N,) max_{j∈S} P[i,j]
    clusters: dict[int, list[int]]     # anchor -> member indices
    F_j: dict[int, float]              # per-anchor contribution Σ_{i∈C_j} ρ²(i,j)
    rho2_mean_j: dict[int, float]      # F_j / |C_j|


@dataclass
class AnchorSelection:
    anchors: list[int]
    assignment: Assignment
    coverage_curve: list[dict[str, Any]]
    F: float                           # F(S)
    Fbar: float                        # F(S) / N
    under_threshold: dict[float, list[int]]  # τ -> V_τ (indices with best ρ² < τ)


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


def coverage(P: np.ndarray, anchors: list[int]) -> float:
    """F(S) = Σ_i max_{j∈S} P[i,j]. F(∅) = 0 (§3.1)."""
    if not anchors:
        return 0.0
    return float(P[:, list(anchors)].max(axis=1).sum())


# ---------------------------------------------------------------------------
# Greedy (§3.3)
# ---------------------------------------------------------------------------


def greedy(P: np.ndarray, k: int) -> GreedyResult:
    """Greedy maximisation of F under |S| = k. O(kN²).

    Each round picks the candidate v maximising the marginal gain
    ``Σ_i max(0, P[i,v] − c[i])`` (ties → smallest index), records it, and updates
    the coverage vector ``c = max(c, P[:,v])``.
    """
    P = np.asarray(P, dtype=float)
    N = P.shape[0]
    k = max(0, min(int(k), N))

    c = np.zeros(N, dtype=float)
    selected = np.zeros(N, dtype=bool)
    anchors: list[int] = []
    marginal: list[float] = []
    curve: list[dict[str, Any]] = []

    for r in range(k):
        # gains[v] = Σ_i max(0, P[i,v] − c[i]); diff[i,v] = P[i,v] − c[i].
        gains = np.clip(P - c[:, None], 0.0, None).sum(axis=0)
        gains[selected] = -np.inf
        best_v = int(np.argmax(gains))        # smallest-index maximiser
        best_gain = float(gains[best_v])

        anchors.append(best_v)
        selected[best_v] = True
        marginal.append(best_gain)
        c = np.maximum(c, P[:, best_v])
        f_val = float(c.sum())
        curve.append({
            "k": r + 1, "anchor": best_v, "marginal_gain": best_gain,
            "F": f_val, "Fbar": (f_val / N if N else 0.0),
        })

    return GreedyResult(anchors=anchors, coverage=c, marginal_gains=marginal,
                        coverage_curve=curve)


# ---------------------------------------------------------------------------
# Assignment (§3.4) + threshold (§3.5)
# ---------------------------------------------------------------------------


def assign(P: np.ndarray, anchors: list[int]) -> Assignment:
    """Assign each ticker to its single best anchor; ties → smallest index (§3.4).

    Anchors are sorted ascending so ``np.argmax`` breaks ties toward the smallest
    ticker index. Because ρ²(j,j)=1 is maximal, a(j)=j for every anchor.
    """
    P = np.asarray(P, dtype=float)
    N = P.shape[0]
    S = sorted(int(a) for a in anchors)
    if not S:
        empty = np.full(N, -1, dtype=int)
        return Assignment(assignment=empty, best_rho2=np.zeros(N), clusters={},
                          F_j={}, rho2_mean_j={})

    cols = np.array(S, dtype=int)
    sub = P[:, cols]                              # (N, |S|)
    pos = np.argmax(sub, axis=1)                  # first max → smallest index in S
    a = cols[pos]                                 # (N,)
    best = sub[np.arange(N), pos]                 # (N,) = max_{j∈S} P[i,j]

    clusters: dict[int, list[int]] = {j: [] for j in S}
    for i in range(N):
        clusters[int(a[i])].append(i)
    f_j = {j: float(best[clusters[j]].sum()) if clusters[j] else 0.0 for j in S}
    rho2_mean = {j: (f_j[j] / len(clusters[j]) if clusters[j] else 0.0) for j in S}

    return Assignment(assignment=a, best_rho2=best, clusters=clusters,
                      F_j=f_j, rho2_mean_j=rho2_mean)


def under_threshold(best_rho2: np.ndarray, tau: float) -> list[int]:
    """V_τ = { i : max_{j∈S} ρ²(i,j) < τ } (§3.5). τ never changes S."""
    return [int(i) for i in np.where(np.asarray(best_rho2, dtype=float) < float(tau))[0]]


# ---------------------------------------------------------------------------
# Complete procedure (§3.7) — pure function of P, k, τ
# ---------------------------------------------------------------------------


def run_anchor_selection(
    P: np.ndarray, k: int, taus: tuple[float, ...] = ()
) -> AnchorSelection:
    """Greedy → assignment → thresholds. Steps 4–7 of §3.7; no DB/clock/env."""
    g = greedy(P, k)
    asn = assign(P, g.anchors)
    N = P.shape[0]
    f_val = float(asn.best_rho2.sum())
    thresholds = {float(t): under_threshold(asn.best_rho2, t) for t in taus}
    return AnchorSelection(
        anchors=g.anchors, assignment=asn, coverage_curve=g.coverage_curve,
        F=f_val, Fbar=(f_val / N if N else 0.0), under_threshold=thresholds,
    )


# ---------------------------------------------------------------------------
# Assertions (§3.4 identities) + exact solver (§3.6, small k only)
# ---------------------------------------------------------------------------


def assert_identities(P: np.ndarray, anchors: list[int], asn: Assignment) -> None:
    """a(j)=j for anchors; F(S)=Σ F_j; clusters partition V (§3.4)."""
    N = P.shape[0]
    for j in {int(a) for a in anchors}:
        assert int(asn.assignment[j]) == j, f"a({j}) != {j}"
    f_val = float(asn.best_rho2.sum())
    assert abs(f_val - sum(asn.F_j.values())) <= 1e-6 * max(1.0, f_val), "F(S) != Σ F_j"
    total = sum(len(m) for m in asn.clusters.values())
    assert total == N, f"clusters do not partition V ({total} != {N})"


def brute_force_best(P: np.ndarray, k: int) -> tuple[tuple[int, ...], float]:
    """Exact max-coverage over all size-k subsets (§3.6). Small N only — O(C(N,k))."""
    import itertools  # noqa: PLC0415

    N = P.shape[0]
    best_s: tuple[int, ...] = ()
    best_f = -1.0
    for combo in itertools.combinations(range(N), k):
        f_val = float(P[:, list(combo)].max(axis=1).sum())
        if f_val > best_f:
            best_f, best_s = f_val, combo
    return best_s, best_f


# ---------------------------------------------------------------------------
# CLI smoke (synthetic, no I/O) — block structure + greedy-vs-exact
# ---------------------------------------------------------------------------


def _mock_P(blocks: tuple[int, ...] = (4, 4, 4), within: float = 0.7,
            cross: float = 0.05) -> np.ndarray:
    """Block-structured ρ²: greedy should pick one anchor per block."""
    n = sum(blocks)
    P = np.full((n, n), cross, dtype=float)
    idx = 0
    for b in blocks:
        P[idx:idx + b, idx:idx + b] = within
        idx += b
    np.fill_diagonal(P, 1.0)
    return P


def main() -> None:
    P = _mock_P()
    n = P.shape[0]
    sel = run_anchor_selection(P, k=3, taus=(0.5, 0.6))
    assert_identities(P, sel.anchors, sel.assignment)

    fs = [round(row["F"], 3) for row in sel.coverage_curve]
    monotone = all(fs[i] <= fs[i + 1] + 1e-9 for i in range(len(fs) - 1))
    _, exact_f = brute_force_best(P, 3)

    print(f"N={n}  anchors(order)={sel.anchors}")
    print(f"coverage curve F: {fs}  monotone={monotone}")
    print(f"F(S)={sel.F:.3f}  Fbar={sel.Fbar:.3f}  exact_F={exact_f:.3f}  "
          f"ratio={sel.F / exact_f:.4f}")
    print(f"cluster sizes: {[len(m) for m in sel.assignment.clusters.values()]} (sum="
          f"{sum(len(m) for m in sel.assignment.clusters.values())})")
    print(f"V_tau: tau=0.5 -> {len(sel.under_threshold[0.5])} under, "
          f"tau=0.6 -> {len(sel.under_threshold[0.6])} under")
    print("assert_identities: OK")


if __name__ == "__main__":
    main()
