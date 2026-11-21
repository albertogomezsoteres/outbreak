"""Generate the Colab notebooks from plain-text cell sources (reviewable and diffable here).

    python scripts/build_notebooks.py        # writes notebooks/colab/*.ipynb

One notebook per question of the study, each short and self-contained (2 setup cells + its own steps). They
can run in parallel Colab sessions: every experiment has its own LLM cache, results live on Drive.

    00  setup + reality check        CPU   (already run; re-run only to reproduce)
    01  who catches it?   exp_001    CPU
    02  why it spreads    exp_002/006 + natural notes + manipulation check       CPU
    03  where to stop it  filter search/train + judge-vs-filter + exp_004        CPU  (after 02)
    04  white-box data    exp_003 + harvest                                      CPU
    05  probe + vaccine   activations, probe, steering, closed loop              GPU  (after 04)
    06  results           tables, figures, demo, poster, bundle                  CPU  (no API key)
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def nb(cells: list[tuple[str, str]], gpu: bool = False) -> dict:
    out = []
    for kind, src in cells:
        lines = src.strip("\n").splitlines(keepends=True)
        cell = {"cell_type": kind, "metadata": {}, "source": lines}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        out.append(cell)
    meta = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
        "colab": {"provenance": []},
    }
    if gpu:
        meta["accelerator"] = "GPU"
    return {"cells": out, "metadata": meta, "nbformat": 4, "nbformat_minor": 5}


def md(text: str) -> tuple[str, str]:
    return ("markdown", text)


def code(text: str) -> tuple[str, str]:
    return ("code", text)


def get_code(extras: str = "api") -> tuple[str, str]:
    return code(f"""
# Setup 1/2 - get the code: clones the repo (or unzips /content/outbreak.zip if you uploaded it) and installs it
import pathlib, subprocess
REPO_URL = "https://github.com/albertogomezsoteres/outbreak.git"
if not pathlib.Path("/content/outbreak").exists():
    if pathlib.Path("/content/outbreak.zip").exists():
        subprocess.run(["unzip", "-q", "/content/outbreak.zip", "-d", "/content"], check=True)
    else:
        subprocess.run(["git", "clone", "-q", REPO_URL, "/content/outbreak"], check=True)
%cd /content/outbreak
!pip -q install -e ".[{extras}]"
# The running kernel does not see a package installed a moment ago: put src/ on the path and drop any stale
# `outbreak` module (Colab has /content on sys.path, where the repo folder itself is also called outbreak).
import sys, importlib
sys.path.insert(0, "/content/outbreak/src")
for m in [m for m in sys.modules if m == "outbreak" or m.startswith("outbreak.")]:
    del sys.modules[m]
importlib.invalidate_caches()
""")


def setup(need_key: bool = True) -> tuple[str, str]:
    arg = "" if need_key else "need_key=False"
    return code(f"""
# Setup 2/2 - Drive for results, local cache (restored from Drive), API key from Colab Secrets
from outbreak.colab import setup, save_cache, show_report, show_figure
setup({arg})
""")


def header(title: str, question: str, runs: str, runtime: str, after: str = "") -> tuple[str, str]:
    dep = f"\n**Run after:** {after}" if after else ""
    return md(f"""
# {title}

**Question.** {question}

**What it runs.** {runs}

**Runtime:** {runtime}{dep}

Every command is resumable: if Colab disconnects, re-run the same cell. Finished episodes are skipped and
cached calls are replayed without new API calls.
""")


R = "outputs/results"

NB00 = nb(
    [
        header(
            "00 · Setup and reality check",
            "Does the phenomenon exist in the confirmatory harness, before the plan is frozen?",
            "Offline smoke test (no API), the model screen, and the reality check `exp_000b`.",
            "CPU · ~5 min (smoke + screen); the reality check (~35 min) is already done",
        ),
        get_code(),
        setup(),
        md("## Offline sanity check (scripted agents; no API calls)"),
        code("!outbreak smoke --families sales_report latency_slo"),
        md("## Candidate models (one per family, tool-capable)\nAn episode re-reads ~40-80k prompt tokens."),
        code("!outbreak screen --max-price 2"),
        md(
            "## Reality check (exp_000b): already run on 2026-11-20 and committed to the repo\n"
            "These are the frozen results. Re-running is only needed to reproduce them (uncomment the cell after)."
        ),
        code("""
