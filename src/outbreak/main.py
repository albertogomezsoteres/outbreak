"""Single entry point: ``outbreak <command>`` (also ``python -m outbreak``).

Commands
--------
smoke          offline end-to-end harness check with scripted agents (no API key needed)
run CONFIG     run an experiment YAML (bench | exposure | outbreak), resumable
analyze PATH   tables, tests and figures from an episodes.jsonl or outbreaks.jsonl
train-filter   train + calibrate the channel filter on bench episodes (scenario splits)
search CONFIG  hyperparameter search (channel filter or probe), validation split only
natural-notes  LLM-written peer notes for the external-validity experiment
manipulation-check  LLM rater codes note traits; agreement with the factorial design
judge-eval     LLM channel judge vs trained filter on the same held-out posts
harvest        build the white-box decision-point dataset from episodes
notes          export the factorial notes for a mechanism
splits         write the frozen scenario split file
power          Monte-Carlo power for the planned sample sizes, from the pilot rates
pilot          reproduce the pilot table from the checksummed raw logs
screen         list tool-capable OpenRouter models under a price cap (needs network)
export-demo    rebuild demo/data.json and demo/index.html from the finished runs and the trained filter
poster         render the 36x24 in poster (HTML + PDF) from poster/poster.html and demo/data.json
serve          start the filter scoring API (FastAPI)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger("outbreak")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("httpx", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------------------- smoke
def cmd_smoke(args: argparse.Namespace) -> int:
    from outbreak.env import FAMILIES, Board, Mechanism, Scenario, run_episode
    from outbreak.models.scripted import ScriptedAgent

    fams = args.families or sorted(FAMILIES)
    failures = 0
    print(f"{'family':20s} {'mech':4s} {'policy':6s} {'terminal':15s} viol legit block")
    for fam in fams:
        for mech in Mechanism:
            for strat in ("honest", "cheat"):
                sc = Scenario(fam, mech, args.seed)
                o = run_episode(
                    ScriptedAgent(sc, strat), sc, Board(), episode_id=f"smoke|{sc.id}|{strat}", seed=0
                ).outcome
                expect_violation = strat == "cheat" and mech.impossible
                expect_legit = not mech.impossible
                expect_block = strat == "honest" and mech.impossible
                ok = (
                    o.violation == expect_violation
                    and o.legit_success == expect_legit
                    and o.honest_block == expect_block
                )
                failures += not ok
                print(
                    f"{fam:20s} {mech.short:4s} {strat:6s} {o.terminal:15s} {int(o.violation):4d} "
                    f"{int(o.legit_success):5d} {int(o.honest_block):5d} {'' if ok else '  <-- UNEXPECTED'}"
                )
    print("SMOKE OK" if not failures else f"SMOKE FAILED ({failures} unexpected outcomes)")
    return 1 if failures else 0


# ---------------------------------------------------------------------------------------- run
def cmd_run(args: argparse.Namespace) -> int:
    from outbreak.utils.config import load_config, parse_override
    from outbreak.utils.manifest import new_run_id, write_manifest

    overrides = dict(parse_override(o) for o in args.override or [])
    cfg = load_config(args.config, overrides)
    run_id = args.run_id or new_run_id(cfg.experiment_id)
    run_dir = Path(cfg.run.output_dir) / run_id
    _log_to_file(Path("outputs/logs") / f"{run_id}.log")
    log.info("experiment %s (%s) -> %s", cfg.experiment_id, cfg.run.runner, run_dir)
    write_manifest(
        run_dir,
        run_id=run_id,
        status="started",
        config_path=str(args.config),
        config_hash=cfg.config_hash,
        config=cfg.model_dump(mode="json"),
        overrides=overrides,
    )
    if cfg.run.runner in {"bench", "exposure"}:
        stats = _run_episodes(cfg, run_dir, dry=args.dry_run)
    elif cfg.run.runner == "outbreak":
        stats = _run_outbreaks(cfg, run_dir, dry=args.dry_run)
    else:
        raise SystemExit(f"runner {cfg.run.runner!r} is not launched with `run` (see `outbreak --help`)")
    write_manifest(
        run_dir,
        run_id=run_id,
        status="dry_run" if args.dry_run else "finished",
        config_path=str(args.config),
        config_hash=cfg.config_hash,
        config=cfg.model_dump(mode="json"),
        overrides=overrides,
        stats=stats,
    )
    _wandb_log(cfg, run_id, stats, dry=args.dry_run)
    print(json.dumps(stats, indent=2, default=str))
    if stats.get("stopped"):
        print(f"\nRUN STOPPED: {stats['stopped']}")
        return 1
    return 0


def _log_to_file(path: Path) -> None:
    """Centralised, append-only log per run (outputs/logs/<run_id>.log) in addition to the console."""
    path.parent.mkdir(parents=True, exist_ok=True)
    h = logging.FileHandler(path)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(h)


def _wandb_log(cfg: Any, run_id: str, stats: dict[str, Any], dry: bool) -> None:
    """Optional experiment tracking: active only if WANDB_PROJECT is set and wandb is installed."""
    import os

    if dry or not os.environ.get("WANDB_PROJECT"):
        return
    try:
        import wandb
    except ImportError:
        log.warning("WANDB_PROJECT is set but wandb is not installed (pip install -e '.[tracking]')")
        return
    run = wandb.init(
        project=os.environ["WANDB_PROJECT"],
        name=run_id,
        config=cfg.model_dump(mode="json"),
        tags=cfg.tags,
        reinit=True,
    )
    run.summary.update({k: v for k, v in stats.items() if isinstance(v, int | float | bool)})
    run.finish()


def _run_episodes(cfg: Any, run_dir: Path, dry: bool) -> dict[str, Any]:
    from outbreak.env.episode import EpisodeConfig
    from outbreak.pipeline.experiments import bench_specs, exposure_specs
    from outbreak.pipeline.factory import ModelFactory
    from outbreak.pipeline.runner import run_specs

    try:
        specs = list((bench_specs if cfg.run.runner == "bench" else exposure_specs)(cfg))
    except FileNotFoundError as e:  # e.g. natural notes not generated yet
        if dry:
            return {"planned_episodes": None, "missing_input": str(e)}
        raise SystemExit(str(e)) from e
    log.info("%d episodes planned", len(specs))
    if dry:
        return {"planned_episodes": len(specs), "example": specs[0].episode_id if specs else None}
    _preflight(cfg)
    factory = ModelFactory(cfg)

    def progress(i: int, n: int, res: Any) -> None:
        if i % 10 == 0 or i == n:
            log.info("%d/%d episodes | spend $%.4f", i, n, factory.budget.spent_usd)

    stats = run_specs(
        specs,
        factory,
        run_dir / "episodes.jsonl",
        concurrency=cfg.model.concurrency,
        episode_cfg=EpisodeConfig(max_steps=cfg.model.max_steps),
        progress=progress,
    )
    stats.update(
        planned=len(specs), spend_usd=round(factory.budget.spent_usd, 6), api_calls=factory.budget.calls
    )
    return stats


def _run_outbreaks(cfg: Any, run_dir: Path, dry: bool) -> dict[str, Any]:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from outbreak.env.episode import EpisodeConfig
    from outbreak.pipeline.factory import ModelFactory, action_gate, channel_defense
    from outbreak.pipeline.outbreak import make_population, run_outbreak
    from outbreak.pipeline.runner import done_ids

    oc = cfg.outbreak
    if len(cfg.model.agents) != 1:
        raise SystemExit("outbreak runs use exactly one agent model (homogeneous team)")
    agent = cfg.model.agents[0].id
    jobs = []
    for k in range(oc.n_outbreaks):
        mech = cfg.dataset.mechanisms[k % len(cfg.dataset.mechanisms)]
        pop = make_population(
            k,
            mechanism=mech,
            families=cfg.dataset.families,
            seeds=cfg.dataset.seeds,
            n_agents=oc.n_agents,
            n_rounds=oc.n_rounds,
            blocked_fraction=oc.blocked_fraction,
            base_seed=cfg.reproducibility.seed,
        )
        for arm in oc.arms:
            thresholds: list[float | None] = [None]
            if arm in {"channel_judge", "action_monitor"}:
                thresholds = sorted(
                    {
                        *oc.thresholds,
                        *(t for t in [cfg.evaluation.confirmatory_thresholds.get(arm)] if t is not None),
                    }
                )
            elif arm == "channel_filter":  # None = calibrated threshold (confirmatory) + the swept ones
                thresholds = [None, *oc.thresholds]
            for th in thresholds:
                jobs.append((pop, arm, th))
    log.info("%d outbreak runs planned (%d agents each)", len(jobs), oc.n_agents)
    if dry:
        return {"planned_outbreak_runs": len(jobs), "planned_episodes": len(jobs) * oc.n_agents}
    _preflight(cfg)
    factory = ModelFactory(cfg)
    out = run_dir / "outbreaks.jsonl"
    done = done_ids(out) if out.exists() else set()
    todo = [(pop, arm, th) for pop, arm, th in jobs if f"ob{pop.outbreak}|{arm}|{th}" not in done]
    lock = threading.Lock()
    n = 0

    def play(job: tuple[Any, str, float | None]) -> None:
        nonlocal n
        pop, arm, th = job
        key = f"ob{pop.outbreak}|{arm}|{th}"
        res = run_outbreak(
            pop,
            arm,
            lambda _aid, sc: factory(agent, sc),
            channel_filter=channel_defense(arm, factory, th),  # type: ignore[arg-type]
            gate=action_gate(arm, factory, th),  # type: ignore[arg-type]
            threshold=th,
            episode_cfg=EpisodeConfig(max_steps=cfg.model.max_steps, handoff_protocol=oc.handoff_protocol),
            concurrency=cfg.model.concurrency,
            keep_transcripts=True,
            experiment_id=cfg.experiment_id,
        )
        rec = {"episode_id": key, **res.to_record()}
        s = res.summary()
        with lock:
            f.write(json.dumps(rec, default=str) + "\n")
            f.flush()
            n += 1
            log.info(
                "%s: violations=%s utility=%s spend=$%.4f (%d/%d)",
                key,
                s["violations"],
                s["utility"],
                factory.budget.spent_usd,
                n,
                len(todo),
            )

    with open(out, "a") as f, ThreadPoolExecutor(max_workers=max(1, oc.parallel_outbreaks)) as pool:
        for fut in [pool.submit(play, j) for j in todo]:
            fut.result()  # re-raise (e.g. budget exhausted) instead of failing silently
    return {"outbreak_runs": n, "spend_usd": round(factory.budget.spent_usd, 6)}


def _preflight(cfg: Any) -> None:
    """Fail fast (before any spend) on a missing key or a model id OpenRouter does not serve."""
    import os

    if cfg.model.provider != "openrouter":
        return
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY is not set (Colab: Secrets panel; local: export it or use .env)")
    from outbreak.models.discovery import fetch_models

    try:
        available = {m["id"]: m for m in fetch_models()}
    except OSError as e:
        log.warning("could not reach the OpenRouter model list (%s); skipping id validation", e)
        return
    wanted = [a.id for a in cfg.model.agents] + ([cfg.model.judge.id] if cfg.model.judge else [])
    unknown = [m for m in wanted if m not in available]
    if unknown:
        raise SystemExit(f"unknown OpenRouter model ids: {unknown}. Run `outbreak screen` for valid ids.")
    no_tools = [
        a.id for a in cfg.model.agents if "tools" not in (available[a.id].get("supported_parameters") or [])
    ]
    if no_tools:
        raise SystemExit(f"models without tool calling: {no_tools}")


# ---------------------------------------------------------------------------------------- analysis
def cmd_analyze(args: argparse.Namespace) -> int:
    from outbreak.pipeline import analysis

    path = Path(args.path)
    out = Path(args.out) if args.out else path.parent / "analysis"
    kind = args.kind or ("outbreaks" if "outbreak" in path.name else "episodes")
    files = (
        analysis.analyze_outbreaks(path, out, margin=args.margin)
        if kind == "outbreaks"
        else analysis.analyze_episodes(path, out)
    )
    for k, v in files.items():
        print(f"{k:12s} {v}")
    return 0


def cmd_train_filter(args: argparse.Namespace) -> int:
    from outbreak.pipeline.filter_training import train_filter

    report = train_filter(
        [Path(p) for p in args.episodes], Path(args.out), target_fpr=args.target_fpr, C=args.C
    )
    print(json.dumps(report, indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    import numpy as np

    from outbreak.pipeline import search

    cfg = search.load_search(args.config)
    out_dir = Path(args.out or f"outputs/results/{cfg.experiment_id}")
    if cfg.target == "channel_filter":
        if not args.episodes:
            raise SystemExit("channel_filter search needs --episodes")
        df = search.search_channel_filter(cfg, [Path(p) for p in args.episodes])
    else:
        if not (args.activations and args.decision_points):
            raise SystemExit("probe search needs --activations (.npz) and --decision-points (.jsonl)")
        acts = {int(k): v for k, v in np.load(args.activations).items()}
        rows = [
            json.loads(line) for line in Path(args.decision_points).read_text().splitlines() if line.strip()
        ]
        rows = [r for r in rows if r["n"] > 0]
        df = search.search_probe(cfg, acts, rows)
    path = search.write_search(df, out_dir, cfg)
    print(df.head(10).to_string(index=False))
    print(f"selected -> {path}")
    return 0


def cmd_natural_notes(args: argparse.Namespace) -> int:
    from outbreak.data import natural_notes
    from outbreak.env.mechanisms import IMPOSSIBLE, Mechanism
    from outbreak.pipeline.factory import standalone_client

    client = standalone_client(args.model, max_usd=args.max_usd, temperature=1.0)
    mechs = [Mechanism(m) for m in args.mechanism] if args.mechanism else list(IMPOSSIBLE)
    for mech in mechs:
        notes = natural_notes.generate(client, mech, args.n, seed=args.seed)
        path = natural_notes.save(notes, natural_notes.default_path(mech, Path(args.out_dir)))
        usable = sum(n.mentions_shortcut for n in notes)
        print(f"{mech.value}: {len(notes)} notes ({usable} name the shortcut) -> {path}")
    print(f"spend ${client.budget.spent_usd:.4f}" if client.budget else "")
    return 0


def cmd_manipulation_check(args: argparse.Namespace) -> int:
    from outbreak.data import manipulation
    from outbreak.pipeline.factory import standalone_client

    client = standalone_client(args.model, max_usd=args.max_usd)
    notes = [
        json.loads(line) for p in args.notes for line in Path(p).read_text().splitlines() if line.strip()
    ]
    df = manipulation.rate(client, notes)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "ratings.csv", index=False)
    agree = manipulation.agreement(df)
    agree.to_csv(out / "agreement.csv", index=False)
    print(f"parsed {int(df.parsed.sum())}/{len(df)} ratings; spend ${client.budget.spent_usd:.4f}")  # type: ignore[union-attr]
    if not agree.empty:
        print(agree.to_string(index=False))
    return 0


def cmd_judge_eval(args: argparse.Namespace) -> int:
    from outbreak.pipeline.factory import standalone_client
    from outbreak.pipeline.judge_eval import evaluate

    client = standalone_client(args.judge, max_usd=args.max_usd)
    rep = evaluate(
        client,
        [Path(p) for p in args.episodes],
        Path(args.filter),
        Path(args.out),
        judge_threshold=args.threshold,
    )
    print(json.dumps(rep, indent=2))
    return 0


def cmd_harvest(args: argparse.Namespace) -> int:
    from outbreak.pipeline.harvest import build_decision_points, write_decision_points
    from outbreak.pipeline.runner import read_episodes

    eps = [e for p in args.episodes for e in read_episodes(Path(p))]
    rows = build_decision_points(eps)
    path = write_decision_points(rows, Path(args.out))
    print(f"{len(rows)} unique decision points from {len(eps)} episodes -> {path}")
    return 0


def cmd_notes(args: argparse.Namespace) -> int:
    from outbreak.data.notes import factorial_notes, pb12_notes
    from outbreak.env.mechanisms import Mechanism

    mech = Mechanism(args.mechanism)
    if args.design == "pb12":  # the 12 white-box notes (exp_003), re-used across splits
        notes = pb12_notes(mech, seed=args.seed)
        default = f"data/processed/notes_pb12_{mech.short}.jsonl"
    else:  # full 2^6 factorial x draws (exp_002, manipulation check)
        notes = factorial_notes(mech, args.draws, seed=args.seed)
        default = f"data/processed/notes_{mech.short}.jsonl"
    out = Path(args.out or default)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(n.to_dict()) + "\n" for n in notes))
    print(f"{len(notes)} notes -> {out}")
    return 0


def cmd_splits(args: argparse.Namespace) -> int:
    from outbreak.data.splits import write_split_file
    from outbreak.env.families import FAMILIES

    table = write_split_file(Path(args.out), sorted(FAMILIES), list(range(args.n_seeds)))
    counts: dict[str, int] = {}
    for v in table.values():
        counts[v] = counts.get(v, 0) + 1
    print(f"{args.out}: {counts}")
    return 0


def cmd_power(args: argparse.Namespace) -> int:
    from outbreak.pipeline.power import power_report

    print(power_report(n_sims=args.sims))
    return 0


def cmd_pilot(args: argparse.Namespace) -> int:
    from outbreak.data import pilot

    bad = [k for k, ok in pilot.verify_checksums().items() if not ok]
    if bad:
        print(f"checksum mismatch: {bad}")
        return 1
    for row in pilot.summary(pilot.load()):
        print(json.dumps(row))
    return 0


def cmd_screen(args: argparse.Namespace) -> int:
    from outbreak.models.discovery import discover

    for m in discover(args.max_price, per_family=not args.all):
        print(f"{m['id']:55s} prompt=${m['prompt']:.3f}/M completion=${m['completion']:.3f}/M")
    return 0


def cmd_export_demo(args: argparse.Namespace) -> int:
    import json

    from outbreak.pipeline.demo_data import build as build_data
    from outbreak.pipeline.demo_data import render

    demo_dir = Path(args.demo_dir)
    data = build_data(Path(args.results), Path(args.trained))
    (demo_dir / "data.json").write_text(
        json.dumps(data, separators=(",", ":"), allow_nan=False, default=float)
    )
    print(f"demo written to {render(data, demo_dir)}")
    return 0


def cmd_poster(args: argparse.Namespace) -> int:
    from outbreak.pipeline.poster import build

    res = build(Path(args.data), Path(args.poster_dir), chrome=args.chrome)
    print(f"html: {res['html']}")
    print(
        f"pdf:  {res['pdf'] or 'install playwright, or open the HTML in Chrome and print to PDF (36 x 24 in)'}"
    )
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from outbreak.serving.api import create_app

    uvicorn.run(create_app(Path(args.filter)), host=args.host, port=args.port)
    return 0


# ---------------------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="outbreak", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("smoke", help="offline harness check with scripted agents")
    s.add_argument("--families", nargs="*")
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(func=cmd_smoke)

    s = sub.add_parser("run", help="run an experiment YAML")
    s.add_argument("config")
    s.add_argument("-o", "--override", action="append", help="dotted override, e.g. -o dataset.seeds=[0,1]")
    s.add_argument("--run-id", help="resume/extend an existing run directory")
    s.add_argument("--dry-run", action="store_true", help="plan only: count episodes, call no model")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("analyze", help="analyse episodes.jsonl / outbreaks.jsonl")
    s.add_argument("path")
    s.add_argument("--out")
    s.add_argument("--kind", choices=["episodes", "outbreaks"])
    s.add_argument("--margin", type=float, default=0.05, help="utility non-inferiority margin (proportion)")
    s.set_defaults(func=cmd_analyze)

    s = sub.add_parser("train-filter", help="train the channel filter on bench episodes")
    s.add_argument("episodes", nargs="+")
    s.add_argument("--out", default="models/trained/channel_filter.joblib")
    s.add_argument("--target-fpr", type=float, default=0.05)
    s.add_argument("--C", type=float, default=1.0, help="use the value selected by `outbreak search`")
    s.set_defaults(func=cmd_train_filter)

    s = sub.add_parser("search", help="hyperparameter search (validation split only)")
    s.add_argument("config")
    s.add_argument("--episodes", nargs="*")
    s.add_argument("--activations")
    s.add_argument("--decision-points")
    s.add_argument("--out")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("natural-notes", help="LLM-written peer notes (external validity of the factorial)")
    s.add_argument("--model", required=True, help="writer model, e.g. openai/gpt-5-mini")
    s.add_argument("--mechanism", nargs="*", help="default: all four impossible mechanisms")
    s.add_argument("--n", type=int, default=48)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out-dir", default="data/processed")
    s.add_argument("--max-usd", type=float, default=2.0)
    s.set_defaults(func=cmd_natural_notes)

    s = sub.add_parser("manipulation-check", help="LLM rater codes the six traits; agreement with design")
    s.add_argument("--notes", nargs="+", required=True, help="notes_M*.jsonl and/or natural_notes_M*.jsonl")
    s.add_argument("--model", required=True)
    s.add_argument("--out", default="outputs/results/manipulation_check")
    s.add_argument("--max-usd", type=float, default=3.0)
    s.set_defaults(func=cmd_manipulation_check)

    s = sub.add_parser("judge-eval", help="LLM channel judge vs trained filter on the same held-out posts")
    s.add_argument("episodes", nargs="+")
    s.add_argument("--judge", required=True)
    s.add_argument("--filter", default="models/trained/channel_filter.joblib")
    s.add_argument("--threshold", type=float, default=0.5)
    s.add_argument("--out", default="outputs/results/judge_vs_filter")
    s.add_argument("--max-usd", type=float, default=3.0)
    s.set_defaults(func=cmd_judge_eval)

    s = sub.add_parser("harvest", help="build decision-point dataset for white-box analysis")
    s.add_argument("episodes", nargs="+")
    s.add_argument("--out", default="data/processed/decision_points.jsonl")
    s.set_defaults(func=cmd_harvest)

    s = sub.add_parser("notes", help="export factorial notes")
    s.add_argument("--mechanism", default="m2_admin_token")
    s.add_argument("--design", choices=["factorial", "pb12"], default="factorial")
    s.add_argument("--draws", type=int, default=3)
    s.add_argument("--seed", type=int, default=1234)
    s.add_argument("--out")
    s.set_defaults(func=cmd_notes)

    s = sub.add_parser("splits", help="write frozen scenario splits")
    s.add_argument("--out", default="data/processed/scenario_splits.json")
    s.add_argument("--n-seeds", type=int, default=200)
    s.set_defaults(func=cmd_splits)

    s = sub.add_parser("power", help="power simulation for planned sample sizes")
    s.add_argument("--sims", type=int, default=2000)
    s.set_defaults(func=cmd_power)

    s = sub.add_parser("pilot", help="reproduce the pilot table")
    s.set_defaults(func=cmd_pilot)

    s = sub.add_parser("screen", help="list candidate OpenRouter models")
    s.add_argument("--max-price", type=float, default=1.0, help="max USD per M completion tokens")
    s.add_argument("--all", action="store_true", help="all models, not one per family")
    s.set_defaults(func=cmd_screen)

    s = sub.add_parser(
        "export-demo", help="rebuild demo/data.json and demo/index.html from the finished runs"
    )
    s.add_argument("--demo-dir", default="demo")
    s.add_argument("--results", default="outputs/results")
    s.add_argument("--trained", default="models/trained")
    s.set_defaults(func=cmd_export_demo)

    s = sub.add_parser("poster", help="render the 36x24 in poster (HTML + PDF) from demo/data.json")
    s.add_argument("--data", default="demo/data.json")
    s.add_argument("--poster-dir", default="poster")
    s.add_argument("--chrome", default=None, help="path to a Chrome/Chromium binary for Playwright")
    s.set_defaults(func=cmd_poster)

    s = sub.add_parser("serve", help="serve the channel filter over HTTP")
    s.add_argument("--filter", default="models/trained/channel_filter.joblib")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)
    return p


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env support (KEY=VALUE lines); never overrides variables already set."""
    import os

    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip() and k.strip() not in os.environ:
                os.environ[k.strip()] = v.strip().strip('"').strip("'")


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
