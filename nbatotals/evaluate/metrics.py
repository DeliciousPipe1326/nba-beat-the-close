"""Statistics for the harness: Wilson intervals, bootstrap, OLS, CLV."""

from __future__ import annotations

from statistics import NormalDist

import numpy as np

Z95 = 1.959963984540054
TOTAL_SD = 18.0  # pre-registered SD of total error around the close (measured here: RMSE 17.8); only for CLV in cents
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


def bootstrap_cluster_mean_ci(x, groups, n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float, float]:
    """Bootstrap the mean of x resampling whole groups (e.g. games) with replacement.

    Returns (lo, hi, se) of the 95% percentile interval and the bootstrap SE.
    """
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return (np.nan, np.nan, np.nan)
    _, codes = np.unique(np.asarray(groups), return_inverse=True)
    sums = np.bincount(codes, weights=x)
    cnts = np.bincount(codes).astype(float)
    g = len(sums)
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    chunk = max(1, min(500, 5_000_000 // g))
    for start in range(0, n_boot, chunk):
        stop = min(n_boot, start + chunk)
        idx = rng.integers(0, g, size=(stop - start, g))
        means[start:stop] = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    return (float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)), float(means.std(ddof=1)))


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


# --------------------------------------------------------------------------- probabilities (Experiment 5)

MARGIN_SD = 12.0  # pre-registered SD of margin error around the close (Experiment 5); only for spread CLV in cents
EPS = 1e-12


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def brier(p, y) -> np.ndarray:
    """Per-game Brier score (p − y)²."""
    return (np.asarray(p, float) - np.asarray(y, float)) ** 2


def log_loss(p, y) -> np.ndarray:
    """Per-game log loss −[y·ln p + (1 − y)·ln(1 − p)]."""
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def fit_logistic_scale(margin, y, lo: float = 1.0, hi: float = 60.0) -> float:
    """Scale s maximising the likelihood of y under p = 1 / (1 + exp(−margin / s)), searched on [lo, hi]
    (golden section; the log likelihood is unimodal in 1/s)."""
    margin, y = np.asarray(margin, float), np.asarray(y, float)
    nll = lambda s: log_loss(1 / (1 + np.exp(-margin / s)), y).sum()
    g = (np.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = nll(c), nll(d)
    for _ in range(200):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = nll(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = nll(d)
        if b - a < 1e-9:
            break
    return float((a + b) / 2)


def logistic_regression(y, X: dict, max_iter: int = 100) -> dict:
    """Maximum-likelihood logistic regression of y on an intercept plus the named columns
    (Newton–Raphson); Wald 95% intervals from the observed information."""
    names = ["const"] + list(X)
    A = np.column_stack([np.ones(len(y))] + [np.asarray(v, dtype=float) for v in X.values()])
    y = np.asarray(y, dtype=float)
    beta = np.zeros(A.shape[1])
    for _ in range(max_iter):
        p = 1 / (1 + np.exp(-(A @ beta)))
        W = p * (1 - p)
        H = A.T @ (A * W[:, None])
        step = np.linalg.solve(H, A.T @ (y - p))
        beta = beta + step
        if np.max(np.abs(step)) < 1e-10:
            break
    p = 1 / (1 + np.exp(-(A @ beta)))
    cov = np.linalg.inv(A.T @ (A * (p * (1 - p))[:, None]))
    se = np.sqrt(np.diag(cov))
    return {n: {"coef": float(b), "lo": float(b - Z95 * s), "hi": float(b + Z95 * s), "se": float(s)}
            for n, b, s in zip(names, beta, se)} | {"n": len(y), "log_loss": float(log_loss(p, y).mean())}