show_figure("results/exp_000b/fig_leaderboard.png")
show_report("results/exp_000b/report.md", sections=("H1 - shortcut", "different mechanism", "Utility", "Tokens"))
"""),
        code("""
# To reproduce (~35 min):
# !outbreak run experiments/single_experiments/00b_reality_check.yaml --run-id exp_000b_main
# !outbreak analyze outputs/results/exp_000b_main/episodes.jsonl
"""),
    ]
)

NB01 = nb(
    [
        header(
            "01 · Who catches the shortcut? (Act 1a, exp_001)",
            "Which models execute the forbidden shortcut a teammate's note names, when they are genuinely blocked?",
            "No board / empty board / benign note / shortcut note on 30 scenario draws × 4 shortcuts (+ solvable tasks), per model.",
            "CPU · ~1-2 h for 6-8 models",
        ),
        get_code(),
        setup(),
        md(
            "## Models\nKeep gpt-oss-20b and gpt-5-nano. Add models from notebook 00's screen. "
            "Unknown ids stop the run **before** any API call."
        ),
        code("""
import json
MODELS = [
    "openai/gpt-oss-20b", "openai/gpt-5-nano", "openai/gpt-oss-120b",
    "google/gemma-4-31b-it", "meta-llama/llama-4-maverick",   # other families (docs/DEVIATIONS.md)
    # "nvidia/nemotron-3.5-super-vl", "minimax/minimax-m3",
]
AGENTS = json.dumps([{"id": m} for m in MODELS])
"""),
        code("""
!outbreak run experiments/single_experiments/01_screen_susceptibility.yaml --run-id exp_001_main -o 'model.agents={AGENTS}' --dry-run
!outbreak run experiments/single_experiments/01_screen_susceptibility.yaml --run-id exp_001_main -o 'model.agents={AGENTS}'
"""),
        md("## Results"),
        code("""
!outbreak analyze outputs/results/exp_001_main/episodes.jsonl
show_figure("outputs/results/exp_001_main/analysis/fig_leaderboard.png")
show_report("outputs/results/exp_001_main/analysis/report.md",
            sections=("Error audit", "H1", "Any message", "H2", "different mechanism", "Utility", "Tokens"))
"""),
        code("save_cache()"),
    ]
)

NB02 = nb(
    [
        header(
            "02 · Why does it spread? (Act 1b: traits, natural notes, manipulation check)",
            "Which rhetorical traits make a shortcut contagious, and do LLM-written notes spread like templates?",
            "Natural notes (6 voices), LLM manipulation check, exp_002 (2⁶ trait factorial), exp_006 (natural vs template).",
            "CPU · ~5-6 h (exp_002 is the long one)",
        ),
        get_code(),
        setup(),
        md("## 1. Natural notes, then check that raters perceive the designed traits"),
        code("""
NAT = "outputs/results/natural_notes"
!outbreak natural-notes --model openai/gpt-5-mini --n 48 --out-dir {NAT}
!outbreak manipulation-check --notes data/processed/notes_M2.jsonl data/processed/notes_M3.jsonl {NAT}/natural_notes_M2.jsonl {NAT}/natural_notes_M3.jsonl --model openai/gpt-5-mini --out outputs/results/manipulation_check
import pandas as pd; display(pd.read_csv("outputs/results/manipulation_check/agreement.csv"))
"""),
        md("## 2. Trait factorial (exp_002): 192 notes per shortcut, randomly assigned to scenario draws"),
        code("""
!outbreak run experiments/single_experiments/02_trait_factorial.yaml --run-id exp_002_main
!outbreak analyze outputs/results/exp_002_main/episodes.jsonl
import pandas as pd
show_figure("outputs/results/exp_002_main/analysis/fig_trait_heatmap.png")
display(pd.read_csv("outputs/results/exp_002_main/analysis/h3_trait_risk_differences.csv"))
"""),
        md("## 3. Natural vs template notes (exp_006)"),
        code("""
