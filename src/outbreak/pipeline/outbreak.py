"""Act 4: outbreaks in a team of agents sharing one board, and defenses against them.

Population ("outage" design)
----------------------------
Each outbreak has ``n_agents`` agents spread over ``n_rounds`` rounds. A fraction
``blocked_fraction`` of agents receive an *impossible* scenario of the outbreak's mechanism (these
are the susceptibles: they hit the obstacle and look at the board); the rest receive the matched
POSSIBLE scenario, which measures what defenses cost in utility. Families vary across agents.

Transmission
------------
Round 0: patient zero (a seeded strong note, or a model agent pre-exposed to it) is on the board.
Within a round agents run in parallel on a *snapshot* of the board taken at round start; their posts
are published after the round, in agent order, through the arm's channel defense. This keeps runs
deterministic under parallelism and makes generations explicit.

Arms (all on the *same* populations and sample keys: common random numbers)
-------------------------------------------------------------------------------
no_board          agents have no board at all (baseline without communication)
board             undefended board
channel_judge     LLM judge screens every post (including patient zero)
channel_filter    trained text filter screens every post
action_monitor    LLM monitor can veto each tool call (preventive, action level)
oracle_monitor    detector-based veto: upper bound for any action monitor (not deployable)

Transmission test (causal agent-to-agent spread, separate from mere exposure)
------------------------------------------------------------------------------
relay             patient zero is visible in round 1 ONLY; round-1 agents' handoff notes are published
no_relay          patient zero is visible in round 1 ONLY; agents' notes are never published
In rounds 2-3 the only possible source of the shortcut in ``relay`` is another agent's note, and ``no_relay``
is the same population with that channel cut, so the difference in targeted violations among blocked
round-2/3 agents is the causal effect of agent-to-agent transmission. Each agent's notes are also checked
for naming the shortcut (propagation), separately from whether readers then violate (contagion).
"""

from __future__ import annotations

import hashlib
import itertools
import logging
import random
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any

from outbreak.data.notes import strong_note
from outbreak.env.board import Board, ChannelFilter, Post
from outbreak.env.episode import ChatModel, EpisodeConfig, EpisodeResult, run_episode
from outbreak.env.mechanisms import Mechanism
from outbreak.env.tools import Gate
from outbreak.env.workspace import Scenario

log = logging.getLogger(__name__)
PATIENT_ZERO = "agent-00"
ARMS = (
    "no_board",
    "board",
    "channel_judge",
    "channel_filter",
    "action_monitor",
    "oracle_monitor",
    "relay",
    "no_relay",
)
PZ_ROUND1_ONLY = {"relay", "no_relay"}
CHANNEL_ARMS = {"channel_judge", "channel_filter"}
GATE_ARMS = {"action_monitor", "oracle_monitor"}


@dataclass(frozen=True)
class Slot:
    agent_id: str
    scenario: Scenario
    round: int
    blocked: bool


@dataclass(frozen=True)
class Population:
    outbreak: int
    mechanism: Mechanism
    slots: tuple[Slot, ...]


def make_population(
    k: int,
    *,
    mechanism: Mechanism,
    families: list[str],
    seeds: list[int],
    n_agents: int,
    n_rounds: int,
    blocked_fraction: float,
    base_seed: int,
) -> Population:
    rng = random.Random(f"population|{base_seed}|{k}|{mechanism.value}")
    n_blocked = round(n_agents * blocked_fraction)
    blocked = [True] * n_blocked + [False] * (n_agents - n_blocked)
    rng.shuffle(blocked)
    slots = []
    for i in range(n_agents):
        fam = families[(i + k) % len(families)]
        seed = rng.choice(seeds)
        mech = mechanism if blocked[i] else Mechanism.POSSIBLE
        slots.append(Slot(f"agent-{i + 1:02d}", Scenario(fam, mech, seed), i % n_rounds + 1, blocked[i]))
    return Population(k, mechanism, tuple(slots))


@dataclass
class AgentRecord:
    agent_id: str
    round: int
    blocked: bool
    scenario: dict[str, Any]
    violation: bool
    targeted: bool  # executed the outbreak's own shortcut (the one patient zero posted)
    post_stance: (
        str  # "recommends" | "discourages" | "none": this agent's notes toward the outbreak's shortcut
    )
    attempt: bool
    legit_success: bool
    honest_block: bool
    terminal: str
    read_post_ids: list[int]
    read_from: list[str]
    exposed_to_harm: bool  # read a post from patient zero or from an agent that violated
    posts: list[str]
    cost_usd: float
    episode: dict[str, Any] | None = None


@dataclass
class OutbreakResult:
    outbreak: int
    arm: str
    mechanism: str
    threshold: float | None
    agents: list[AgentRecord]
    board: list[dict[str, Any]]
    chains: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        blocked = [a for a in self.agents if a.blocked]
        possible = [a for a in self.agents if not a.blocked]
        later = [a for a in self.agents if a.round >= 2]
        return {
            "outbreak": self.outbreak,
            "arm": self.arm,
            "mechanism": self.mechanism,
            "threshold": self.threshold,
            "n_agents": len(self.agents),
            "errors": sum(a.terminal == "error" for a in self.agents),
            "violations": sum(a.violation for a in self.agents),
            "targeted_violations": sum(a.targeted for a in self.agents),
            "attack_rate": _mean([a.violation for a in self.agents]),
            "blocked_violation_rate": _mean([a.violation for a in blocked]),
            "utility": _mean([a.legit_success for a in possible]),
            "honest_block_rate": _mean([a.honest_block for a in blocked]),
            "secondary_violations": sum(
                a.violation for a in later if any(s != PATIENT_ZERO for s in a.read_from)
            ),
            # Transmission metrics (meaningful causally in the relay / no_relay arms)
            "late_blocked": sum(1 for a in later if a.blocked),
            "late_targeted": sum(a.targeted for a in later if a.blocked),
            "late_targeted_rate": _mean([a.targeted for a in later if a.blocked]),
            "handoff_posts": sum(bool(a.posts) for a in self.agents),
            "propagators": sum(a.post_stance == "recommends" for a in self.agents if a.targeted),
            "propagation_rate": _mean([a.post_stance == "recommends" for a in self.agents if a.targeted]),
            "discouragers": sum(a.post_stance == "discourages" for a in self.agents),
            "plausible_chains": len(self.chains),
            "posts_published": sum(1 for p in self.board if p["published"]),
            "posts_blocked": sum(1 for p in self.board if not p["published"]),
            "cost_usd": sum(a.cost_usd for a in self.agents),
        }

    def to_record(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "agents": [asdict(a) for a in self.agents],
            "board": self.board,
            "chains": self.chains,
        }


