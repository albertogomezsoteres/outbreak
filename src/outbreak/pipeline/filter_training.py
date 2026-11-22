"""Train, calibrate and evaluate the channel filter from bench episodes.

Unit of splitting = the *note text* (a filter is a function of text, so the same note must never be
in train and test). Notes are assigned to train/val/test by hashing their id; benign notes are always
used for the false-positive budget on validation. The report includes AUROC with note-clustered
bootstrap CIs, the calibration table, the chosen threshold, TPR/FPR at that threshold, the leakage
report, and the most predictive n-grams.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from outbreak.models.text_filter import TextFilter, leakage_report
from outbreak.pipeline.runner import read_episodes
from outbreak.utils.stats import auroc_ci


def note_split(note_id: str) -> str:
    base = note_id.rsplit("-r", 1)[0] if note_id.startswith("M") else note_id
    u = int(hashlib.sha256(f"note-split|{note_id}|{base}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "train" if u < 0.6 else ("val" if u < 0.8 else "test")


def exposures(paths: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for p in paths:
        for ep in read_episodes(p):
            c = ep["condition"]
            if c.get("board") not in {"note", "benign"} or not c.get("note_text"):
                continue
            rows.append(
                {
                    "note_id": c["note_id"],
                    "text": c["note_text"],
                    "benign": c["board"] == "benign",
                    "y": int(ep["outcome"]["violation"]),
                    "model": ep["model"],
                    "split": "benign" if c["board"] == "benign" else note_split(c["note_id"]),
                }
            )
    return rows


def train_filter(
    paths: list[Path], out: Path, *, target_fpr: float = 0.05, C: float = 1.0, seed: int = 0
) -> dict[str, Any]:
    rows = exposures(paths)
    if not rows:
        raise SystemExit("no note/benign exposures with note_text found in the given episodes")
    by = {s: [r for r in rows if r["split"] == s] for s in ("train", "val", "test", "benign")}
    benign = by["benign"]
    train = by["train"] + benign[::2]  # half the benign exposures teach the negative class
    benign_val = benign[1::2]
    if len({r["y"] for r in train}) < 2:
        raise SystemExit("training exposures contain a single outcome class; collect more bench episodes")
    flt = TextFilter.fit([r["text"] for r in train], [r["y"] for r in train], C=C, seed=seed)
    flt.calibrate([r["text"] for r in by["val"]], [r["y"] for r in by["val"]])
    flt.set_threshold_for_fpr(
        [r["text"] for r in benign_val] or [r["text"] for r in by["val"] if not r["y"]], target_fpr
    )
    report: dict[str, Any] = {
        "n_exposures": {k: len(v) for k, v in by.items()},
        "threshold": flt.threshold,
        "target_fpr": target_fpr,
        "C": C,
    }
    for split in ("val", "test"):
        rs = by[split]
        if not rs:
            continue
        s = flt.scores([r["text"] for r in rs])
        y = np.asarray([r["y"] for r in rs])
        ci = auroc_ci(s, y, [r["note_id"] for r in rs], seed=seed)
        flagged = s >= flt.threshold
        report[split] = {
            "auroc": ci.estimate,
            "auroc_ci": [ci.low, ci.high],
            "base_rate": float(y.mean()),
            "tpr_at_threshold": float(flagged[y == 1].mean()) if (y == 1).any() else None,
            "flag_rate_at_threshold": float(flagged.mean()),
        }
    if benign_val:
        report["benign_fpr_at_threshold"] = float(
            (flt.scores([r["text"] for r in benign_val]) >= flt.threshold).mean()
        )
    report["leakage_train_vs_test"] = leakage_report(
        sorted({r["text"] for r in train}), sorted({r["text"] for r in by["test"]})
    )
    report["top_features"] = flt.top_features(15)
    flt.save(out)
    out.with_suffix(".report.json").write_text(json.dumps(report, indent=2))
    return report
