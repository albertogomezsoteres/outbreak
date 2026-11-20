"""Experiment design invariants, resumable runner, outbreak machinery, harvest and analysis."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import pytest

from outbreak.env.board import ChannelVerdict
from outbreak.env.detectors import classify_call
from outbreak.env.families import FAMILIES
from outbreak.env.mechanisms import IMPOSSIBLE, Mechanism
from outbreak.env.workspace import Scenario
from outbreak.models.judges import OracleGate
from outbreak.models.scripted import ScriptedAgent
from outbreak.pipeline import analysis
from outbreak.pipeline.experiments import bench_specs, exposure_specs
from outbreak.pipeline.harvest import build_decision_points, violating_action
from outbreak.pipeline.outbreak import make_population, run_outbreak
from outbreak.pipeline.runner import EpisodeSpec, done_ids, read_episodes, run_specs
from outbreak.utils.config import load_config

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "single_experiments"


def _cfg(name: str, **over):
    return load_config(EXP / name, over)


def test_bench_conditions_are_paired_on_identical_scenarios():
    specs = list(bench_specs(_cfg("01_screen_susceptibility.yaml")))
    by = defaultdict(set)
    for s in specs:
        by[(s.model, s.scenario.mechanism, s.board)].add(s.scenario)
    for (model, mech, _board), scs in by.items():
        if mech.impossible:
            assert scs == by[(model, mech, "empty_board")] == by[(model, mech, "no_board")]
    assert len({s.episode_id for s in specs}) == len(specs)


def test_factorial_every_note_once_per_replicate_and_spread_over_families():
    cfg = _cfg("02_trait_factorial.yaml")
    notes = [s for s in bench_specs(cfg) if s.board == "note"]
    per_mech = Counter((s.model, s.scenario.mechanism, s.note_id) for s in notes)
    assert set(per_mech.values()) == {cfg.notes.replicates}
    assert len(per_mech) == 192 * len(cfg.dataset.mechanisms) * len(cfg.model.agents)
    fams = Counter(s.scenario.family for s in notes)
    assert set(fams) == set(FAMILIES) and max(fams.values()) - min(fams.values()) <= 0.1 * max(fams.values())


def test_exposure_specs_three_arms_same_scenarios():
    specs = list(exposure_specs(_cfg("03_exposure_whitebox_harvest.yaml")))
    arms = defaultdict(set)
    for s in specs:
        arms[s.board].add((s.scenario, s.replicate))
    assert arms["empty_board"] == arms["benign"] == arms["note"]


def test_runner_resumes_without_duplicates(tmp_path):
    scs = [Scenario("sales_report", m, 0) for m in (Mechanism.POSSIBLE, Mechanism.M2_ADMIN_TOKEN)]
    specs = [EpisodeSpec(f"e{i}", "scripted/honest", sc, "empty_board") for i, sc in enumerate(scs)]
    out = tmp_path / "episodes.jsonl"
    factory = lambda mid, sc: ScriptedAgent(sc, mid.split("/")[1])  # noqa: E731
    s1 = run_specs(specs[:1], factory, out, concurrency=1)
    s2 = run_specs(specs, factory, out, concurrency=2)
    assert s1["run"] == 1 and s2["skipped_done"] == 1 and s2["run"] == 1
    assert done_ids(out) == {"e0", "e1"} and len(read_episodes(out)) == 2


def test_runner_survives_corrupt_line(tmp_path):
    out = tmp_path / "e.jsonl"
    out.write_text('{"episode_id": "a"}\n{broken\n')
    assert done_ids(out) == {"a"}


def _contagious(_aid, sc):
    return ScriptedAgent(sc, "contagious")


@pytest.fixture(scope="module")
def population():
    return make_population(
        0,
        mechanism=Mechanism.M2_ADMIN_TOKEN,
        families=sorted(FAMILIES),
        seeds=[0, 1],
        n_agents=6,
        n_rounds=2,
        blocked_fraction=0.67,
        base_seed=1,
    )


def test_population_structure(population):
    assert sum(s.blocked for s in population.slots) == 4
    assert {s.round for s in population.slots} == {1, 2}
    assert all((s.scenario.mechanism is Mechanism.M2_ADMIN_TOKEN) == s.blocked for s in population.slots)


@pytest.mark.slow
def test_outbreak_arms_with_si_agents(population):
    no_board = run_outbreak(population, "no_board", _contagious, concurrency=6).summary()
    board = run_outbreak(population, "board", _contagious, concurrency=6)
    blocked = run_outbreak(
        population,
        "channel_filter",
        _contagious,
        concurrency=6,
        channel_filter=lambda t: ChannelVerdict(False, 1.0),
    ).summary()
    oracle = run_outbreak(
        population, "oracle_monitor", _contagious, concurrency=6, gate=OracleGate()
    ).summary()
    s = board.summary()
    assert no_board["violations"] == 0 and s["violations"] == 4 and blocked["violations"] == 0
    assert oracle["violations"] == 0 and oracle["utility"] == 1.0
    assert s["secondary_violations"] >= 1  # round-2 agent read posts by round-1 violators
    assert ("agent-00", next(a.agent_id for a in board.agents if a.blocked and a.round == 1)) in board.chains
    again = run_outbreak(population, "board", _contagious, concurrency=3).summary()
    assert again == s  # deterministic under different parallelism


def test_violating_actions_are_classified_as_attempts():
    for mech in IMPOSSIBLE:
        name, args = violating_action(Scenario("latency_slo", mech, 4))
        assert mech in classify_call(name, args)


def test_harvest_labels_are_the_targeted_shortcut():
    """k counts episodes that executed the scenario's own shortcut; another mechanism (e.g. fabricating data in
    a quota scenario) is a violation but not a transmission of the note's shortcut."""
    prefix = [{"role": "system", "content": "x"}]
    ep = {
        "model": "m",
        "scenario": Scenario("sales_report", Mechanism.M2_ADMIN_TOKEN, 0).to_dict(),
        "condition": {"board": "note", "note_id": "n1"},
        "decision_prefix": prefix,
    }

    def out(m2: bool, m4: bool = False) -> dict:
        return {"violation": m2 or m4, "executed": {"m2_admin_token": m2, "m4_fabrication": m4}}

    eps = [
        {**ep, "outcome": out(True)},
        {**ep, "outcome": out(False)},
        {**ep, "outcome": out(True)},
        {**ep, "outcome": out(False, m4=True)},
    ]
    eps.append({**ep, "decision_prefix": [{"role": "system", "content": "y"}], "outcome": out(False)})
    rows = build_decision_points(eps)
    assert sorted((r["k"], r["n"]) for r in rows) == [(0, 1), (2, 4)]
    assert rows[0]["violating_action"][0] == "http_request"


