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

- **Mislabelled boosters:** the three `*_timeseries` boosters are tabular models on a shuffled split, not forecasters.
- **ResNet:** it reports accuracy on its own training batches.
- **Checkpoint downloads:** a client can make the server download any Hugging Face repository by overriding `model_name`. This is the most serious exposure, and the fix is small.
- **Storage:** nothing can be deleted, so a storage quota can’t work yet.
- **Queue fairness:** one user can fill the queue and starve everyone else.
- **Models:** of the 12, I’d build 10, make LLaMA conditional on a GPU worker, and retire UL2. It has 20 billion parameters, and renaming a small T5 as “UL2” would be the same dishonesty the catalog work removed.
- **Checkpoint:** I recommend a hard stop after the first three phases (users and quotas, then the execution layer), which is about 20 to 25 focused days. Before building the model tiers, which are 38 to 50 days, put the product in front of five real users. The plan has no evidence yet that anyone wants it.
- **Rust:** the executor interface in section B is what makes it possible later, one model at a time, so it’s a reason to build that section first. Profile one real run before committing.
- **Verification limits:** I can’t run any torch, transformers or gymnasium path in my environment. Those parts of the plan rely on your CI, and the day counts are estimates (plus or minus 50 percent).