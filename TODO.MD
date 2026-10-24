- [DONE] add auto fine-tuning features with and without using llm (implemented in W1-7)
- [DONE] a real search for `auto_tune` (W1-7; was listed as out of scope in FOLLOWUP_PLAN section 11)

Deferred from FOLLOWUP_PLAN.md section 11 (still open):

- [ ] Real LSTM / RNN / SSM / TCN, GNN, ViT, Autoencoder and Q-Learning trainers (they need new data contracts: a time axis, an edge list, an image pipeline). Until then they stay `implemented: False`.
- [ ] Real BERT2BERT / seq2seq / UL2 (encoder-decoder or generation trainers) and GPT / LLaMA (causal language-model trainers). Today they only fit a sequence classifier, so they are `implemented: False`.
- [ ] A production-grade job queue (Celery / RQ / arq). `_execute_training` in `backend/app/main.py` is the seam: today it runs in the web process through `BackgroundTasks`, and the startup reaper is only exact for a single worker (a multi-worker deployment needs a heartbeat).
- [ ] `updated_at` maintained by a database trigger instead of the ORM `onupdate`.
- [ ] `postgresql.JSONB` for the JSON columns (needs an ORM change and breaks SQLite).
- [ ] A held-out accuracy for the NLP classifiers (BERT, DistilBERT, self-attenetion_transformer, MiniLM report `train_loss` only, so they advertise no accuracy range).

Not recoverable, nothing to do: the `notes` data of a database created by the previous project (the table is dropped by revision `c4a9e2b17d3f`).
