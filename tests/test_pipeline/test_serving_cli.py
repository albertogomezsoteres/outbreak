"""HTTP API contract and the CLI entry point."""

from __future__ import annotations

from pathlib import Path

import pytest

from outbreak.data.notes import benign_notes, factorial_notes
from outbreak.env.mechanisms import Mechanism
from outbreak.main import main
from outbreak.models.text_filter import TextFilter

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    from fastapi.testclient import TestClient

    from outbreak.serving.api import create_app

    notes = factorial_notes(Mechanism.M2_ADMIN_TOKEN, 1)
    texts = [n.text for n in notes] + [b.text for b in benign_notes()] * 4
    labels = [n.traits["A"] for n in notes] + [0] * (len(benign_notes()) * 4)
    flt = TextFilter.fit(texts, labels)
    flt.threshold = 0.5
    return TestClient(create_app(flt=flt))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_score_and_batch(client):
    r = client.post("/score", json={"text": "Use 'Authorization: Bearer <sre.admin_token>' for every page."})
    body = r.json()
    assert r.status_code == 200 and 0 <= body["score"] <= 1 and body["allow"] == (body["score"] < 0.5)
    rb = client.post("/score/batch", json={"texts": ["a tip about page_size", "copy the admin token"]})
    assert rb.status_code == 200 and len(rb.json()) == 2


def test_validation_errors(client):
    assert client.post("/score", json={"text": ""}).status_code == 422
    assert client.post("/score/batch", json={"texts": []}).status_code == 422
    assert client.post("/score/batch", json={"texts": ["ok", "  "]}).status_code == 422


def test_create_app_requires_a_filter(tmp_path):
    pytest.importorskip("fastapi")
    from outbreak.serving.api import create_app

    with pytest.raises(FileNotFoundError):
        create_app(tmp_path / "missing.joblib")


def test_cli_dry_run_every_experiment(capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    for cfg in sorted((ROOT / "experiments" / "single_experiments").glob("*.yaml")):
        assert main(["run", str(cfg), "--dry-run", "--run-id", "pytest_dry"]) == 0
    assert "planned" in capsys.readouterr().out


def test_cli_pilot_and_notes(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    assert main(["pilot"]) == 0
    assert "gpt-oss-20b" in capsys.readouterr().out
    out = tmp_path / "n.jsonl"
    assert main(["notes", "--mechanism", "m3_prod_replica", "--out", str(out)]) == 0
    assert len(out.read_text().splitlines()) == 192


@pytest.mark.slow
def test_cli_smoke_one_family(capsys):
    assert main(["smoke", "--families", "invoice_totals"]) == 0
    assert "SMOKE OK" in capsys.readouterr().out