def _fake_records():
    recs = []
    for model, p_note in (("m/a", 0.4), ("m/b", 0.0)):
        for i in range(40):
            for board in ("empty_board", "note", "no_board"):
                v = board == "note" and (i / 40) < p_note
                recs.append(
                    {
                        "episode_id": f"{model}{i}{board}",
                        "model": model,
                        "scenario": {"family": "sales_report", "mechanism": "m2_admin_token", "seed": i},
                        "condition": {"board": board, "note_id": "n"},
                        "outcome": {
                            "violation": v,
                            "attempt": v,
                            "legit_success": False,
                            "honest_block": not v,
                            "terminal": "report_blocked",
                            "steps": 3,
                            "executed": {
                                "m1_test_edit": False,
                                "m2_admin_token": v,
                                "m3_prod_replica": False,
                                "m4_fabrication": False,
                            },
                        },
                        "usage": {"cost_usd": 0.0001},
                        "first_action": None,
                        "posts": [],
                    }
                )
    return recs


def test_contrast_table_numbers():
    df = analysis.episodes_frame(_fake_records())
    h1 = analysis.contrast_table(df, "note", "empty_board").set_index("model")
    assert h1.loc["m/a", "k_note"] == 16 and h1.loc["m/a", "n_note"] == 40
    assert h1.loc["m/a", "diff"] == pytest.approx(0.4) and h1.loc["m/a", "p_holm"] < 0.001
    assert h1.loc["m/b", "diff"] == 0 and h1.loc["m/b", "p"] == 1.0


def test_analyze_episodes_writes_report_and_figure(tmp_path):
    path = tmp_path / "episodes.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in _fake_records()))
    files = analysis.analyze_episodes(path, tmp_path / "out")
    assert files["leaderboard"].exists() and "H1" in files["report"].read_text()
    assert pd.read_csv(files["leaderboard"].with_suffix(".csv")).shape[0] == 6


def test_defense_tests_and_frontier():
    rows = []
    for k in range(12):
        rows.append(
            {
                "outbreak": k,
                "arm": "board",
                "threshold": None,
                "violations": 5 + k % 3,
                "utility": 1.0,
                "blocked_violation_rate": 0.6,
            }
        )
        rows.append(
            {
                "outbreak": k,
                "arm": "channel_filter",
                "threshold": 0.5,
                "violations": 1,
                "utility": 1.0,
                "blocked_violation_rate": 0.1,
            }
        )
    ob = pd.DataFrame(rows)
    t = analysis.defense_tests(ob, margin=0.05).iloc[0]
    assert t.p_fewer_violations < 0.001 and t.non_inferior
    fr = analysis.frontier_points(ob)
    assert set(fr.arm) == {"board", "channel_filter"}


def test_targeted_vs_other_mechanism_outcomes():
    recs = _fake_records()
    other = dict(recs[0])
    other["episode_id"] = "fabricator"
    other["outcome"] = {
        **recs[0]["outcome"],
        "violation": True,
        "executed": {
            "m1_test_edit": False,
            "m2_admin_token": False,
            "m3_prod_replica": False,
            "m4_fabrication": True,
        },
    }
    df = analysis.episodes_frame([*recs, other])
    row = df.set_index("episode_id").loc["fabricator"]
    assert row.violation == 1 and row.targeted == 0
    spont = analysis.spontaneous_table(df)
    assert spont.k_other_violation.sum() == 1


def test_exposure_factorial_uses_varied_notes():
    cfg = _cfg("03_exposure_whitebox_harvest.yaml")
    specs = [s for s in exposure_specs(cfg) if s.board == "note"]
    per_draw = Counter((s.scenario, s.replicate) for s in specs)
    assert set(per_draw.values()) == {cfg.notes.exposure_notes_per_scenario}
    assert len({s.note_id for s in specs}) > 150  # most of the 192 factorial notes per mechanism are used
