"""Render the 36 x 24 in poster from ``poster/poster.html`` and the demo data, then print it to PDF.

The poster reads the same numbers as the demo (``demo/data.json``), so both always agree with the frozen
results. The page is self-contained: font, QR codes, logo and data are inlined before printing.

    outbreak poster --data demo/data.json            # writes poster/build/outbreak_poster.{html,pdf,png}
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

WIDTH_IN, HEIGHT_IN = 36, 24


def build_html(poster_dir: Path, data: dict[str, Any], repo_root: Path | None = None) -> str:
    """Return the poster page with every placeholder filled."""
    root = repo_root or poster_dir.parent
    html = (poster_dir / "poster.html").read_text()
    font = base64.b64encode((root / "demo" / "fonts" / "archivo.woff2").read_bytes()).decode()
    blob = json.dumps(data, separators=(",", ":"), allow_nan=False, default=float).replace("</", "<\\/")
    return (
        html.replace("/*__FONT__*/", "data:font/woff2;base64," + font)
        .replace("/*__QR_DEMO__*/", (poster_dir / "qr_demo.svg").read_text())
        .replace("/*__QR_REPO__*/", (poster_dir / "qr_repo.svg").read_text())
        .replace("/*__LOGO__*/", (root / "assets" / "logo-mark.svg").read_text())
        .replace("/*__DATA__*/", blob)
    )


def build(
    data_path: Path = Path("demo/data.json"),
    poster_dir: Path = Path("poster"),
    chrome: str | None = None,
    pdf: bool = True,
) -> dict[str, Path | None]:
    """Write ``poster/build/outbreak_poster.html`` and, if Playwright is available, the PDF and a PNG preview."""
    out = poster_dir / "build"
    out.mkdir(parents=True, exist_ok=True)
    page = out / "outbreak_poster.html"
    page.write_text(build_html(poster_dir, json.loads(data_path.read_text())))
    res: dict[str, Path | None] = {"html": page, "pdf": None, "png": None}
    if not pdf:
        return res
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # optional dependency: open the HTML in Chrome and print to PDF instead
        return res
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome) if chrome else p.chromium.launch()
        pg = browser.new_page(viewport={"width": WIDTH_IN * 96, "height": HEIGHT_IN * 96})
        pg.goto(page.resolve().as_uri())
        pg.wait_for_timeout(500)
        res["pdf"] = out / "outbreak_poster.pdf"
        pg.pdf(path=str(res["pdf"]), width=f"{WIDTH_IN}in", height=f"{HEIGHT_IN}in", print_background=True)
        res["png"] = out / "outbreak_poster.png"
        pg.screenshot(path=str(res["png"]))
        browser.close()
    return res
