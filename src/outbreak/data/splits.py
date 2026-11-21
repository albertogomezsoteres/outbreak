"""Frozen scenario-level splits.

Anything trained on episodes (the text filter, the activation probe) is evaluated on scenarios it has
never seen. The split unit is the *scenario draw* ``(family, seed)``; one family
(``experiment_readout``) is additionally held out entirely as an out-of-distribution test set, so we
can report both in-distribution and cross-family generalisation. The assignment is a pure function of
the key (sha256), so it never changes when new seeds are added.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

Split = Literal["train", "val", "test", "ood"]
OOD_FAMILY = "experiment_readout"
FRACTIONS = {"train": 0.6, "val": 0.2, "test": 0.2}


def assign(family: str, seed: int) -> Split:
    if family == OOD_FAMILY:
        return "ood"
    u = int(hashlib.sha256(f"split|{family}|{seed}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    if u < FRACTIONS["train"]:
        return "train"
    if u < FRACTIONS["train"] + FRACTIONS["val"]:
        return "val"
    return "test"


def write_split_file(path: Path, families: list[str], seeds: list[int]) -> dict[str, str]:
    table: dict[str, str] = {f"{f}:{s}": assign(f, s) for f in families for s in seeds}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"version": "splits-v1", "ood_family": OOD_FAMILY, "fractions": FRACTIONS, "assignments": table},
            indent=1,
            sort_keys=True,
        )
    )
    return table