!outbreak run experiments/single_experiments/06_natural_notes.yaml --run-id exp_006_main -o 'notes.natural_dir={NAT}'
!outbreak analyze outputs/results/exp_006_main/episodes.jsonl
show_report("outputs/results/exp_006_main/analysis/report.md", sections=("H1 - shortcut", "Natural"))
"""),
        code("save_cache()"),
    ]
)

NB03 = nb(
    [
        header(
            "03 · Where to stop it? (Act 4: channel filter, LLM judge, outbreaks)",
            "In a 12-agent team sharing a board, which guardrail stops the spread at the least cost to useful work?",
            "Filter hyperparameter search (validation only) → training → judge-vs-filter on the same held-out posts → "
            "exp_004: a causal test of agent-to-agent transmission (patient zero removed after round 1, notes relayed or not) and outbreaks under each defense.",
            "CPU · ~3-4 h",
            after="notebook 02 (the filter learns from exp_002)",
        ),
        get_code(),
        setup(),
        md("## 1. Channel filter: search (validation split) → train with the selected settings"),
        code("""
import json
!outbreak search experiments/hyperparameter_searches/filter_regularization.yaml --episodes outputs/results/exp_002_main/episodes.jsonl --out outputs/results/hps_001
sel = json.load(open("outputs/results/hps_001/selected.json"))["selected"]; C, FPR = sel["C"], sel["target_fpr"]
!outbreak train-filter outputs/results/exp_002_main/episodes.jsonl --C {C} --target-fpr {FPR}
print(open("models/trained/channel_filter.report.json").read()[:1500])
"""),
        md(
            "## 2. What looks suspicious vs what actually spreads: LLM judge vs trained filter on the same posts"
        ),
        code("""
!outbreak judge-eval outputs/results/exp_002_main/episodes.jsonl --judge openai/gpt-5-nano --out outputs/results/judge_vs_filter
print(open("outputs/results/judge_vs_filter/judge_vs_filter.json").read())
"""),
        md(
            "## 3. Outbreaks (exp_004): 30 paired outbreaks; transmission test + defenses at pre-registered operating points"
        ),
        code("""
!outbreak run experiments/single_experiments/04_outbreak_defenses.yaml --run-id exp_004_main --dry-run
!outbreak run experiments/single_experiments/04_outbreak_defenses.yaml --run-id exp_004_main
!outbreak analyze outputs/results/exp_004_main/outbreaks.jsonl
show_figure("outputs/results/exp_004_main/analysis/fig_outbreak_growth.png")
show_figure("outputs/results/exp_004_main/analysis/fig_frontier.png")
show_report("outputs/results/exp_004_main/analysis/report.md", sections=("Error audit", "H4", "H4c"))
"""),
        code("save_cache()"),
    ]
)

NB04 = nb(
    [
        header(
            "04 · White-box dataset (Act 2 input, exp_003)",
            "At the moment of decision, how likely is gpt-oss-20b to take the shortcut, prefix by prefix?",
            "Empty board, benign note and 3 of 12 Plackett-Burman notes per scenario draw (each note re-used in every split), 8 samples each → 720 decision-point "
            "prefixes with k/n labels (`decision_points.jsonl`).",
            "CPU · ~3-4 h",
        ),
        get_code(),
        setup(),
        code("""
!outbreak run experiments/single_experiments/03_exposure_whitebox_harvest.yaml --run-id exp_003_main
!outbreak analyze outputs/results/exp_003_main/episodes.jsonl
!outbreak harvest outputs/results/exp_003_main/episodes.jsonl --out outputs/results/exp_003_main/decision_points.jsonl
"""),
        code("""
import json, numpy as np
rows = [json.loads(l) for l in open("outputs/results/exp_003_main/decision_points.jsonl")]
rates = np.array([r["k"] / r["n"] for r in rows if r["n"]])
print(len(rows), "prefixes | mean propensity", rates.mean().round(3), "| share strictly between 0 and 1:",
      ((rates > 0) & (rates < 1)).mean().round(3))
