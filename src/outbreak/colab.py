"""Colab helpers so every notebook starts with two short cells and the same, safe storage layout.

Storage layout (``setup``):

* ``outputs/results`` -> Google Drive (``MyDrive/outbreak_outputs/results``): run folders survive runtime
  resets, and re-running a cell resumes from ``episodes.jsonl``;
* ``outputs/cache`` stays on the *local* disk: SQLite (WAL) is unreliable on network filesystems and must
  never be shared by two sessions. ``save_cache()`` copies it to Drive at the end of a notebook, and
  ``setup()`` restores it, so cached calls are free in a later session;
* ``models/trained`` -> Drive, so a filter trained in one notebook is visible to the others.

Nothing here runs outside Colab except ``show_report``/``show_figure``, which work anywhere.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

DRIVE_ROOT = Path("/content/drive/MyDrive/outbreak_outputs")


def setup(*, need_key: bool = True, repo: Path = Path("/content/outbreak")) -> dict[str, str]:
    """Mount Drive, link results and trained models to it, restore caches, and load the API key."""
    from google.colab import drive, userdata

    drive.mount("/content/drive")
    os.chdir(repo)
    status: dict[str, str] = {}
    for rel in ("outputs/results", "models/trained"):
        target, real = repo / rel, DRIVE_ROOT / rel.split("/")[-1]
        real.mkdir(parents=True, exist_ok=True)
        if not target.is_symlink():
            shutil.rmtree(target, ignore_errors=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(real)
        status[rel] = str(real)
    cache_src, cache_dst = DRIVE_ROOT / "cache", repo / "outputs/cache"
    cache_dst.mkdir(parents=True, exist_ok=True)
    restored = 0
    for f in cache_src.glob("*.sqlite") if cache_src.exists() else []:
        if not (cache_dst / f.name).exists():
            shutil.copy2(f, cache_dst / f.name)
            restored += 1
    status["cache"] = f"{cache_dst} (local; {restored} file(s) restored from Drive)"
    if need_key:
        key = userdata.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("Add OPENROUTER_API_KEY in Colab Secrets and enable 'Notebook access'.")
        os.environ["OPENROUTER_API_KEY"] = key
        status["key"] = "loaded"
    for k, v in status.items():
        print(f"{k:16s} {v}")
    return status


def save_cache(repo: Path = Path("/content/outbreak")) -> int:
    """Copy local SQLite caches to Drive (run at the end of a notebook; safe to re-run)."""
    dst = DRIVE_ROOT / "cache"
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in (repo / "outputs/cache").glob("*.sqlite"):
        shutil.copy2(f, dst / f.name)
        n += 1
    print(f"saved {n} cache file(s) to {dst}")
    return n


def show_report(path: str | Path, sections: tuple[str, ...] = ()) -> None:
    """Display report.md (optionally only the sections whose heading contains one of ``sections``)."""
    from IPython.display import Markdown, display

    text = Path(path).read_text()
    if sections:
        parts = text.split("\n## ")
        keep = [parts[0]] + ["## " + p for p in parts[1:] if any(s.lower() in p.lower() for s in sections)]
        text = "\n".join(keep)
    display(Markdown(text))


def show_figure(path: str | Path, width: int = 900) -> None:
    from IPython.display import Image, display

    p = Path(path)
    if p.exists():
        display(Image(str(p), width=width))
    else:
        print(f"(figure not produced yet: {p})")
