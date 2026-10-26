# Using the workbench

This page is for the person who trains models in the browser. The
operator's manual lives in `docs/OPERATOR_GUIDE.md`.

## An account

You register, an administrator may have to approve the account, and you
sign in. The browser session is a short-lived access token plus a refresh
token the page renews for you; "log out" ends the session on the server,
not just in the tab. You can change your password and delete your own
account (with its data) from the interface.

## The data

Upload a CSV and it becomes a dataset of yours; the datasets that ship with
the repository are marked built-in and cannot be deleted. Every dataset is
identified by its content hash, which is what the comparison view uses to
tell you whether two runs are comparable at all. You can delete your own
datasets - unless a queued or running training is reading one.

## A training

Pick a model, a dataset, a label column, and (optionally) the preprocessing
options, the split strategy, and the hyperparameters. The run goes into a
queue; quotas decide how many you may have in flight. While it trains, the
run page shows what the training is doing - the phase it is in, the metrics
it reports - and you can cancel it: with the subprocess executor a cancel
stops the training immediately.

When it finishes you get the honest version of the result: the score
against a baseline, the cross-validation spread, the charts (curves, error
views, importances) and the dataset profile. A metric without a baseline is
not shown as an achievement.

## Comparing runs

Select runs on the same dataset and compare them. The comparison says when
two runs are not comparable (different data, different split) instead of
letting the numbers lie, and it shows the cross-validation noise, so a
0.3 percent difference is not mistaken for a winner.

## Serving a model

Deploy a finished run under a name; the name survives retraining. Predict
through the API with a key that may predict and nothing else, score a CSV
in one request or queue it as a job, and watch the monitoring counters
(requests, errors, drift) of the deployment.

## The limits you will meet

Every refusal names the limit it hit and when it resets - a quota refusal
is information, not an insult. If a category (vision, text,
reinforcement-learning) is closed for your profile, the model's form says
so; an administrator opens it.