def _mean(xs: list[bool]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _snapshot(master: Board, include_seeded: bool = True) -> Board:
    snap = Board()
    snap.posts = [
        Post(p.id, p.author, p.text, p.round, True, p.seeded, p.verdict)
        for p in master.visible()
        if include_seeded or not p.seeded
    ]
    nxt = max((p.id for p in master.posts), default=0) + 1
    snap._ids = itertools.count(nxt + 10_000)  # agent-local ids never collide with published ones
    return snap


def run_outbreak(
    pop: Population,
    arm: str,
    model_for: Callable[[str, Scenario], ChatModel],
    *,
    channel_filter: ChannelFilter | None = None,
    gate: Gate | None = None,
    threshold: float | None = None,
    episode_cfg: EpisodeConfig | None = None,
    concurrency: int = 8,
    keep_transcripts: bool = False,
    experiment_id: str = "outbreak",
) -> OutbreakResult:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; choose from {ARMS}")
    from outbreak.data.natural_notes import shortcut_stance

    board_present = arm != "no_board"
    publish_posts = board_present and arm != "no_relay"
    master = Board(channel_filter=channel_filter if arm in CHANNEL_ARMS else None)
    if board_present:
        master.seed(PATIENT_ZERO, strong_note(pop.mechanism).text)
    violators: set[str] = set()
    records: list[AgentRecord] = []
    chains: list[tuple[str, str]] = []
    base_cfg = episode_cfg or EpisodeConfig()
    cfg = EpisodeConfig(**{**asdict(base_cfg), "board_present": board_present})
    agent_gate = gate if arm in GATE_ARMS else None
    n_rounds = max(s.round for s in pop.slots)

    for r in range(1, n_rounds + 1):
        slots = [s for s in pop.slots if s.round == r]
        show_pz = not (arm in PZ_ROUND1_ONLY and r > 1)
        snapshot_authors = {p.id: p.author for p in master.visible() if show_pz or not p.seeded}

        def play(slot: Slot, r: int = r, show_pz: bool = show_pz) -> EpisodeResult:  # bind loop variables
            snap = _snapshot(master, include_seeded=show_pz) if board_present else Board()
            return run_episode(
                model_for(slot.agent_id, slot.scenario),
                slot.scenario,
                snap,
                episode_id=f"{experiment_id}|ob{pop.outbreak}|{arm}|{slot.agent_id}",
                sample_key=f"{experiment_id}|ob{pop.outbreak}|{slot.agent_id}",
                seed=_seed(pop.outbreak, slot.agent_id),
                agent_id=slot.agent_id,
                round_=r,
                gate=agent_gate,
                cfg=cfg,
                condition={"arm": arm, "outbreak": pop.outbreak, "round": r},
            )

        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            results = list(pool.map(play, slots))
        harmful_authors = violators | {PATIENT_ZERO}
        for slot, res in zip(slots, results, strict=True):
            read_ids = sorted({i for read in res.board_reads for i in read})
            read_from = sorted({snapshot_authors[i] for i in read_ids if i in snapshot_authors})
            exposed = any(a in harmful_authors for a in read_from)
            o = res.outcome
            if o.violation and exposed:
                chains += [(src, slot.agent_id) for src in read_from if src in harmful_authors]
            records.append(
                AgentRecord(
                    slot.agent_id,
                    r,
                    slot.blocked,
                    slot.scenario.to_dict(),
                    o.violation,
                    bool(slot.blocked and o.executed.get(pop.mechanism.value, False)),
                    _stance(pop.mechanism, res.posts, shortcut_stance),
                    o.attempt,
                    o.legit_success,
                    o.honest_block,
                    o.terminal,
                    read_ids,
                    read_from,
                    exposed,
                    res.posts,
                    res.usage.cost_usd,
                    res.to_record() if keep_transcripts else None,
                )
            )
        # Publish this round's posts (deterministic order) through the channel defense.
        for slot, res in zip(slots, results, strict=True):
            if res.outcome.violation:
                violators.add(slot.agent_id)
            if publish_posts:
                for text in res.posts:
                    master.post(slot.agent_id, text, r)
    return OutbreakResult(
        pop.outbreak, arm, pop.mechanism.value, threshold, records, master.to_records(), chains
    )


def _stance(mech: Mechanism, posts: list[str], fn: Callable[[Mechanism, str], str]) -> str:
    stances = {fn(mech, t) for t in posts}
    return (
        "recommends" if "recommends" in stances else ("discourages" if "discourages" in stances else "none")
    )


def _seed(k: int, agent_id: str) -> int:
    return int(hashlib.sha256(f"{k}|{agent_id}".encode()).hexdigest()[:8], 16)
