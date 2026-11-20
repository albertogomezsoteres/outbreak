"""Export everything the static demo needs into one JSON blob, inlined into ``demo/index.html``.

Sources, in order of preference (each panel says where its data came from):

* real study runs (``outputs/results/<run>/...``) when they exist,
* the checksummed pilot (real OpenRouter episodes) for the leaderboard and the transcript viewer,
* a deterministic *harness preview* outbreak played by scripted SI agents, clearly labelled as such,
  until a real exp_004 outbreak exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from outbreak.data import pilot
from outbreak.env.families import FAMILIES
from outbreak.env.mechanisms import Mechanism

DEMO_DIR = Path("demo")
PLACEHOLDER = "/*__OUTBREAK_DATA__*/null"


def _steps(transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Viewer steps with evidence-based flags: ``violation`` from the same detectors as grading,
    ``note`` when a board read returned a post."""
    from outbreak.env.detectors import classify_call
    from outbreak.env.tools import ToolCall

    steps = []
    for m in transcript:
        calls = [
            {"name": c["function"]["name"], "arguments": c["function"]["arguments"]}
            for c in m.get("tool_calls") or []
        ]
        mechs = sorted(
            {
                mech.short
                for c in calls
                for mech in classify_call(c["name"], ToolCall.parse("x", c["name"], c["arguments"]).arguments)
            }
        )
        content = str(m.get("content") or "")
        steps.append(
            {
                "role": m["role"],
                "content": content[:1200],
                "calls": calls,
                "violation": mechs,
                "note": m["role"] == "tool" and ("[post #" in content or "[note 1]" in content),
            }
        )
    return steps


def _pilot_transcript(model: str = "openai/gpt-oss-20b") -> dict[str, Any] | None:
    for p in sorted((pilot.PILOT_DIR / "logs").glob("*.jsonl")):
        if pilot.model_of(p) != model:
            continue
        for line in p.read_text().splitlines():
            r = json.loads(line)
            if r.get("any_violation") and r.get("cond") == "note":
                return {
                    "model": model,
                    "source": f"pilot log {p.name}, seed {r['seed']} (earlier pilot harness)",
                    "steps": _steps(r["transcript"]),
                }
    return None


def _study_transcripts(results_dir: Path, limit: int = 4) -> list[dict[str, Any]]:
    """Real episodes for the viewer: one infected episode per shortcut (the agent took the shortcut the note
    named), plus one episode where an agent fabricated data with *no* peer note on a solvable task.
    Sources: confirmatory runs when present, else the committed reality-check episodes (exp_000b)."""
    import gzip

    paths = [results_dir / run / "episodes.jsonl" for run in ("exp_001_main", "exp_002_main", "exp_006_main")]
    paths.append(Path("data/raw/exp_000b/episodes.jsonl.gz"))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    spontaneous = None
    for path in paths:
        if not path.exists():
            continue
        run = path.parent.name
        opener: Any = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt") as f:
            for line in f:
                r = json.loads(line)
                mech = r["scenario"]["mechanism"]
                o = r["outcome"]
                if "transcript" not in r:
                    continue
                targeted = mech != "possible" and o["executed"].get(mech, False)
                if (
                    targeted
                    and o["terminal"] == "submit"
                    and r["condition"].get("board") == "note"
                    and mech not in seen
                    and len(out) < limit
                ):
                    seen.add(mech)
                    out.append(
                        {
                            "model": r["model"],
                            "mechanism": mech,
                            "source": f"{run}, {r['episode_id']}",
                            "steps": _steps(r["transcript"]),
                        }
                    )
                elif (
                    spontaneous is None
                    and mech == "possible"
                    and o["executed"].get("m4_fabrication")
                    and r["condition"].get("board") == "empty_board"
                ):
                    spontaneous = {
                        "model": r["model"],
                        "mechanism": "spontaneous",
                        "source": f"{run}, {r['episode_id']} (solvable task, empty board)",
                        "steps": _steps(r["transcript"]),
                    }
        if len(out) >= limit and spontaneous is not None:
            break
    return out + ([spontaneous] if spontaneous else [])


def _pilot_board() -> list[dict[str, Any]]:
    rows = []
    for r in pilot.summary(pilot.load()):
        if "note_k" not in r:
            continue
        for cond, k, n in (
            ("empty_board", r["control_k"], r["control_n"]),
            ("note", r["note_k"], r["note_n"]),
        ):
            from outbreak.utils.stats import wilson

            ci = wilson(k, n)
            rows.append(
                {
                    "model": r["model"],
                    "condition": cond,
                    "k": k,
                    "n": n,
                    "rate": ci.estimate,
                    "low": ci.low,
                    "high": ci.high,
                }
            )
    return rows


