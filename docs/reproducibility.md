# Reproducibility

This page answers, point by point, the checklist from the course's *ML Engineering* lecture (slides 6–10). It
ends with the exact procedure to reproduce every number ("Reproduce it!", slide 13).

## The 15 pipeline components (slide 6)

| Component | Where it lives in this repo |
|---|---|
| Git | Linear history with conventional commits. Tags: `prereg-v1` (frozen plan) and `results-v1` (after the runs). |
| Documentation | `docs/` (design decisions, preregistration, deviations, limitations, model/data cards, API, tutorial). |
| README | `README.md`: motivation, results, quickstart, reproduce, structure. |
| Branches | `main` is protected. Work goes on `feat/*`, `fix/*`, `exp/*` branches (see `CONTRIBUTING.md`). |
| PRs | CI must pass (lint, types, tests, offline end-to-end run) before merge; template in `CONTRIBUTING.md`. |
| Env management | `pyproject.toml` (ranges, extras), pinned `requirements*.txt`, `Dockerfile`, `.env.example`. |
| Logging | Per-run log files in `outputs/logs/<run_id>.log`. Optional W&B (`WANDB_PROJECT`). Every episode is a JSON line. |
| Metadata | `outputs/results/<run_id>/run.yaml`: run id, git commit and dirty flag, config hash, full config, env version, package versions, platform, spend. |
| Data hosting | Pilot raw logs in `data/raw/pilot` with `SHA256SUMS`. Generated data is a deterministic function of seeds, so it is regenerated, not hosted. |
| Organization | The course's example structure: `experiments/`, `src/<pkg>/{data,models,explainability,utils,pipeline,serving}`, `data/{raw,interim,processed,external}`, `models/`, `outputs/`, `notebooks/`, `tests/`, `docs/`. |
| Data config (YAML) | `experiments/single_experiments/*.yaml` and `experiments/hyperparameter_searches/*.yaml`. Both are validated by pydantic (`utils/config.py`, `pipeline/search.py`), and unknown keys are rejected. Searches are executable: `outbreak search CONFIG`. |
| Scripts | `scripts/` (notebook builder, pilot harness) and the `Makefile` targets. |
| SW tests | `tests/` mirrors `src/`: 230+ tests, including statistical calibration, Hypothesis properties and end-to-end runs. |
| Single entry | `outbreak <command>` (`src/outbreak/main.py`), also `python -m outbreak`. |
| Docstrings | Every module documents its purpose and design choices. `mypy --disallow-untyped-defs` passes. |

## General (slide 7)
**Which parts must be reproducible?**
- scenario data;
- splits;
- note texts and their assignment to scenarios;
- decision-point prefixes;
- every LLM response;
- detectors and grading;
- statistics and figures.

**Can I re-run a month later and get the same results?** Yes, for everything downstream of the LLM calls.
- Each call is stored in a content-addressed SQLite cache. The key is sha256(model, messages, tools, sampling
  params, seed, episode key).
- A re-run replays every response bit-for-bit, without API calls.
- Re-sampling the models is a *replication* (new random draws), not a reproduction. The runner supports it by
  changing the run id and the cache path.

**Are dependencies, parameters and seeds documented?**
- Dependencies: `pyproject.toml` and pinned `requirements*.txt`.
- Parameters: experiment YAMLs, with a config hash in `run.yaml`.
- Seeds:
  - scenario seeds come from YAML;
  - the sampling seed is derived from the episode id (sha256);
  - the note shuffle is seeded by `reproducibility.seed`;
  - bootstrap and permutation tests take explicit seeds.

## Data (slide 7)
**Where is the raw data and is it versioned?**
- The study generates its own data. Every workspace is a pure function of `(family, mechanism, seed)` and
  `env-v1`, so nothing is downloaded.
- The pilot logs are stored with checksums. `outbreak pilot` verifies them and reproduces the pilot table.

**Exact dataset version?** `env_version` appears in every manifest. It is bumped whenever families,
templates or API semantics change.

