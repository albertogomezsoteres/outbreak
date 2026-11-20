# Contributing

## Workflow
- **Branches.** `main` holds releases only, each one tagged (`prereg-v1`, `v1.0`). `dev` is the integration
  branch.
- **Topic branches.** Branch from `dev`:
  - `feat/<topic>` for code;
  - `exp/<experiment-id>` for new configs or runs;
  - `fix/<bug>` for fixes;
  - `docs/<topic>` for documentation;
  - `chore/<topic>` for tooling.
- **Commits.** Small, self-contained, with conventional messages (`feat:`, `fix:`, `test:`, `docs:`, `exp:`,
  `ci:`, `chore:`).
- **Checks.** Run `make check` (ruff, mypy, pytest). `pre-commit install` runs the fast checks on every commit
  and refuses API keys.
- **Pull requests.** Open a PR into `dev`. The template (`.github/pull_request_template.md`) asks for a summary,
  the motivation, the tests and the study impact. CI must be green. Merge with a merge commit, so each
  feature's commits stay readable in the history.
- **Releases.** A PR from `dev` into `main`, then a tag.

## Rules that protect the study
- Never edit `docs/preregistration.md` after `prereg-v1`. Record changes in `docs/DEVIATIONS.md`.
- Any change to families, templates, API behaviour or detectors bumps `ENV_VERSION` in
  `utils/manifest.py`.
- Never commit keys, `.env`, `outputs/cache/` or raw run folders.
- New statistics need a calibration test (coverage or size under simulation), not just an example.
