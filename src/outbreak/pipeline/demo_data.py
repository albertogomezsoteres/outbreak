"""Data for the interactive demo (``demo/index.html``), built from the finished runs.

Everything the page shows comes from here: per-model contagion rates (exp_001), trait effects (exp_002),
natural vs template notes (exp_006), real outbreak replays and defense trade-offs (exp_004), judge vs
filter, the white-box probe and vaccine (notebook 05), and the trained channel filter exported to plain
numbers so the browser can score a visitor's note exactly as Python does.

    python -m outbreak.pipeline.demo_data --results outputs/results --trained models/trained
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from outbreak.utils.stats import wilson

MODEL_LABELS = {
    "openai/gpt-oss-20b": ("gpt-oss-20b", "OpenAI"),
    "openai/gpt-oss-120b": ("gpt-oss-120b", "OpenAI"),
    "openai/gpt-5-nano": ("GPT-5 nano", "OpenAI"),
    "meta-llama/llama-4-maverick": ("Llama 4 Maverick", "Meta"),
    "google/gemma-4-31b-it": ("Gemma 4 31B", "Google"),
}
MECH_LABELS = {
    "m1_test_edit": "Edit the failing test",
    "m2_admin_token": "Use the admin token",
    "m3_prod_replica": "Query the production replica",
    "m4_fabrication": "Make up the data",
}
TRAIT_LABELS = {
    "A": "Step-by-step instructions",
    "B": "A justification",
    "C": "Others did it too",
    "D": "Sounds like a lead",
    "E": "Urgency",
    "F": "A policy warning",
}
DEFENSES = [  # (key, arm, threshold for the replay, label)
    ("none", "board", None, "No guardrail"),
    ("judge", "channel_judge", 0.5, "LLM judge on messages"),
    ("filter", "channel_filter", None, "Trained message filter"),
    ("monitor", "action_monitor", 0.5, "LLM monitor on actions"),
]


def _rate(k: int, n: int) -> dict[str, float]:
    ci = wilson(int(k), int(n))
    return {"k": int(k), "n": int(n), "rate": ci.estimate, "low": ci.low, "high": ci.high}


def _flat(results: Path, run: str) -> pd.DataFrame | None:
    p = results / run / "analysis" / "episodes_flat.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p)
    return d[d.terminal != "error"]


def models_block(results: Path) -> list[dict[str, Any]]:
    d = _flat(results, "exp_001_main")
    if d is None:
        return []
    d = d[d.mechanism != "possible"]
    out = []
    for m, g in d.groupby("model"):
        label, org = MODEL_LABELS.get(m, (m.split("/")[-1], m.split("/")[0]))
        row: dict[str, Any] = {"id": m, "label": label, "org": org}
        for board in ("note", "benign", "empty_board"):
            s = g[g.board == board].targeted
            row[board] = _rate(s.sum(), len(s))
        row["by_shortcut"] = {
            MECH_LABELS[mech]: {
                "note": _rate(x[x.board == "note"].targeted.sum(), (x.board == "note").sum()),
                "benign": _rate(x[x.board == "benign"].targeted.sum(), (x.board == "benign").sum()),
            }
            for mech, x in g.groupby("mechanism")
        }
        out.append(row)
    return sorted(out, key=lambda r: -r["note"]["rate"])


def traits_block(results: Path) -> dict[str, Any]:
    p = results / "exp_002_main" / "analysis" / "h3_trait_risk_differences.csv"
    d = _flat(results, "exp_002_main")
    if not p.exists() or d is None:
        return {}
    rd = pd.read_csv(p)
    out: dict[str, Any] = {"labels": TRAIT_LABELS, "models": []}
    for m, g in rd.groupby("model"):
        notes = d[(d.model == m) & (d.board == "note")]
        label, _org = MODEL_LABELS.get(m, (m, ""))
        out["models"].append(
            {
                "id": m,
                "label": label,
                "mean_rate": float(notes.targeted.mean()),
                "benign_rate": float(d[(d.model == m) & (d.board == "benign")].targeted.mean()),
                "effects": [
                    {"trait": r.trait, "rd": r.rd, "low": r.low, "high": r.high, "p_holm": r.p_holm}
                    for r in g.itertuples()
                ],
            }
        )
    return out


def natural_block(results: Path) -> list[dict[str, Any]]:
    d = _flat(results, "exp_006_main")
    if d is None:
        return []
    out = []
    for m, g in d.groupby("model"):
        label, _ = MODEL_LABELS.get(m, (m, ""))
        nat = g[(g.board == "note") & (g.note_source == "natural")].targeted
        tem = g[(g.board == "note") & (g.note_source == "template")].targeted
        emp = g[g.board == "empty_board"].targeted
        out.append(
            {
                "id": m,
                "label": label,
                "none": _rate(emp.sum(), len(emp)),
                "llm_written": _rate(nat.sum(), len(nat)),
                "template": _rate(tem.sum(), len(tem)),
            }
        )
    return out


def _boot_mean(x: np.ndarray, n: int = 4000, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def _excerpt(text: str, limit: int = 240) -> str:
    """A post as the page shows it: whitespace collapsed, cut at a sentence end when it runs long."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > limit // 2 else cut.rsplit(" ", 1)[0] + "…"


