Developer guide — adding ML / DL / RL models
=============================================

This document explains how the backend training system is organized and shows step-by-step instructions for adding new models (ML / DL / RL), where to wire them in, and the limitations of the core functions you will interact with.

High-level architecture
-----------------------

- Core registry: `MODEL_CATALOG` in `backend/app/model_training.py` is the single source of truth for model metadata used by the API and frontend.
- Normalization/aliases: `ALIASES` maps common alternate names to canonical catalog keys.
- Entry points:
  - `train_model(...)` — main orchestration function that prepares data, merges the catalog defaults, the mode's suggestions and the client's values into a single set of effective parameters (the preset is applied there, exactly once), routes to model-specific trainers, and returns metrics + artifact path.
  - `suggest_hyperparameters(...)` — returns the catalog parameters of a model; with `use_llm=True` it asks Google Gemini for values for the keys the catalog declares.
  - `build_model(...)` — factory for simple sklearn/tabular models.
  - `_train_transformer_text_classifier(...)`, `_train_resnet_image_model(...)`, `_train_rl_model(...)`, `_train_clustering(...)` — category-specific training helpers.
- Category routing: the `category` of a catalog entry selects the code path used by `train_model(...)`:

  | category | code path |
  | --- | --- |
  | `reinforcement-learning` | `_train_rl_model(...)` |
  | `vision` | `_train_resnet_image_model(...)` |
  | `clustering` | `_train_clustering(...)` |
  | `nlp` | `_train_transformer_text_classifier(...)` |
  | `timeseries`, `graph`, `autoencoder` | `_train_torch_regression_or_classification(...)` |
  | `classification`, `regression`, `time-series` | tabular sklearn flow via `build_model(...)` |

  The boosting entries (`XGboost_timeseries`, `lightGBM_timeseries`, `CATboost_timeseries`) use the `time-series` category and train as tabular models through `build_model(...)`. `HMM_timeseries` uses the `clustering` category because its trainer (`hmm.GaussianHMM`) lives in `_train_clustering(...)`.

Where to add a new model (quick)
-------------------------------

1. Open `backend/app/model_training.py`.
2. Add a new entry to `MODEL_CATALOG` (see the existing entries). Each entry should include at minimum:

```py
"MyModelName": {
    "category": "classification",  # classification, regression, vision, nlp, timeseries, reinforcement-learning, clustering, autoencoder, graph
    "description": "Short description",
    # Only keys that the estimator of the chosen code path accepts. A sklearn-style
    # estimator is constructed with exactly these keyword arguments (see
    # build_model() below), so a key such as "learning_rate" or "epochs" would raise
    # a TypeError during training.
    "params": {"n_estimators": 100, "max_depth": None},
    "optimization": ["n_estimators", "max_depth"],
    "test_results": {
        "expected_accuracy": (0.7, 0.9),
        "best_for": ["tabular_classification"],
        "typical_training_time_sec": 10,
        "scalability": "medium",
    }
}
```

3. If your model name has alternate spellings, add an alias to `ALIASES`.

4. Decide whether the generic `build_model()` + tabular training flow supports it. If not, implement a new `_train_<category>_model()` helper and route from `train_model()`.
5. Make sure the `params` of the entry only contain keys the estimator actually accepts — they are splatted into the constructor (see `build_model()` below). Keys of the training loop itself (e.g. `test_size`) do not belong in `params`.

The `category` also decides the code path (see the routing table above), so the keys in
`params` must match the estimator of *that* path: the sklearn-style `build_model()`
branch, the clustering constructors of `_train_clustering()`, the torch trainer, the
transformer trainer or the RL trainer.

Parameter ownership
-------------------

