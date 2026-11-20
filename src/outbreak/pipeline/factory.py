"""Construct models, defenses and the shared cache/budget from an experiment config."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from outbreak.env.episode import ChatModel
from outbreak.env.mechanisms import POLICY_LINES
from outbreak.env.workspace import Scenario
from outbreak.models.client import Budget, OpenRouterClient, Pricing, SamplingParams
from outbreak.models.judges import LLMActionMonitor, LLMChannelJudge, OracleGate
from outbreak.models.scripted import ScriptedAgent
from outbreak.models.text_filter import TextFilter
from outbreak.utils.cache import LLMCache
from outbreak.utils.config import AgentModel, ExperimentConfig

DEFAULT_FILTER_PATH = Path("models/trained/channel_filter.joblib")


class ModelFactory:
    """Callable ``(model_id, scenario) -> ChatModel``. OpenRouter clients are shared per model id (one
    cache, one budget); ``scripted/<strategy>`` ids build harness policies bound to the scenario."""

    def __init__(self, cfg: ExperimentConfig) -> None:
        self.cfg = cfg
        self.budget = Budget(cfg.budget.max_usd)
        path = cfg.model.cache_path or f"outputs/cache/{cfg.experiment_id}.sqlite"
        self.cache = LLMCache(path) if cfg.model.provider == "openrouter" else None
        self._clients: dict[str, OpenRouterClient] = {}
        self._lock = threading.Lock()
        self._specs = {a.id: a for a in cfg.model.agents}

    def client(self, spec: AgentModel) -> OpenRouterClient:
        with self._lock:
            if spec.id not in self._clients:
                s = self.cfg.model.sampling
                self._clients[spec.id] = OpenRouterClient(
                    spec.id,
                    cache=self.cache,
                    budget=self.budget,
                    params=SamplingParams(s.temperature, s.top_p, s.max_tokens, s.reasoning_effort),
                    pricing=Pricing(spec.prompt_price_per_m, spec.completion_price_per_m),
                )
            return self._clients[spec.id]

    def __call__(self, model_id: str, scenario: Scenario) -> ChatModel:
        if model_id.startswith("scripted/"):
            return ScriptedAgent(scenario, model_id.split("/", 1)[1])
        return self.client(self._specs.get(model_id) or AgentModel(id=model_id))

    def judge_model(self) -> ChatModel:
        if self.cfg.model.judge is None:
            raise ValueError("this experiment needs model.judge (LLM judge / monitor)")
        return self.client(self.cfg.model.judge)


def channel_defense(
    arm: str, factory: ModelFactory, threshold: float | None, filter_path: Path = DEFAULT_FILTER_PATH
) -> Callable[[str], object] | None:
    """``threshold=None`` keeps the filter's calibrated threshold (its confirmatory operating point)."""
    if arm == "channel_judge":
        return LLMChannelJudge(factory.judge_model(), threshold=0.5 if threshold is None else threshold)
    if arm == "channel_filter":
        if not filter_path.exists():
            raise FileNotFoundError(f"{filter_path} missing: run `outbreak train-filter` first")
        f = TextFilter.load(filter_path)
        if threshold is not None:
            f.threshold = threshold
        return f
    return None


def action_gate(arm: str, factory: ModelFactory, threshold: float | None) -> object | None:
    if arm == "action_monitor":
        return LLMActionMonitor(
            factory.judge_model(),
            policy="\n".join(POLICY_LINES),
            threshold=0.5 if threshold is None else threshold,
        )
    if arm == "oracle_monitor":
        return OracleGate()
    return None


def standalone_client(
    model_id: str,
    *,
    max_usd: float,
    cache_path: str = "outputs/cache/standalone.sqlite",
    temperature: float = 0.0,
    reasoning_effort: str | None = "low",
) -> OpenRouterClient:
    """Client for one-off jobs outside an experiment YAML (natural notes, manipulation check, judge eval).
    Shares the project cache, so re-running these jobs is free and reproducible."""
    import os

    if not model_id.startswith("scripted/") and not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY is not set")
    return OpenRouterClient(
        model_id,
        cache=LLMCache(cache_path),
        budget=Budget(max_usd),
        params=SamplingParams(temperature, 1.0, 1024, reasoning_effort),
    )