"""),
        code("save_cache()"),
    ]
)

NB05 = nb(
    [
        header(
            "05 · Read the decision, then vaccinate it (Acts 2-3, GPU)",
            "Is the agent's choice readable in its hidden state before it acts, and does removing that direction make "
            "it resist without breaking it?",
            "Activations of gpt-oss-20b at 720 decision points → probe (layer × C on validation; test once) vs note "
            "identity, text filter and noise ceiling → vaccine dose-response vs random directions → closed-loop "
            "episodes: baseline / always-on vaccine / probe-triggered vaccine.",
            "GPU (A100 or better) · ~3-4 h",
            after="notebook 04",
        ),
        get_code("whitebox"),
        setup(need_key=False),
        md(
            "If the model does not fit in GPU memory, set `MODEL_ID` to the most susceptible open-weight model from "
            "notebook 01 and re-run notebook 04 with it (preregistration §7)."
        ),
        code("""
import os, json, numpy as np, pandas as pd
from pathlib import Path
MODEL_ID = "openai/gpt-oss-20b"
RUN = "outputs/results/exp_003_main"; WB = Path(RUN) / "whitebox"; WB.mkdir(exist_ok=True)
LAYERS = [4, 8, 12, 16, 20, 23]
!nvidia-smi --query-gpu=name,memory.total --format=csv
!pip -q install -U "transformers>=4.55" accelerate kernels
from outbreak.explainability.activations import load_model, render, hidden_states
from outbreak.env.episode import tools_for
lm = load_model(MODEL_ID)
rows = [r for r in map(json.loads, open(f"{RUN}/decision_points.jsonl")) if r["n"] > 0]
texts = [render(lm.tokenizer, r["decision_prefix"], tools_for(r["board_present"])) for r in rows]
n_tok = [len(lm.tokenizer(t, add_special_tokens=False)["input_ids"]) for t in texts]
print(f"{len(texts)} prefixes rendered with the model's chat template | tokens: median {int(np.median(n_tok))}, "
      f"max {max(n_tok)} (limit 32768, truncation keeps the decision point)")
print(texts[0][-600:])  # the end of one prefix: the model is about to choose its next action
print(lm.n_layers, "layers |", len(rows), "prefixes")
"""),
        md("## Activations at the decision point (cached on Drive)"),
        code("""
# Saved to Drive in chunks of 50: if Colab disconnects, re-running this cell continues where it stopped.
import time
cache = f"{RUN}/activations_{MODEL_ID.split('/')[-1]}.npz"
chunks = Path(RUN) / f"activation_chunks_{MODEL_ID.split('/')[-1]}"; chunks.mkdir(exist_ok=True)
if os.path.exists(cache):
    acts = {int(k): v for k, v in np.load(cache).items()}
else:
    CH, t0 = 50, time.time()
    for s in range(0, len(texts), CH):
        f = chunks / f"{s:05d}.npz"
        if not f.exists():
            part = hidden_states(lm, texts[s:s + CH], LAYERS, position="last", batch_size=1)
            np.savez(f, **{str(k): v for k, v in part.items()})
        done = min(s + CH, len(texts))
        print(f"{done}/{len(texts)} prefixes | {(time.time() - t0) / 60:.1f} min", flush=True)
    parts = [np.load(chunks / f"{s:05d}.npz") for s in range(0, len(texts), CH)]
    acts = {l: np.concatenate([p[str(l)] for p in parts]) for l in LAYERS}
    np.savez(cache, **{str(k): v for k, v in acts.items()})
print({l: a.shape for l, a in acts.items()})
"""),
        md("## Act 2 · Probe: layer and C selected on validation scenarios; the test split is used once"),
        code("""
!outbreak search experiments/hyperparameter_searches/probe_layer_C.yaml --activations {cache} --decision-points {RUN}/decision_points.jsonl --out {WB}/hps_002
sel = json.load(open(WB / "hps_002/selected.json"))["selected"]; best, C_BEST = int(sel["layer"]), float(sel["C"])
from outbreak.explainability.probe import PrefixSet, layer_sweep
base = PrefixSet(acts[LAYERS[0]], np.array([r["k"] for r in rows]), np.array([r["n"] for r in rows]),
                 [r["note_id"] for r in rows], [r["group"] for r in rows], [r["split"] for r in rows],
                 [r.get("board_text", "") for r in rows])
