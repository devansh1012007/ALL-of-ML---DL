# Local Dataset Storage

The CSV files in this directory are the datasets that ship with the
repository. They are registered automatically when the application starts, so
a fresh clone can train a model without any setup.

| File | Task | Label column | Rows |
|---|---|---|---|
| `sample_customer_churn.csv` | classification | `churned` | 400 |
| `sample_house_prices.csv` | regression | `price_k` | 300 |

Both files are synthetic and deterministic: they were generated with a fixed
seed, so a run on them always produces the same metrics.

## Adding your own datasets

There are two ways:

1. **Upload them in the application.** The *New Training Job* view has an
   upload button; the file is stored under `uploads/<user>/` and belongs to
   the user who uploaded it.
2. **Put them in this directory.** A CSV file that is placed here is
   registered as a built-in dataset at the next start of the application, and
   it is visible to every user. The files of this directory are git-ignored
   (`data/*.csv`), except the `sample_*.csv` files.

## The format

- a CSV file with a header row,
- at least two columns and at least one data row,
- **numeric columns only** for now: the trainer does not encode the
  categorical or the textual columns yet, so a file with a column of strings
  fails with an error from the estimator. A column of strings can be mapped
  to numbers before the upload.
- one column is the target. The application suggests it (a column named
  `label`, `target`, `y`, `class`, `outcome` or `churn`, otherwise the last
  column) and the suggestion can be changed in the form.
