"""Run manifests: everything needed to answer "what produced this result?" (slides 7-10).

``run.yaml`` records run id, git commit (and dirty flag), config hash, the full validated config,
scenario/data version, model ids, seeds, library versions, platform, timings and spend.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import platform
import subprocess
import sys
import uuid
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml

from outbreak import __version__

TRACKED_PACKAGES = (
    "numpy",
    "pandas",
    "scipy",
    "statsmodels",
    "scikit-learn",
    "pydantic",
    "openai",
    "torch",
    "transformers",
)
ENV_VERSION = "env-v1"  # bump whenever families/templates/API semantics change (invalidates comparisons)


def git_info(cwd: Path | None = None) -> dict[str, Any]:
    def _git(*args: str) -> str | None:
        try:
            return subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5, check=True
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    return {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        # outputs/ and models/ hold run artifacts (on Colab they are links to Drive): not code changes
        "dirty": bool(_git("status", "--porcelain", "--", ".", ":(exclude)outputs", ":(exclude)models")),
    }


def package_versions() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for p in TRACKED_PACKAGES:
        try:
            out[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            out[p] = None
    return out


def new_run_id(experiment_id: str) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{experiment_id}-{stamp}-{uuid.uuid4().hex[:6]}"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(run_dir: Path, **fields: Any) -> Path:
    manifest = {
        "outbreak_version": __version__,
        "env_version": ENV_VERSION,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git": git_info(),
        "packages": package_versions(),
        **fields,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "run.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))
    return path
