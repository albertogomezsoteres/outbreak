"""Act 2: can the agent's hidden state at the decision point predict whether it will take the shortcut?

Label. Activations at the end of a fixed prefix are deterministic, so the only thing they can encode
is the *propensity* of the model to violate from that state. We therefore estimate, for every unique
prefix (scenario x board content), the empirical violation rate over ``n`` sampled continuations and
fit a binomial logistic probe (each prefix enters with weights k and n-k). Evaluation is at the
episode level (AUROC) and the prefix level (Spearman with the empirical rate).

Controls (each answers "is the probe just reading something trivial?"):

* ``shuffled``      labels permuted within the training set - must be ~0.5 AUROC;
* ``note_identity`` predict a test prefix with its note's training-set mean rate - the probe must
                    beat knowing *which note* was read;
* ``within_note``   rank correlation of probe score and rate *among prefixes sharing a note*
                    (scenario-driven variation the note identity cannot explain);
* ``text_filter``   the text-only filter on the same prefixes (black-box comparison, computed in the
                    analysis pipeline).

Splits are scenario-level (``outbreak.data.splits``): no scenario draw is in both train and test.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats as sstats

from outbreak.utils.stats import Interval, auroc, auroc_ci


@dataclass
class PrefixSet:
    """One row per unique decision-point prefix."""

    X: np.ndarray  # [n_prefix, d]
    k: np.ndarray  # violations among sampled continuations
    n: np.ndarray  # sampled continuations
    note_id: list[str]
    group: list[str]  # scenario key used for cluster bootstrap
    split: list[str]
    text: list[str] | None = None  # what the agent read on the board (for the text-only baseline)

    def subset(self, mask: np.ndarray) -> PrefixSet:
        idx = np.flatnonzero(mask)
        return PrefixSet(
            self.X[idx],
            self.k[idx],
            self.n[idx],
            [self.note_id[i] for i in idx],
            [self.group[i] for i in idx],
            [self.split[i] for i in idx],
            [self.text[i] for i in idx] if self.text is not None else None,
        )

    def with_X(self, X: np.ndarray) -> PrefixSet:
        return PrefixSet(X, self.k, self.n, self.note_id, self.group, self.split, self.text)

    @property
    def rate(self) -> np.ndarray:
        return self.k / np.maximum(self.n, 1)


def _expand(ps: PrefixSet) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Binomial rows -> weighted Bernoulli rows (same likelihood)."""
    X = np.concatenate([ps.X, ps.X])
    y = np.concatenate([np.ones(len(ps.k)), np.zeros(len(ps.k))])
    w = np.concatenate([ps.k, ps.n - ps.k]).astype(float)
    keep = w > 0
    return X[keep], y[keep], w[keep]


def fit_probe(train: PrefixSet, C: float = 0.1, seed: int = 0) -> Any:
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    X, y, w = _expand(train)
    if len(set(y.tolist())) < 2:
        raise ValueError("training prefixes contain only one outcome class")
    pipe = make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=5000, random_state=seed))
    pipe.fit(X, y, logisticregression__sample_weight=w)
    return pipe


def episode_level(scores: np.ndarray, ps: PrefixSet) -> tuple[np.ndarray, np.ndarray, list[str]]:
    s, y, g = [], [], []
    for i in range(len(ps.k)):
        k, n = int(ps.k[i]), int(ps.n[i])
        s += [scores[i]] * n
        y += [1] * k + [0] * (n - k)
        g += [ps.note_id[i]] * n
    return np.asarray(s), np.asarray(y), g


@dataclass
class ProbeReport:
    layer: int
    auroc: Interval
    spearman: float
    shuffled_auroc: float
    note_identity_auroc: float
    within_note_spearman: float
    n_test_prefixes: int
    n_test_episodes: int
    text_filter_auroc: float = float("nan")
    noise_ceiling_auroc: float = float("nan")
    extra: dict[str, Any] = field(default_factory=dict)


def note_identity_scores(train: PrefixSet, test: PrefixSet) -> np.ndarray:
    tot: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for nid, k, n in zip(train.note_id, train.k, train.n, strict=True):
        tot[nid][0] += k
        tot[nid][1] += n
    glob = train.k.sum() / max(train.n.sum(), 1)
    return np.asarray([tot[n][0] / tot[n][1] if n in tot and tot[n][1] else glob for n in test.note_id])


def within_note_spearman(scores: np.ndarray, ps: PrefixSet) -> float:
    """Mean Spearman rho of score vs rate within note groups that have >=3 prefixes and rate variance."""
    by: dict[str, list[int]] = defaultdict(list)
    for i, n in enumerate(ps.note_id):
        by[n].append(i)
    rhos, weights = [], []
    for idx in by.values():
        r = ps.rate[idx]
        if len(idx) >= 3 and np.ptp(r) > 0 and np.ptp(scores[idx]) > 0:
            rho = sstats.spearmanr(scores[idx], r).statistic
            if np.isfinite(rho):
                rhos.append(rho)
                weights.append(len(idx))
    return float(np.average(rhos, weights=weights)) if rhos else float("nan")