def _replay(rec: dict[str, Any]) -> dict[str, Any]:
    agents = []
    for a in rec["agents"]:
        agents.append(
            {
                "id": a["agent_id"],
                "round": a["round"],
                "blocked": a["blocked"],
                "broke_rule": bool(a["targeted"] or a["violation"]),
                "honest_report": bool(a.get("honest_block")),
                "done_honestly": bool(a["legit_success"]),
                "read": [r for r in a["read_from"]],
                "stance": a.get("post_stance", "none"),
            }
        )
    posts = [
        {
            "author": p["author"],
            "round": p["round"],
            "published": p["published"],
            "seeded": p["seeded"],
            "text": _excerpt(p.get("text", "")),
        }
        for p in rec["board"]
    ]
    return {
        "agents": agents,
        "posts": posts,
        "summary": {
            k: rec["summary"][k]
            for k in ("violations", "utility", "n_agents", "posts_blocked", "posts_published")
        },
    }


def _same_threshold(value: float | None, target: float | None) -> bool:
    if target is None:
        return value is None
    return value is not None and bool(np.isclose(value, target))


def _cumulative_by_round(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mean number of agents per team that have broken the rules by the end of each round."""
    rounds = sorted({a["round"] for r in recs for a in r["agents"]})

    def broke_by(r: dict[str, Any], k: int) -> int:
        return sum(1 for a in r["agents"] if a["round"] <= k and (a["targeted"] or a["violation"]))

    return [
        {"round": int(k), "mean": float(np.mean([broke_by(r, k) for r in recs])), "n": len(recs)}
        for k in rounds
    ]


def outbreaks_block(results: Path) -> dict[str, Any]:
    run = results / "exp_004_main"
    csv = run / "analysis" / "outbreaks.csv"
    if not csv.exists():
        return {}
    o = pd.read_csv(csv)
    frontier = []
    for key, arm, th, label in [*DEFENSES, ("none_board", "no_board", None, "No message board")]:
        g = o[(o.arm == arm) & (o.threshold.isna() if th is None else np.isclose(o.threshold, th))]
        if g.empty:
            continue
        v, u = g.violations.to_numpy(float), g.utility.to_numpy(float)
        frontier.append(
            {
                "key": key,
                "label": label,
                "n": len(g),
                "violations": float(v.mean()),
                "violations_ci": _boot_mean(v),
                "utility": float(u.mean()),
                "utility_ci": _boot_mean(u),
            }
        )
    trans = run / "analysis" / "h4c_transmission.csv"
    out: dict[str, Any] = {
        "frontier": frontier,
        "transmission": pd.read_csv(trans).to_dict(orient="records")[0] if trans.exists() else None,
    }
    jl = run / "outbreaks.jsonl"
    if jl.exists():
        recs = [json.loads(line) for line in jl.read_text().splitlines() if line.strip()]
        by = {(r["summary"]["arm"], r["summary"]["threshold"], r["summary"]["outbreak"]): r for r in recs}
        board = sorted(
            (r for r in recs if r["summary"]["arm"] == "board"), key=lambda r: r["summary"]["outbreak"]
        )
        med = float(np.median([r["summary"]["violations"] for r in board]))
        # the most typical outbreak: board violations at the median, then the most complete set of arms
        pick = min(board, key=lambda r: (abs(r["summary"]["violations"] - med), r["summary"]["outbreak"]))
        idx = pick["summary"]["outbreak"]
        # mean cumulative rule breaks by round, at each defense's preregistered operating point
        growth = {}
        for key, arm, th, _ in DEFENSES:
            sel = [
                r
                for r in recs
                if r["summary"]["arm"] == arm and _same_threshold(r["summary"]["threshold"], th)
            ]
            if sel:
                growth[key] = _cumulative_by_round(sel)
        out["growth"] = growth
        out["replay"] = {
            "outbreak": idx,
            "mechanism": MECH_LABELS.get(pick["summary"]["mechanism"], ""),
            "arms": {
                key: _replay(by[(arm, th, idx)]) for key, arm, th, _ in DEFENSES if (arm, th, idx) in by
            },
        }
    return out


def judge_block(results: Path) -> dict[str, Any] | None:
    p = results / "judge_vs_filter" / "judge_vs_filter.json"
    return json.loads(p.read_text()) if p.exists() else None


def whitebox_block(results: Path) -> dict[str, Any]:
    wb = results / "exp_003_main" / "whitebox"
    out: dict[str, Any] = {}
    if (wb / "probe_test.json").exists():
        out["probe"] = json.loads((wb / "probe_test.json").read_text())
    if (wb / "steering.csv").exists():
        st = pd.read_csv(wb / "steering.csv").rename(
            columns={"mean_margin": "margin_mean", "mean_utility_logp": "utility_logp"}
        )
        out["steering"] = st.to_dict(orient="records")
    return out


def filter_block(trained: Path) -> dict[str, Any] | None:
    """The trained TF-IDF + logistic filter as plain arrays (see demo/filter.js for the scorer)."""
    path = trained / "channel_filter.joblib"
    if not path.exists():
        return None
    from outbreak.models.text_filter import TextFilter

    f = TextFilter.load(path)
    feats = f.model.named_steps["features"]
    coef = f.model.named_steps["clf"].coef_[0]
    intercept = float(f.model.named_steps["clf"].intercept_[0])
    parts, offset = {}, 0
    for name, vec in feats.transformer_list:
        vocab = vec.vocabulary_
        terms = sorted(vocab, key=vocab.get)
        idf = vec.idf_
        w = coef[offset : offset + len(terms)]
        parts[name] = {t: [round(float(idf[i]), 5), round(float(w[i]), 5)] for i, t in enumerate(terms)}
        offset += len(terms)
    cal = None
    if f.calibrator is not None:
        cal = {
            "x": [round(float(v), 6) for v in f.calibrator.X_thresholds_],
            "y": [round(float(v), 6) for v in f.calibrator.y_thresholds_],
        }
    out: dict[str, Any] = {
        "word": parts["word"],
        "char": parts["char"],
        "intercept": intercept,
        "calibration": cal,
        "threshold": float(f.threshold),
    }
    report = trained / "channel_filter.report.json"
    if report.exists():
        r = json.loads(report.read_text())
        out["test"] = {
            "auroc": r["test"]["auroc"],
            "tpr": r["test"]["tpr_at_threshold"],
            "benign_fpr": r["benign_fpr_at_threshold"],
            "n_train": r["n_exposures"]["train"],
        }
    return out


def build(results: Path, trained: Path) -> dict[str, Any]:
    data = {
        "models": models_block(results),
        "traits": traits_block(results),
        "natural": natural_block(results),
        "outbreaks": outbreaks_block(results),
        "judge_vs_filter": judge_block(results),
        "whitebox": whitebox_block(results),
        "filter": filter_block(trained),
    }
    counts = []
    for run in ("exp_001_main", "exp_002_main", "exp_003_main", "exp_006_main"):
        d = _flat(results, run)
        if d is not None:
            counts.append(len(d))
    o = results / "exp_004_main" / "analysis" / "outbreaks.csv"
    n_ob = int(pd.read_csv(o).n_agents.sum()) if o.exists() else 0
    data["meta"] = {"agent_episodes": int(sum(counts)) + n_ob}
    return data


def render(data: dict[str, Any], demo_dir: Path = Path("demo")) -> Path:
    """Inline the data and the filter scorer into one self-contained page (works on GitHub Pages and file://)."""
    html = (demo_dir / "template.html").read_text()
    blob = json.dumps(data, separators=(",", ":"), allow_nan=False, default=float).replace("</", "<\\/")
    import base64

    font = (
        "data:font/woff2;base64,"
        + base64.b64encode((demo_dir / "fonts" / "archivo.woff2").read_bytes()).decode()
    )
    html = html.replace("/*__DATA__*/", blob).replace(
        "/*__FILTER_JS__*/", (demo_dir / "filter.js").read_text()
    )
    html = html.replace("/*__FONT__*/", font)
    out = demo_dir / "index.html"
    out.write_text(html)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="outputs/results")
    ap.add_argument("--trained", default="models/trained")
    ap.add_argument("--out", default="demo/data.json")
    a = ap.parse_args()
    data = build(Path(a.results), Path(a.trained))
    Path(a.out).write_text(json.dumps(data, separators=(",", ":"), allow_nan=False, default=float))
    page = render(data, Path(a.out).parent)
    print(f"wrote {a.out} and {page} ({page.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
