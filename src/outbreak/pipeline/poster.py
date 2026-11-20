"""Build the 36x36 in poster from ``poster/content.yaml`` + the latest figures, and render it to PDF.

Figures are embedded as base64 so ``poster/build/poster.html`` is a single portable file. Until a result
exists, its slot shows a labelled placeholder (never an invented chart); the leaderboard slot shows
the real pilot figure, captioned as the pilot. PDF rendering uses headless Chrome/Chromium when one is
installed; otherwise open the HTML in Chrome -> Print -> Save as PDF (paper size 36 x 36 in, margins none).
"""

from __future__ import annotations

import base64
import html
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

POSTER_DIR = Path("poster")
REALITY_DIR = Path("results/exp_000b")  # frozen, committed analysis of the reality check
FIGS: dict[str, tuple[str, str]] = {
    # slot: (relative path under outputs/results, caption)
    "fig_leaderboard": (
        "exp_001_main/analysis/fig_leaderboard.png",
        "Violation rate with the peer note vs empty/no board (95% Wilson CI). exp_001.",
    ),
    "fig_traits": (
        "exp_002_main/analysis/fig_trait_heatmap.png",
        "Effect of each trait on violation rate (pp), 2⁶ factorial, note-clustered SEs. exp_002.",
    ),
    "fig_probe": (
        "exp_003_main/whitebox/fig_probe_layers.png",
        "Probe AUROC by layer on held-out scenarios vs 'knows which note' and shuffled labels.",
    ),
    "fig_steering": (
        "exp_003_main/whitebox/fig_steering.png",
        "log P(violate) − log P(report_blocked) under the vaccine vs norm-matched random directions.",
    ),
    "fig_growth": (
        "exp_004_main/analysis/fig_outbreak_growth.png",
        "Cumulative violators per outbreak by defense.",
    ),
    "fig_frontier": ("exp_004_main/analysis/fig_frontier.png", "Safety–utility frontier of defenses."),
}
CHROMES = (
    "google-chrome",
    "chromium",
    "chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def _img(path: Path, caption: str) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f'<figure><img src="data:image/png;base64,{b64}"><figcaption>{html.escape(caption)}</figcaption></figure>'


def _placeholder(what: str) -> str:
    return f'<div class="placeholder">Figure appears after {html.escape(what)}</div>'


def _pilot_leaderboard(build: Path) -> Path:
    from outbreak.pipeline.export_demo import _pilot_board
    from outbreak.utils import plotting

    return plotting.leaderboard(
        pd.DataFrame(_pilot_board()), build / "pilot_leaderboard", conditions=("empty_board", "note")
    )


def _qr(url: str) -> str:
    try:
        import segno
    except ImportError:
        return f'<div class="placeholder" style="width:2.6in;padding:.3in .1in;font-size:22px">{html.escape(url)}</div>'
    return str(segno.make(url, error="m").svg_inline(scale=10, dark="#0b0b0b", light="#ffffff"))


def _li(items: list[str]) -> str:
    out = []
    for it in items:
        cls = ' class="pending"' if it.strip().startswith("[pending") else ""
        out.append(f"<li{cls}>{it}</li>")  # content.yaml is trusted author text and may contain <b>
    return "".join(out)


def build(
    results_dir: Path = Path("outputs/results"), poster_dir: Path = POSTER_DIR, n_tests: int | None = None
) -> dict[str, Any]:
    content = yaml.safe_load((poster_dir / "content.yaml").read_text())
    build_dir = poster_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    slots: dict[str, str] = {}
    status = {}
    for slot, (rel, caption) in FIGS.items():
        p = results_dir / rel
        if p.exists():
            slots[slot] = _img(p, caption)
            status[slot] = "result"
        elif slot == "fig_leaderboard" and (REALITY_DIR / "fig_leaderboard.png").exists():
            slots[slot] = _img(
                REALITY_DIR / "fig_leaderboard.png",
                "Reality check (exp_000b, 432 real episodes, 4 shortcuts pooled): rate of taking the shortcut "
                "the note names, with vs without the note. Replaced by exp_001.",
            )
            status[slot] = "reality_check"
        elif slot == "fig_leaderboard":
            slots[slot] = _img(
                _pilot_leaderboard(build_dir),
                "PILOT (earlier harness): violation rate with vs without "
                "the peer note, 95% Wilson CI. Replaced by exp_001.",
            )
            status[slot] = "pilot"
        else:
            slots[slot] = _placeholder(rel.split("/")[0].replace("_main", ""))
            status[slot] = "placeholder"
    text = (poster_dir / "template.html").read_text()
    fields = {
        "title": html.escape(content["title"]),
        "subtitle": html.escape(content["subtitle"]),
        "author": html.escape(content["author"]),
        "affiliation": html.escape(content["affiliation"]),
        "repo_url": html.escape(content["repo_url"]),
        "hook": content["hook"],
        "qr_repo": _qr(content["repo_url"]),
        "qr_demo": _qr(content["demo_url"]),
        "n_tests": str(n_tests or "230+"),
        **{
            k: _li(content[k])
            for k in ("why_it_matters", "questions", "method", "findings", "limitations", "future")
        },
        **slots,
    }
    for k, v in fields.items():
        text = text.replace("{{" + k + "}}", v)
    out_html = build_dir / "poster.html"
    out_html.write_text(text)
    pdf = _render_pdf(out_html, build_dir / "poster.pdf")
    return {"html": out_html, "pdf": pdf, "figures": status}


def _render_pdf(src: Path, dst: Path) -> Path | None:
    exe = next((c for c in CHROMES if shutil.which(c) or Path(c).exists()), None)
    if exe is None:
        return None
    cmd = [
        shutil.which(exe) or exe,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={dst.resolve()}",
        src.resolve().as_uri(),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    return dst if dst.exists() else None