def evaluate_probe(
    train: PrefixSet, test: PrefixSet, layer: int, *, C: float = 0.1, seed: int = 0, n_boot: int = 2000
) -> ProbeReport:
    probe = fit_probe(train, C, seed)
    scores = probe.predict_proba(test.X)[:, 1]
    s_ep, y_ep, g_ep = episode_level(scores, test)
    ci = auroc_ci(s_ep, y_ep, g_ep, n_boot=n_boot, seed=seed)

    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(train.k))
    shuffled = PrefixSet(train.X, train.k[perm], train.n[perm], train.note_id, train.group, train.split)
    txt = (
        text_baseline_auroc(train, test, seed)
        if train.text is not None and test.text is not None
        else float("nan")
    )
    ceiling = noise_ceiling(test.k, test.n, seed=seed)
    try:
        sh_scores = fit_probe(shuffled, C, seed).predict_proba(test.X)[:, 1]
        sh = auroc(*episode_level(sh_scores, test)[:2])
    except ValueError:
        sh = float("nan")
    ni = auroc(*episode_level(note_identity_scores(train, test), test)[:2])
    rho = sstats.spearmanr(scores, test.rate).statistic if np.ptp(test.rate) > 0 else float("nan")
    return ProbeReport(
        layer,
        ci,
        float(rho),
        sh,
        ni,
        within_note_spearman(scores, test),
        len(test.k),
        int(test.n.sum()),
        txt,
        ceiling,
        {"C": C},
    )


def layer_sweep(
    acts: dict[int, np.ndarray], base: PrefixSet, train_mask: np.ndarray, test_mask: np.ndarray, **kw: Any
) -> list[ProbeReport]:
    reports = []
    for layer, X in sorted(acts.items()):
        ps = base.with_X(X)
        reports.append(evaluate_probe(ps.subset(train_mask), ps.subset(test_mask), layer, **kw))
    return reports


def text_baseline_auroc(train: PrefixSet, test: PrefixSet, seed: int = 0) -> float:
    """Black-box comparison on the *same* prefixes: a TF-IDF + logistic filter trained on what the
    agent read (board text), with binomial weights. If the probe does not beat this, the hidden state
    adds nothing a text filter on the board could not see."""
    from outbreak.models.text_filter import TextFilter

    assert train.text is not None and test.text is not None
    texts, labels = [], []
    for t, k, n in zip(train.text, train.k, train.n, strict=True):
        texts += [t or "(empty board)"] * int(n)
        labels += [1] * int(k) + [0] * int(n - k)
    if len(set(labels)) < 2:
        return float("nan")
    flt = TextFilter.fit(texts, labels, seed=seed)
    scores = flt.raw_scores([t or "(empty board)" for t in test.text])
    return auroc(*episode_level(scores, test)[:2])


def noise_ceiling(k: np.ndarray, n: np.ndarray, *, n_sims: int = 200, seed: int = 0) -> float:
    """Best episode-level AUROC any predictor could reach on these prefixes.

    Each prefix has a true propensity p_i; episodes are Bernoulli(p_i) draws, so even a perfect
    predictor (score = p_i) has AUROC < 1. We place a Beta prior on p (method of moments on k/n),
    draw p_i from each posterior Beta(a + k_i, b + n_i - k_i), simulate n_i outcomes and score them
    with p_i; the mean AUROC over simulations is the ceiling against which probe results are read.
    """
    k, n = np.asarray(k, float), np.asarray(n, float)
    rate = k / np.maximum(n, 1)
    m, v = float(rate.mean()), float(rate.var())
    if m <= 0 or m >= 1:
        return float("nan")
    common = m * (1 - m) / v - 1 if v > 0 else 1e3
    a, b = max(m * common, 1e-3), max((1 - m) * common, 1e-3)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_sims):
        p = rng.beta(a + k, b + n - k)
        s, y = [], []
        for pi, ni in zip(p, n.astype(int), strict=True):
            out = rng.random(ni) < pi
            s += [pi] * ni
            y += out.astype(int).tolist()
        val = auroc(s, y)
        if not np.isnan(val):
            vals.append(val)
    return float(np.mean(vals)) if vals else float("nan")


def group_prefixes(rows: Sequence[dict[str, Any]], key: str = "prefix_hash") -> list[dict[str, Any]]:
    """Aggregate episode rows (with ``prefix_hash``, ``violation``) into unique prefixes with k/n."""
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        a = agg.setdefault(r[key], {**r, "k": 0, "n": 0})
        a["k"] += int(r["violation"])
        a["n"] += 1
    return list(agg.values())
