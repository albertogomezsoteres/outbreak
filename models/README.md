# models/

| folder | contents |
|---|---|
| `trained/` | `channel_filter.joblib` and its `channel_filter.report.json` (splits, AUROC CIs, threshold, leakage, top n-grams). Created by `outbreak train-filter`. |
| `checkpoints/` | Not used: nothing is trained iteratively. |
| `pretrained/` | Not committed. Hugging Face weights (gpt-oss-20b) are downloaded by the white-box notebook into the HF cache. |

Model cards: `docs/model_card.md`.
