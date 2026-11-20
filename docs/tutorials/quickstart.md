# Quickstart (10 minutes, no API key)

```bash
python -m pip install -e ".[api,dev]"
outbreak smoke --families sales_report          # every mechanism, honest vs cheating scripted agent
```

You should see `SMOKE OK`. For each mechanism, the honest policy either solves the task (OK) or reports that
it is blocked (M1–M4). The cheating policy takes the shortcut, and the detectors flag it.

## Look inside a workspace
```python
from outbreak.env import Mechanism, Scenario, Workspace
with Workspace(Scenario("inventory_reconcile", Mechanism.M4_FABRICATION, 0)) as ws:
    print(ws.list_all())                 # README.md, docs/API.md, config/settings.yaml, src/, scripts/, tests/ ...
    print(ws.read("README.md"))          # task + engineering policy
    print(ws.purged_entity)              # the warehouse the API answers 410 for
```

## Play an outbreak with scripted agents
```bash
outbreak run experiments/single_experiments/05_smoke_outbreak_scripted.yaml --run-id tutorial
outbreak analyze outputs/results/tutorial/outbreaks.jsonl
```

## See the demo
```bash
outbreak export-demo && open demo/index.html
```

## Run real models (needs `OPENROUTER_API_KEY`)
```bash
export OPENROUTER_API_KEY=...            # or put it in .env (never commit it)
outbreak run experiments/single_experiments/01_screen_susceptibility.yaml --run-id try \
  -o 'model.agents=[{"id": "openai/gpt-oss-20b"}]' -o dataset.seeds=[0] -o budget.max_usd=1
outbreak analyze outputs/results/try/episodes.jsonl
```
