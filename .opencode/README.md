# The subagent framework of this repository

The workflow of `AGENTS.md` is binding: a context-gathering subagent runs
before every change, an independent review subagent runs after every atomic
phase, and one more review runs before the end. These agents are the ones
that carry it out. They live in `.opencode/agents/`, so every clone of the
repository has them, and they are part of the contract of the repository
rather than the setting of one machine.

## The agents

| agent | what it is for | may it write? |
|---|---|---|
| `recon` | the context of a phase: the files, the flows, the invariants, the tests that pin them | no |
| `implementer` | one atomic phase: the code, the tests, the commit on the given branch | yes |
| `reviewer` | the review gate: it audits a diff and tries to break the change | no |
| `verifier` | the mechanical checks: the test suite, the frontend build, the migration drift | no |

They are used with the `task` tool:

```
task(subagent_type="recon",        description="...", prompt="...")
task(subagent_type="implementer",  description="...", prompt="...")
task(subagent_type="reviewer",     description="...", prompt="...")
task(subagent_type="verifier",     description="...", prompt="...")
```

## What each agent is given, and what it returns

Every agent gets a self-contained brief: the goal, the scope, the files to
look at, the commands to run, and the format of the answer. The formats are
part of the contract, because a report that has to be re-read is a report
that was not written well.

- `recon` returns the **context report**: the affected files with
  `file:line` evidence, the behaviour that must not change, the risks and the
  hidden coupling, the unknowns, and the tests that are required. Facts and
  inferences are separated; an unknown is resolved by investigation, not by a
  guess.
- `implementer` returns the **change report**: what changed and why, the
  files, the verification with the real output of the commands, and the open
  points. The agent writes the failing test first and proves that it fails
  without the fix.
- `reviewer` returns the **findings**: severity (`critical`, `major`,
  `minor`), the evidence, why it matters, and the fix. It ends with the
  requirements it verified and the ones it could not, and with the real output
  of the commands it ran. It never edits a file.
- `verifier` returns the **command output**: the command, the directory, the
  real output, and the result. It never changes the code to make a command
  pass.

## The rules that the agents share

1. `AGENTS.md` comes first: the layout, the commands and the conventions of
   the repository. `WEEK1_PLAN.md` holds the requirements of the current
   phase when there is one.
2. The reviewer is independent: it is not the agent that wrote the change, and
   it gets the requirements, the diff and the commands - not the conclusions of
   the implementer.
3. A phase is not done because the tests are green. The tests are the
   evidence that the change does what it claims; the review is the evidence
   that it does not break anything else.
4. Every agent reports what it did not manage to verify. An honest gap is
   useful; a fabricated pass is not.

## The branch and the commit

The agents do not choose a branch: the brief names it, and the commit goes
there. The commit message of this repository starts with the phase it belongs
to (`PLAN:week1:W1-4 - ...`), and says why the change was needed, not only
what it does.

## When the agents are not available

If a subagent cannot be run, the workflow does not pretend that it was: the
blocker is reported, and the change waits. The same goes for the verification
- a phase without a run of the suite and of the build is not finished.