- `test_size` is a **trainer-owned** parameter: it configures the train/test split and is passed to `train_test_split()` separately. It is never a valid estimator argument.
- The client-supplied `hyperparameters` are filtered in `train_model()` (the central place) and the trainer-owned keys listed in `_TRAINER_OWNED_PARAMS` (`test_size`) are dropped there. `build_model()` and `_train_clustering()` apply the same filter again as defence in depth, so **no** estimator — sklearn, boosting or clustering — ever receives `test_size`.
- A client-supplied `hyperparameters["test_size"]` is therefore **ignored**: the split is governed by the request's top-level `test_size` field (`TrainRequest.test_size`, the `test_size` argument of `train_model()`). Because the key is dropped before the run report is built, `metrics["model_parameters"]` does not echo the ignored value either.
- Every other key of the client-supplied `hyperparameters` reaches the estimator (a preset may scale its *value*, see "Presets" below). A name the estimator does not accept (a typo) still raises `TypeError`: there is deliberately no blanket signature filtering, because a silently ignored parameter is worse than a loud failure.

Presets
-------

`TRAINING_PRESETS` defines the three presets of the API (`conservative`, `balanced`,
`aggressive`). A preset scales a fixed set of parameters (`learning_rate`,
`weight_decay`, `epochs`, `n_estimators`); `apply_preset()` only touches the keys
that are **present** in the dict it is given and never adds a key.

The preset is applied **once per run**, to the *merged base* — the catalog defaults
plus the mode's own suggestions — inside `train_model()`:

```py
base   = {**MODEL_CATALOG[model]["params"], **mode_suggestions}
base   = apply_preset(base, preset)           # the catalog / mode values are scaled
client = apply_preset(client_values, preset)  # the client's values are scaled too
params = {**base, **client}                   # the client's values still win
```

Consequences:

- A preset is effective in **every** mode — also when the request carries an empty
  `hyperparameters` dict (the SPA sends one in the automatic modes so that the
  backend's own suggestions are not overridden). The catalog defaults are scaled as
  well, so `conservative` also lowers the `n_estimators` of a parameter the client
  never mentioned.
- The client's explicit values are scaled by the preset too and still win over the
  base: a client that asks for `n_estimators=100` with the `conservative` preset
  gets `70`.
- `balanced` is the default and changes nothing.
- The `auto_search` mode trains every candidate in `manual` mode and applies the
  preset **once per candidate**: the recursion forwards the *raw* client values
  together with the preset, never already-adjusted values (forwarding the adjusted
  ones would scale the parameters twice).
- `metrics["model_parameters"]` reports the parameters that were really used (the
  merged base plus the client's values, with the preset applied once), so the
  "Effective parameters" panel of the UI is truthful in every mode.

A preset can never break the estimator constructor: it only scales the values of
the keys it knows and never introduces a key.

Detailed steps and examples
---------------------------

1) Tabular / sklearn-like models

- If your model is a scikit-learn estimator (classification/regression), you can often add it by:
  - Adding a `MODEL_CATALOG` entry with `params` matching the estimator signature
  - Extending `build_model()` with a branch that returns the estimator, e.g.:

```py
if model_name == "My_Sklearn_Model":
    return MyEstimator(**params)
```

- `train_model()` will call `build_model()` and run the standard fit/predict/score flow.

Limitations / notes:
- `build_model()` currently contains only a subset of sklearn estimators. Add imports at top of file and a branch in `build_model()`.
- Tabular flows expect a pandas `DataFrame` with a `label_column`. Missing or mis-typed label columns will raise errors.
- The catalog `params` are forwarded to the estimator constructor as keyword arguments, so an entry must only declare keys the estimator accepts. Train/test-split keys such as `test_size` are owned by the training loop: they are stripped from the client-supplied `hyperparameters` in `train_model()` and again in `build_model()` before the constructor call, every other key is passed through (a preset may scale its value, a typo therefore still raises `TypeError`). See "Parameter ownership" and "Presets" above.
- A model that maps to two estimators (e.g. `SVM` → `SVC` for classification, `SVR` for regression) may only declare keys that **both** accept — a branch-specific key is inexpressible in a shared catalog entry. `build_model()` therefore sets the classifier-only keys on the `SVC` branch and drops them on the `SVR` branch (the keys are listed in `_BRANCH_SPECIFIC_PARAMS`):
  - classification: `probability=True` (the run reports `predict_proba`) and `random_state` (default `42`; a client-supplied seed is honoured). The seed is required because the Platt calibration that `probability=True` enables shuffles the data — an unseeded `SVC` produced different `predict_proba` values on every run.
  - regression: the `SVR` accepts neither `probability` nor `random_state` (scikit-learn ≥ 1.9), so both are dropped — a client-supplied `random_state` cannot crash the regression branch.

2) Vision models (images)

