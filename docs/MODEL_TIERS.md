# The model tiers: the order inside Phase 5, and where the ladder stops

This is the **F7** section of the plan of 25 October 2026. The models are
the expensive, slow, support-heavy part of the product; the order below is
chosen so that every step is either cheap-and-complete, or the honest
baseline of the step after it. The checkpoint (`docs/CHECKPOINT.md`) gates
the whole ladder: **stop after step 2 if no outside user has appeared.**

## The rule that gates every entry (plan F0)

An entry may say `implemented: true` only when all three hold, and a
parametrized smoke test enforces it (`backend/tests/test_model_smoke.py`):

1. a smoke test with a tiny configuration runs offline and reports the
   advertised metric on held-out data, next to a baseline;
2. it saves a `ModelBundle` that can predict (`backend/app/bundles.py`);
3. it declares what it needs: `requires_gpu`, `min_memory_mb`,
   `downloads_checkpoint`, `allowed_checkpoints`, `dataset_kind`,
   `bundle_kind`.

`implemented` (the code exists and is tested) is separate from `available`
(this deployment has the packages and the hardware), which
`GET /api/v1/ml/models` computes with a reason - the interface disables an
unavailable model and says why instead of queueing it forever.

## Where this repository stands

Every step of the ladder below is **built**; what remains is the
checkpoint decision about *serving* the later tiers, and the entries whose
hardware this deployment lacks stay `available: false` with the reason.

| Step | Family | Status | Notes |
|---|---|---|---|
| 1 | **Q-Learning** | done | the real table; non-slippery FrozenLake reaches a 1.0 success rate; needs no torch |
| 2 | **The forecasting family** (RNN, LSTM, TCN, SSM, the boosters in forecasting mode) | done | one shared contract: a chronological split, direct multi-step, the naive and seasonal-naive baselines, a skill score; the boosters are the honest baseline family |
| 3 | **The text foundation and GPT, then seq2seq** | done | GPT is causal-LM fine-tuning with held-out perplexity; seq2seq (t5) with ROUGE against the copy baseline; BERT2BERT warm-started from two BERT checkpoints |
| 4 | **GNN** | done | a two-layer GCN/SAGE in plain torch (no PyTorch Geometric), with the feature-only MLP baseline that tests whether the graph helps |
| 4 | **ViT** | done | the allow-listed `google/vit-base-patch16-224` checkpoint with a new head; a linear probe by default; `requires_gpu: recommended` |
| 4 | **SSM** | done | a diagonal state-space model in the style of S4D/LRU; the magnitude stays below one by construction |
| 5 | **BERT2BERT** | done | `requires_gpu: recommended` - it learns its cross-attention from scratch, weaker than T5 on small data |
| 5 | **LLaMA** | done, GPU-gated | LoRA (peft) of an allow-listed Llama checkpoint; `requires_gpu: true`, `min_memory_mb: 12000`; on a CPU-only deployment the entry is unavailable and says why; the artifact is the adapter, a few megabytes |
| 5 | **UL2** | retired | 20 billion parameters cannot be trained or served on the hardware this product targets; hidden, with the permanent reason in the catalog |

## The order, and why this order

1. **Q-Learning first** (about 2 days): cheap, no dependencies, visibly
   complete. It proves the F0 gate works before anything expensive rides on
   it.
2. **The forecasting foundation second** (about 9 days): forecasting is the
   most common real task of the missing ones, and the boosters give an
   honest baseline - if a neural forecaster does not beat them, the number
   says so in the comparison view, which is the point of the whole
   evaluation-honesty work.
3. **The text foundation and GPT, then seq2seq** (about 9 days): the most
   requested capability, and the one that depends most on the quota and
   executor work being in place (a fine-tune is long and a token cap has
   to bound it).
4. **GNN, ViT, SSM** (4 to 5 days each): real work, distinct audiences,
   none of them a baseline for the others.
5. **BERT2BERT and LLaMA, UL2 retired**: BERT2BERT is kept because it is
   real and cheap to maintain behind the shared trainer; LLaMA only exists
   with a GPU worker (the capability routing makes that explicit instead of
   silent); UL2 leaves the catalog because keeping it would be the same
   false claim the catalog work removed elsewhere.

**Stop after step 2 if no outside user has appeared by the checkpoint.**
The later steps are the expensive ones, and every model is a permanent
support burden: versions, downloads, GPU memory, licences. Build only what
a user asks for.

## Operating the tiers

- The compute-heavy categories (`timeseries`, `graph`, `nlp`, `vision`,
  `reinforcement-learning`) are **off** in the free quota profile until an
  administrator enables them (`QUOTA_FREE_CATEGORIES` for the deployment,
  or the profile editor in the admin screen for the fine-grained case).
  This is on purpose: those are the entries that can cost real money or
  block the machine.
- Every checkpoint a text or vision model may download comes from the
  entry's `allowed_checkpoints`; anything else is refused before anything
  is fetched, and `trust_remote_code` is never enabled.
- The offline sample data of every dataset kind lives in `data/`
  (`synthetic_sine.csv`, `karate_club.zip`, `sbm_graph.zip`,
  `sample_text_corpus.csv`, `sample_text_pairs.csv`): the tests never
  download anything, and a user can try every family.
