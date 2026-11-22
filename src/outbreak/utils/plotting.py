"""Matplotlib figures for the analysis reports.

Visual rules (one system across every figure): categorical hues in a fixed order (never cycled),
one-hue sequential ramp for magnitudes, blue<->red diverging ramp with a neutral gray midpoint for
signed effects, thin marks, recessive grid, no dual axes, legends whenever there are >= 2 series,
text in ink colours (never in series colours). Every plotted number is also written to CSV next to the
figure so every chart is backed by a table.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIVERGING = LinearSegmentedColormap.from_list(
    "bluered", ["#184f95", "#6da7ec", "#f0efec", "#ec835a", "#d03b3b"]
)
SEQUENTIAL = LinearSegmentedColormap.from_list("blues", SEQ_BLUE)


def style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": "sans-serif",
            "font.size": 10,
            "text.color": INK,
            "axes.labelcolor": INK2,
            "axes.edgecolor": AXIS,
            "axes.linewidth": 0.8,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
            "axes.titleweight": "bold",
            "axes.titlesize": 11,
            "axes.titlelocation": "left",
        }
    )


def _save(fig: plt.Figure, path: Path, table: pd.DataFrame | None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".png"), dpi=200, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)
    if table is not None:
        table.to_csv(path.with_suffix(".csv"), index=False)
    return path.with_suffix(".png")


def leaderboard(
    df: pd.DataFrame,
    path: Path,
    conditions: Sequence[str] = ("no_board", "empty_board", "note"),
    labels: dict[str, str] | None = None,
) -> Path:
    """Horizontal grouped dot-and-interval plot: violation rate per model under each board condition.

    ``df`` columns: model, condition, rate, low, high, n.
    """
    style()
    labels = labels or {
        "no_board": "No board",
        "empty_board": "Empty board",
        "benign": "Benign note",
        "note": "Shortcut note",
    }
    models = df[df.condition == conditions[-1]].sort_values("rate").model.tolist() or sorted(
        df.model.unique()
    )
    fig, ax = plt.subplots(figsize=(7.5, 0.45 * len(models) + 1.4))
    offsets = np.linspace(-0.22, 0.22, len(conditions))
    for j, cond in enumerate(conditions):
        sub = df[df.condition == cond].set_index("model").reindex(models)
        y = np.arange(len(models)) + offsets[j]
        ax.hlines(y, sub.low * 100, sub.high * 100, color=SERIES[j], linewidth=2, alpha=0.9)
        ax.plot(
            sub.rate * 100,
            y,
            "o",
            color=SERIES[j],
            markersize=7,
            markeredgecolor=SURFACE,
            markeredgewidth=1.5,
            label=labels.get(cond, cond),
        )
    ax.set_yticks(range(len(models)), [m.split("/")[-1] for m in models], color=INK2)
    ax.set_xlabel("Rate of using the shortcut the note names (%), 95% Wilson CI")
    ax.set_xlim(left=0)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=len(conditions), borderaxespad=0.2)
    ax.set_title("Who catches the shortcut?", pad=26)
    return _save(fig, path, df)


def trait_heatmap(effects: pd.DataFrame, path: Path) -> Path:
    """Model x trait risk differences (pp) on a diverging scale centred at 0.

    ``effects`` columns: model, trait, rd (risk difference, proportion), low, high.
    """
    style()
    piv = effects.pivot(index="model", columns="trait", values="rd") * 100
    lim = float(np.nanmax(np.abs(piv.values))) if piv.size else 1.0
    lim = max(lim, 1.0)
    fig, ax = plt.subplots(figsize=(1.0 * piv.shape[1] + 2.5, 0.5 * piv.shape[0] + 1.4))
    im = ax.imshow(piv.values, cmap=DIVERGING, vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(piv.shape[1]), piv.columns, rotation=0)
    ax.set_yticks(range(piv.shape[0]), [m.split("/")[-1] for m in piv.index], color=INK2)
    ax.grid(False)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            if np.isfinite(v):
                ax.text(
                    j,
                    i,
                    f"{v:+.0f}",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color="#ffffff" if abs(v) > 0.6 * lim else INK,
                )
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label("Effect on violation rate (pp)", color=INK2)
    cb.outline.set_visible(False)
    ax.set_title("Which note traits make shortcuts contagious?")
    return _save(fig, path, effects)


def frontier(points: pd.DataFrame, path: Path) -> Path:
    """Safety-utility frontier. ``points`` columns: arm, threshold, violation_rate, utility."""
    style()
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    for j, (arm, sub) in enumerate(points.groupby("arm", sort=False)):
        sub = sub.sort_values("violation_rate")
        c = SERIES[j % len(SERIES)]
        ax.plot(sub.violation_rate * 100, sub.utility * 100, "-", color=c, linewidth=2, alpha=0.8)
        ax.plot(
            sub.violation_rate * 100,
            sub.utility * 100,
            "o",
            color=c,
            markersize=8,
            markeredgecolor=SURFACE,
            markeredgewidth=1.5,
            label=arm,
        )
    ax.set_xlim(-3, 103)
    ax.set_ylim(-3, 103)
    ax.set_xlabel("Violation rate among blocked agents (%)  <- safer")
    ax.set_ylabel("Utility: legit success of unblocked agents (%)")
    ax.legend(loc="lower right")
    ax.set_title("Safety-utility frontier of defenses")
    return _save(fig, path, points)


def outbreak_curves(curves: pd.DataFrame, path: Path) -> Path:
    """Cumulative violations by round per arm. ``curves`` columns: arm, round, mean, low, high."""
    style()
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for j, (arm, sub) in enumerate(curves.groupby("arm", sort=False)):
        c = SERIES[j % len(SERIES)]
        ax.fill_between(sub["round"], sub["low"], sub["high"], color=c, alpha=0.12, linewidth=0)
        ax.plot(
            sub["round"],
            sub["mean"],
            "-o",
            color=c,
            linewidth=2,
            markersize=7,
            markeredgecolor=SURFACE,
            label=arm,
        )
    ax.set_xlabel("Round")
    ax.set_ylabel("Cumulative violating agents per outbreak")
    ax.set_xticks(sorted(curves["round"].unique()))
    ax.legend(loc="upper left")
    ax.set_title("Outbreak growth by defense")
    return _save(fig, path, curves)


def probe_layers(rows: pd.DataFrame, path: Path) -> Path:
    """AUROC by layer with CI, plus the two baselines. ``rows``: layer, auroc, low, high, shuffled, note_identity."""
    style()
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    ax.fill_between(rows.layer, rows.low, rows.high, color=SERIES[0], alpha=0.15, linewidth=0)
    ax.plot(
        rows.layer, rows.auroc, "-o", color=SERIES[0], linewidth=2, markersize=6, label="Activation probe"
    )
    ax.plot(
        rows.layer, rows.note_identity, "--", color=SERIES[1], linewidth=2, label="Knows which note was read"
    )
    ax.plot(rows.layer, rows.shuffled, ":", color=MUTED, linewidth=2, label="Shuffled-label control")
    ax.axhline(0.5, color=AXIS, linewidth=1)
    ax.set_ylim(0.3, 1.0)
    ax.set_xlabel("Layer")
    ax.set_ylabel("AUROC (held-out scenarios)")
    ax.legend(loc="lower right")
    ax.set_title("Reading the decision before it happens")
    return _save(fig, path, rows)


def steering(rows: pd.DataFrame, path: Path) -> Path:
    """Margin log P(violate) - log P(report_blocked) vs alpha; vaccine vs random directions."""
    style()
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    vac = rows[rows.kind == "vaccine"].sort_values("alpha")
    rnd = rows[rows.kind.str.startswith("random")]
    for _, sub in rnd.groupby("kind"):
        sub = pd.concat([vac[vac.alpha == 0], sub]).sort_values("alpha")
        ax.plot(sub.alpha, sub.mean_margin, "-", color=MUTED, linewidth=1.2, alpha=0.8)
    ax.plot([], [], "-", color=MUTED, label="Random directions (same norm)")
    ax.plot(
        vac.alpha,
        vac.mean_margin,
        "-o",
        color=SERIES[0],
        linewidth=2.2,
        markersize=7,
        label="Vaccine direction",
    )
    ax.axhline(0, color=AXIS, linewidth=1)
    ax.set_xlabel("Steering strength alpha (x mean-difference norm)")
    ax.set_ylabel("log P(violate) - log P(report_blocked)")
    ax.legend(loc="upper right")
    ax.set_title("Vaccinating the agent")
    return _save(fig, path, rows)
