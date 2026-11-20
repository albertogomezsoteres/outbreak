"""Generic, resumable, parallel episode runner.

Episodes are described by :class:`EpisodeSpec` (pure data). ``run_specs`` executes them with a thread
pool, appends one JSON line per finished episode to ``episodes.jsonl`` (flushed immediately), and on
restart skips every ``episode_id`` already present, so a crashed or interrupted run resumes where it
stopped without duplicating or re-paying for anything (the LLM cache makes replays free as well).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from outbreak.env.board import Board, ChannelFilter
from outbreak.env.episode import ChatModel, EpisodeConfig, EpisodeResult, run_episode
from outbreak.env.tools import Gate
from outbreak.env.workspace import Scenario
from outbreak.models.client import BudgetExceededError

log = logging.getLogger(__name__)

TEAMMATE = "agent-7"


@dataclass(frozen=True)
class EpisodeSpec:
    episode_id: str
    model: str
    scenario: Scenario
    board: str  # no_board | empty_board | benign | note
    note_id: str | None = None
    note_text: str | None = None
    replicate: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def seed(self) -> int:
        return int(hashlib.sha256(self.episode_id.encode()).hexdigest()[:8], 16)

    def condition(self) -> dict[str, Any]:
        return {
            "board": self.board,
            "note_id": self.note_id,
            "note_text": self.note_text,
            "replicate": self.replicate,
            **self.meta,
        }


def make_board(spec: EpisodeSpec, channel_filter: ChannelFilter | None = None) -> Board:
    board = Board(channel_filter=channel_filter)
    if spec.board in {"benign", "note"}:
        if not spec.note_text:
            raise ValueError(f"{spec.episode_id}: board={spec.board} needs note_text")
        board.seed(TEAMMATE, spec.note_text)
    return board


MAX_CONSECUTIVE_ERRORS = 25  # this many errored episodes in a row means the provider is refusing calls


def failed(rec: dict[str, Any]) -> bool:
    """An episode (``outcome.terminal == "error"``) or an outbreak (``summary.errors > 0``) hit provider errors."""
    if (rec.get("outcome") or {}).get("terminal") == "error":
        return True
    return bool((rec.get("summary") or {}).get("errors"))


def done_ids(path: Path) -> set[str]:
    """Ids whose latest record finished without provider errors. Failed ones are run again on resume
    (preregistration section 6: errored arms are re-run); the newer record then supersedes the old one."""
    if not path.exists():
        return set()
    latest: dict[str, bool] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    latest[rec["episode_id"]] = not failed(rec)
                except (json.JSONDecodeError, KeyError):
                    log.warning("skipping corrupt line in %s", path)
    return {k for k, ok in latest.items() if ok}


def run_specs(
    specs: Iterable[EpisodeSpec],
    model_factory: Callable[[str, Scenario], ChatModel],
    out_path: Path,
    *,
    concurrency: int = 8,
    episode_cfg: EpisodeConfig | None = None,
    gate: Gate | None = None,
    channel_filter: ChannelFilter | None = None,
    include_transcripts: bool = True,
    progress: Callable[[int, int, EpisodeResult], None] | None = None,
) -> dict[str, Any]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    finished = done_ids(out_path)
    todo = [s for s in specs if s.episode_id not in finished]
    lock = threading.Lock()
    stats: dict[str, Any] = {
        "skipped_done": len(finished),
        "run": 0,
        "errors": 0,
        "budget_stopped": False,
        "stopped": None,
    }
    consecutive_errors = 0

    def work(spec: EpisodeSpec) -> EpisodeResult:
        cfg = episode_cfg or EpisodeConfig()
        cfg = EpisodeConfig(**{**asdict(cfg), "board_present": spec.board != "no_board"})
        return run_episode(
            model_factory(spec.model, spec.scenario),
            spec.scenario,
            make_board(spec, channel_filter),
            episode_id=spec.episode_id,
            seed=spec.seed,
            gate=gate,
            cfg=cfg,
            condition=spec.condition(),
        )

    with open(out_path, "a") as fout, ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(work, s): s for s in todo}
        for fut in as_completed(futures):
            spec = futures[fut]
            try:
                res = fut.result()
            except BudgetExceededError as e:
                log.error("budget exhausted; stopping: %s", e)
                stats["budget_stopped"] = True
                stats["stopped"] = f"budget: {e}"
                for f in futures:
                    f.cancel()
                break
            except Exception as e:
                if getattr(e, "fatal", False):  # e.g. the provider refused the account
                    log.error("stopping the run: %s", e)
                    stats["stopped"] = str(e)
                    for f in futures:
                        f.cancel()
                    break
                log.exception("episode %s crashed", spec.episode_id)
                stats["errors"] += 1
                continue
            rec = res.to_record(include_transcript=include_transcripts)
            rec["spec_meta"] = spec.meta
            with lock:
                fout.write(json.dumps(rec, default=str) + "\n")
                fout.flush()
                stats["run"] += 1
            if res.outcome.terminal == "error":
                stats["errors"] += 1
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    stats["stopped"] = (
                        f"{consecutive_errors} episodes in a row failed at the provider; check the account "
                        "(credits, key limit) and re-run: failed episodes are retried"
                    )
                    log.error("stopping the run: %s", stats["stopped"])
                    for f in futures:
                        f.cancel()
                    break
            else:
                consecutive_errors = 0
            if progress:
                progress(stats["run"], len(todo), res)
    return stats


def latest_records(recs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the last record of each ``episode_id`` (a re-run of a failed episode supersedes it)."""
    by_id: dict[str, dict[str, Any]] = {}
    for r in recs:
        by_id.pop(r["episode_id"], None)  # keep file order of the surviving record
        by_id[r["episode_id"]] = r
    return list(by_id.values())


def read_episodes(path: Path) -> list[dict[str, Any]]:
    with open(path) as f:
        return latest_records(json.loads(line) for line in f if line.strip())
