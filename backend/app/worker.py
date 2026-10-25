"""Run the training queue without the web server.

    python -m backend.app.worker          (from the repository root)
    python -m app.worker                  (inside the docker image)

The web process only has to enqueue when it is started with
``TRAINING_IN_API=0``; one or more of these processes then run the queued
trainings. They need nothing but the database: the queue is the table of the
runs, a run is claimed with one atomic UPDATE, and every worker says that it
is alive while it trains, so the sweeper of any process can tell a dead run
from a live one.
"""

import asyncio
import logging

from . import main


async def run_forever() -> None:
    await main.verify_schema()
    await main.reap_the_interrupted_runs()
    logging.getLogger(__name__).info("Training worker %s started", main.WORKER_ID)
    await main.maintenance_loop()


if __name__ == "__main__":
    asyncio.run(run_forever())
