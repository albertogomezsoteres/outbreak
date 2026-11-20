"""Hyperparameter searches declared in ``experiments/hyperparameter_searches/*.yaml``.

Two targets, both selected on the *validation* split only (the test split is evaluated once, with the
selected configuration, by ``train-filter`` / the white-box notebook):

* ``channel_filter`` - grid over the logistic regression's ``C`` and the target false-positive rate
  used to set the threshold. Selection metric: validation AUROC (ties broken by the smaller C, i.e.
  the stronger regularisation).
* ``probe`` - grid over layer x ``C`` on cached decision-point activations (``.npz``) and the
  harvested ``decision_points.jsonl``. Selection metric: validation AUROC.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field

from outbreak.utils.stats import auroc


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchSpec(_Strict):
    method: Literal["grid"] = "grid"
    selection_metric: Literal["val_auroc"] = "val_auroc"
    parameters: dict[str, list[Any]]


class SearchConfig(_Strict):
    experiment_id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    target: Literal["channel_filter", "probe"]
    search: SearchSpec
    reproducibility: dict[str, Any] = Field(default_factory=lambda: {"seed": 1234})

    @property
    def seed(self) -> int:
        return int(self.reproducibility.get("seed", 1234))


def load_search(path: str | Path) -> SearchConfig:
    return SearchConfig.model_validate(yaml.safe_load(Path(path).read_text()))


def _grid(params: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = sorted(params)
    return [dict(zip(keys, vals, strict=True)) for vals in itertools.product(*(params[k] for k in keys))]


def search_channel_filter(cfg: SearchConfig, episode_paths: list[Path]) -> pd.DataFrame:
    from outbreak.models.text_filter import TextFilter
    from outbreak.pipeline.filter_training import exposures

    rows = exposures(episode_paths)
    by = {s: [r for r in rows if r["split"] == s] for s in ("train", "val", "benign")}
    train = by["train"] + by["benign"][::2]
    benign_val = [r["text"] for r in by["benign"][1::2]]
    if len({r["y"] for r in train}) < 2 or len({r["y"] for r in by["val"]}) < 2:
        raise SystemExit("train and val exposures must each contain both outcomes; collect more episodes")
    out = []
    for combo in _grid(cfg.search.parameters):
        flt = TextFilter.fit(
            [r["text"] for r in train], [r["y"] for r in train], C=float(combo["C"]), seed=cfg.seed
        )
        flt.calibrate([r["text"] for r in by["val"]], [r["y"] for r in by["val"]])
        thr = (
            flt.set_threshold_for_fpr(benign_val, float(combo.get("target_fpr", 0.05))) if benign_val else 0.5
        )
        s = flt.scores([r["text"] for r in by["val"]])
        y = np.asarray([r["y"] for r in by["val"]])
        out.append(
            {
                **combo,
                "val_auroc": auroc(s, y),
                "threshold": thr,
                "val_tpr": float((s[y == 1] >= thr).mean()) if (y == 1).any() else np.nan,
                "val_flag_rate": float((s >= thr).mean()),
            }
        )
    return _rank(pd.DataFrame(out), tie_breaker=("C", True))


def search_probe(
    cfg: SearchConfig, activations: dict[int, np.ndarray], rows: list[dict[str, Any]]
) -> pd.DataFrame:
    from outbreak.explainability.probe import PrefixSet, episode_level, fit_probe

    split = np.array([r["split"] for r in rows])
    base = PrefixSet(
        np.zeros((len(rows), 1)),
        np.array([r["k"] for r in rows]),
        np.array([r["n"] for r in rows]),
        [r["note_id"] for r in rows],
        [r["group"] for r in rows],
        list(split),
        [r.get("board_text", "") for r in rows],
    )
    params = dict(cfg.search.parameters)
    layers = [int(x) for x in params.pop("layer", sorted(activations))]
    out = []
    for layer in layers:
        if layer not in activations:
            raise KeyError(f"layer {layer} not in the activation file (have {sorted(activations)})")
        ps = base.with_X(activations[layer])
        tr, va = ps.subset(split == "train"), ps.subset(split == "val")
        for combo in _grid(params) if params else [{}]:
            probe = fit_probe(tr, C=float(combo.get("C", 0.1)), seed=cfg.seed)
            s, y, _ = episode_level(probe.predict_proba(va.X)[:, 1], va)
            out.append({"layer": layer, **combo, "val_auroc": auroc(s, y)})
    return _rank(pd.DataFrame(out), tie_breaker=("C", True) if "C" in params else None)


def _rank(df: pd.DataFrame, tie_breaker: tuple[str, bool] | None) -> pd.DataFrame:
    by, asc = ["val_auroc"], [False]
    if tie_breaker and tie_breaker[0] in df:
        by.append(tie_breaker[0])
        asc.append(tie_breaker[1])
    df = df.sort_values(by, ascending=asc).reset_index(drop=True)
    df["selected"] = df.index == 0
    return df


def write_search(df: pd.DataFrame, out_dir: Path, cfg: SearchConfig) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "search_results.csv", index=False)
    best = {k: (v.item() if hasattr(v, "item") else v) for k, v in df.iloc[0].to_dict().items()}
    (out_dir / "selected.json").write_text(
        json.dumps(
            {"experiment_id": cfg.experiment_id, "target": cfg.target, "selected": best},
            indent=2,
            default=str,
        )
    )
    return out_dir / "selected.json"
