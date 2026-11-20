"""OpenRouter chat client with caching, cost accounting, a hard budget guard and retries.

The API key is read from the environment (``OPENROUTER_API_KEY``) and never logged or cached.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from outbreak.env.episode import AssistantTurn, Usage
from outbreak.env.tools import ToolCall
from outbreak.utils.cache import LLMCache, cache_key

log = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class BudgetExceededError(RuntimeError):
    fatal = True  # tells the episode loop to abort the run instead of recording an errored episode


@dataclass
class Budget:
    """Thread-safe spend tracker. ``max_usd`` is a hard stop checked before every uncached call."""

    max_usd: float
    spent_usd: float = 0.0
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def check(self) -> None:
        with self._lock:
            if self.spent_usd >= self.max_usd:
                raise BudgetExceededError(f"budget exhausted: ${self.spent_usd:.4f} >= ${self.max_usd:.2f}")

    def charge(self, usd: float) -> None:
        with self._lock:
            self.spent_usd += usd
            self.calls += 1


@dataclass
class SamplingParams:
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: int = 2048
    reasoning_effort: str | None = "low"  # passed as OpenRouter's unified ``reasoning`` field

    def to_payload(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "reasoning_effort": self.reasoning_effort,
        }


@dataclass
class Pricing:
    """USD per million tokens; used only if the provider does not return the exact cost."""

    prompt: float = 0.0
    completion: float = 0.0

    def cost(self, pt: int, ct: int) -> float:
        return (pt * self.prompt + ct * self.completion) / 1e6


class OpenRouterClient:
    """Implements :class:`outbreak.env.episode.ChatModel` against OpenRouter's OpenAI-compatible API."""

    def __init__(
        self,
        model: str,
        *,
        cache: LLMCache | None = None,
        budget: Budget | None = None,
        params: SamplingParams | None = None,
        pricing: Pricing | None = None,
        max_retries: int = 6,
        timeout_s: float = 120.0,
        provider_order: list[str] | None = None,
    ) -> None:
        self.name = model
        self.cache = cache
        self.budget = budget
        self.params = params or SamplingParams()
        self.pricing = pricing or Pricing()
        self.max_retries = max_retries
        self.provider_order = provider_order
        self._client: Any = None
        self._timeout = timeout_s

    def _openai(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # imported lazily so offline paths need no key

            key = os.environ.get("OPENROUTER_API_KEY")
            if not key:
                raise RuntimeError("OPENROUTER_API_KEY is not set (use Colab Secrets or a .env file)")
            self._client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=key, timeout=self._timeout)
        return self._client

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, seed: int, key: str
    ) -> AssistantTurn:
        payload = {
            "model": self.name,
            "messages": messages,
            "tools": tools,
            "params": self.params.to_payload(),
            "seed": seed,
            "episode_key": key,
        }
        k = cache_key(payload)
        if self.cache is not None and (hit := self.cache.get(k)) is not None:
            turn = _turn_from_record(hit)
            turn.usage = Usage(cache_hits=1)
            return turn
        if self.budget is not None:
            self.budget.check()
        t0 = time.monotonic()
        resp = self._call_with_retries(messages, tools, seed)
        latency = time.monotonic() - t0
        record = _record_from_response(resp)
        u = record["usage"]
        cost = u.get("cost")
        if cost is None:
            cost = self.pricing.cost(u["prompt_tokens"], u["completion_tokens"])
        record["usage"]["cost"] = float(cost)
        if self.budget is not None:
            self.budget.charge(float(cost))
        if self.cache is not None:
            self.cache.put(k, self.name, record)
        turn = _turn_from_record(record)
        turn.usage = Usage(u["prompt_tokens"], u["completion_tokens"], float(cost), latency, 1, 0)
        return turn

    def _call_with_retries(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], seed: int
    ) -> Any:
        extra: dict[str, Any] = {"usage": {"include": True}}
        if self.params.reasoning_effort:
            extra["reasoning"] = {"effort": self.params.reasoning_effort}
        if self.provider_order:
            extra["provider"] = {"order": self.provider_order, "allow_fallbacks": True}
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            try:
                tool_kw: dict[str, Any] = {"tools": tools, "tool_choice": "auto"} if tools else {}
                resp = self._openai().chat.completions.create(
                    model=self.name,
                    messages=messages,
                    seed=seed,
                    temperature=self.params.temperature,
                    top_p=self.params.top_p,
                    max_tokens=self.params.max_tokens,
                    extra_body=extra,
                    **tool_kw,
                )
                if not getattr(resp, "choices", None):
                    raise RuntimeError(f"empty choices: {getattr(resp, 'error', resp)}")
                return resp
            except BudgetExceededError:
                raise
            except Exception as e:
                status = getattr(e, "status_code", None)
                retryable = status in {
                    None,
                    408,
                    409,
                    425,
                    429,
                    500,
                    502,
                    503,
                    504,
                } or "empty choices" in str(e)
                if not retryable or attempt == self.max_retries:
                    raise
                sleep = delay * (1 + random.random())
                log.warning(
                    "OpenRouter %s (status=%s); retry %d in %.1fs",
                    type(e).__name__,
                    status,
                    attempt + 1,
                    sleep,
                )
                time.sleep(sleep)
                delay = min(delay * 2, 60)
        raise AssertionError("unreachable")  # pragma: no cover


def _record_from_response(resp: Any) -> dict[str, Any]:
    msg = resp.choices[0].message
    calls = []
    for tc in msg.tool_calls or []:
        calls.append({"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments or ""})
    usage = getattr(resp, "usage", None)
    return {
        "content": msg.content,
        "reasoning": getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None),
        "tool_calls": calls,
        "finish_reason": resp.choices[0].finish_reason,
        "provider": getattr(resp, "provider", None),
        "usage": {
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "cost": getattr(usage, "cost", None),
        },
    }


def _turn_from_record(rec: dict[str, Any]) -> AssistantTurn:
    calls = [
        ToolCall.parse(c["id"] or f"call_{i}", c["name"], c["arguments"])
        for i, c in enumerate(rec.get("tool_calls") or [])
    ]
    prov = rec.get("provider")
    return AssistantTurn(
        rec.get("content"),
        calls,
        rec.get("reasoning"),
        Usage(),
        rec.get("finish_reason"),
        provider=str(prov) if prov else None,
    )
