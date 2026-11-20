# results/

These are frozen, committed analysis outputs. The raw episodes live in `data/raw/` and are checksummed.

| folder | what | regenerate |
|---|---|---|
| `exp_000b/` | Reality check in the confirmatory harness: 432 real episodes, gpt-oss-20b and gpt-5-nano, run on 2026-11-20 before `prereg-v1`. Exploratory: these episodes are never pooled with confirmatory runs. | `gunzip -k data/raw/exp_000b/episodes.jsonl.gz && outbreak analyze data/raw/exp_000b/episodes.jsonl --out results/exp_000b`, then delete the large `episodes_flat.csv` |

Confirmatory runs (exp_001 to exp_006) are written to `outputs/results/<run_id>/`. Their `analysis/` folders are
copied here once the results are frozen (`results-v1`).
