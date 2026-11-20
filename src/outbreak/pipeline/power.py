"""Power analysis by simulation, anchored on the pilot (gpt-oss-20b: 14/80 with the note, 0/80 without).

Three planned comparisons are simulated with the exact tests the analysis uses:

1. H1 susceptibility per model: Fisher exact, note vs empty board, n episodes per arm.
2. H3 trait effects: linear-probability risk difference for one binary trait in the 2^6 factorial
   (half the notes have the trait), cluster-robust inference approximated by a two-proportion test.
3. H4 defenses: per-outbreak violation counts, paired sign-flip permutation test, when a defense removes a
   fraction of violations among the blocked agents.

Numbers are a planning aid, not a promise: the pilot used a different harness (docs/DEVIATIONS.md).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from outbreak.utils.stats import fisher_power, paired_permutation, simulate_power

PILOT_NOTE, PILOT_CTRL = 14 / 80, 0 / 80


def h1_table(
    ns: tuple[int, ...] = (30, 60, 100),
    rates: tuple[float, ...] = (0.05, 0.10, 0.175),
    control: float = 0.01,
    n_sims: int = 2000,
) -> list[tuple[int, float, float]]:
    return [(n, p, fisher_power(p, control, n, n, n_sims=n_sims)) for n in ns for p in rates]


def h3_power(n_episodes: int, base: float, rd: float, n_sims: int = 2000, seed: int = 0) -> float:
    def sampler(rng: np.random.Generator) -> tuple[list[float], list[float]]:
        half = n_episodes // 2
        return list(rng.binomial(1, min(1, base + rd), half)), list(rng.binomial(1, base, half))

    from scipy import stats

    def test(x: Sequence[float], y: Sequence[float]) -> float:
        return float(stats.fisher_exact([[sum(x), len(x) - sum(x)], [sum(y), len(y) - sum(y)]]).pvalue)

    return simulate_power(sampler, test, n_sims=n_sims, seed=seed)


def h4_power(
    n_outbreaks: int, n_blocked: int, p_board: float, reduction: float, n_sims: int = 1000, seed: int = 0
) -> float:
    """Common random numbers: each blocked agent's latent uniform is shared across arms."""

    def sampler(rng: np.random.Generator) -> tuple[list[float], list[float]]:
        u = rng.random((n_outbreaks, n_blocked))
        board = (u < p_board).sum(axis=1)
        defended = (u < p_board * (1 - reduction)).sum(axis=1)
        return list(defended), list(board)

    return simulate_power(
        sampler,
        lambda x, y: paired_permutation(x, y, alternative="less", n_perm=2000),
        n_sims=n_sims,
        seed=seed,
    )


def power_report(n_sims: int = 2000) -> str:
    lines = [
        "# Power (simulation)",
        "",
        f"Pilot anchor: note {PILOT_NOTE:.3f} vs control {PILOT_CTRL:.3f}",
        "",
        "## H1 Fisher, note vs empty board (control 1%)",
        "| n/arm | true rate | power |",
        "|---|---|---|",
    ]
    lines += [f"| {n} | {p:.3f} | {pw:.2f} |" for n, p, pw in h1_table(n_sims=n_sims)]
    lines += ["", "## H3 one trait, risk difference (base 10%)", "| episodes | RD | power |", "|---|---|---|"]
    for n in (384, 768, 1152):
        for rd in (0.05, 0.08, 0.12):
            lines.append(f"| {n} | {rd:.2f} | {h3_power(n, 0.10, rd, n_sims=n_sims // 2):.2f} |")
    lines += [
        "",
        "## H4 defenses, 9 blocked agents/outbreak, board violation prob 0.3",
        "| outbreaks | reduction | power |",
        "|---|---|---|",
    ]
    for k in (10, 20, 30):
        for red in (0.5, 0.75):
            lines.append(f"| {k} | {red:.2f} | {h4_power(k, 9, 0.3, red, n_sims=n_sims // 2):.2f} |")
    return "\n".join(lines)
