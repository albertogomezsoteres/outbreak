# Outbreak

**How a forbidden shortcut spreads through a team of LLM agents, and where to stop it.**

An agent hits a task it cannot finish honestly: a missing API quota, a purged dataset, a test that cannot
pass. A note from a peer suggests a shortcut that breaks policy, such as editing the test, using an admin
token, querying the production replica or fabricating the data. This project studies what happens next:

1. **Who catches it?** Which models take a peer's forbidden shortcut, compared with a harmless note of the
   same length.
2. **Why does it spread?** Which features of a note make it contagious: a 2⁶ factorial of persuasive traits,
   plus notes written naturally by an LLM.
3. **Can we see it coming?** A probe on the hidden states of `gpt-oss-20b` at the moment of decision, and a
   steering "vaccine" that turns the decision down.
4. **Where do we stop it?** Outbreaks in 12-agent teams sharing a message board, under an LLM judge, a
   trained filter, an action monitor and an oracle. Each defense is scored on the violations it stops and
   the useful work it keeps.

## Status

- The design, hypotheses and analyses are preregistered in [`docs/preregistration.md`](docs/preregistration.md)
  (tag `prereg-v1`). Changes made since are logged in [`docs/DEVIATIONS.md`](docs/DEVIATIONS.md).
- A reality check with real models is in [`docs/reality_check.md`](docs/reality_check.md).
- Confirmatory experiments are running. Results will be added here.

## Quickstart

```bash
pip install -e ".[dev]"
make check     # ruff, mypy and the test suite (no network, no API key)
make smoke     # the full pipeline offline, with scripted agents
```

- **Real models:** runs go through OpenRouter. Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.
- **Colab:** one notebook per question, listed in [`notebooks/README.md`](notebooks/README.md).

## Repository

```
src/outbreak/
  env/             task families, sandboxed tools, internal API, team board, violation detectors
  data/            peer notes (trait factorial, natural notes), splits, archived pilot
  models/          cached LLM client, scripted policies, LLM judge and monitor, text filter
  pipeline/        experiment runners, outbreaks, preregistered analysis, power
  explainability/  hidden-state probe, steering vaccine, local steered agent
experiments/       one YAML config per experiment
notebooks/colab/   the Colab notebooks, generated from scripts/build_notebooks.py
docs/              preregistration, deviations, design decisions, limitations, cards
results/           frozen analysis outputs
tests/             environment validity, statistics calibration, pipeline and white-box tests
```

## Documentation

- [Preregistration](docs/preregistration.md) and [deviations log](docs/DEVIATIONS.md)
- [Design decisions](docs/design_decisions.md) and [limitations](docs/limitations.md)
- [Related work](docs/related_work.md)
- [Reproducibility](docs/reproducibility.md)
- [Model card](docs/model_card.md) and [data card](docs/data_card.md)
- [Quickstart tutorial](docs/tutorials/quickstart.md) and [API reference](docs/api/README.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT. See [`LICENSE`](LICENSE) and [`CITATION.cff`](CITATION.cff).
