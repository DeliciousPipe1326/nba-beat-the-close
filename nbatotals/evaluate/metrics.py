"""Statistics for the harness: Wilson intervals, bootstrap, OLS, CLV."""

from __future__ import annotations

from statistics import NormalDist

import numpy as np

Z95 = 1.959963984540054
TOTAL_SD = 18.0  # SD of total error vs the close, from the earlier variance study; used only for CLV in cents
SEED = 20261020
N_BOOT = 10_000
_N = NormalDist()


def wilson(wins: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def bootstrap_mean_ci(x, n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    chunk = 500
    for start in range(0, n_boot, chunk):
        stop = min(n_boot, start + chunk)
        idx = rng.integers(0, len(x), size=(stop - start, len(x)))
        means[start:stop] = x[idx].mean(axis=1)
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)))


def ols(y, X: dict) -> dict:
    """OLS of y on an intercept plus the named columns; classic standard errors."""
    names = ["const"] + list(X)
    A = np.column_stack([np.ones(len(y))] + [np.asarray(v, dtype=float) for v in X.values()])
    y = np.asarray(y, dtype=float)
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ beta
    dof = len(y) - A.shape[1]
    sigma2 = resid @ resid / dof
    cov = sigma2 * np.linalg.inv(A.T @ A)
    se = np.sqrt(np.diag(cov))
    return {n: {"coef": float(b), "lo": float(b - Z95 * s), "hi": float(b + Z95 * s), "se": float(s)}
            for n, b, s in zip(names, beta, se)} | {"n": len(y), "rmse": float(np.sqrt(resid @ resid / len(y)))}


def corr_ci(x, y) -> tuple[float, float, float, int]:
    x, y = np.asarray(x, float), np.asarray(y, float)
    n = len(x)
    r = float(np.corrcoef(x, y)[0, 1])
    z = np.arctanh(r)
    se = 1 / np.sqrt(n - 3)
    return r, float(np.tanh(z - Z95 * se)), float(np.tanh(z + Z95 * se)), n


def prob_over_at(line_at: np.ndarray, close_line: np.ndarray, close_p_over: np.ndarray, sd: float = TOTAL_SD):
    """P(total > line_at) under the close: normal with SD `sd`, centred so that
    P(total > close_line) equals the close's devigged p_over."""
    inv = np.vectorize(lambda p: _N.inv_cdf(min(max(p, 1e-9), 1 - 1e-9)))
    mu = close_line + sd * inv(close_p_over)
    cdf = np.vectorize(_N.cdf)
    return 1.0 - cdf((line_at - mu) / sd)
