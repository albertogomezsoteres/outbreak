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


def ni_power(
    n_outbreaks: int,
    n_unblocked: int,
    p_ref: float,
    p_def: float,
    *,
    same_sample: float = 0.8,
    margin: float = 0.05,
    n_sims: int = 400,
    seed: int = 0,
) -> float:
    """Utility non-inferiority (H4): per-outbreak legit-success rates of the unblocked agents. With common random
    numbers an unblocked agent whose context the defense does not change gets the identical sample in both
    arms (``same_sample`` = probability of that)."""
    from outbreak.utils.stats import noninferiority

    rng = np.random.default_rng(seed)
    hits = 0
    for s in range(n_sims):
        u = rng.random((n_outbreaks, n_unblocked))
        ref = (u < p_ref).astype(float)
        u2 = np.where(rng.random(u.shape) < same_sample, u, rng.random(u.shape))
        de = (u2 < p_def).astype(float)
        hits += noninferiority(de.mean(1), ref.mean(1), margin, n_boot=500, seed=s).non_inferior
    return hits / n_sims


def transmission_power(
    n_outbreaks: int, n_late_blocked: int, p_relay: float, p_none: float, *, n_sims: int = 1000, seed: int = 0
) -> float:
    """H4c: late-round targeted violations per outbreak, relay vs no_relay (one-sided permutation)."""

    def sampler(rng: np.random.Generator) -> tuple[list[float], list[float]]:
        return (
            list(rng.binomial(n_late_blocked, p_relay, n_outbreaks)),
            list(rng.binomial(n_late_blocked, p_none, n_outbreaks)),
        )

    return simulate_power(
        sampler,
        lambda x, y: paired_permutation(x, y, alternative="greater", n_perm=2000),
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
    lines += [
        "",
        "## H4 utility non-inferiority (margin 5 pp), 4 unblocked agents per outbreak",
        "| outbreaks | true utility (ref → defense) | same-sample prob. | power |",
        "|---|---|---|---|",
    ]
    for k in (20, 30):
        for pr, pd_ in ((0.97, 0.97), (0.95, 0.93)):
            for rho in (0.5, 0.8):
                lines.append(
                    f"| {k} | {pr:.2f} → {pd_:.2f} | {rho} | "
                    f"{ni_power(k, 4, pr, pd_, same_sample=rho, n_sims=max(100, n_sims // 8)):.2f} |"
                )
    lines += [
        "",
        "## H4c transmission, 5 blocked agents in rounds 2-3 per outbreak",
        "| outbreaks | P(violate) relay vs no relay | power |",
        "|---|---|---|",
    ]
    for k in (20, 30):
        for pr, pn in ((0.3, 0.05), (0.2, 0.05), (0.5, 0.1)):
            lines.append(
                f"| {k} | {pr:.2f} vs {pn:.2f} | "
                f"{transmission_power(k, 5, pr, pn, n_sims=max(200, n_sims // 4)):.2f} |"
            )
    return "\n".join(lines)
