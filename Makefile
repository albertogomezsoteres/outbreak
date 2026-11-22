# Outbreak - one-command entry points (see README "Reproduce it").
PY ?= python
RUN ?= main

.PHONY: help install dev test test-fast lint typecheck check smoke notebooks demo pilot power \
        reality natural exp1 exp2 search-filter filter judge exp3 exp4 exp6 manip analyze reproduce docker clean

help:            ## list targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install:         ## runtime install (API runs + serving)
	$(PY) -m pip install -e ".[api]"

dev:             ## everything for development + white-box tests
	$(PY) -m pip install -e ".[api,dev,whitebox,tracking]" && pre-commit install

test:            ## full test suite (parallel)
	$(PY) -m pytest -n auto

test-fast:       ## skip slow end-to-end and calibration tests
	$(PY) -m pytest -n auto -m "not slow"

lint:            ## ruff lint + format check
	ruff check src tests scripts && ruff format --check src tests scripts

typecheck:       ## mypy (strict defs)
	mypy

check: lint typecheck test  ## what CI runs

smoke:           ## offline harness check with scripted agents (no API key)
	outbreak smoke

notebooks:       ## regenerate the Colab notebooks from scripts/build_notebooks.py
	$(PY) scripts/build_notebooks.py

demo:            ## rebuild demo/data.json + demo/index.html from the finished runs and the trained filter
	outbreak export-demo

pilot:           ## reproduce the pilot table from checksummed raw logs
	outbreak pilot

power:           ## power simulation for the planned sample sizes
	outbreak power

# ---- confirmatory experiments (need OPENROUTER_API_KEY; resumable; cached) ----
reality:         ## reality check in env-v1 BEFORE tagging prereg-v1
	outbreak run experiments/single_experiments/00b_reality_check.yaml --run-id exp_000b_$(RUN)
	outbreak analyze outputs/results/exp_000b_$(RUN)/episodes.jsonl
natural:         ## LLM-written notes for exp_006 (writer model configurable)
	outbreak natural-notes --model openai/gpt-5-mini --n 48
exp1:            ## Act 1a: susceptibility screen
	outbreak run experiments/single_experiments/01_screen_susceptibility.yaml --run-id exp_001_$(RUN)
exp2:            ## Act 1b: trait factorial
	outbreak run experiments/single_experiments/02_trait_factorial.yaml --run-id exp_002_$(RUN)
search-filter:   ## filter hyperparameters on the validation split
	outbreak search experiments/hyperparameter_searches/filter_regularization.yaml \
	  --episodes outputs/results/exp_002_$(RUN)/episodes.jsonl --out outputs/results/hps_001
filter: search-filter  ## train the channel filter on exp_002 with the selected C / FPR
	outbreak train-filter outputs/results/exp_002_$(RUN)/episodes.jsonl \
	  --C $$(python -c "import json;print(json.load(open('outputs/results/hps_001/selected.json'))['selected']['C'])") \
	  --target-fpr $$(python -c "import json;print(json.load(open('outputs/results/hps_001/selected.json'))['selected']['target_fpr'])")
judge:           ## LLM channel judge vs trained filter on the same held-out posts
	outbreak judge-eval outputs/results/exp_002_$(RUN)/episodes.jsonl --judge openai/gpt-5-nano
exp3:            ## Act 2 input: randomised exposure + harvest
	outbreak run experiments/single_experiments/03_exposure_whitebox_harvest.yaml --run-id exp_003_$(RUN)
	outbreak harvest outputs/results/exp_003_$(RUN)/episodes.jsonl --out outputs/results/exp_003_$(RUN)/decision_points.jsonl
exp4: filter     ## Act 4: outbreaks + defenses
	outbreak run experiments/single_experiments/04_outbreak_defenses.yaml --run-id exp_004_$(RUN)
exp6: natural    ## external validity: natural vs template notes
	outbreak run experiments/single_experiments/06_natural_notes.yaml --run-id exp_006_$(RUN)
manip:           ## LLM manipulation check of template + natural notes
	outbreak manipulation-check --notes data/processed/notes_M*.jsonl data/processed/natural_notes_M*.jsonl --model openai/gpt-5-mini

analyze:         ## tables + figures for every finished run
	for f in outputs/results/*_$(RUN)/episodes.jsonl; do [ -f $$f ] && outbreak analyze $$f; done; \
	for f in outputs/results/*_$(RUN)/outbreaks.jsonl; do [ -f $$f ] && outbreak analyze $$f; done; true

reproduce: smoke exp1 exp2 filter judge exp3 exp4 exp6 manip analyze demo  ## the whole black-box study (run `make reality` + tag prereg-v1 first)

docker:          ## build the isolated image
	docker build -t outbreak:latest .

clean:           ## remove caches (keeps results and the LLM cache)
	rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis build dist src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
