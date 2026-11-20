"""Trained channel filter: predicts from a post's *text* whether reading it leads agents to violate.

Labels come from consequences, not from opinions: a post is labelled by the observed violation of the
episodes in which an agent read it (``label = mean violation >= 0.5`` or, for a single exposure, the
outcome itself). That makes the filter learn "what actually spreads", which can differ from what an
LLM judge thinks is suspicious - the comparison is one of the project's questions.

Model: TF-IDF (word 1-2 grams + char 3-5 grams) + L2 logistic regression, probability calibration on
a held-out validation split, and a threshold chosen on validation for a target false-positive rate
on benign posts. Evaluation must use the frozen scenario splits (``outbreak.data.splits``) and the
leakage report below, because generated notes share sentences across cells.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from outbreak.env.board import ChannelVerdict


def _pipeline(C: float = 1.0, seed: int = 0) -> Any:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline

    feats = FeatureUnion(
        [
            ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True, lowercase=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)),
        ]
    )
    return Pipeline(
        [
            ("features", feats),
            ("clf", LogisticRegression(C=C, max_iter=2000, class_weight="balanced", random_state=seed)),
        ]
    )


@dataclass
class TextFilter:
    model: Any
    calibrator: Any | None = None
    threshold: float = 0.5
    version: str = "filter-v1"

    @classmethod
    def fit(cls, texts: Sequence[str], labels: Sequence[int], *, C: float = 1.0, seed: int = 0) -> TextFilter:
        y = np.asarray(labels, int)
        if len(set(y.tolist())) < 2:
            raise ValueError("need both classes to train the filter")
        m = _pipeline(C, seed)
        m.fit(list(texts), y)
        return cls(m)

    def raw_scores(self, texts: Sequence[str]) -> np.ndarray:
        return np.asarray(self.model.predict_proba(list(texts))[:, 1])

    def calibrate(self, texts: Sequence[str], labels: Sequence[int]) -> TextFilter:
        """Isotonic calibration on a validation split (falls back to identity if too few positives)."""
        from sklearn.isotonic import IsotonicRegression

        y = np.asarray(labels, int)
        if y.sum() < 5 or (1 - y).sum() < 5:
            return self
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(self.raw_scores(texts), y)
        self.calibrator = iso
        return self

    def scores(self, texts: Sequence[str]) -> np.ndarray:
        s = self.raw_scores(texts)
        return np.asarray(self.calibrator.predict(s)) if self.calibrator is not None else s

    def set_threshold_for_fpr(self, benign_texts: Sequence[str], target_fpr: float = 0.05) -> float:
        s = self.scores(benign_texts)
        self.threshold = float(np.quantile(s, 1 - target_fpr)) + 1e-9 if len(s) else 0.5
        return self.threshold

    def __call__(self, text: str) -> ChannelVerdict:
        score = float(self.scores([text])[0])
        return ChannelVerdict(
            allow=score < self.threshold, score=score, reason=f"{self.version} p={score:.3f}"
        )

    def top_features(self, k: int = 20) -> list[tuple[str, float]]:
        """Most positive (violation-predicting) n-grams: an interpretable view of what spreads."""
        feats = self.model.named_steps["features"]
        names = np.concatenate(
            [
                [f"w:{n}" for n in feats.transformer_list[0][1].get_feature_names_out()],
                [f"c:{n}" for n in feats.transformer_list[1][1].get_feature_names_out()],
            ]
        )
        coef = self.model.named_steps["clf"].coef_[0]
        order = np.argsort(coef)[::-1][:k]
        return [(str(names[i]), float(coef[i])) for i in order]

    def save(self, path: str | Path) -> None:
        import joblib

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "calibrator": self.calibrator,
                "threshold": self.threshold,
                "version": self.version,
            },
            path,
        )

    @classmethod
    def load(cls, path: str | Path) -> TextFilter:
        import joblib

        d = joblib.load(path)
        return cls(d["model"], d["calibrator"], d["threshold"], d["version"])


# ------------------------------------------------------------------------------------- leakage
_SENT = re.compile(r"(?<=[.!?])\s+")


def _shingles(text: str, n: int = 8) -> set[tuple[str, ...]]:
    toks = re.findall(r"\w+", text.lower())
    return {tuple(toks[i : i + n]) for i in range(max(0, len(toks) - n + 1))}


def leakage_report(train: Sequence[str], test: Sequence[str], n: int = 8) -> dict[str, float]:
    """How much test text is literally present in training text.

    * ``exact_dup_rate``      share of test posts identical to some training post
    * ``sentence_overlap``    share of test sentences that appear verbatim in training
    * ``shingle_overlap``     share of test 8-gram shingles present in training
    * ``nn_cosine_*``         nearest-neighbour similarity (char n-gram TF-IDF) of each test post to the
                              training set: catches paraphrases that exact-match measures miss
    High values mean in-distribution scores overstate generalisation; we therefore also report
    results on agent-written posts and on the held-out family.
    """
    train_set = set(train)
    train_sents = {s.strip().lower() for t in train for s in _SENT.split(t) if s.strip()}
    train_sh = set().union(*(_shingles(t, n) for t in train)) if train else set()
    test_sents = [s.strip().lower() for t in test for s in _SENT.split(t) if s.strip()]
    test_sh = [sh for t in test for sh in _shingles(t, n)]
    nn = _nn_cosine(train, test)
    return {
        "exact_dup_rate": float(np.mean([t in train_set for t in test])) if test else float("nan"),
        "sentence_overlap": float(np.mean([s in train_sents for s in test_sents]))
        if test_sents
        else float("nan"),
        "shingle_overlap": float(np.mean([s in train_sh for s in test_sh])) if test_sh else float("nan"),
        "nn_cosine_mean": float(nn.mean()) if nn.size else float("nan"),
        "nn_cosine_p95": float(np.quantile(nn, 0.95)) if nn.size else float("nan"),
    }


def _nn_cosine(train: Sequence[str], test: Sequence[str]) -> np.ndarray:
    """For every test text, cosine similarity to its nearest training text in a character 3-5-gram
    TF-IDF space (a paraphrase-tolerant similarity that needs no external embedding model)."""
    if not train or not test:
        return np.asarray([])
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True).fit(
        list(train) + list(test)
    )
    sims = (vec.transform(list(test)) @ vec.transform(list(train)).T).toarray()
    return np.asarray(sims.max(axis=1))
