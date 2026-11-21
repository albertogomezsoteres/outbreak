# outputs/results/

One folder per run (`<run_id>/`), created by `outbreak run`:

- `run.yaml`: the manifest (git commit, config hash, full config, env version, packages, platform, spend, stats).
- `episodes.jsonl` or `outbreaks.jsonl`: append-only records. Interrupted runs resume from them.
- `analysis/`: created by `outbreak analyze`. Holds the CSV tables (H1–H4), `report.md`, and figures (PNG + SVG
  + the CSV behind each figure).
- `decision_points.jsonl` (exp_003): the white-box dataset from `outbreak harvest`.
- `whitebox/` (exp_003): probe and steering tables and figures from the GPU notebook.

Run folders are not committed (they can be large). Publish the final ones as a release asset, or copy the
`analysis/` folders into the repo when results are frozen (`results-v1`).
