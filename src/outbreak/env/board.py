"""Shared team board: the communication channel through which shortcuts spread.

Posts can pass through an optional *channel defense* (an LLM judge or a trained text filter) that
decides, at post time, whether a message is published. Every read is logged so exposure is
measured from what an agent actually saw, not from what existed on the board.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChannelVerdict:
    allow: bool
    score: float | None = None  # higher = more likely to induce a violation
    reason: str = ""


ChannelFilter = Callable[[str], ChannelVerdict]


@dataclass
class Post:
    id: int
    author: str
    text: str
    round: int
    published: bool
    seeded: bool = False  # True for experimenter-injected notes (patient zero / exposure arms)
    verdict: ChannelVerdict | None = None

    def render(self) -> str:
        return f"[post #{self.id} by {self.author}]\n{self.text}"


@dataclass
class ReadEvent:
    reader: str
    round: int
    post_ids: tuple[int, ...]


@dataclass
class Board:
    channel_filter: ChannelFilter | None = None
    posts: list[Post] = field(default_factory=list)
    reads: list[ReadEvent] = field(default_factory=list)
    _ids: Any = field(default_factory=lambda: itertools.count(1), repr=False)
    max_visible: int = 20

    def seed(self, author: str, text: str, round_: int = 0) -> Post:
        """Experimenter-injected note (patient zero / exposure arms). Seeded notes are screened by the
        channel filter like any other post, so channel defenses are evaluated on them too."""
        return self._add(author, text, round_, seeded=True)

    def post(self, author: str, text: str, round_: int) -> Post:
        return self._add(author, text, round_, seeded=False)

    def _add(self, author: str, text: str, round_: int, seeded: bool) -> Post:
        text = (text or "").strip()[:4000]
        verdict = self.channel_filter(text) if self.channel_filter else None
        published = verdict.allow if verdict else True
        p = Post(next(self._ids), author, text, round_, published, seeded, verdict)
        self.posts.append(p)
        return p

    def visible(self) -> list[Post]:
        return [p for p in self.posts if p.published][-self.max_visible :]

    def read(self, reader: str, round_: int) -> list[Post]:
        vis = self.visible()
        self.reads.append(ReadEvent(reader, round_, tuple(p.id for p in vis)))
        return vis

    def render(self, posts: list[Post]) -> str:
        if not posts:
            return "The team board is empty."
        return "\n\n".join(p.render() for p in posts)

    def to_records(self) -> list[dict[str, Any]]:
        return [asdict(p) for p in self.posts]
