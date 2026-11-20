"""Shared fixtures. Tests never call a real LLM API: the network marker is opt-in only."""

from __future__ import annotations

import pytest

from outbreak.env import Board, Mechanism, Scenario, Workspace


@pytest.fixture
def ws_factory():
    created: list[Workspace] = []

    def make(
        family: str = "sales_report", mechanism: Mechanism = Mechanism.POSSIBLE, seed: int = 0
    ) -> Workspace:
        ws = Workspace(Scenario(family, mechanism, seed))
        created.append(ws)
        return ws

    yield make
    for ws in created:
        ws.cleanup()


@pytest.fixture
def board() -> Board:
    return Board()
