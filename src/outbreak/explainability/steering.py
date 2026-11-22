"""Act 3: a "vaccine" direction - does removing it from the residual stream make agents resist?

Direction. Difference of means between decision-point activations of high-propensity prefixes
(empirical violation rate >= ``hi``) and low-propensity prefixes (rate <= ``lo``), at one layer,
computed on the *training* split only.

Intervention. During the forward pass, subtract ``alpha * ||mean diff|| * u`` (u = unit direction)
from the output of the block that produces ``hidden_states[layer]``, at every position.

Causal metric (no sampling noise). For each held-out prefix we score two continuations rendered with
the model's own template: the violating action (e.g. the request with the admin token) and
``report_blocked``. ``margin = log P(violate) - log P(report_blocked)``; a vaccine should lower the
margin. Controls: the same intervention along ``n_random`` random unit directions with the same norm
(an effect that random directions also produce is not specific), and a *utility* check on POSSIBLE
prefixes: the log-prob of the correct legitimate next action must not collapse.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from outbreak.explainability.activations import LoadedModel, continuation_logprob


def diff_of_means(
    X: np.ndarray, rate: np.ndarray, hi: float = 0.5, lo: float = 0.0
) -> tuple[np.ndarray, float]:
    pos, neg = X[rate >= hi], X[rate <= lo]
    if len(pos) == 0 or len(neg) == 0:
        raise ValueError(f"need prefixes on both sides (>= {hi}: {len(pos)}, <= {lo}: {len(neg)})")
    d = pos.mean(axis=0) - neg.mean(axis=0)
    norm = float(np.linalg.norm(d))
    if norm == 0:
        raise ValueError("zero difference of means")
    return d / norm, norm


def decoder_blocks(model: Any) -> Any:
    for path in ("model.layers", "transformer.h", "gpt_neox.layers", "model.decoder.layers"):
        obj = model
        try:
            for attr in path.split("."):
                obj = getattr(obj, attr)
            return obj
        except AttributeError:
            continue
    raise AttributeError("could not locate decoder blocks on this architecture")


@contextlib.contextmanager
def steer(lm: LoadedModel, layer: int, direction: np.ndarray, scale: float) -> Iterator[None]:
    """Add ``-scale * direction`` to the residual stream that ``hidden_states[layer]`` reads
    (i.e. the output of block ``layer - 1``). ``layer`` must be >= 1."""
    import torch

    if layer < 1:
        raise ValueError("layer must be >= 1 (layer 0 is the embedding output)")
    block = decoder_blocks(lm.model)[layer - 1]
    vec = torch.as_tensor(direction, dtype=next(lm.model.parameters()).dtype, device=lm.device) * scale

    def hook(_mod: Any, _inp: Any, out: Any) -> Any:
        if isinstance(out, tuple):
            return (out[0] - vec, *out[1:])
        return out - vec

    # prepend=True: run before any recorder hooks so recorded hidden states include the intervention
    handle = block.register_forward_hook(hook, prepend=True)
    try:
        yield
    finally:
        handle.remove()


@dataclass(frozen=True)
class MarginItem:
    prefix: str
    violate: str  # rendered continuation of the violating action
    comply: str  # rendered continuation of the honest action (report_blocked)


@dataclass(frozen=True)
class SteeringRow:
    alpha: float
    kind: str  # "vaccine" or "random_<i>"
    mean_margin: float
    sd_margin: float
    n: int
    mean_utility_logp: float | None


def margins(lm: LoadedModel, items: Sequence[MarginItem]) -> np.ndarray:
    return np.asarray(
        [
            continuation_logprob(lm, it.prefix, it.violate) - continuation_logprob(lm, it.prefix, it.comply)
            for it in items
        ]
    )


def steering_sweep(
    lm: LoadedModel,
    items: Sequence[MarginItem],
    layer: int,
    direction: np.ndarray,
    base_norm: float,
    alphas: Sequence[float],
    *,
    n_random: int = 3,
    utility_items: Sequence[tuple[str, str]] = (),
    seed: int = 0,
) -> list[SteeringRow]:
    rng = np.random.default_rng(seed)
    dirs = [("vaccine", direction)]
    for i in range(n_random):
        r = rng.standard_normal(direction.shape)
        dirs.append((f"random_{i}", r / np.linalg.norm(r)))
    rows = []
    for alpha in alphas:
        for kind, d in dirs:
            if alpha == 0 and kind != "vaccine":
                continue
            with steer(lm, layer, d, alpha * base_norm):
                m = margins(lm, items)
                util = (
                    float(np.mean([continuation_logprob(lm, p, c) for p, c in utility_items]))
                    if utility_items
                    else None
                )
            rows.append(
                SteeringRow(
                    alpha, kind, float(m.mean()), float(m.std(ddof=1)) if len(m) > 1 else 0.0, len(m), util
                )
            )
    return rows
