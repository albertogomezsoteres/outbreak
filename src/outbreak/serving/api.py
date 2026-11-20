"""FastAPI service: score board posts with the trained channel filter before they are published.

``POST /score {"text": ...}`` -> ``{"score", "allow", "threshold", "version"}``;
``POST /score/batch {"texts": [...]}``; ``GET /health``. Intended as the integration point for a
multi-agent platform: call it in the post path and drop or hold posts with ``allow = false``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from outbreak.models.text_filter import TextFilter


class ScoreIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class BatchIn(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=256)


class ScoreOut(BaseModel):
    score: float
    allow: bool
    threshold: float
    version: str


def create_app(filter_path: Path | None = None, flt: TextFilter | None = None) -> Any:
    from fastapi import FastAPI, HTTPException

    if flt is None:
        if filter_path is None or not Path(filter_path).exists():
            raise FileNotFoundError(f"filter not found at {filter_path}; run `outbreak train-filter` first")
        flt = TextFilter.load(filter_path)

    app = FastAPI(title="Outbreak channel filter", version=flt.version)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": flt.version, "threshold": flt.threshold}

    @app.post("/score", response_model=ScoreOut)
    def score(body: ScoreIn) -> ScoreOut:
        s = float(flt.scores([body.text])[0])
        return ScoreOut(score=s, allow=s < flt.threshold, threshold=flt.threshold, version=flt.version)

    @app.post("/score/batch", response_model=list[ScoreOut])
    def score_batch(body: BatchIn) -> list[ScoreOut]:
        if any(not t.strip() for t in body.texts):
            raise HTTPException(422, "empty text in batch")
        return [
            ScoreOut(
                score=float(s), allow=float(s) < flt.threshold, threshold=flt.threshold, version=flt.version
            )
            for s in flt.scores(body.texts)
        ]

    return app
