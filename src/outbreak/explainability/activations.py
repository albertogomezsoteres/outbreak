"""White-box access to an open-weight agent model: rendering, hidden states, continuation log-probs.

The *decision point* is the end of the scripted prefix (see ``outbreak.env.episode``): the agent has
seen the obstacle and the board, and has not yet acted. Everything here operates on that prefix,
rendered with the model's own chat template (tools included), so the white-box view is the same input
the black-box API experiments sent.

Heavy dependencies (torch, transformers) are imported lazily; the module imports without them.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class LoadedModel:
    model: Any
    tokenizer: Any
    model_id: str
    n_layers: int
    device: str


def load_model(model_id: str, *, dtype: str = "bfloat16", device_map: str = "auto") -> LoadedModel:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, torch_dtype=getattr(torch, dtype), device_map=device_map
    )
    model.eval()
    n_layers = int(getattr(model.config, "num_hidden_layers", getattr(model.config, "n_layer", 0)))
    device = str(next(model.parameters()).device)
    return LoadedModel(model, tok, model_id, n_layers, device)


def _fallback_render(messages: Sequence[dict[str, Any]], add_generation_prompt: bool) -> str:
    """Plain template for models without a chat template (only used for tiny test models)."""
    out = []
    for m in messages:
        body = m.get("content") or ""
        if m.get("tool_calls"):
            body += "".join(
                f"\n<call>{c['function']['name']} {c['function']['arguments']}</call>"
                for c in m["tool_calls"]
            )
        out.append(f"<|{m['role']}|>\n{body}\n")
    if add_generation_prompt:
        out.append("<|assistant|>\n")
    return "".join(out)


def render(
    tokenizer: Any,
    messages: Sequence[dict[str, Any]],
    tools: Sequence[dict[str, Any]] | None = None,
    add_generation_prompt: bool = True,
) -> str:
    msgs = [_normalize(m) for m in messages]
    # Some templates (e.g. gpt-oss harmony) name tool results after the function that produced them.
    names = {c["id"]: c["function"]["name"] for m in msgs for c in m.get("tool_calls") or []}
    for m in msgs:
        if m.get("role") == "tool" and "name" not in m and m.get("tool_call_id") in names:
            m["name"] = names[m["tool_call_id"]]
    if getattr(tokenizer, "chat_template", None):
        return str(
            tokenizer.apply_chat_template(
                msgs,
                tools=list(tools) if tools else None,
                tokenize=False,
                add_generation_prompt=add_generation_prompt,
            )
        )
    return _fallback_render(msgs, add_generation_prompt)


def _normalize(m: dict[str, Any]) -> dict[str, Any]:
    """Chat templates disagree on tool-call argument types; most expect dicts."""
    m = dict(m)
    if m.get("tool_calls"):
        calls = []
        for c in m["tool_calls"]:
            fn = dict(c["function"])
            if isinstance(fn.get("arguments"), str):
                with contextlib.suppress(json.JSONDecodeError):
                    fn["arguments"] = json.loads(fn["arguments"] or "{}")
            calls.append({**c, "function": fn})
        m["tool_calls"] = calls
    return m


def hidden_states(
    lm: LoadedModel,
    texts: Sequence[str],
    layers: Sequence[int],
    *,
    position: str = "last",
    last_k: int = 8,
    batch_size: int = 1,
    max_length: int = 16_384,
) -> dict[int, np.ndarray]:
    """Residual-stream activations (output of block ``l``; index 0 = embeddings) at the decision point.

    ``position='last'`` takes the final prefix token; ``'mean_last_k'`` averages the last ``k`` tokens.
    Returns ``{layer: array[n_texts, d_model]}`` in float32.
    """
    import torch

    out: dict[int, list[np.ndarray]] = {layer: [] for layer in layers}
    tok = lm.tokenizer
    for i in range(0, len(texts), batch_size):
        batch = list(texts[i : i + batch_size])
        enc = tok(
            batch,
            return_tensors="pt",
            padding=len(batch) > 1,
            truncation=True,
            max_length=max_length,
            add_special_tokens=False,
        )
        enc = {k: v.to(lm.device) for k, v in enc.items()}
        with torch.no_grad():
            res = lm.model(**enc, output_hidden_states=True, use_cache=False)
        mask = enc.get("attention_mask", torch.ones_like(enc["input_ids"]))
        lengths = mask.sum(dim=1)
        for layer in layers:
            hs = res.hidden_states[layer]
            for b in range(hs.shape[0]):
                n = int(lengths[b])
                # right padding is assumed (tokenizer default); positions [0, n) are real tokens
                vec = hs[b, n - 1] if position == "last" else hs[b, max(0, n - last_k) : n].mean(dim=0)
                out[layer].append(vec.float().cpu().numpy())
    return {layer: np.stack(v) for layer, v in out.items()}


def continuation_logprob(lm: LoadedModel, prefix: str, continuation: str) -> float:
    """Sum of log-probabilities of ``continuation`` tokens given ``prefix`` (teacher forcing)."""
    import torch

    tok = lm.tokenizer
    p_ids = tok(prefix, add_special_tokens=False, return_tensors="pt")["input_ids"]
    c_ids = tok(continuation, add_special_tokens=False, return_tensors="pt")["input_ids"]
    ids = torch.cat([p_ids, c_ids], dim=1).to(lm.device)
    with torch.no_grad():
        logits = lm.model(input_ids=ids, use_cache=False).logits[0, :-1].float()
    logp = torch.log_softmax(logits, dim=-1)
    targets = ids[0, 1:]
    start = p_ids.shape[1] - 1
    return float(logp[start:, :].gather(1, targets[start:, None]).sum())


def action_continuation(
    tokenizer: Any,
    prefix_messages: Sequence[dict[str, Any]],
    tools: Sequence[dict[str, Any]],
    name: str,
    arguments: dict[str, Any],
) -> tuple[str, str]:
    """Render (prefix, continuation) where continuation is the assistant emitting one tool call.

    The continuation is obtained as ``render(prefix + [call]) - render(prefix, gen_prompt)`` so it is
    exactly what the model's own template would produce, including special tokens.
    """
    prefix = render(tokenizer, prefix_messages, tools, add_generation_prompt=True)
    call_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "cand", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
        ],
    }
    full = render(tokenizer, [*prefix_messages, call_msg], tools, add_generation_prompt=False)
    if not full.startswith(prefix):
        # Some templates rewrite earlier turns (e.g. drop reasoning); fall back to the common prefix.
        k = 0
        while k < min(len(full), len(prefix)) and full[k] == prefix[k]:
            k += 1
        return full[:k], full[k:]
    return prefix, full[len(prefix) :]
