"""pipelines.factor.model — one-factor OLS + residual similarity (spec §2).

Pure numpy, no I/O. Given the aligned return matrix X (T×N) and the observed
market factor f (T), fit a one-factor model **per ticker** by OLS and turn the
residuals into the similarity matrix the anchor algorithm consumes.

    x_{i,t} = α_i + β_i · f_t + e_{i,t}        (§2.2, observed factor, with intercept)

    β̂_i = Cov(x_i, f) / Var(f)
    α̂_i = x̄_i − β̂_i · f̄
    ê_i  = x_i − α̂_i − β̂_i · f

    ρ²(i,j) = corr(ê_i, ê_j)²                  P = corr(E) ∘ corr(E)   (§2.4)

The factor is the *observed* index series, not a principal component of X, so the
residual definition is independent of the universe composition. The intercept is
kept because it changes the **fit**, not because it changes ρ². Dropping α forces
β̂ = (f·x)/(f·f) instead of the demeaned covariance form above, which is a
different β̂ and therefore a different E — that is the real reason to keep it.
The α term inside the residual expression itself has no effect on ρ² by contrast:
Pearson correlation demeans each column before comparing them, so adding any
constant to a series (α is constant over t) cannot move its correlation with
another series. Keeping α is still the right call; the reason is upstream of ρ²,
not inside it.

Properties asserted (not assumed): each residual column has ~zero mean (an OLS
identity — a non-zero mean means the intercept was dropped); P is symmetric, has
unit diagonal, and lies in [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FactorFit:
    """Per-ticker OLS fit over the aligned window."""

    alpha: np.ndarray       # (N,) intercepts
    beta: np.ndarray        # (N,) factor loadings
    sigma: np.ndarray       # (N,) residual sd, T−2 dof (docs/04 §2 σ̂_i)
    r2: np.ndarray          # (N,) regression R² in [0, 1]
    residuals: np.ndarray   # (T, N) residual matrix E, column i = ê_i


def fit_factor_model(X: np.ndarray, f: np.ndarray) -> FactorFit:
    """Fit x_i = α_i + β_i·f + e_i by OLS for every column of X (closed form).

    ``X`` is (T, N) log returns, ``f`` is (T,) the index log returns. A degenerate
    factor (zero variance) yields β=0, α=x̄, residuals = demeaned X, R²=0 rather
    than dividing by zero.

    Raises ``ValueError`` if T < 3: two parameters (α, β) are fit per ticker, so σ̂'s
    denominator T−2 needs at least one degree of freedom left to be positive.
    """
    X = np.asarray(X, dtype=float)
    f = np.asarray(f, dtype=float)
    if X.ndim != 2:
        raise ValueError("X must be 2-D (T×N)")
    T, N = X.shape
    if f.shape != (T,):
        raise ValueError(f"f shape {f.shape} != ({T},)")
    if T < 3:
        raise ValueError(f"T={T} too short — sigma_hat needs T-2 > 0 degrees of freedom")

    fbar = float(f.mean()) if T else 0.0
    fc = f - fbar
    denom = float(fc @ fc)                       # Σ (f_t − f̄)²

    xbar = X.mean(axis=0)                         # (N,)
    Xc = X - xbar                                 # (T, N)
    if denom > 0:
        beta = (fc @ Xc) / denom                 # (N,) = Cov(x_i,f)/Var(f)
    else:
        beta = np.zeros(N, dtype=float)
    alpha = xbar - beta * fbar                    # (N,)

    E = X - alpha[None, :] - np.outer(f, beta)    # (T, N) residuals

    ss_res = np.sum(E * E, axis=0)
    ss_tot = np.sum(Xc * Xc, axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        r2 = np.where(ss_tot > 0, 1.0 - ss_res / ss_tot, 0.0)
    r2 = np.clip(np.nan_to_num(r2, nan=0.0), 0.0, 1.0)

    sigma = np.sqrt(ss_res / (T - 2))              # (N,) — two fitted params per ticker

    return FactorFit(alpha=alpha, beta=beta, sigma=sigma, r2=r2, residuals=E)


def residual_similarity(E: np.ndarray) -> np.ndarray:
    """P = corr(E) ∘ corr(E) — squared Pearson correlation of residual columns.

    Symmetric, unit diagonal, values in [0, 1]. A constant (zero-variance) residual
    column has undefined correlation; it is set to 0 off-diagonal and the diagonal
    is forced to exactly 1.
    """
    E = np.asarray(E, dtype=float)
    N = E.shape[1]
    if N == 0:
        return np.zeros((0, 0), dtype=float)
    if N == 1:
        return np.ones((1, 1), dtype=float)

    R = np.corrcoef(E, rowvar=False)              # (N, N)
    R = np.nan_to_num(R, nan=0.0, posinf=0.0, neginf=0.0)
    P = R * R
    P = 0.5 * (P + P.T)                            # enforce exact symmetry
    P = np.clip(P, 0.0, 1.0)
    np.fill_diagonal(P, 1.0)
    return P


# ---------------------------------------------------------------------------
# Assertions (spec §2.3 / §2.4) — usable as quality checks
# ---------------------------------------------------------------------------


def assert_residual_mean_zero(E: np.ndarray, tol: float = 1e-8) -> None:
    """Each residual column has ~zero sample mean (OLS-with-intercept identity)."""
    if E.size == 0:
        return
    max_abs_mean = float(np.max(np.abs(E.mean(axis=0))))
    scale = float(np.max(np.abs(E))) or 1.0
    assert max_abs_mean <= tol * scale + tol, (
        f"residual mean {max_abs_mean:.2e} not ~0 — intercept dropped?"
    )


def assert_similarity(P: np.ndarray, tol: float = 1e-8) -> None:
    """P is symmetric, unit-diagonal, and bounded to [0, 1] (spec §2.4)."""
    N = P.shape[0]
    assert P.shape == (N, N), f"P not square: {P.shape}"
    if N == 0:
        return
    assert np.allclose(P, P.T, atol=1e-8), "P is not symmetric"
    assert np.all(np.abs(np.diag(P) - 1.0) <= 1e-6), "diag(P) != 1"
    assert np.all(P >= -tol) and np.all(P <= 1.0 + tol), "P outside [0, 1]"


def assert_sigma_positive(sigma: np.ndarray) -> None:
    """σ̂_i > 0 for every ticker (schema: ``model_ticker_params.sigma_hat CHECK (> 0)``).

    A zero here means a perfectly constant residual column — legitimate in synthetic data,
    a red flag in real data (a stalled or duplicated price series). This function only
    asserts; deciding what to do about a zero belongs to the artifact-writing step (P4),
    which is where the schema constraint actually bites.
    """
    if sigma.size == 0:
        return
    assert np.all(np.isfinite(sigma)), "sigma_hat contains non-finite values"
    assert np.all(sigma > 0), f"sigma_hat <= 0 for {int(np.sum(sigma <= 0))} ticker(s)"


# ---------------------------------------------------------------------------
# CLI smoke (synthetic, no I/O) — validates the identities
# ---------------------------------------------------------------------------


def _mock_fit(T: int = 250, N: int = 6, seed: int = 42):
    """Synthetic X where each column loads on f plus idiosyncratic noise."""
    rng = np.random.RandomState(seed)
    f = rng.normal(0.0, 0.01, size=T)
    betas = np.linspace(0.5, 1.5, N)
    E_true = rng.normal(0.0, 0.008, size=(T, N))
    X = betas[None, :] * f[:, None] + E_true      # α_true = 0
    return X, f, betas


_MOCK_SIGMA_TRUE: float = 0.008


def main() -> None:
    X, f, betas = _mock_fit()
    fit = fit_factor_model(X, f)
    P = residual_similarity(fit.residuals)
    assert_residual_mean_zero(fit.residuals)
    assert_similarity(P)
    assert_sigma_positive(fit.sigma)
    beta_err = float(np.max(np.abs(fit.beta - betas)))
    sigma_err = float(np.max(np.abs(fit.sigma - _MOCK_SIGMA_TRUE)))
    print(f"TxN = {X.shape}")
    print(f"beta recovered (max |beta_hat - beta_true|): {beta_err:.4f}")
    print(f"sigma recovered (max |sigma_hat - {_MOCK_SIGMA_TRUE}|): {sigma_err:.4f}  "
          f"range=[{fit.sigma.min():.4f}, {fit.sigma.max():.4f}]")
    print(f"R2 range: [{fit.r2.min():.3f}, {fit.r2.max():.3f}]")
    print(f"P: shape={P.shape} symmetric+unit-diag+bounded OK  "
          f"mean_offdiag={P[~np.eye(P.shape[0], dtype=bool)].mean():.4f}")

    try:
        fit_factor_model(X[:2], f[:2])
    except ValueError:
        pass
    else:
        raise AssertionError("fit_factor_model should reject T<3 (sigma_hat needs T-2>0)")

    print("assert_residual_mean_zero + assert_similarity + assert_sigma_positive: OK")
    print("T<3 rejection: OK")


if __name__ == "__main__":
    main()
