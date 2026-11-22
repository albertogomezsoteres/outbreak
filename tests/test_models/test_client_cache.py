"""OpenRouter client behaviour against a fake transport: caching, budget, retries, cost accounting."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from outbreak.models.client import (
    Budget,
    BudgetExceededError,
    OpenRouterClient,
    Pricing,
    ProviderAccountError,
)
from outbreak.utils.cache import LLMCache, cache_key


def _resp(content="ok", tool=None, cost=0.001, pt=100, ct=20):
    tcs = (
        [SimpleNamespace(id="c1", function=SimpleNamespace(name=tool[0], arguments=tool[1]))]
        if tool
        else None
    )
    msg = SimpleNamespace(content=content, tool_calls=tcs, reasoning="thinking")
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=pt, completion_tokens=ct, cost=cost),
        provider="x",
    )


class FakeOpenAI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _client(tmp_path, responses, budget=1.0, **kw):
    c = OpenRouterClient("m/x", cache=LLMCache(tmp_path / "c.sqlite"), budget=Budget(budget), **kw)
    fake = FakeOpenAI(responses)
    c._client = fake
    return c, fake


MSGS = [{"role": "user", "content": "hi"}]


def test_cache_hit_costs_nothing(tmp_path):
    c, fake = _client(tmp_path, [_resp(tool=("list_files", "{}"))])
    t1 = c.complete(MSGS, [], seed=1, key="ep1:t0")
    t2 = c.complete(MSGS, [], seed=1, key="ep1:t0")
    assert len(fake.calls) == 1 and t2.usage.cache_hits == 1 and t2.usage.cost_usd == 0
    assert t1.tool_calls[0].name == t2.tool_calls[0].name == "list_files"
    assert c.budget.spent_usd == pytest.approx(0.001)


def test_replicates_are_not_collapsed_by_cache(tmp_path):
    c, fake = _client(tmp_path, [_resp("a"), _resp("b")])
    assert c.complete(MSGS, [], seed=1, key="ep1:t0").content == "a"
    assert c.complete(MSGS, [], seed=1, key="ep2:t0").content == "b"
    assert len(fake.calls) == 2


def test_budget_is_a_hard_stop(tmp_path):
    c, fake = _client(tmp_path, [_resp(cost=0.6), _resp(cost=0.6), _resp()], budget=1.0)
    c.complete(MSGS, [], seed=1, key="a")
    c.complete(MSGS, [], seed=1, key="b")
    with pytest.raises(BudgetExceededError):
        c.complete(MSGS, [], seed=1, key="c")
    assert len(fake.calls) == 2


def test_retries_transient_errors(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    err = RuntimeError("rate limited")
    err.status_code = 429  # type: ignore[attr-defined]
    c, fake = _client(tmp_path, [err, err, _resp("fine")])
    assert c.complete(MSGS, [], seed=1, key="a").content == "fine" and len(fake.calls) == 3


def test_non_retryable_errors_propagate(tmp_path):
    err = RuntimeError("bad request")
    err.status_code = 400  # type: ignore[attr-defined]
    c, _ = _client(tmp_path, [err])
    with pytest.raises(RuntimeError, match="bad request"):
        c.complete(MSGS, [], seed=1, key="a")


def test_cost_falls_back_to_pricing(tmp_path):
    c, _ = _client(tmp_path, [_resp(cost=None, pt=1_000_000, ct=500_000)], pricing=Pricing(0.1, 0.4))
    t = c.complete(MSGS, [], seed=1, key="a")
    assert t.usage.cost_usd == pytest.approx(0.1 + 0.2)


def test_tools_omitted_when_empty_and_reasoning_passed(tmp_path):
    c, fake = _client(tmp_path, [_resp(), _resp()])
    c.complete(MSGS, [], seed=1, key="a")
    c.complete(MSGS, [{"type": "function", "function": {"name": "f", "parameters": {}}}], seed=1, key="b")
    assert "tools" not in fake.calls[0] and fake.calls[1]["tool_choice"] == "auto"
    assert fake.calls[0]["extra_body"]["reasoning"] == {"effort": "low"}


def test_cache_key_is_canonical():
    assert cache_key({"a": 1, "b": [1, 2]}) == cache_key({"b": [1, 2], "a": 1})
    assert cache_key({"a": 1}) != cache_key({"a": 2})


def test_cache_is_thread_safe(tmp_path):
    cache = LLMCache(tmp_path / "t.sqlite")

    def work(i):
        for j in range(50):
            cache.put(f"{i}-{j}", "m", {"v": j})
            assert cache.get(f"{i}-{j}") == {"v": j}

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(cache) == 400


@pytest.mark.parametrize("status", [401, 402, 403])
def test_account_refusal_is_fatal_and_not_retried(tmp_path, status):
    err = RuntimeError("Insufficient credits")
    err.status_code = status  # type: ignore[attr-defined]
    c, fake = _client(tmp_path, [err, _resp()])
    with pytest.raises(ProviderAccountError) as exc:
        c.complete(MSGS, [], seed=1, key="ep1:t0")
    assert exc.value.fatal and len(fake.calls) == 1 and str(status) in str(exc.value)
