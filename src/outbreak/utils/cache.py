"""Content-addressed SQLite cache for LLM calls.

Key = sha256 of the canonical JSON of (model, messages, tools, sampling params, seed, episode key).
Including the episode key means two replicate episodes with identical prompts are *not* collapsed
onto one cached sample (that would silently destroy independence), while re-running the same
experiment replays every call exactly, at zero cost. The cache is safe for concurrent threads.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


def cache_key(payload: dict[str, Any]) -> str:
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canon.encode()).hexdigest()


class LLMCache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, model TEXT, response TEXT, created REAL)"
        )

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT response FROM calls WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, model: str, response: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO calls VALUES (?,?,?,?)",
                (key, model, json.dumps(response), time.time()),
            )

    def __len__(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()
