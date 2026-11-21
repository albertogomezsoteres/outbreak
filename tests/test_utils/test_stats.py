"""Calibration tests: intervals cover at their nominal rate and tests hold their size, by simulation."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score
from statsmodels.stats.multitest import multipletests

from outbreak.utils import stats


@pytest.mark.parametrize(("p", "n"), [(0.02, 80), (0.1, 60), (0.3, 30), (0.5, 20)])
def test_wilson_coverage(p, n):
    rng = np.random.default_rng(0)
    ks = rng.binomial(n, p, 4000)
    cover = np.mean([(lambda ci: ci.low <= p <= ci.high)(stats.wilson(int(k), n)) for k in ks])
    assert cover > 0.92  # Wilson is close to nominal even for small n and extreme p


@pytest.mark.parametrize(("p1", "p2", "n"), [(0.15, 0.02, 60), (0.3, 0.3, 40), (0.05, 0.0, 80)])
def test_newcombe_coverage(p1, p2, n):
    rng = np.random.default_rng(1)
    k1, k2 = rng.binomial(n, p1, 3000), rng.binomial(n, p2, 3000)
    cover = np.mean(
        [
            (lambda ci: ci.low <= p1 - p2 <= ci.high)(stats.newcombe_diff(int(a), n, int(b), n))
            for a, b in zip(k1, k2, strict=True)
        ]
    )
    assert cover > 0.93


def test_fisher_size_under_null():
    rng = np.random.default_rng(2)
    p = [stats.fisher(int(rng.binomial(50, 0.1)), 50, int(rng.binomial(50, 0.1)), 50) for _ in range(2000)]
    assert np.mean(np.asarray(p) < 0.05) <= 0.05 + 0.01  # Fisher is conservative


def test_holm_matches_statsmodels():
    rng = np.random.default_rng(3)
    for _ in range(50):
        p = rng.uniform(0, 0.2, rng.integers(1, 12)).tolist()
        assert np.allclose(stats.holm(p), multipletests(p, method="holm")[1])


def _null_outbreak_counts(rng):
    return (rng.random((20, 9)) < 0.3).sum(1), (rng.random((20, 9)) < 0.3).sum(1)


def test_wilcoxon_pratt_is_slightly_liberal_with_ties():
    """Documents *why* the primary H4 test is the permutation test (see docs/DEVIATIONS.md):
    with 20 outbreaks of small integer counts the normal-approximation signed-rank test rejects a
    true null more often than 5%."""
    rng = np.random.default_rng(4)
    rej = np.mean([stats.wilcoxon_pratt(*_null_outbreak_counts(rng)) < 0.05 for _ in range(1500)])
    assert 0.04 < rej < 0.09
    assert stats.wilcoxon_pratt([1, 2, 3], [1, 2, 3]) == 1.0


def test_paired_permutation_has_exact_size():
    rng = np.random.default_rng(4)
    rej = np.mean(
        [
            stats.paired_permutation(*_null_outbreak_counts(rng), n_perm=2000, seed=i) < 0.05
            for i in range(1500)
        ]
    )
    assert rej <= 0.05 + 2.5 * np.sqrt(0.05 * 0.95 / 1500)


def test_paired_permutation_exact_small_case_and_direction():
    # d = (1, 2, 3): 8 sign patterns; only (+,+,+) has sum >= 6 -> p = 1/8.
    assert stats.paired_permutation([1, 2, 3], [0, 0, 0], "greater") == pytest.approx(1 / 8)
    assert stats.paired_permutation([0, 0, 0], [1, 2, 3], "less") == pytest.approx(1 / 8)
    assert stats.paired_permutation([1, 1], [1, 1]) == 1.0
    big_effect = stats.paired_permutation(np.zeros(20), np.full(20, 3.0), "less")
    assert big_effect < 1e-3


def test_noninferiority_size_at_margin():
    """At the boundary (true diff = -margin) the procedure rejects at most ~alpha."""
    rng = np.random.default_rng(5)
    margin, rej = 0.1, []
    for i in range(400):
        c = rng.binomial(1, 0.7, 40).astype(float)
        t = rng.binomial(1, 0.6, 40).astype(float)
        rej.append(stats.noninferiority(t, c, margin, n_boot=1000, seed=i).non_inferior)
    assert np.mean(rej) <= 0.09


def test_noninferiority_power_when_equal():
    rng = np.random.default_rng(6)
    c = rng.binomial(1, 0.7, 300).astype(float)
    assert stats.noninferiority(c.copy(), c, 0.05, n_boot=2000).non_inferior


def test_auroc_matches_sklearn_and_ci_brackets():
    rng = np.random.default_rng(7)
    y = rng.integers(0, 2, 300)
    s = y + rng.normal(0, 1.2, 300)
    assert stats.auroc(s, y) == pytest.approx(roc_auc_score(y, s))
    ci = stats.auroc_ci(s, y, groups=[str(i // 5) for i in range(300)], n_boot=500)
    assert ci.low < ci.estimate < ci.high
    assert np.isnan(stats.auroc([0.1, 0.2], [1, 1]))


def test_fisher_power_increases_with_n():
    a = stats.fisher_power(0.175, 0.01, 30, 30, n_sims=500)
    b = stats.fisher_power(0.175, 0.01, 100, 100, n_sims=500)
    assert b > a and b > 0.8
