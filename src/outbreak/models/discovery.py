"""Discover candidate agent models on OpenRouter (tool calling, price cap, one per family)."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

MODELS_URL = "https://openrouter.ai/api/v1/models"
FAMILIES = (
    "openai/gpt-oss",
    "openai/gpt-5",
    "deepseek/",
    "z-ai/glm",
    "qwen/qwen3",
    "meta-llama/llama-4",
    "mistralai/",
    "google/gemini",
    "google/gemma",
    "x-ai/grok",
    "moonshotai/kimi",
    "minimax/",
    "nvidia/",
    "microsoft/phi",
)


def fetch_models(timeout: float = 30) -> list[dict[str, Any]]:
    with urllib.request.urlopen(MODELS_URL, timeout=timeout) as r:
        return list(json.load(r)["data"])


def discover(
    max_completion_price_per_m: float, per_family: bool = True, models: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Tool-capable models with completion price <= cap. With ``per_family`` keep the most expensive
    (usually the most capable) model under the cap in each family."""
    out = []
    for m in models if models is not None else fetch_models():
        if "tools" not in (m.get("supported_parameters") or []):
            continue
        pr = m.get("pricing") or {}
        try:
            prompt, comp = float(pr.get("prompt", 0)) * 1e6, float(pr.get("completion", 0)) * 1e6
        except (TypeError, ValueError):
            continue
        # ":free" models are rate-limited and ":batch" endpoints are asynchronous: neither suits agent loops.
        if comp > max_completion_price_per_m or m["id"].endswith((":free", ":batch")):
            continue
        fam = next((f for f in FAMILIES if m["id"].startswith(f)), None)
        out.append({"id": m["id"], "prompt": prompt, "completion": comp, "family": fam})
    if not per_family:
        return sorted(out, key=lambda x: x["id"])
    best: dict[str, dict[str, Any]] = {}
    for m in out:
        if m["family"] is None:
            continue
        if m["family"] not in best or m["completion"] > best[m["family"]]["completion"]:
            best[m["family"]] = m
    return sorted(best.values(), key=lambda x: x["id"])
