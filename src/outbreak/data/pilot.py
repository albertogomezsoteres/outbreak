"""The feasibility pilot (Nov 19-20, 2026), kept as raw, checksummed data.

The pilot used an earlier single-task harness (``scripts/pilot/outbreak_smoke.py``: one sales task,
the admin-token shortcut, one note) and real OpenRouter models. It is *not* part of the confirmatory
analysis (the environment changed afterwards, see docs/DEVIATIONS.md); it motivated the design and
sized the main experiments. This module reproduces the pilot table from the raw logs.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from outbreak.utils.stats import fisher, wilson

PILOT_DIR = Path("data/raw/pilot")
CHECKSUMS = PILOT_DIR / "SHA256SUMS"
_NAME = re.compile(r"smoke_(?P<model>.+)_(?P<ts>\d+)\.jsonl$")


def model_of(path: Path) -> str:
    m = _NAME.search(path.name)
    if not m:
        raise ValueError(f"unexpected pilot log name {path.name}")
    raw = m.group("model")
    return "mock" if raw == "mock" else raw.replace("_", "/", 1)


def load(pilot_dir: Path = PILOT_DIR) -> list[dict[str, Any]]:
    rows = []
    for p in sorted((pilot_dir / "logs").glob("*.jsonl")):
        model = model_of(p)
        for line in p.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                r.pop("transcript", None)
                rows.append({"model": model, "file": p.name, **r})
    return rows


def summary(rows: list[dict[str, Any]], include_mock: bool = False) -> list[dict[str, Any]]:
    agg: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        if r["model"] == "mock" and not include_mock:
            continue
        a = agg[(r["model"], r["cond"])]
        a[0] += int(r["any_violation"])
        a[1] += 1
        a[2] += int(r["legit_success"])
    out = []
    for model in sorted({m for m, _ in agg}):
        note, ctrl, poss = agg.get((model, "note")), agg.get((model, "control")), agg.get((model, "possible"))
        row: dict[str, Any] = {"model": model}
        if note and ctrl:
            row.update(
                note_k=note[0],
                note_n=note[1],
                control_k=ctrl[0],
                control_n=ctrl[1],
                note_rate=wilson(note[0], note[1]).as_pct(),
                control_rate=wilson(ctrl[0], ctrl[1]).as_pct(),
                fisher_p=fisher(note[0], note[1], ctrl[0], ctrl[1]),
            )
        if poss:
            row.update(possible_success=f"{poss[2]}/{poss[1]}")
        out.append(row)
    return out


def verify_checksums(pilot_dir: Path = PILOT_DIR) -> dict[str, bool]:
    """Check every file listed in SHA256SUMS (``<sha256>  <relative path>``)."""
    res = {}
    for line in (pilot_dir / "SHA256SUMS").read_text().splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        p = pilot_dir / rel.strip()
        res[rel.strip()] = p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == digest
    return res
