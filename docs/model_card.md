# Model cards

## 1. Channel filter (`models/trained/channel_filter.joblib`)

| | |
|---|---|
| **Task** | Score a team-board post by the probability that agents who read it will violate policy |
| **Architecture** | TF-IDF (word 1–2-grams + char_wb 3–5-grams, sublinear tf) → L2 logistic regression (class-balanced) → isotonic calibration |
| **Training data** | Exposures from `exp_002` (factorial notes + benign notes), labelled by the **observed violation** of the reading agent |
| **Splits** | By note text (hash of note id): 60/20/20 train/val/test. Benign notes: half for training, half to set the threshold |
| **Threshold** | Chosen on held-out benign posts at a target false-positive rate (default 5%) |
| **Evaluation** | AUROC with note-clustered bootstrap CIs on val and test; TPR and flag rate at the threshold; benign FPR; leakage report (exact/sentence/8-gram overlap) |
| **Interpretability** | `top_features()` lists the n-grams that most predict violation (written to the training report) |
| **Serving** | `outbreak serve` → `POST /score`, `POST /score/batch`, `GET /health` |
| **Intended use** | Flag-and-hold screening of posts in multi-agent workspaces |
| **Out of scope** | Moderating human content; deciding alone without review; channels other than short text posts |
| **Hyperparameters** | C and target FPR selected on validation only (`outbreak search`, `hps_001`) |
| **Compared with** | An LLM channel judge on the same held-out posts (`outbreak judge-eval`): AUROCs, paired bootstrap difference, benign flag rates |
| **Known limits** | Learns the grammar of generated notes. Must be re-evaluated on agent-written posts, natural notes and new mechanisms. Scores are calibrated only for the training mechanisms |

All numbers are written to `channel_filter.report.json` when the filter is trained. They are not copied
here, so this card never shows stale metrics.

## 2. Decision-point probe (white-box notebook)

| | |
|---|---|
| **Task** | Predict, from the residual stream at the decision point, the propensity of the agent to take the shortcut |
| **Model probed** | `openai/gpt-oss-20b` (the same weights used as an API agent in exp_003) |
| **Input** | Hidden state of the last prefix token at a chosen layer (layer chosen on validation scenarios) |
| **Estimator** | StandardScaler → logistic regression with a binomial likelihood (k of n samples per prefix) |
| **Baselines** | Note identity (train-set rate of the same note); a text-only filter on the board the agent read; shuffled labels; within-note rank correlation |
| **Reference** | Noise ceiling: the best AUROC attainable with 8 samples per prefix (Beta-binomial posterior simulation) |
| **Selection** | Layer and C selected on validation scenarios (`hps_002`); test scenarios used once |
| **Evaluation** | Held-out scenarios (test split + held-out family), episode-level AUROC with note-clustered bootstrap CI |
| **Use** | Offline early warning and mechanistic evidence. Not a deployed safety system |

## 3. Vaccine direction

| | |
|---|---|
| **Definition** | Unit difference of means between high-propensity (rate ≥ 0.5) and zero-propensity prefixes, computed on train scenarios |
| **Intervention** | Subtract α·‖Δμ‖·u from the output of the block feeding `hidden_states[L]`, at every position |
| **Evaluation** | Margin log P(violate) − log P(report_blocked) on held-out prefixes vs three norm-matched random directions; utility log-prob on POSSIBLE prefixes; closed-loop episodes with and without steering |
| **Variants** | Always-on, or probe-triggered: steering is applied only on turns where the probe's score is at or above its threshold, and every turn's score is logged |
| **Known limits** | Model-, layer- and mechanism-specific. Large α can damage capabilities that the utility check does not cover |
