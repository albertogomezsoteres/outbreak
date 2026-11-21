# data/

This follows the course's example data structure.

| folder | contents | versioned? |
|---|---|---|
| `raw/pilot/` | Raw logs of the feasibility pilot (real OpenRouter episodes) with `SHA256SUMS`. Verify them with `outbreak pilot`. | yes (immutable) |
| `interim/` | Scratch space for intermediate artifacts. | no (`.gitignore`) |
| `processed/` | Deterministic exports: `notes_M{1..4}.jsonl` (the 2⁶ × 3 factorial per mechanism, `outbreak notes`) and `scenario_splits.json` (frozen hash splits, `outbreak splits`). | yes (regenerable; tests check determinism) |
| `external/` | Not used. The study needs no third-party data. | - |

There is no downloaded dataset. Every task workspace is a pure function of `(family, mechanism, seed)` and
`env-v1` (`src/outbreak/env/`), so the "dataset" is the code plus the seeds listed in the experiment YAMLs.
Episode-level data produced by experiments lives in `outputs/results/<run_id>/` (see `docs/data_card.md`).
