# The checkpoint: when to keep building, and when to stop

This is the **I2** section of the plan of 25 October 2026, written down as
the commitment it is. Everything in the phases 3 to 5 work is supply-side:
it makes the product *able* to do more. Nothing in it is evidence that one
outside person wants it to. The checkpoint is the honest measurement that
decides what gets built next, and it comes **after Phase 2 and before the
model tiers are extended further**.

## The three measurements

At the end of Phase 2 (the queue, the executor, the quotas, the admin
screen - all of which this repository now carries), measure these three
things before building anything more:

1. **A stranger can go from the readme to a trained model and a prediction
   in under ten minutes, unaided.** Time it on a clean machine: a clean
   clone, the install script, the two commands of the readme, one training,
   one prediction. No help from the author, no chat open, no workaround.
   If this fails, nothing else matters yet - fix onboarding first, because
   every later number is measured against a door nobody got through.

2. **At least five people who are not you have trained something.** Not
   registered; not "had a look". Trained a run, waited for it, and looked
   at the result. Five is the smallest number that is not a coincidence.

3. **You can say what they used it for.** In one sentence each: the task,
   the data, whether the product was the right tool for it. The answer is
   allowed to be "a class exercise" or "curiosity" - but it has to be
   *known*, not assumed.

## How to take the measurements

- Give the product to the five people the way a stranger would find it: the
  readme of a fresh clone, or one deployed URL. Do not sit next to them;
  watch only what the product shows you (the runs they create, the errors
  they hit, the audit trail).
- Write the three answers down in this file, under *Results* below, with a
  date. An unrecorded measurement is a vibe.
- Every question a tester asks is an onboarding defect: add it to the readme
  or the interface, then re-measure with the next stranger.

## What each answer decides

- **If the first fails** (the ten minutes): fix onboarding. The ten minutes
  is the gate; the model tiers behind it are the most expensive work in the
  plan and they only pay off for someone who got through the door.
- **If the second fails** (the five people): stop adding models. The model
  tiers are 25 to 40 days of work; without five users they are a cost with
  no return. Find out why the product was not used - wrong audience, wrong
  task, wrong shape - before writing another trainer. The forecasting
  family and Q-Learning (already built) stay; the rest of the ladder waits.
- **If the third fails** (the "what for"): the product has no job yet. That
  is a better thing to learn at day 25 than at day 90. A product with no
  job needs a pivot, not more models - and the honest pivot is usually
  "shrink to the one task the first five almost used it for."

## What is deliberately *not* behind the checkpoint

The infrastructure this repository already carries is not wasted if the
checkpoint fails: the honest evaluation, the bundle contract, the quotas
and the admin screen are the cost of *safely offering* any model at all,
and they are done. The checkpoint protects the next 25 to 40 days - the
remaining tiers of section F - not what is already here.

## Results

| Date | Measurement 1 (10 minutes) | Measurement 2 (five users) | Measurement 3 (what for) | Decision |
|---|---|---|---|---|
| — | *not yet measured* | *not yet measured* | *not yet measured* | — |

Fill a row per attempt. An empty table is the honest current state.
