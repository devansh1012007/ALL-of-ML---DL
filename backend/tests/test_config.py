"""The validated configuration (plan H4).

The variables used to be read where they were used, with ``int(os.getenv)``
as the only check. The tests pin the validation: a nonsense value refuses
the start with a message that names the variable, the relations between the
values hold (a stale limit that is shorter than a heartbeat is nonsense),
and the effective configuration that the startup prints never contains a
secret.
"""

import json
import os
import subprocess
import sys

import pytest

from backend.app.config import ConfigError, Settings


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")


def test_a_valid_environment_loads_and_masks_the_secrets(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a-very-secret-value")
    monkeypatch.setenv("SECRET_KEYS", "key-one,key-two")
    monkeypatch.setenv("TRAINING_CONCURRENCY", "2")
    settings = Settings.from_env()

    assert settings.training_concurrency == 2
    assert settings.secret_keys_count == 2
    printed = json.dumps(settings.effective_non_secret())
    assert "a-very-secret-value" not in printed
    assert "key-one" not in printed
    assert settings.secret_key_provided is True


@pytest.mark.parametrize(
    "variable, value",
    [
        ("TRAINING_CONCURRENCY", "0"),
        ("TRAINING_CONCURRENCY", "many"),
        ("TRAINING_HEARTBEAT_SECONDS", "often"),
        ("ACCESS_TOKEN_MINUTES", "-5"),
        ("RATE_LIMIT_WINDOW_SECONDS", "0"),
        ("REGISTRATION_MODE", "whenever"),
        ("TRAINING_IN_API", "maybe"),
    ],
)
def test_nonsense_values_are_refused(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(ConfigError) as refused:
        Settings.from_env()
    assert variable in str(refused.value)


def test_a_stale_limit_shorter_than_two_heartbeats_is_refused(monkeypatch):
    """A worker that misses one beat must not have its run failed."""
    monkeypatch.setenv("TRAINING_HEARTBEAT_SECONDS", "5")
    monkeypatch.setenv("TRAINING_STALE_SECONDS", "6")
    with pytest.raises(ConfigError) as refused:
        Settings.from_env()
    assert "TRAINING_STALE_SECONDS" in str(refused.value)


def test_a_misconfigured_process_refuses_to_start():
    """The lifespan turns a ConfigError into a refusal with the reason."""
    env = dict(os.environ, PYTHONPATH=REPO_ROOT)
    env["TRAINING_CONCURRENCY"] = "0"
    env["DATABASE_URL"] = "sqlite+aiosqlite:///./config-check.db"
    env["SECRET_KEY"] = "check-key"
    result = subprocess.run(
        [sys.executable, "-c", "import backend.app.main"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    # The import itself must succeed (the validation runs in the lifespan);
    # a client that starts the app is the one that sees the refusal.
    assert result.returncode == 0, result.stderr

    program = (
        "import asyncio\n"
        "from fastapi import FastAPI\n"
        "from backend.app.main import lifespan\n"
        "\n"
        "async def main():\n"
        "    app = FastAPI()\n"
        "    try:\n"
        "        async with lifespan(app):\n"
        "            pass\n"
        "    except RuntimeError as refused:\n"
        "        print('REFUSED:', refused)\n"
        "        return\n"
        "    print('STARTED')\n"
        "\n"
        "asyncio.run(main())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "REFUSED" in result.stdout
    assert "TRAINING_CONCURRENCY" in result.stdout
