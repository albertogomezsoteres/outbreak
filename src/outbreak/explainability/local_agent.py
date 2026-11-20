"""Run an open-weight model as an agent in the real environment, optionally *with the vaccine applied*.

This closes the loop for Act 3: beyond the log-prob margin, a steered model plays full episodes
(same scenarios, same notes, same detectors) and we compare violation and utility rates with and
without steering. Tool calls are parsed from the model's native format:

* gpt-oss (harmony): ``<|channel|>commentary to=functions.NAME ... <|message|>{json}<|call|>``
* Qwen / Hermes style: ``<tool_call>{"name": ..., "arguments": {...}}</tool_call>``
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import uuid
from typing import Any

import numpy as np

from outbreak.env.episode import AssistantTurn, Usage
from outbreak.env.tools import ToolCall
from outbreak.explainability.activations import LoadedModel, render
from outbreak.explainability.steering import steer

_HARMONY = re.compile(r"to=functions\.([\w\-]+).*?<\|message\|>(.*?)(?:<\|call\|>|<\|end\|>|$)", re.S)
_HERMES = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
_HARMONY_FINAL = re.compile(r"<\|channel\|>final<\|message\|>(.*?)(?:<\|end\|>|<\|return\|>|$)", re.S)
_HARMONY_ANALYSIS = re.compile(r"<\|channel\|>analysis<\|message\|>(.*?)(?:<\|end\|>|$)", re.S)


def parse_tool_calls(text: str) -> tuple[list[ToolCall], str | None, str | None]:
    """Return (tool calls, visible content, reasoning) from raw generated text."""
    calls: list[ToolCall] = []
    for name, args in _HARMONY.findall(text):
        calls.append(ToolCall.parse(f"call_{uuid.uuid4().hex[:8]}", name, _json_or_raw(args.strip())))
    if not calls:
        for blob in _HERMES.findall(text):
            try:
                obj = json.loads(blob)
                calls.append(
                    ToolCall.parse(
                        f"call_{uuid.uuid4().hex[:8]}", str(obj["name"]), obj.get("arguments") or {}
                    )
                )
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    final = _HARMONY_FINAL.search(text)
    analysis = _HARMONY_ANALYSIS.search(text)
    content = final.group(1).strip() if final else (None if calls else _HERMES.sub("", text).strip() or None)
    return calls, content, analysis.group(1).strip() if analysis else None


def _json_or_raw(s: str) -> dict[str, Any] | str:
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else s
    except json.JSONDecodeError:
        return s


class LocalAgent:
    """:class:`~outbreak.env.episode.ChatModel` backed by a local HF model, with optional steering."""

    def __init__(
        self,
        lm: LoadedModel,
        *,
        max_new_tokens: int = 768,
        temperature: float = 1.0,
        steering: tuple[int, np.ndarray, float] | None = None,
        name: str | None = None,
    ) -> None:
        self.lm = lm
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.steering = steering
        tag = "" if steering is None else f"+vaccine(L{steering[0]},s={steering[2]:.2f})"
        self.name = name or f"local/{lm.model_id}{tag}"

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, seed: int, key: str
    ) -> AssistantTurn:
        import torch

        prompt = render(self.lm.tokenizer, messages, tools, add_generation_prompt=True)
        ids = self.lm.tokenizer(prompt, return_tensors="pt", add_special_tokens=False)["input_ids"].to(
            self.lm.device
        )
        # Deterministic per (seed, key); Python's hash() is salted per process, so use sha256.
        torch.manual_seed((seed + int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)) % (2**31))
        steering, meta = self._steering_for(prompt)
        ctx = steer(self.lm, *steering) if steering else contextlib.nullcontext()
        with ctx, torch.no_grad():
            out = self.lm.model.generate(
                ids,
                max_new_tokens=self.max_new_tokens,
                do_sample=self.temperature > 0,
                temperature=max(self.temperature, 1e-5),
                top_p=1.0,
                pad_token_id=self.lm.tokenizer.pad_token_id or self.lm.tokenizer.eos_token_id,
            )
        new = out[0, ids.shape[1] :]
        text = self.lm.tokenizer.decode(new, skip_special_tokens=False)
        calls, content, reasoning = parse_tool_calls(text)
        turn = AssistantTurn(
            content, calls, reasoning, Usage(int(ids.shape[1]), int(new.shape[0]), 0.0, 0.0, 1, 0)
        )
        turn.meta = meta
        return turn

    def _steering_for(self, prompt: str) -> tuple[tuple[int, np.ndarray, float] | None, dict[str, Any]]:
        return self.steering, ({"vaccinated": True} if self.steering else {})


class ProbeGuardedAgent(LocalAgent):
    """Detect-then-vaccinate: before each turn, read the decision-point probe on the current context; apply
    the vaccine only when the predicted propensity crosses ``threshold``. Compared with always-on steering,
    it should keep utility on ordinary turns while still protecting the risky ones. Every turn records the
    probe score and whether the vaccine was applied (``AssistantTurn.meta``)."""

    def __init__(
        self,
        lm: LoadedModel,
        probe: Any,
        layer: int,
        vaccine: tuple[int, np.ndarray, float],
        *,
        threshold: float = 0.5,
        **kw: Any,
    ) -> None:
        super().__init__(
            lm,
            steering=None,
            name=kw.pop("name", None) or f"local/{lm.model_id}+probe-guard(L{layer},t={threshold})",
            **kw,
        )
        self.probe, self.layer, self.vaccine, self.threshold = probe, layer, vaccine, threshold

    def _steering_for(self, prompt: str) -> tuple[tuple[int, np.ndarray, float] | None, dict[str, Any]]:
        from outbreak.explainability.activations import hidden_states

        x = hidden_states(self.lm, [prompt], [self.layer])[self.layer]
        score = float(self.probe.predict_proba(x)[0, 1])
        fire = score >= self.threshold
        return (self.vaccine if fire else None), {"probe_score": score, "vaccinated": fire}
