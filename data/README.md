# Local Dataset Storage

The CSV files in this directory are the datasets that ship with the
repository. They are registered automatically when the application starts, so
a fresh clone can train a model without any setup. A directory that holds one
subdirectory per class is registered as well: it is the dataset of a vision
model.

| File | Task | Label column | Rows |
|---|---|---|---|
| `sample_customer_churn.csv` | classification | `churned` | 400 |
| `sample_house_prices.csv` | regression | `price_k` | 300 |

Both files are synthetic and deterministic: they were generated with a fixed
seed, so a run on them always produces the same metrics.

## Adding your own datasets

There are two ways:

1. **Upload them in the application.** The *New Training Job* view has an
   upload button; the file is stored under `uploads/<user id>/` with a
   generated name, and it belongs to the user who uploaded it.
2. **Put them in this directory.** A CSV file that is placed here is
   registered as a built-in dataset at the next start of the application, and
   it is visible to every user. The files of this directory are git-ignored
   (`data/*.csv`), except the `sample_*.csv` files.

## The format

- a CSV file with a header row, **separated by commas**: the separator is a
  comma, and a file with another separator is refused by the upload,
- a name that ends with `.csv`: only CSV files can be uploaded,
- at least two columns and at least one data row,
- at most 50 MiB, at most 1000 columns and at most 2000000 rows for an upload
  (`MAX_UPLOAD_BYTES`, `MAX_UPLOAD_COLUMNS` and `MAX_UPLOAD_ROWS` in
  `backend/app/datasets.py`; the limits are read at import time, so a change
  needs a restart of the server). A file that is placed in this directory is
  only described at the startup: the column limit applies to it, the size and
  the row limit do not.
- **numeric columns only** for now: the trainer does not encode the
  categorical or the textual columns yet, so a file with a column of strings
  fails with an error from the estimator. A column of strings can be mapped
  to numbers before the upload.
- one column is the target. The application suggests it (a column named
  `label`, `target`, `y`, `class`, `outcome` or `churn`, otherwise the last
  column) and the suggestion can be changed in the form.


## The sample data of every dataset kind (plan F1)

The tests must not download anything, and a user needs a file of every
dataset kind to try the corresponding model family:

- `synthetic_sine.csv` - a sine plus noise series (kind: timeseries). Train
  the forecasters on it: `LSTM` with `label_column=value`.
- `karate_club.zip` - the Zachary karate club graph, 34 nodes and 78 edges
  (kind: graph). Train `GNN` on it for the classic semi-supervised split.
- `sbm_graph.zip` - a stochastic block model with informative structure and
  uninformative features: the graph is the signal, which is the honest test
  of whether a GNN uses it at all.
- `sample_text_corpus.csv` - a small text corpus (kind: text) for the text
  classifiers and the GPT fine-tuning.
- `sample_text_pairs.csv` - a source/target pair file (kind: text_pairs):
  an uppercase mapping, a deterministic relation a tiny T5 can learn.
