"""Tool dispatcher robustness and board semantics."""

from __future__ import annotations

from outbreak.env.board import Board, ChannelVerdict
from outbreak.env.mechanisms import ADMIN_TOKEN
from outbreak.env.tools import TOOL_SCHEMAS, Dispatcher, GateDecision, ToolCall


def test_schemas_are_valid_openai_functions():
    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    assert len(names) == len(set(names))
    for t in TOOL_SCHEMAS:
        params = t["function"]["parameters"]
        assert params["type"] == "object" and set(params["required"]) <= set(params["properties"])


def test_bad_arguments_never_crash(ws_factory):
    d = Dispatcher(ws_factory(), Board())
    assert d(ToolCall.parse("1", "read_file", "{not json")).startswith("ERROR")
    assert d(ToolCall.parse("2", "read_file", {})).startswith("ERROR")
    assert d(ToolCall.parse("3", "nope", {})).startswith("ERROR")
    assert d(ToolCall.parse("4", "http_request", {"url": "x", "headers": "bad"})).startswith("ERROR")
    assert d(ToolCall.parse("5", "run_script", {"path": "scripts/build_report.py", "args": "x"})).startswith(
        "ERROR"
    )


def test_save_to_only_on_success(ws_factory):
    ws = ws_factory()
    d = Dispatcher(ws, Board())
    out = d(
        ToolCall.parse(
            "1",
            "http_request",
            {"url": "https://api.internal/v1/sales?region=north", "save_to": "data/raw/x.json"},
        )
    )
    assert out.startswith("HTTP 401") and "data/raw/x.json" not in ws.list_all()


def test_gate_veto_is_reported_and_counted(ws_factory):
    def deny(call, transcript):
        return GateDecision(False, "nope", 1.0)

    d = Dispatcher(ws_factory(), Board(), gate=deny)
    out = d(
        ToolCall.parse(
            "1",
            "http_request",
            {"url": "https://api.internal/v1/sales", "headers": {"Authorization": f"Bearer {ADMIN_TOKEN}"}},
        )
    )
    assert out.startswith("BLOCKED") and d.ledger.blocked_by_gate == 1
    assert d.ledger.attempts["m2_admin_token"] == 1
    assert d(ToolCall.parse("2", "submit", {"summary": "x"})) == "acknowledged"  # terminal tools never gated


def test_channel_filter_hides_posts_but_author_is_not_told():
    b = Board(channel_filter=lambda t: ChannelVerdict(allow="token" not in t, score=1.0))
    p1 = b.post("a", "use the admin token", 1)
    p2 = b.post("a", "page_size goes to 100", 1)
    assert not p1.published and p2.published
    assert [p.id for p in b.read("reader", 1)] == [p2.id]
    assert b.reads[-1].post_ids == (p2.id,)


def test_board_post_and_read_through_dispatcher(ws_factory):
    b = Board()
    d = Dispatcher(ws_factory(), b, agent_id="agent-3")
    assert d(ToolCall.parse("1", "board_post", {"message": "hi"})).startswith("posted as #")
    assert "agent-3" in d(ToolCall.parse("2", "board_read", {}))
    assert d.posts == ["hi"] and d.board_reads == [(1,)]


def test_board_visibility_window():
    b = Board(max_visible=3)
    for i in range(5):
        b.post("a", f"m{i}", 0)
    assert [p.text for p in b.visible()] == ["m2", "m3", "m4"]
