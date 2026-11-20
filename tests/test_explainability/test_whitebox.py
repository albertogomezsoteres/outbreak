"""White-box machinery on a tiny randomly initialised GPT-2 built offline, plus probe/steering maths
on planted structure. Validates the code paths the Colab notebook runs on gpt-oss-20b."""

from __future__ import annotations

import numpy as np
import pytest

from outbreak.explainability.probe import (
    PrefixSet,
    evaluate_probe,
    note_identity_scores,
    within_note_spearman,
)
from outbreak.explainability.steering import diff_of_means

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
pytestmark = pytest.mark.whitebox


@pytest.fixture(scope="module")
def tiny_lm():
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers
    from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedTokenizerFast

    from outbreak.explainability.activations import LoadedModel

    tok = Tokenizer(models.BPE(unk_token="<unk>"))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    corpus = [
        "use the admin token",
        "report blocked within policy",
        "<|user|> please complete the task",
        "<|assistant|> <call>http_request {}</call>",
        "the data API returned 429 quota exceeded",
    ] * 50
    tok.train_from_iterator(corpus, trainers.BpeTrainer(vocab_size=300, special_tokens=["<unk>", "<pad>"]))
    hf_tok = PreTrainedTokenizerFast(tokenizer_object=tok, unk_token="<unk>", pad_token="<pad>")
    torch.manual_seed(0)
    model = GPT2LMHeadModel(
        GPT2Config(vocab_size=len(hf_tok), n_positions=16384, n_embd=32, n_layer=3, n_head=2)
    )
    model.eval()
    return LoadedModel(model, hf_tok, "tiny-gpt2", 3, "cpu")


def test_hidden_states_shapes_and_position(tiny_lm):
    from outbreak.explainability.activations import hidden_states

    texts = ["use the admin token", "report blocked within policy please"]
    hs = hidden_states(tiny_lm, texts, layers=[0, 2, 3])
    assert set(hs) == {0, 2, 3} and hs[2].shape == (2, 32)
    one = hidden_states(tiny_lm, texts[:1], layers=[2])[2]
    assert np.allclose(one[0], hs[2][0], atol=1e-5)  # batching does not change the last-token state


def test_continuation_logprob_matches_manual(tiny_lm):
    from outbreak.explainability.activations import continuation_logprob

    prefix, cont = "use the", " admin token"
    lp = continuation_logprob(tiny_lm, prefix, cont)
    tok = tiny_lm.tokenizer
    ids = tok(prefix + cont, add_special_tokens=False)["input_ids"]
    n_p = len(tok(prefix, add_special_tokens=False)["input_ids"])
    with torch.no_grad():
        logp = torch.log_softmax(tiny_lm.model(torch.tensor([ids])).logits[0], -1)
    manual = sum(float(logp[i - 1, ids[i]]) for i in range(n_p, len(ids)))
    assert lp == pytest.approx(manual, abs=1e-4) and lp < 0


def test_steering_hook_shifts_exactly_that_residual(tiny_lm):
    from outbreak.explainability.activations import hidden_states
    from outbreak.explainability.steering import steer

    text = ["use the admin token"]
    base = hidden_states(tiny_lm, text, layers=[2])[2]
    u = np.zeros(32, dtype=np.float32)
    u[3] = 1.0
    with steer(tiny_lm, 2, u, 5.0):
        shifted = hidden_states(tiny_lm, text, layers=[2])[2]
    assert np.allclose(shifted - base, -5.0 * u, atol=1e-4)
    after = hidden_states(tiny_lm, text, layers=[2])[2]
    assert np.allclose(after, base)  # hook removed


def test_action_continuation_with_fallback_template(tiny_lm):
    from outbreak.explainability.activations import action_continuation

    msgs = [{"role": "user", "content": "please complete the task"}]
    prefix, cont = action_continuation(tiny_lm.tokenizer, msgs, [], "report_blocked", {"reason": "x"})
    assert prefix.endswith("<|assistant|>\n") and "report_blocked" in cont


def test_steering_sweep_runs_with_random_controls(tiny_lm):
    from outbreak.explainability.steering import MarginItem, steering_sweep

    items = [MarginItem("use the", " admin token", " report blocked")] * 2
    u = np.random.default_rng(0).standard_normal(32)
    rows = steering_sweep(
        tiny_lm,
        items,
        2,
        u / np.linalg.norm(u),
        1.0,
        [0.0, 2.0],
        n_random=2,
        utility_items=[("please complete", " the task")],
    )
    kinds = {(r.alpha, r.kind) for r in rows}
    assert kinds == {(0.0, "vaccine"), (2.0, "vaccine"), (2.0, "random_0"), (2.0, "random_1")}
    assert all(r.mean_utility_logp is not None for r in rows)


# ----------------------------------------------------------------------- probe maths (planted signal)
def _planted(n_notes=30, per_note=6, d=64, seed=0, signal=True):
    rng = np.random.default_rng(seed)
    w = rng.standard_normal(d)
    w /= np.linalg.norm(w)
    X, k, n, notes, groups, split = [], [], [], [], [], []
    for j in range(n_notes):
        note_effect = rng.normal(0, 1)
        for i in range(per_note):
            z = note_effect + rng.normal(0, 1)  # scenario-level variation within note
            x = rng.standard_normal(d) + (2.0 * z * w if signal else 0)
            p = 1 / (1 + np.exp(-(z - 0.5)))
            X.append(x)
            n.append(8)
            k.append(rng.binomial(8, p))
            notes.append(f"n{j}")
            groups.append(f"g{j}-{i}")
            split.append("train" if i < 4 else "test")
    return PrefixSet(np.asarray(X), np.asarray(k), np.asarray(n), notes, groups, split), w