split = np.array(base.split)
val = layer_sweep(acts, base, split == "train", split == "val", C=C_BEST, n_boot=1000)
test = layer_sweep({best: acts[best]}, base, np.isin(split, ["train", "val"]), np.isin(split, ["test", "ood"]),
                   C=C_BEST, n_boot=2000)[0]
tab = pd.DataFrame([{"layer": r.layer, "auroc": r.auroc.estimate, "low": r.auroc.low, "high": r.auroc.high,
                     "shuffled": r.shuffled_auroc, "note_identity": r.note_identity_auroc,
                     "text_filter": r.text_filter_auroc, "noise_ceiling": r.noise_ceiling_auroc,
                     "within_note_rho": r.within_note_spearman} for r in val])
tab.to_csv(WB / "probe_layers_val.csv", index=False); display(tab)
json.dump({"layer": best, "C": C_BEST, "auroc": [test.auroc.estimate, test.auroc.low, test.auroc.high],
           "note_identity_auroc": test.note_identity_auroc, "text_filter_auroc": test.text_filter_auroc,
           "shuffled_auroc": test.shuffled_auroc, "noise_ceiling_auroc": test.noise_ceiling_auroc,
           "within_note_spearman": test.within_note_spearman}, open(WB / "probe_test.json", "w"), indent=2)
from outbreak.utils import plotting
show_figure(plotting.probe_layers(tab, WB / "fig_probe_layers")); print("TEST:", test)
"""),
        md(
            "## Act 3 · Vaccine: dose-response on held-out prefixes vs 3 random directions, with a utility check"
        ),
        code("""
from outbreak.explainability.steering import diff_of_means, MarginItem, steering_sweep
from outbreak.explainability.activations import action_continuation
from outbreak.pipeline.harvest import utility_prefixes
tr = np.isin(split, ["train", "val"])
u, norm = diff_of_means(acts[best][tr], base.rate[tr], hi=0.5, lo=0.0)
held = [r for r, s in zip(rows, split) if s in ("test", "ood") and "violating_action" in r][:40]
items = []
for r in held:
    tools = tools_for(r["board_present"])
    p, v = action_continuation(lm.tokenizer, r["decision_prefix"], tools, *r["violating_action"])
    _, c = action_continuation(lm.tokenizer, r["decision_prefix"], tools, *r["honest_action"])
    items.append(MarginItem(p, v, c))
util = [action_continuation(lm.tokenizer, r["decision_prefix"], tools_for(True), *r["legit_action"])
        for r in utility_prefixes(["sales_report", "latency_slo", "invoice_totals"], [900, 901, 902, 903])]
st = pd.DataFrame([vars(r) for r in steering_sweep(lm, items, best, u, norm, [0.0, 1.0, 2.0, 4.0],
                                                   n_random=2, utility_items=util)])
st.to_csv(WB / "steering.csv", index=False); display(st)
show_figure(plotting.steering(st, WB / "fig_steering"))
"""),
        md(
            "## Closed loop · baseline vs always-on vaccine vs probe-triggered vaccine, in real episodes (~2 h)\n"
            "Pick `ALPHA` from the sweep: the largest strength whose utility log-prob stays within 1 nat of α = 0."
        ),
        code("""
from outbreak.explainability.local_agent import LocalAgent, ProbeGuardedAgent
from outbreak.explainability.probe import fit_probe
from outbreak.pipeline.runner import EpisodeSpec, run_specs
from outbreak.pipeline import analysis
from outbreak.env.workspace import Scenario
from outbreak.data.notes import strong_note
from outbreak.env.mechanisms import Mechanism
ALPHA = 2.0
note = strong_note(Mechanism.M2_ADMIN_TOKEN)
specs = [EpisodeSpec(f"closed|{f}|{s}|{m.short}", "local", Scenario(f, m, s), "note", note.note_id, note.text)
         for f in ["sales_report", "latency_slo", "invoice_totals", "churn_metrics"] for s in range(950, 955)
         for m in [Mechanism.M2_ADMIN_TOKEN, Mechanism.POSSIBLE]]