- Image trainers expect a folder with structure `root/class_name/*.jpg` and rely on `torchvision.datasets.ImageFolder` in `_train_resnet_image_model()`. Such a folder is a dataset of the registry whose `source` is `folder`: the directories of `data/` are registered with that source at the startup by `seed_builtin_datasets()`, and the training request refers to the folder by its `dataset_id`. Only the directories of `data/` are registered that way, because an upload is always a CSV file.
- For a new custom vision model:
  - Add catalog entry with category `vision` and sensible `params` (`epochs`, `batch_size`, `learning_rate`, `model_name`)
  - Add a new trainer like `_train_myvision_model(dataset_path, hyperparameters)` using the pattern in `_train_resnet_image_model()`.
  - Route calls from `train_model()` when `entry["category"] == 'vision'` and `model_name == 'MyVisionModel'`.

Limitations:
- Image pipelines assume ImageFolder layout and use CPU/GPU available from PyTorch defaults. If you need custom transforms, add them inside the trainer.
- Large image models (ResNet50, ViT) require significant GPU memory; the backend doesn't currently orchestrate distributed or multi-GPU training.

3) NLP / Transformers

- For transformer-based models use `_train_transformer_text_classifier()` as a template. It relies on `transformers` and `datasets` libraries.
- Add entry to `MODEL_CATALOG` with `category: 'nlp'` and `params` like `epochs`, `batch_size`, `learning_rate`, `model_name`.

When to implement a custom trainer:
- If your model requires sequence-to-sequence training, different tokenization logic, or custom training loops, implement a dedicated `_train_<your_model>()` function and call it from `train_model()`.

Limitations:
- Transformers training requires `transformers`, `datasets`, and (ideally) a GPU. Without a GPU, training will be slow and may OOM for large models.
- The helper assumes labels are available and that datasets are not extremely large (no streaming or sharded loading by default).

4) Reinforcement Learning

- RL support uses `stable-baselines3` and `gymnasium` in `_train_rl_model()`.
- To add a new algorithm or tweak training, modify `_train_rl_model()` or add a new helper function.

Limitations:
- Gym envs must be available in the runtime environment (i.e., installed or reachable). Installing custom environments is outside the repo scope.
- RL training is long-running and currently executed synchronously in a threadpool; consider using an async job queue (Celery / RQ) for production.

5) Autoencoders, Graph models, Timeseries

- Follow the same pattern: catalog entry + params + trainer if needed. For timeseries and graph models you will likely need to write a PyTorch training loop similar to `_train_torch_regression_or_classification()`.

6) Clustering models

- The clustering entries (`K-Mean`, `GMM`, `Hierarchical_Clustering`, `DBSCAN`, `HDBSCAN`, `PCA`, `t-SNE`, `UMAP`, `HMM_timeseries`) all use the `clustering` category and are trained by `_train_clustering(...)`.
- Their constructors are called with the merged params verbatim (`KMeans(**params)`, `GaussianMixture(**params)`, ...), so the entry's `params` must only contain keys that constructor accepts, and the trainer-owned keys (`test_size`) are filtered out there as well. The merged params are the catalog defaults, the mode's suggestions and the client's values, with the preset applied once (see "Presets").
- `PCA`, `t-SNE` and `UMAP` are embeddings rather than clusterers: they report `embedding_shape` / `sample_count` instead of `cluster_count`, plus a real quality number (`explained_variance` for PCA, `trustworthiness` for t-SNE and UMAP; the latter needs at least 12 rows).
- `HDBSCAN` uses `sklearn.cluster.HDBSCAN` (scikit-learn >= 1.3), `UMAP` needs `umap-learn` (in `requirements.txt`) and `HMM_timeseries` needs `hmmlearn`. When a library is missing the trainer raises `RuntimeError("<lib> is not installed")`.

Frontend integration
-------------------

- The frontend obtains model metadata from `GET /api/v1/ml/models` and `GET /api/v1/ml/model-details` endpoints which use `list_available_models()` in `model_training.py`.
- If you add special UI fields (e.g., `env_id` required for RL), update the frontend `NewJob` component to request and validate those fields before submission.

