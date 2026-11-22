"""Statistics used in the pre-registered analysis plan (docs/preregistration.md).

Every function here is covered by *calibration* tests (tests/test_utils/test_stats.py): coverage of
the intervals and type-I error of the tests are checked by simulation, not just on examples.

Conventions: proportions are reported with Wilson intervals; differences of independent proportions
with Newcombe's hybrid score interval; paired outbreak-level comparisons with the Wilcoxon signed-rank
test using Pratt's treatment of zeros (ties at zero are common with small counts); utility
non-inferiority with a one-sided percentile-bootstrap bound on the mean paired difference; multiple
comparisons with Holm's step-down procedure within pre-declared families.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy import stats

Z95 = 1.959963984540054


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float

    def as_pct(self, digits: int = 1) -> str:
        return (
            f"{100 * self.estimate:.{digits}f}% [{100 * self.low:.{digits}f}, {100 * self.high:.{digits}f}]"
        )


def wilson(k: int, n: int, z: float = Z95) -> Interval:
    if n <= 0:
        return Interval(float("nan"), 0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return Interval(p, max(0.0, centre - half), min(1.0, centre + half))


def newcombe_diff(k1: int, n1: int, k2: int, n2: int, z: float = Z95) -> Interval:
    """CI for p1 - p2 (independent samples), Newcombe (1998) method 10."""
    a, b = wilson(k1, n1, z), wilson(k2, n2, z)
    p1, p2 = k1 / n1, k2 / n2
    d = p1 - p2
    low = d - math.sqrt((p1 - a.low) ** 2 + (b.high - p2) ** 2)
    high = d + math.sqrt((a.high - p1) ** 2 + (p2 - b.low) ** 2)
    return Interval(d, max(-1.0, low), min(1.0, high))


def fisher(k1: int, n1: int, k2: int, n2: int, alternative: str = "two-sided") -> float:
    table = [[k1, n1 - k1], [k2, n2 - k2]]
    return float(stats.fisher_exact(table, alternative=alternative).pvalue)


def holm(pvalues: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values (monotone, capped at 1)."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * pvalues[i])
        adj[i] = min(1.0, running)
    return adj


def wilcoxon_pratt(x: Sequence[float], y: Sequence[float], alternative: str = "two-sided") -> float:
    """Paired Wilcoxon signed-rank test on x - y with Pratt zero handling. Returns 1.0 if all diffs are 0."""
    d = np.asarray(x, float) - np.asarray(y, float)
    if np.allclose(d, 0):
        return 1.0
    return float(stats.wilcoxon(d, zero_method="pratt", alternative=alternative, method="auto").pvalue)


def paired_permutation(
    x: Sequence[float],
    y: Sequence[float],
    alternative: str = "two-sided",
    *,
    n_perm: int = 20_000,
    seed: int = 0,
) -> float:
    """Sign-flip permutation test on the paired differences d = x - y (statistic: sum of d).

    Under H0 (exchangeability of the two arms within a pair) every sign pattern of the non-zero
    differences is equally likely, so the test has exact size regardless of ties - unlike the normal
    approximation of the signed-rank test, which our calibration test showed to be slightly liberal
    (~6.6% at nominal 5%) for small integer counts. Exact enumeration up to 2^16 patterns, Monte Carlo
    (with the +1 correction) beyond.
    """
    d = np.asarray(x, float) - np.asarray(y, float)
    d = d[d != 0]
    if d.size == 0:
        return 1.0
    obs = d.sum()
    if d.size <= 16:
        signs = ((np.arange(2**d.size)[:, None] >> np.arange(d.size)) & 1) * 2 - 1
        null = (signs * np.abs(d)).sum(axis=1)
        total, extra = null.size, 0
    else:
        rng = np.random.default_rng(seed)
        null = (rng.choice([-1.0, 1.0], size=(n_perm, d.size)) * np.abs(d)).sum(axis=1)
        total, extra = n_perm + 1, 1
    eps = 1e-12
    if alternative == "less":
        hits = np.sum(null <= obs + eps)
    elif alternative == "greater":
        hits = np.sum(null >= obs - eps)
    else:
        hits = np.sum(np.abs(null) >= abs(obs) - eps)
    return float(min(1.0, (hits + extra) / total))


def bootstrap_mean_ci(
    diffs: Sequence[float],
    *,
    n_boot: int = 10_000,
    alpha: float = 0.05,
    one_sided: str | None = None,
    seed: int = 0,
) -> Interval:
    """Percentile bootstrap CI for the mean. ``one_sided='lower'`` returns (lower bound at 1-alpha, +inf)."""
    d = np.asarray(diffs, float)
    rng = np.random.default_rng(seed)
    means = rng.choice(d, size=(n_boot, d.size), replace=True).mean(axis=1)
    if one_sided == "lower":
        return Interval(float(d.mean()), float(np.quantile(means, alpha)), float("inf"))
    if one_sided == "upper":
        return Interval(float(d.mean()), float("-inf"), float(np.quantile(means, 1 - alpha)))
    return Interval(
        float(d.mean()), float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))
    )


@dataclass(frozen=True)
class NonInferiority:
    mean_diff: float
    lower_bound: float
    margin: float
    non_inferior: bool


def noninferiority(
    treatment: npt.ArrayLike,
    control: npt.ArrayLike,
    margin: float,
    *,
    alpha: float = 0.05,
    n_boot: int = 10_000,
    seed: int = 0,
) -> NonInferiority:
    """H0: mean(treatment - control) <= -margin. Reject (non-inferior) if the one-sided lower bound > -margin."""
    diffs = np.asarray(treatment, float) - np.asarray(control, float)
    ci = bootstrap_mean_ci(diffs, n_boot=n_boot, alpha=alpha, one_sided="lower", seed=seed)
    return NonInferiority(ci.estimate, ci.low, margin, ci.low > -margin)


def simulate_power(
    sampler: Callable[[np.random.Generator], tuple[Any, Any]],
    test: Callable[[Any, Any], float],
    *,
    n_sims: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> float:
    """Monte-Carlo power: fraction of simulated datasets on which ``test`` rejects at ``alpha``."""
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(n_sims):
        x, y = sampler(rng)
        hits += test(x, y) < alpha
    return hits / n_sims


def fisher_power(
    p1: float, p2: float, n1: int, n2: int, *, n_sims: int = 2000, alpha: float = 0.05, seed: int = 0
) -> float:
    rng = np.random.default_rng(seed)
    k1 = rng.binomial(n1, p1, n_sims)
    k2 = rng.binomial(n2, p2, n_sims)
    return float(np.mean([fisher(a, n1, b, n2) < alpha for a, b in zip(k1, k2, strict=True)]))


def auroc(scores: npt.ArrayLike, labels: npt.ArrayLike) -> float:
    """Mann-Whitney AUROC with ties counted as 1/2; nan if one class is absent."""
    s = np.asarray(scores, float)
    y = np.asarray(labels, int)
    pos, neg = s[y == 1], s[y == 0]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    ranks = stats.rankdata(np.concatenate([pos, neg]))
    return float((ranks[: pos.size].sum() - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size))


def auroc_ci(
    scores: npt.ArrayLike,
    labels: npt.ArrayLike,
    groups: Sequence[str] | None = None,
    *,
    n_boot: int = 2000,
    seed: int = 0,
) -> Interval:
    """AUROC with a (cluster) bootstrap CI; resampling whole groups when ``groups`` is given, because
    episodes sharing a note or scenario are not independent."""
    s = np.asarray(scores, float)
    y = np.asarray(labels, int)
    est = auroc(s, y)
    rng = np.random.default_rng(seed)
    g = np.asarray(groups if groups is not None else np.arange(len(s)))
    uniq = np.unique(g)
    idx_by = {u: np.flatnonzero(g == u) for u in uniq}
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(uniq, size=uniq.size, replace=True)
        idx = np.concatenate([idx_by[u] for u in pick])
        a = auroc(s[idx], y[idx])
        if not math.isnan(a):
            boots.append(a)
    if not boots:
        return Interval(est, float("nan"), float("nan"))
    return Interval(est, float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975)))


def auroc_diff_ci(
    scores_a: npt.ArrayLike,
    scores_b: npt.ArrayLike,
    labels: npt.ArrayLike,
    groups: Sequence[str] | None = None,
    *,
    n_boot: int = 2000,
    seed: int = 0,
) -> Interval:
    """Paired (cluster) bootstrap CI for AUROC(a) - AUROC(b) on the same items."""
    a, b, y = np.asarray(scores_a, float), np.asarray(scores_b, float), np.asarray(labels, int)
    est = auroc(a, y) - auroc(b, y)
    g = np.asarray(groups if groups is not None else np.arange(len(y)))
    uniq = np.unique(g)
    idx_by = {u: np.flatnonzero(g == u) for u in uniq}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = np.concatenate([idx_by[u] for u in rng.choice(uniq, size=uniq.size, replace=True)])
        d = auroc(a[idx], y[idx]) - auroc(b[idx], y[idx])
        if not math.isnan(d):
            boots.append(d)
    if not boots:
        return Interval(est, float("nan"), float("nan"))
    return Interval(est, float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975)))
