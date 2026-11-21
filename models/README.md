# models/

| folder | contents |
|---|---|
| `trained/` | `channel_filter.joblib` and its `channel_filter.report.json` (splits, AUROC CIs, threshold, leakage, top n-grams). Created by `outbreak train-filter` (trained in Colab with scikit-learn 1.6.1; it loads under the pinned versions, and a test checks that the browser port in `demo/filter.js` scores notes exactly like it). |
| `checkpoints/` | Not used: nothing is trained iteratively. |
| `pretrained/` | Not committed. Hugging Face weights (gpt-oss-20b) are downloaded by the white-box notebook into the HF cache. |

Model cards: `docs/model_card.md`.