Testing and validation
----------------------

- Add unit tests for:
  - `get_model_entry()` and `normalize_model_name()` behavior when new aliases or keys are added.
  - New trainer function logic with small synthetic datasets.
  - `train_model()` end-to-end flow (can be a fast smoke test using very small datasets / few epochs).
- Use `pytest` and add tests under `backend/tests/`.

Function limitations (detailed)
------------------------------

1) `suggest_hyperparameters(...)`
- If `use_llm=True` this function calls Google Gemini (via `google-generativeai`). Limitations:
  - Requires `GOOGLE_API_KEY` and the library installed — network call latency and quota apply.
  - LLM output may not be valid JSON; the function strips some markdown wrappers and then `json.loads()` the response — malformed responses will raise errors.
  - The function only accepts suggested keys that the catalog entry declares for the model (`base_params`). The result is merged into the estimator constructor, so accepting an unknown key (e.g. `learning_rate` for `Logistic_Regression`) would raise `TypeError` during training.
  - **Without the LLM the function returns the catalog parameters of the model unchanged**: `suggest_hyperparameters(model, ...) == MODEL_CATALOG[model]["params"]` for every model. There is no heuristic left that could add a value, because a key the catalog does not declare is rejected by the estimator constructor.
  - Consequence: `auto_tune` runs a randomized hyperparameter search over the model's
    curated `search_space` (`RandomizedSearchCV`, `n_iter = min(12, combinations)`,
    `cv=3` with `cv=2` fallback on small folds, scoring accuracy for classification and
    `r2` for regression) and reports `best_params` as `metrics["model_parameters"]` plus
    `metrics["search_results"]`; `auto_fine_tune` runs the same search on a neighbourhood
    of the base configuration; the preset is applied once on top of the merged base (see
    "Presets"). Client-pinned hyperparameters are sampled out of the space and still win.

2) `train_model(...)`
- Synchronous execution: `train_model` is typically executed inside `run_in_threadpool()` (FastAPI endpoint). Long-running training will block the threadpool thread; for production use a job queue or background worker.
- Resource management: The code does not manage GPU allocation, it uses the default PyTorch device; adding explicit device selection is recommended for multi-GPU systems.
- Error handling: Many helpers raise exceptions which bubble up to the endpoint; consider more granular error reporting and retries for recoverable failures.
- `auto_search` ranks the trained candidates with `score_candidate(metrics, optimize_metric)`: the requested metric is used when the run reports it, otherwise the first reported metric of `accuracy` / `r2` / `mse` / `mean_reward` / `silhouette` is used. The error metrics (`mse`, `rmse`, `mae`) are negated because lower is better for them, and a candidate that reports none of these metrics scores `0.0`. The ranking therefore works for classification, regression, RL and clustering runs: clustering candidates are ranked by their `silhouette` score (DBSCAN's noise label `-1` is excluded from the computation, and a run with fewer than two clusters scores `0.0`).
- `auto_search` trains every candidate in `manual` mode and applies the preset **once per candidate** (the recursion forwards the raw client values plus the preset, never already-adjusted values). It also forwards only the client parameters that the candidate's own catalog entry declares: a parameter of another candidate (e.g. `C` for `Random_Forest`) must not make a candidate fail and silently disappear from the comparison. This is the one deliberate asymmetry to the single-model path, where an unknown parameter name still raises `TypeError`. The filter is catalog-based, so a parameter that the estimator accepts but the catalog does not declare (e.g. `max_features` for `Random_Forest`) is honoured in the single-model path yet dropped for the candidates of an `auto_search` run.

3) `build_model(...)`
- Only supports a subset of sklearn/XGBoost/LightGBM/CatBoost models implemented in the function. Add imports and branches for new estimators.
- Parameter validation is minimal — invalid param names will raise exceptions from the estimator constructors. The only keys that are removed before the constructor call are the training-loop keys listed in `_TRAINER_OWNED_PARAMS` (`test_size`, which is passed to `train_test_split()` separately) and the branch-specific keys of `_BRANCH_SPECIFIC_PARAMS` (`probability`, `random_state`) on the `SVR` branch of `SVM`.
- Forced constructor values (`probability` for `SVC`, `eval_metric` for `XGBClassifier`, `verbose` for the CatBoost estimators) are merged into the kwargs dict instead of being passed as a separate keyword, so a client-supplied value for them no longer collides with the forced one.

