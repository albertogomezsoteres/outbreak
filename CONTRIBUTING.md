# Contributing

## Workflow
1. Branch from `main`:
   - `feat/<topic>` for code;
   - `exp/<experiment-id>` for new configs or runs;
   - `fix/<bug>` for fixes;
   - `docs/<topic>` for documentation.
2. Commit with conventional messages (`feat:`, `fix:`, `test:`, `docs:`, `exp:`, `refactor:`).
3. Run `make check` (ruff, mypy, pytest). `pre-commit install` runs the fast checks on every commit and refuses
   API keys.
4. Open a PR using the template below. CI must be green. Squash-merge.

## PR template
```
## What
## Why (which RQ / hypothesis / deviation)
## How it was validated (tests added, runs, figures)
## Does it change env-v1 semantics?  [ ] no  [ ] yes -> bump ENV_VERSION + DEVIATIONS.md
```

## Rules that protect the study
- Never edit `docs/preregistration.md` after `prereg-v1`. Record changes in `docs/DEVIATIONS.md`.
- Any change to families, templates, API behaviour or detectors bumps `ENV_VERSION` in
  `utils/manifest.py`.
- Never commit keys, `.env`, `outputs/cache/` or raw run folders.
- New statistics need a calibration test (coverage or size under simulation), not just an example.
