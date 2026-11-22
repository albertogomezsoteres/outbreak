"""Builders that turn an :class:`ExperimentConfig` into a list of :class:`EpisodeSpec`.

Design rules enforced here (they are what make the comparisons causal):

* **Pairing** - every board condition of a scenario uses the same scenario draw and the same
  sampling seed base, so conditions differ only in what is on the board.
* **Randomised exposure** - in factorial runs, notes are assigned to scenario draws by a seeded
  permutation, not by hand, so trait effects are not confounded with task difficulty.
* **Balanced families** - every note cell is spread over all families.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from typing import Any

from outbreak.data.notes import benign_notes, factorial_notes, pb12_notes, strong_note
from outbreak.data.splits import assign
from outbreak.env.mechanisms import Mechanism
from outbreak.env.workspace import Scenario
from outbreak.pipeline.runner import EpisodeSpec
from outbreak.utils.config import ExperimentConfig


def scenarios(cfg: ExperimentConfig, mechanism: Mechanism) -> list[Scenario]:
    out = []
    for fam in cfg.dataset.families:
        for seed in cfg.dataset.seeds:
            if cfg.dataset.split != "all" and assign(fam, seed) != cfg.dataset.split:
                continue
            out.append(Scenario(fam, mechanism, seed))
    return out


def _benign_for(sc: Scenario) -> tuple[str, str]:
    notes = benign_notes()
    n = notes[(sc.seed + hash_family(sc.family)) % len(notes)]
    return n.note_id, n.text


def hash_family(f: str) -> int:
    return sum(map(ord, f))


def bench_specs(cfg: ExperimentConfig) -> Iterator[EpisodeSpec]:
    """Act 1. ``cells='strong'``: every scenario under every board condition (paired).
    ``cells='factorial'``: control conditions on every scenario, plus the 2^6 x paraphrase notes
    randomly assigned to scenario draws (each note seen ``replicates`` times on different draws)."""
    rng = random.Random(cfg.reproducibility.seed)
    for agent in cfg.model.agents:
        for mech in cfg.dataset.mechanisms:
            scs = scenarios(cfg, mech)
            if not scs:
                continue
            for sc in scs:
                for cond in cfg.notes.conditions:
                    if cond == "note" and cfg.notes.cells == "factorial":
                        continue
                    for rep in range(cfg.notes.replicates):
                        nid = text = None
                        if cond == "benign":
                            nid, text = _benign_for(sc)
                        elif cond == "note":
                            if not mech.impossible:
                                continue
                            n = strong_note(mech)
                            nid, text = n.note_id, n.text
                        yield EpisodeSpec(
                            episode_id=f"{cfg.experiment_id}|{agent.id}|{sc.id}|{cond}|{nid or '-'}|r{rep}",
                            model=agent.id,
                            scenario=sc,
                            board=cond,
                            note_id=nid,
                            note_text=text,
                            replicate=rep,
                            meta={"mechanism": mech.value, "family": sc.family}
                            | ({"note_source": "template"} if cond == "note" else {}),
                        )
            if "note" in cfg.notes.conditions and cfg.notes.cells == "natural" and mech.impossible:
                yield from _natural_specs(cfg, agent.id, mech, scs, rng)
            if "note" in cfg.notes.conditions and cfg.notes.cells == "factorial" and mech.impossible:
                notes = factorial_notes(mech, cfg.notes.paraphrase_draws, seed=cfg.reproducibility.seed)
                # Interleave scenario draws by family so consecutive slots rotate through families;
                # a seeded shuffle of the notes then makes trait cells independent of the draw.
                inter = sorted(scs, key=lambda s: (s.seed, cfg.dataset.families.index(s.family)))
                for rep in range(cfg.notes.replicates):
                    order = list(range(len(notes)))
                    rng.shuffle(order)
                    for k, i in enumerate(order):
                        n = notes[i]
                        sc = inter[(k + rep * len(notes)) % len(inter)]
                        yield EpisodeSpec(
                            episode_id=f"{cfg.experiment_id}|{agent.id}|{sc.id}|note|{n.note_id}|r{rep}",
                            model=agent.id,
                            scenario=sc,
                            board="note",
                            note_id=n.note_id,
                            note_text=n.text,
                            replicate=rep,
                            meta={
                                "mechanism": mech.value,
                                "family": sc.family,
                                "cell": n.cell,
                                **n.traits,
                                "n_chars": n.n_chars,
                            },
                        )


def _natural_specs(
    cfg: ExperimentConfig, model: str, mech: Mechanism, scs: list[Scenario], rng: random.Random
) -> Iterator[EpisodeSpec]:
    """Each usable natural note x ``replicates``, assigned to interleaved scenario draws (as the factorial)."""
    from pathlib import Path

    from outbreak.data import natural_notes

    path = natural_notes.default_path(mech, Path(cfg.notes.natural_dir))
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing: run `outbreak natural-notes --mechanism {mech.value}` first"
        )
    notes = natural_notes.load(path)
    inter = sorted(scs, key=lambda s: (s.seed, cfg.dataset.families.index(s.family)))
    for rep in range(cfg.notes.replicates):
        order = list(range(len(notes)))
        rng.shuffle(order)
        for k, i in enumerate(order):
            n = notes[i]
            sc = inter[(k + rep * len(notes)) % len(inter)]
            yield EpisodeSpec(
                episode_id=f"{cfg.experiment_id}|{model}|{sc.id}|note|{n.note_id}|r{rep}",
                model=model,
                scenario=sc,
                board="note",
                note_id=n.note_id,
                note_text=n.text,
                replicate=rep,
                meta={
                    "mechanism": mech.value,
                    "family": sc.family,
                    "note_source": "natural",
                    "voice": n.voice,
                    "n_chars": n.n_chars,
                },
            )


def exposure_specs(cfg: ExperimentConfig) -> Iterator[EpisodeSpec]:
    """Randomised exposure with many samples per decision-point prefix (the white-box dataset).

    Every scenario draw is played under an empty board and a benign note, plus harmful notes:
    ``cells='strong'`` uses the single strong note; ``cells='factorial'`` assigns
    ``exposure_notes_per_scenario`` factorial notes per draw (cycling through a seeded shuffle so every note
    is used about equally). Varied notes give the probe a continuous range of propensities, so it must
    explain variation *between notes and between scenarios*, not just "is there a note".
    """
    for agent in cfg.model.agents:
        for mech in cfg.dataset.mechanisms:
            pool: list[tuple[str, str]] = []
            if mech.impossible and cfg.notes.cells == "factorial":
                # A fixed, balanced set of 12 notes (Plackett-Burman cells) re-used across scenario draws and
                # cycled *within each split*, so every note appears in train, val and test scenarios. That makes
                # the note-identity baseline informative and within-note comparisons possible.
                notes = pb12_notes(mech, seed=cfg.reproducibility.seed)
                pool = [(n.note_id, n.text) for n in notes]
            cursors: dict[str, int] = {}
            orders: dict[str, list[int]] = {}
            for sc in scenarios(cfg, mech):
                bid, btext = _benign_for(sc)
                arms: list[tuple[str, str | None, str | None, dict[str, Any]]] = [
                    ("empty_board", None, None, {}),
                    ("benign", bid, btext, {}),
                ]
                if mech.impossible:
                    if pool:
                        split = assign(sc.family, sc.seed)
                        if split not in orders:
                            orders[split] = list(range(len(pool)))
                            random.Random(
                                f"exposure|{cfg.reproducibility.seed}|{mech.value}|{split}"
                            ).shuffle(orders[split])
                            cursors[split] = 0
                        for _ in range(cfg.notes.exposure_notes_per_scenario):
                            pid, ptext = pool[orders[split][cursors[split] % len(pool)]]
                            cursors[split] += 1
                            arms.append(("note", pid, ptext, {"note_source": "template"}))
                    else:
                        n = strong_note(mech)
                        arms.append(("note", n.note_id, n.text, {"note_source": "template"}))
                for cond, nid, text, extra in arms:
                    for rep in range(cfg.notes.replicates):
                        yield EpisodeSpec(
                            episode_id=f"{cfg.experiment_id}|{agent.id}|{sc.id}|{cond}|{nid or '-'}|r{rep}",
                            model=agent.id,
                            scenario=sc,
                            board=cond,
                            note_id=nid,
                            note_text=text,
                            replicate=rep,
                            meta={"mechanism": mech.value, "family": sc.family, **extra},
                        )
