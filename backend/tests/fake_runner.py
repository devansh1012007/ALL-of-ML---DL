"""A fake runner for the subprocess executor (plan B2's TRAINING_RUNNER seam).

The behaviour is chosen by ``FAKE_RUNNER_MODE`` in the environment the parent
hands to the child:

* ``ok``    - a small, honest result: metrics, an artifact, a few events;
* ``slow``  - sleeps far beyond any wall clock: the limit must stop it;
* ``hang``  - sleeps until it is killed: the cancel must stop it;
* ``fail``  - raises: the failure must reach the run row.
"""

import json
import os
import time
from pathlib import Path


def execute_run(stored: dict) -> dict:
    mode = os.environ.get("FAKE_RUNNER_MODE", "ok")
    print(json.dumps({"kind": "phase", "payload": {"phase": "fake-training"}}), flush=True)
    print(json.dumps({"kind": "metric", "payload": {"loss": 0.5}}), flush=True)

    if mode == "fail":
        raise RuntimeError("the fake runner failed on purpose")

    if mode == "slow":
        time.sleep(120)
    if mode == "hang":
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            time.sleep(0.2)
            print(json.dumps({"kind": "log", "payload": {"message": "still here"}}), flush=True)

    artifact_dir = Path(os.environ.get("MODEL_DIR", "./models"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    bundle = artifact_dir / f"fake_bundle_{os.urandom(3).hex()}"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "bundle.json").write_text("{}", encoding="utf-8")
    return {
        "status": "completed",
        "metrics": {"score": 0.5, "task_type": "classification"},
        "artifact": {"artifact_path": str(bundle), "artifact_sha256": "fake", "artifact_bytes": 2},
        "charts": None,
        "dataset_source": "local",
        "dataset_tag": "fake",
        "resource": {"wall_seconds": 0.1},
    }
