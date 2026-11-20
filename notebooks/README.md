# notebooks/

## Colab notebooks: one per question, short and self-contained

| notebook | question | runtime | run after |
|---|---|---|---|
| [`00_setup_and_reality_check`](colab/00_setup_and_reality_check.ipynb) | Does the phenomenon exist in the confirmatory harness? (frozen results + smoke + screen) | CPU · 5 min | – |
| [`01_who_catches_it`](colab/01_who_catches_it.ipynb) | **Act 1a:** which models take a peer's forbidden shortcut? (exp_001) | CPU · 1–2 h | – |
| [`02_why_it_spreads`](colab/02_why_it_spreads.ipynb) | **Act 1b:** which note traits make it contagious? Natural notes, manipulation check (exp_002, exp_006) | CPU · 5–6 h | – |
| [`03_where_to_stop_it`](colab/03_where_to_stop_it.ipynb) | **Act 4:** filter vs LLM judge; outbreaks under 6 defenses (exp_004) | CPU · 3–4 h | 02 |
| [`04_whitebox_dataset`](colab/04_whitebox_dataset.ipynb) | **Act 2 input:** 720 decision points with k/n labels (exp_003) | CPU · 3–4 h | – |
| [`05_probe_and_vaccine_gpu`](colab/05_probe_and_vaccine_gpu.ipynb) | **Acts 2–3:** probe and vaccine on gpt-oss-20b; closed-loop episodes | GPU · 3–4 h | 04 |
| [`06_results`](colab/06_results.ipynb) | Every table and figure; freezes `results/`; rebuilds the demo and poster | CPU · 5 min | all |

**Run them in parallel.** Each experiment has its own LLM cache, and results go to Google Drive, so the
sessions never share a database file.

| session | notebooks |
|---|---|
| A | 01, then 03 (once 02 has finished) |
| B | 02 |
| C | 04, then 05 on a GPU runtime |

Run 06 at the end.

Each notebook starts with the same two setup cells (get the code; Drive + key). Every step is resumable. To keep a run
with its outputs visible on GitHub, use File → Save a copy in GitHub.

The notebooks are generated from `scripts/build_notebooks.py` (`make notebooks`). Edit the script, not the
`.ipynb`. CI fails if they drift.

`exploratory/`, `analysis/` and `visualization/` are reserved for ad-hoc work. Anything reusable belongs in
`src/outbreak/`.