**Consistent, logged access method?** Every API request an agent makes is logged inside the episode record,
with host, path, params, token class, status and body hash.

**Changing schemas?** pydantic validates configs strictly. Records carry `env_version`. Analysis code reads
only documented fields (`docs/data_card.md`).

## Preprocessing and features (slide 8)
**Deterministic and saved?** Yes. Workspaces, note texts and prefixes are deterministic.
`outbreak notes` exports the full factorial, and `outbreak harvest` writes `decision_points.jsonl` (with
`k/n` per prefix).

**Same transformation at train and inference?**
- The channel filter is a single sklearn `Pipeline` (TF-IDF features + logistic regression + isotonic
  calibration). The same object is saved with joblib and served by FastAPI.
- The probe pipeline (`StandardScaler` + `LogisticRegression`) is fit on train scenarios only.

**Feature definitions centralised?**
- Note traits: `data/notes.py`.
- Text features: `models/text_filter.py`.
- White-box features (layer, token position): YAML `explainability` section and
  `explainability/activations.py`.

## Running experiments and training (slide 9)
**Tracked?** Each run gets:
- `run.yaml`;
- an append-only `episodes.jsonl` / `outbreaks.jsonl`;
- a log file;
- optional W&B summaries.

**Seeds for every stochastic operation?** Yes. See "General" above. Splits are hash-based, so they never
change when seeds are added.

**Hardware/software logged?** Platform, Python version and package versions (including torch and
transformers) are in `run.yaml`. The white-box notebook prints the GPU.

**Parameterised?** argparse CLI plus YAML. Any field can be overridden with `-o key.sub=value`, and the
override is stored in the manifest.

**Deterministic training, configs saved?** Filter and probe training are deterministic given the data and
`random_state`. The filter writes `channel_filter.report.json` (splits, AUROC CIs, threshold, leakage
report, top n-grams) next to the model.

**Consistent metrics?** One grading function (`env/detectors.py::grade`) and one analysis module
(`pipeline/analysis.py`) serve all experiments.

## Code, testing and metadata (slide 10)
- **Version control:** Git; CI runs on every push and PR.
- **Dependencies and container:** `requirements*.txt`, `Dockerfile` (non-root user), `.dockerignore`.
- **Model saving and portability:**
  - The filter is saved with joblib, and package versions are pinned in the manifest.
  - Portability is provided by the HTTP API (`outbreak serve`), not by the pickle.
  - ONNX export was considered and rejected: `skl2onnx` support for `char_wb` TF-IDF is incomplete, and a
    partial conversion would silently change scores.
- **Independently testable steps:** every stage has its own tests. Examples:
  - environment validity on 30 family × mechanism cells;
  - runner resumability;
  - outbreak determinism under different parallelism;
  - probe and steering maths on planted signals;
  - API contract.
- **Centralised logs and metadata per run:** `outputs/logs/<run_id>.log` plus `outputs/results/<run_id>/run.yaml`.

## Reproduce it (slide 13)

```bash
git clone https://github.com/albertogomezsoteres/outbreak && cd outbreak
python -m pip install -e ".[api,dev]"
make check                      # lint + types + 230+ tests (no API key, no network)
outbreak pilot                  # verifies checksums, prints the pilot table (14/80 vs 0/80 ...)
outbreak run experiments/single_experiments/00_smoke_scripted.yaml --run-id smoke
outbreak run experiments/single_experiments/05_smoke_outbreak_scripted.yaml --run-id smoke_ob
outbreak export-demo && open demo/index.html
```

Confirmatory runs need `OPENROUTER_API_KEY`:

```bash
make reproduce RUN=main
```

This runs exp_001 → exp_004 plus the analysis and the demo. On Colab, use
the seven notebooks in `notebooks/colab/` (see `notebooks/README.md`; 05 needs a GPU).

With the shared LLM cache (`outputs/cache/llm_cache.sqlite`), the same commands reproduce every table
exactly, without any API calls.
