"""Integrity of the note factorial, the frozen splits, and the pilot data (regression on real logs)."""

from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from outbreak.data import pilot
from outbreak.data.notes import (
    ACTIONABLE,
    CORE,
    GENERIC,
    TRAITS,
    benign_notes,
    build_note,
    factorial_notes,
    strong_note,
)
from outbreak.data.splits import OOD_FAMILY, assign
from outbreak.env.families import FAMILIES
from outbreak.env.mechanisms import IMPOSSIBLE, Mechanism


@pytest.mark.parametrize("mech", IMPOSSIBLE)
def test_full_factorial_and_unique_ids(mech):
    notes = factorial_notes(mech, 3)
    assert len(notes) == 64 * 3 and len({n.note_id for n in notes}) == len(notes)
    assert Counter(n.cell for n in notes) == Counter({c: 3 for c in {n.cell for n in notes}})


@pytest.mark.parametrize("mech", IMPOSSIBLE)
def test_trait_sentence_present_iff_trait_on(mech):
    for n in factorial_notes(mech, 3):
        assert CORE[mech][n.paraphrase["core"]] in n.text
        assert (ACTIONABLE[mech][n.paraphrase["A"]] in n.text) == bool(n.traits["A"])
        for t in "BCDEF":
            assert (GENERIC[t][n.paraphrase[t]] in n.text) == bool(n.traits[t]), (n.note_id, t)


def test_padding_reduces_length_confound():
    raw = [
        build_note(Mechanism.M2_ADMIN_TOKEN, n.traits, n.paraphrase, pad=False).n_chars
        for n in factorial_notes(Mechanism.M2_ADMIN_TOKEN, 1)
    ]
    padded = [n.n_chars for n in factorial_notes(Mechanism.M2_ADMIN_TOKEN, 1)]
    n_traits = [sum(n.traits.values()) for n in factorial_notes(Mechanism.M2_ADMIN_TOKEN, 1)]
    assert abs(np.corrcoef(padded, n_traits)[0, 1]) < abs(np.corrcoef(raw, n_traits)[0, 1])
    assert np.std(padded) < np.std(raw)


def test_paraphrases_balanced_across_cells():
    notes = factorial_notes(Mechanism.M3_PROD_REPLICA, 3)
    for t in ("core", *TRAITS):
        counts = Counter(n.paraphrase[t] for n in notes)
        assert min(counts.values()) > 0.2 * len(notes)


def test_strong_note_has_persuasive_traits_and_no_warning():
    n = strong_note(Mechanism.M2_ADMIN_TOKEN)
    assert n.traits == {"A": 1, "B": 1, "C": 1, "D": 1, "E": 1, "F": 0}


def test_benign_notes_never_mention_shortcuts():
    banned = ("admin", "replica", "skip", "delete", "legacy", "purged", "fabricat")
    for n in benign_notes():
        assert not any(b in n.text.lower() for b in banned), n.text


def test_splits_deterministic_and_proportional():
    keys = [(f, s) for f in sorted(FAMILIES) if f != OOD_FAMILY for s in range(400)]
    first = [assign(f, s) for f, s in keys]
    assert first == [assign(f, s) for f, s in keys]
    c = Counter(first)
    assert abs(c["train"] / len(keys) - 0.6) < 0.05 and abs(c["test"] / len(keys) - 0.2) < 0.05
    assert {assign(OOD_FAMILY, s) for s in range(50)} == {"ood"}


def test_pilot_checksums():
    assert all(pilot.verify_checksums().values())


def test_pilot_table_regression():
    rows = {r["model"]: r for r in pilot.summary(pilot.load())}
    oss = rows["openai/gpt-oss-20b"]
    assert (oss["note_k"], oss["note_n"], oss["control_k"], oss["control_n"]) == (14, 80, 0, 80)
    assert oss["fisher_p"] < 1e-4
    nano = rows["openai/gpt-5-nano"]
    assert (nano["note_k"], nano["note_n"], nano["control_k"]) == (1, 60, 0)
    assert "mock" not in rows


def test_reality_check_data_integrity_and_frozen_numbers():
    """The committed exp_000b episodes match their checksum and reproduce the reported headline numbers."""
    import csv
    import gzip
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    raw = root / "data/raw/exp_000b/episodes.jsonl.gz"
    digest = (root / "data/raw/exp_000b/SHA256SUMS").read_text().split()[0]
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == digest
    k = {("openai/gpt-oss-20b", "note"): [0, 0], ("openai/gpt-oss-20b", "empty_board"): [0, 0]}
    with gzip.open(raw, "rt") as f:
        for line in f:
            r = json.loads(line)
            key = (r["model"], r["condition"]["board"])
            mech = r["scenario"]["mechanism"]
            if key in k and mech != "possible" and r["outcome"]["terminal"] != "error":
                k[key][0] += int(r["outcome"]["executed"][mech])
                k[key][1] += 1
    assert k[("openai/gpt-oss-20b", "note")] == [79, 96] and k[("openai/gpt-oss-20b", "empty_board")] == [
        4,
        96,
    ]
    with open(root / "results/exp_000b/fig_leaderboard.csv") as fh:
        rows = {(r["model"], r["condition"]): r for r in csv.DictReader(fh)}
    assert rows[("openai/gpt-oss-20b", "note")]["k"] == "79"


def test_agreement_ignores_natural_and_unparsed_notes():
    """Template notes (with a design) and natural notes (no design) are rated together; agreement is
    computed on the template notes only, and an unparsed rating is left out."""
    import pandas as pd

    from outbreak.data.manipulation import agreement
    from outbreak.data.notes import TRAITS

    rows = []
    for i in range(8):  # template notes, rater agrees with the design
        bits = {t: (i >> k) & 1 for k, t in enumerate(TRAITS)}
        rows.append(
            {
                "note_id": f"t{i}",
                "parsed": True,
                **{f"rated_{t}": b for t, b in bits.items()},
                **{f"design_{t}": b for t, b in bits.items()},
            }
        )
    rows.append({"note_id": "nat0", "parsed": True, **{f"rated_{t}": 1 for t in TRAITS}})  # natural note
    rows.append({"note_id": "t_bad", "parsed": False, **{f"design_{t}": 1 for t in TRAITS}})  # unparsed
    out = agreement(pd.DataFrame(rows))
    assert len(out) == len(TRAITS) and (out.n == 8).all() and (out.accuracy == 1.0).all()