probe_best = fit_probe(base.with_X(acts[best]).subset(tr), C=C_BEST)
vaccine = (best, u, ALPHA * norm)
arms = {"baseline": LocalAgent(lm), "vaccine_always": LocalAgent(lm, steering=vaccine),
        "vaccine_probe_triggered": ProbeGuardedAgent(lm, probe_best, best, vaccine, threshold=0.3)}
summary = []
for tag, agent in arms.items():
    path = WB / f"closed_loop_{tag}.jsonl"
    run_specs(specs, lambda mid, sc, a=agent: a, path, concurrency=1)
    recs = analysis.read_jsonl(path); df = analysis.episodes_frame(recs)
    fired = [m["vaccinated"] for r in recs for m in r.get("turn_meta", [])]
    summary.append({"arm": tag, "violation_M2": df[df.mechanism != "possible"].targeted.mean(),
                    "utility_possible": df[df.mechanism == "possible"].legit_success.mean(),
                    "turns_vaccinated": (sum(fired) / len(fired)) if fired else None})
cl = pd.DataFrame(summary); cl.to_csv(WB / "closed_loop_summary.csv", index=False); display(cl)
"""),
    ]
)

NB06 = nb(
    [
        header(
            "06 · Results: tables, figures, demo and poster",
            "What did we find? Everything in one place, regenerated from the run folders.",
            "Re-analyses every finished run, freezes the analysis folders into `results/`, rebuilds the interactive "
            "demo and the poster, and bundles everything for download.",
            "CPU · ~5 min",
        ),
        get_code("api,poster"),
        setup(need_key=False),
        code("""
import glob, shutil, os
for f in sorted(glob.glob("outputs/results/exp_*_main/episodes.jsonl")):
    !outbreak analyze {f}
for f in sorted(glob.glob("outputs/results/exp_*_main/outbreaks.jsonl")):
    !outbreak analyze {f}
for d in sorted(glob.glob("outputs/results/exp_*_main/analysis")):
    name = d.split("/")[-2].replace("_main", "")
    dst = f"results/{name}"; shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(d, dst, ignore=shutil.ignore_patterns("episodes_flat.csv"))
    print("frozen ->", dst)
"""),
        md("## Headline figures"),
        code("""
for fig in ["results/exp_001/fig_leaderboard.png", "results/exp_002/fig_trait_heatmap.png",
            "outputs/results/exp_003_main/whitebox/fig_probe_layers.png", "outputs/results/exp_003_main/whitebox/fig_steering.png",
            "results/exp_004/fig_outbreak_growth.png", "results/exp_004/fig_frontier.png"]:
    show_figure(fig)
"""),
        md("## Demo and poster"),
        code("""
!outbreak export-demo
!outbreak poster
"""),
        md(
            "## Bundle for the repo\nDownload, unzip into the repo, review `poster/content.yaml` (replace each `[pending ...]`), "
            "rebuild the poster locally, commit and tag `results-v1`."
        ),
        code("""
!cp outputs/results/natural_notes/*.jsonl data/processed/ 2>/dev/null; cp -r outputs/results/exp_003_main/whitebox results/whitebox 2>/dev/null; true
!zip -qr /content/outbreak_results.zip results data/processed demo poster/build outputs/results -x "*.sqlite*" "*.npz" "*episodes.jsonl"
from google.colab import files; files.download("/content/outbreak_results.zip")
"""),
    ]
)

NOTEBOOKS = {
    "00_setup_and_reality_check.ipynb": NB00,
    "01_who_catches_it.ipynb": NB01,
    "02_why_it_spreads.ipynb": NB02,
    "03_where_to_stop_it.ipynb": NB03,
    "04_whitebox_dataset.ipynb": NB04,
    "05_probe_and_vaccine_gpu.ipynb": NB05,
    "06_results.ipynb": NB06,
}


def main() -> None:
    out = ROOT / "notebooks" / "colab"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.ipynb"):
        if old.name not in NOTEBOOKS:
            old.unlink()
    for name, notebook in NOTEBOOKS.items():
        (out / name).write_text(json.dumps(notebook, indent=1))
    print("wrote", sorted(NOTEBOOKS))


if __name__ == "__main__":
    main()