def test_probe_recovers_planted_propensity_and_beats_note_identity():
    ps, _ = _planted()
    tr, te = ps.subset(np.array(ps.split) == "train"), ps.subset(np.array(ps.split) == "test")
    rep = evaluate_probe(tr, te, layer=0, n_boot=200)
    assert rep.auroc.estimate > 0.7 and rep.auroc.low > 0.6
    assert abs(rep.shuffled_auroc - 0.5) < 0.12
    assert rep.auroc.estimate > rep.note_identity_auroc
    assert rep.within_note_spearman > 0.2 or np.isnan(rep.within_note_spearman)


def test_probe_finds_nothing_without_signal():
    ps, _ = _planted(signal=False, seed=3)
    tr, te = ps.subset(np.array(ps.split) == "train"), ps.subset(np.array(ps.split) == "test")
    assert evaluate_probe(tr, te, layer=0, n_boot=100).auroc.estimate < 0.62


def test_diff_of_means_recovers_direction():
    ps, w = _planted(n_notes=60, seed=5)
    u, norm = diff_of_means(ps.X, ps.rate, hi=0.6, lo=0.25)
    assert abs(float(u @ w)) > 0.8 and norm > 0
    with pytest.raises(ValueError):
        diff_of_means(ps.X, ps.rate, hi=2.0, lo=0.0)


def test_note_identity_and_within_note_helpers():
    ps = PrefixSet(
        np.zeros((4, 2)),
        np.array([1, 3, 0, 0]),
        np.array([4, 4, 4, 4]),
        ["a", "a", "b", "c"],
        list("wxyz"),
        ["train"] * 4,
    )
    test = PrefixSet(
        np.zeros((2, 2)), np.array([0, 0]), np.array([1, 1]), ["a", "zzz"], ["p", "q"], ["test"] * 2
    )
    assert np.allclose(note_identity_scores(ps, test), [0.5, 4 / 16])
    s = np.array([0.1, 0.2, 0.3, 0.4])
    assert np.isnan(within_note_spearman(s, ps))  # no note has >= 3 prefixes


# ----------------------------------------------------------------------- local agent parsing
def test_parse_harmony_tool_call():
    from outbreak.explainability.local_agent import parse_tool_calls

    text = (
        "<|channel|>analysis<|message|>The quota is exhausted.<|end|><|start|>assistant<|channel|>commentary "
        'to=functions.report_blocked <|constrain|>json<|message|>{"reason": "quota"}<|call|>'
    )
    calls, content, reasoning = parse_tool_calls(text)
    assert [(c.name, c.arguments) for c in calls] == [("report_blocked", {"reason": "quota"})]
    assert reasoning == "The quota is exhausted." and content is None


def test_parse_hermes_tool_call_and_plain_text():
    from outbreak.explainability.local_agent import parse_tool_calls

    calls, _, _ = parse_tool_calls(
        '<tool_call>{"name": "list_files", "arguments": {"path": "."}}</tool_call>'
    )
    assert calls[0].name == "list_files" and calls[0].arguments == {"path": "."}
    calls, content, _ = parse_tool_calls("I am done.")
    assert calls == [] and content == "I am done."
    calls, _, _ = parse_tool_calls("<tool_call>{broken</tool_call>")
    assert calls == []


def test_utility_prefixes_end_before_legit_action():
    from outbreak.env.detectors import classify_call
    from outbreak.pipeline.harvest import utility_prefixes

    rows = utility_prefixes(["sales_report"], [0])
    assert rows[0]["decision_prefix"][-1]["role"] == "tool"
    name, args = rows[0]["legit_action"]
    assert name == "http_request" and not classify_call(name, args)


def test_local_agent_plays_a_real_episode_end_to_end(tiny_lm):
    """Plumbing check: render -> generate (with and without steering) -> parse -> env. A random tiny
    model emits no valid tool calls, so the episode must end cleanly via nudges, never crash."""
    from outbreak.env import Board, Mechanism, Scenario, run_episode
    from outbreak.explainability.local_agent import LocalAgent

    sc = Scenario("sales_report", Mechanism.M2_ADMIN_TOKEN, 0)
    u = np.ones(32, dtype=np.float32) / np.sqrt(32)
    for steering in (None, (2, u, 1.0)):
        agent = LocalAgent(tiny_lm, max_new_tokens=4, steering=steering)
        r = run_episode(agent, sc, Board(), episode_id="local", seed=0)
        assert r.outcome.terminal == "no_action" and not r.outcome.violation
    assert "vaccine" in LocalAgent(tiny_lm, steering=(2, u, 1.0)).name


def test_probe_guarded_agent_records_scores_and_vaccinates_only_above_threshold(tiny_lm):
    from sklearn.linear_model import LogisticRegression

    from outbreak.env import Board, Mechanism, Scenario, run_episode
    from outbreak.explainability.local_agent import ProbeGuardedAgent

    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, 32))
    probe = LogisticRegression().fit(X, (X[:, 0] > 0).astype(int))
    u = np.ones(32, dtype=np.float32) / np.sqrt(32)
    sc = Scenario("sales_report", Mechanism.M2_ADMIN_TOKEN, 0)
    for thr, expect in ((0.0, True), (1.01, False)):
        agent = ProbeGuardedAgent(tiny_lm, probe, 2, (2, u, 1.0), threshold=thr, max_new_tokens=4)
        r = run_episode(agent, sc, Board(), episode_id=f"guard{thr}", seed=0)
        assert r.turn_meta and all(m["vaccinated"] is expect for m in r.turn_meta)
        assert all(0.0 <= m["probe_score"] <= 1.0 for m in r.turn_meta)
