- [DONE] add auto fine-tuning features with and without using llm (implemented in W1-7)
- [DONE] a real search for `auto_tune` (W1-7; was listed as out of scope in FOLLOWUP_PLAN section 11)
+- [DONE] an inference endpoint: `GET /runs/{id}/schema` and `POST /runs/{id}/predict` (bundle artifacts)
+- [DONE] preprocessing (imputation, one-hot, scaling), a stratified hold-out, task-correct metrics with baselines and a cross-validation for the tabular models
+- [DONE] a real `Autoencoder` (encoder-bottleneck-decoder, held-out error against a baseline, anomaly threshold)
+- [DONE] a heartbeat, a stale-run sweeper, a cancel endpoint, and a queue that survives a restart (the rows of `training_runs`); an optional separate worker (`python -m backend.app.worker`)
+- [DONE] a run comparison view with a chart, the evaluation / confusion matrix / data-preparation panels, a prediction form
 
-Deferred from FOLLOWUP_PLAN.md section 11 (still open):
+Still open:
 
-- [ ] Real LSTM / RNN / SSM / TCN, GNN, ViT, Autoencoder and Q-Learning trainers (they need new data contracts: a time axis, an edge list, an image pipeline). Until then they stay `implemented: False`.
+- [ ] Real LSTM / RNN / SSM / TCN, GNN, ViT and Q-Learning trainers (they need new data contracts: a time axis, an edge list, an image pipeline). Until then they stay `implemented: False`.
 - [ ] Real BERT2BERT / seq2seq / UL2 (encoder-decoder or generation trainers) and GPT / LLaMA (causal language-model trainers). Today they only fit a sequence classifier, so they are `implemented: False`.
-- [ ] A production-grade job queue (Celery / RQ / arq). `_execute_training` in `backend/app/main.py` is the seam: today it runs in the web process through `BackgroundTasks`, and the startup reaper is only exact for a single worker (a multi-worker deployment needs a heartbeat).
+- [ ] Interruptible trainings: run each training in a process of its own (a `fit` cannot be stopped inside a thread), so that cancel frees the slot at once, a crash of a training cannot take the worker with it, and memory is returned to the system. Today cancel discards the result when the training ends.
+- [ ] A dedicated job queue (Celery / RQ / arq) if one database is not enough: priorities, per-user fairness, retries. The seam is `_claim_next_run` / `_run_claimed` in `backend/app/main.py`.
+- [ ] Preprocessing for the clustering, NLP, vision and RL trainers (only the supervised tabular models and the autoencoder have it); a clustering run on a CSV with text or NaN still fails.
+- [ ] Batch prediction from a CSV upload (the endpoint takes JSON rows, at most `PREDICT_MAX_ROWS`).
+- [ ] Prediction for the clustering / embedding runs (a bundle for `K-Mean`, `GMM`, `PCA`, `UMAP` with the same preprocessing) and for the torch trainers.
+- [ ] Feature importances / permutation importance in the run page (the pipeline now knows its encoded feature names).
+- [ ] A held-out accuracy for the NLP classifiers (BERT, DistilBERT, self-attenetion_transformer, MiniLM report `train_loss` only, so they advertise no accuracy range).
 - [ ] `updated_at` maintained by a database trigger instead of the ORM `onupdate`.
 - [ ] `postgresql.JSONB` for the JSON columns (needs an ORM change and breaks SQLite).
-- [ ] A held-out accuracy for the NLP classifiers (BERT, DistilBERT, self-attenetion_transformer, MiniLM report `train_loss` only, so they advertise no accuracy range).
+- [ ] A frontend test setup (the display components were checked by server-side rendering during development, but no test of the suite does it).

 Not recoverable, nothing to do: the `notes` data of a database created by the previous project (the table is dropped by revision `c4a9e2b17d3f`).
