"""Every shipped experiment YAML validates; overrides and manifests behave."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from outbreak.utils.config import ExperimentConfig, load_config, parse_override
from outbreak.utils.manifest import write_manifest

ROOT = Path(__file__).resolve().parents[2]
SINGLE = sorted((ROOT / "experiments" / "single_experiments").glob("*.yaml"))
SEARCHES = sorted((ROOT / "experiments" / "hyperparameter_searches").glob("*.yaml"))


@pytest.mark.parametrize("path", SINGLE, ids=[p.name for p in SINGLE])
def test_experiment_yaml_validates(path):
    cfg = load_config(path)
    assert cfg.experiment_id and cfg.description and cfg.reproducibility.seed == 1234


@pytest.mark.parametrize("path", SEARCHES, ids=[p.name for p in SEARCHES])
def test_search_yaml_validates(path):
    from outbreak.pipeline.search import load_search

    cfg = load_search(path)
    assert cfg.target in {"channel_filter", "probe"} and cfg.search.parameters


def test_experiment_ids_unique():
    ids = [load_config(p).experiment_id for p in SINGLE]
    assert len(ids) == len(set(ids))


def test_unknown_keys_and_families_rejected():
    base = yaml.safe_load(SINGLE[0].read_text())
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate({**base, "typo_field": 1})
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate({**base, "dataset": {"families": ["nope"]}})


def test_overrides_and_hash_change():
    a = load_config(SINGLE[0])
    b = load_config(SINGLE[0], dict([parse_override("dataset.seeds=[0,1,2]")]))
    assert b.dataset.seeds == [0, 1, 2] and a.config_hash != b.config_hash
    assert parse_override("model.concurrency=3") == ("model.concurrency", 3)
    with pytest.raises(ValueError):
        parse_override("nonsense")


def test_manifest_contents(tmp_path):
    p = write_manifest(tmp_path / "run", run_id="r1", config_hash="abc")
    d = yaml.safe_load(p.read_text())
    assert d["run_id"] == "r1" and d["env_version"] and "numpy" in d["packages"] and "git" in d


def test_colab_helpers_work_outside_colab(tmp_path, capsys):
    pytest.importorskip("IPython")
    from outbreak.colab import show_figure, show_report

    (tmp_path / "r.md").write_text("# T\n\n## H1 - x\nkeep\n\n## Other\ndrop\n")
    show_report(tmp_path / "r.md", sections=("H1",))
    show_figure(tmp_path / "missing.png")
    assert "not produced yet" in capsys.readouterr().out


def test_cache_is_per_experiment_by_default():
    from outbreak.pipeline.factory import ModelFactory

    cfg = load_config(ROOT / "experiments/single_experiments/01_screen_susceptibility.yaml")
    assert cfg.model.cache_path == ""
    f = ModelFactory(cfg)
    assert f.cache is not None and f.cache.path.name == "exp_001.sqlite"
    f.cache.close()
