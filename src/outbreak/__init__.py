"""Outbreak: how forbidden shortcuts spread between LLM agents, why, and how to stop them.

Subpackages
-----------
env             realistic task repos, internal API, tools, team board, violation detectors
models          LLM clients (cached, budgeted), scripted harness policies, LLM judges/monitors
data            note factorial, datasets of episodes, splits
pipeline        experiment runners (bench, exposure, outbreak) and the analysis pipeline
explainability  white-box probes and steering ("vaccine") on open-weight models
serving         FastAPI service scoring board posts with the trained filter
utils           config, manifests, caching, statistics, logging
"""

__version__ = "1.0.0"