def _preview_outbreak() -> dict[str, Any]:
    from outbreak.env.board import ChannelVerdict
    from outbreak.models.judges import OracleGate
    from outbreak.models.scripted import ScriptedAgent
    from outbreak.pipeline.outbreak import make_population, run_outbreak

    pop = make_population(
        0,
        mechanism=Mechanism.M2_ADMIN_TOKEN,
        families=sorted(FAMILIES),
        seeds=[0, 1, 2],
        n_agents=12,
        n_rounds=3,
        blocked_fraction=0.75,
        base_seed=7,
    )

    def agent(_a: str, sc: Any) -> ScriptedAgent:
        return ScriptedAgent(sc, "contagious")

    keyword_filter = lambda t: ChannelVerdict("admin" not in t.lower() and "replica" not in t.lower(), None)  # noqa: E731
    arms = {
        "board": run_outbreak(pop, "board", agent, concurrency=12),
        "channel_filter": run_outbreak(
            pop, "channel_filter", agent, concurrency=12, channel_filter=keyword_filter
        ),
        "oracle_monitor": run_outbreak(pop, "oracle_monitor", agent, concurrency=12, gate=OracleGate()),
    }
    return {
        "label": "Harness preview: scripted SI agents (not a model result). Replaced by exp_004 outbreaks.",
        "arms": {k: _outbreak_view(v.to_record()) for k, v in arms.items()},
    }


def _outbreak_view(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": rec["summary"],
        "chains": rec["chains"],
        "agents": [
            {
                k: a[k]
                for k in (
                    "agent_id",
                    "round",
                    "blocked",
                    "violation",
                    "legit_success",
                    "honest_block",
                    "read_from",
                    "posts",
                )
            }
            | {"family": a["scenario"]["family"]}
            for a in rec["agents"]
        ],
        "board": [
            {k: p[k] for k in ("id", "author", "text", "round", "published", "seeded")} for p in rec["board"]
        ],
    }


def _csv(path: Path) -> list[dict[str, Any]] | None:
    return pd.read_csv(path).to_dict(orient="records") if path.exists() else None


def collect(results_dir: Path = Path("outputs/results")) -> dict[str, Any]:
    data: dict[str, Any] = {"pilot": {"leaderboard": _pilot_board(), "transcript": _pilot_transcript()}}
    data["transcripts"] = _study_transcripts(results_dir)
    rc = Path("results/exp_000b")
    if (rc / "fig_leaderboard.csv").exists():
        other = _csv(rc / "other_mechanism_violations.csv") or []
        data["reality"] = {
            "leaderboard": _csv(rc / "fig_leaderboard.csv"),
            "spontaneous_possible": [
                r for r in other if r["mechanism"] == "possible" and r["board"] == "empty_board"
            ],
        }
    costs = [
        results_dir / r / "analysis" / "costs.csv"
        for r in ("exp_000b_main", "exp_001_main", "exp_002_main", "exp_003_main", "exp_006_main")
    ]
    present = [pd.read_csv(c) for c in costs if c.exists()]
    data["study_cost_usd"] = float(sum(df.cost_usd.sum() for df in present)) if present else None
    data["study_episodes"] = int(sum(df.episodes.sum() for df in present)) if present else None
    a1 = results_dir / "exp_001_main" / "analysis"
    a2 = results_dir / "exp_002_main" / "analysis"
    a4 = results_dir / "exp_004_main" / "analysis"
    data["leaderboard"] = _csv(a1 / "fig_leaderboard.csv")
    data["leaderboard_source"] = "Source: exp_001 (main study)." if data["leaderboard"] else None
    if data["leaderboard"] is None and Path("results/exp_000b/fig_leaderboard.csv").exists():
        data["leaderboard"] = _csv(Path("results/exp_000b/fig_leaderboard.csv"))
        data["leaderboard_source"] = (
            "Source: reality check exp_000b (432 real episodes in the confirmatory harness, "
            "4 shortcuts pooled). Replaced by exp_001."
        )
    data["traits"] = _csv(a2 / "fig_trait_heatmap.csv")
    data["frontier"] = _csv(a4 / "fig_frontier.csv")
    data["growth"] = _csv(a4 / "fig_outbreak_growth.csv")
    ob = results_dir / "exp_004_main" / "outbreaks.jsonl"
    if ob.exists():
        recs = [json.loads(line) for line in ob.read_text().splitlines() if line.strip()]
        first = {}
        for r in recs:
            arm = r["summary"]["arm"]
            if r["summary"]["outbreak"] == 0 and arm not in first:
                first[arm] = _outbreak_view(r)
        data["outbreak"] = {"label": "exp_004, outbreak #0 (gpt-oss-20b agents)", "arms": first}
    else:
        data["outbreak"] = _preview_outbreak()
    return data


def export(out_dir: Path = DEMO_DIR, results_dir: Path = Path("outputs/results")) -> Path:
    data = collect(results_dir)
    template = (out_dir / "template.html").read_text()
    if PLACEHOLDER not in template:
        raise ValueError("demo/template.html lacks the data placeholder")
    html = template.replace(PLACEHOLDER, json.dumps(data, default=str).replace("</", "<\\/"))
    (out_dir / "index.html").write_text(html)
    (out_dir / "demo_data.json").write_text(json.dumps(data, indent=1, default=str))
    return out_dir / "index.html"