4) Data helpers (`_prepare_dataset`, `load_huggingface_dataset`, the dataset registry of `backend/app/datasets.py`)
- CSV loading assumes the label column exists; missing columns raise errors. Ensure datasets are preprocessed to include labeled columns.
- Hugging Face loading converts to a temporary CSV and expects modest dataset sizes; for large datasets consider using streaming or HF dataset streaming APIs.
- A dataset is a row of the `datasets` table (`backend/app/models.py`), not a path the client sends. The client refers to it by `dataset_id`; `dataset_name` is a lookup in the same registry, never a path. The server resolves the row to a path **relative** to the datasets root (`DATASETS_ROOT`, the repository root by default) with `resolve_storage_path()` (`backend/app/datasets.py`), which refuses an absolute path, a `..` and a symlink that points out of the root. A client therefore cannot make the server read a file outside of the root.
- The registry holds three kinds of rows: `builtin` (a CSV file of `data/`, registered at the startup by `seed_builtin_datasets()` in `backend/app/main.py`), `upload` (a CSV file the user sent, stored under `uploads/<user id>/` with a generated name) and `folder` (a directory of `data/`, the layout the vision models expect: one subdirectory per class). The listing returns the rows of the caller and the built-in ones; the columns of a row are capped by `MAX_REPORTED_COLUMNS`.
- The helpers of the registry are `resolve_storage_path()`, `relative_storage_path()`, `validate_upload()`, `write_upload()`, `describe_csv()`, `suggest_label()`, `size_of()`, `unique_dataset_name()`, `builtin_files()`, `builtin_folders()` and `dataset_to_dict()`. There is no `store_upload()` any more: the endpoint validates the file with `validate_upload()` and writes it with `write_upload()`, so the description of the file is computed once and reused for the row of the registry.
- The endpoints are `GET /api/v1/ml/datasets` (the listing of the registry, which replaced the old listing of the files of `data/`), `GET /api/v1/ml/datasets/{id}` (one row, with its columns and its suggested label) and `POST /api/v1/ml/datasets/upload` (the upload). An upload is a **comma separated** CSV file: `validate_upload()` refuses a file with another separator, a file with less than two columns and a file without rows. The endpoint reads the body itself, after the token was checked, so an unauthenticated request is refused before its file is written to the disk.

5) Category-specific trainers
- Transformers trainer uses the Hugging Face `Trainer` and assumes the dataset fits in memory or is handled by the `datasets` library. It does not implement advanced features like LoRA or quantized fine-tuning by default.
- Vision trainer uses `torchvision` and a basic training loop. If you need advanced scheduling, mixed precision, or distributed training, integrate `accelerate` or custom training loops.

Operational notes
-----------------

- Artifacts are written to `MODEL_DIR` (defined in `model_training.py`). Ensure persistent storage in production.
- Secrets: do not commit API keys. Set `GOOGLE_API_KEY` in environment variables or secret manager used by your runtime.
- Consider replacing synchronous job execution with a background worker for scalability (RQ, Celery, or a Kubernetes Job).

Checklist when adding a new model
--------------------------------

1. Add `MODEL_CATALOG` entry and optional `ALIASES` mapping.
2. Add imports and expand `build_model()` if the model is sklearn-like.
3. Add or reuse a category-specific trainer; add tests for the trainer.
4. Check that the entry's `params` only contain keys the estimator accepts, and that the `category` maps to the intended code path (see the routing table above).
5. Update `list_available_models()` metadata if special UI fields are needed.
6. Add any new Python dependencies to `backend/requirements.txt` and document them here.
7. Run `python -m py_compile backend/app/model_training.py` to catch syntax errors.

License & contact
-----------------

This document is part of the project; adapt the instructions to your team's workflow. For help, open an issue or ask me to demonstrate adding a concrete example model.
