Developer guide — adding ML / DL / RL models
=============================================

This document explains how the backend training system is organized and shows step-by-step instructions for adding new models (ML / DL / RL), where to wire them in, and the limitations of the core functions you will interact with.

High-level architecture
-----------------------

- Core registry: `MODEL_CATALOG` in `backend/app/model_training.py` is the single source of truth for model metadata used by the API and frontend.
- Normalization/aliases: `ALIASES` maps common alternate names to canonical catalog keys.
- Entry points:
  - `train_model(...)` — main orchestration function that prepares data, applies presets/modes, routes to model-specific trainers, and returns metrics + artifact path.
  - `suggest_hyperparameters(...)` — LLM-assisted or heuristic hyperparameter suggestion.
  - `build_model(...)` — factory for simple sklearn/tabular models.
  - `_train_transformer_text_classifier(...)`, `_train_resnet_image_model(...)`, `_train_rl_model(...)`, `_train_clustering(...)` — category-specific training helpers.

Where to add a new model (quick)
-------------------------------

1. Open `backend/app/model_training.py`.
2. Add a new entry to `MODEL_CATALOG` (see the existing entries). Each entry should include at minimum:

```py
"MyModelName": {
    "category": "classification",  # classification, regression, vision, nlp, timeseries, reinforcement-learning, clustering, autoencoder, graph
    "description": "Short description",
    "params": {"learning_rate": 1e-3, "epochs": 5, ...},
    "optimization": ["learning_rate", "epochs"],
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

2) Vision models (images)

- Image trainers expect a folder with structure `root/class_name/*.jpg` and rely on `torchvision.datasets.ImageFolder` in `_train_resnet_image_model()`.
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
  - The function merges suggested keys only when keys are in `base_params` or are primitive values; it will not accept nested complex structures safely.
  - For reproducible automated tuning prefer deterministic heuristics or a grid-search implementation.

2) `train_model(...)`
- Synchronous execution: `train_model` is typically executed inside `run_in_threadpool()` (FastAPI endpoint). Long-running training will block the threadpool thread; for production use a job queue or background worker.
- Resource management: The code does not manage GPU allocation, it uses the default PyTorch device; adding explicit device selection is recommended for multi-GPU systems.
- Error handling: Many helpers raise exceptions which bubble up to the endpoint; consider more granular error reporting and retries for recoverable failures.

3) `build_model(...)`
- Only supports a subset of sklearn/XGBoost/LightGBM/CatBoost models implemented in the function. Add imports and branches for new estimators.
- Parameter validation is minimal — invalid param names will raise exceptions from the estimator constructors.

4) Data helpers (`_prepare_dataset`, `load_huggingface_dataset`)
- CSV loading assumes the label column exists; missing columns raise errors. Ensure datasets are preprocessed to include labeled columns.
- Hugging Face loading converts to a temporary CSV and expects modest dataset sizes; for large datasets consider using streaming or HF dataset streaming APIs.

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
4. Update `list_available_models()` metadata if special UI fields are needed.
5. Add any new Python dependencies to `backend/requirements.txt` and document them here.
6. Run `python -m py_compile backend/app/model_training.py` to catch syntax errors.

If you want, I can also add a template `backend/tests/test_new_model.py` and create `Dockerfile` + `docker-compose.yml` ready for production/dev — tell me which you'd prefer next.

License & contact
-----------------

This document is part of the project; adapt the instructions to your team's workflow. For help, open an issue or ask me to demonstrate adding a concrete example model.
