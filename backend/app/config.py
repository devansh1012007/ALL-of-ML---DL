"""The configuration of the application, validated in one place (plan H4).

About twenty environment variables steer this application and, before this
module, each of them was read where it was used, with ``int(os.getenv(...))``
as the only check. A typo in a value surfaced as a ``ValueError`` from deep
inside a request, or worse, as a silent default.

``Settings.from_env()`` reads every variable once, validates it, and refuses
nonsense with a message that names the variable and the reason. The lifespan
of the application calls it at the startup, so a misconfigured deployment
fails before it serves a request, and prints the effective non-secret
configuration, so an operator can see what the process actually uses.

Two honest boundaries:

* the modules keep reading their own module-level constants (the test suite
  patches those to steer one test at a time); this module is the schema and
  the validator, and the startup refuses what it cannot accept;
* the secrets (``SECRET_KEY``, ``SECRET_KEYS``, the database URL's password)
  are never printed: ``effective_non_secret()`` masks them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ConfigError(Exception):
    """A variable holds a value the application refuses to start with."""


def _int(name: str, default: Optional[int], minimum: Optional[int] = None) -> Optional[int]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} is not an integer.") from None
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name}={value} is below the minimum of {minimum}.")
    return value


def _float(name: str, default: Optional[float], minimum: Optional[float] = None) -> Optional[float]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} is not a number.") from None
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name}={value} is below the minimum of {minimum}.")
    return value


def _one_of(name: str, allowed: set, default: str) -> str:
    raw = (os.getenv(name) or default).strip().lower()
    if raw not in allowed:
        raise ConfigError(
            f"{name}={raw!r} is not one of {sorted(allowed)}."
        )
    return raw


def _csv(name: str) -> List[str]:
    return [entry.strip() for entry in (os.getenv(name) or "").split(",") if entry.strip()]


@dataclass
class Settings:
    """The validated configuration of one process."""

    # The identity of the deployment.
    app_env: str
    registration_mode: str
    cors_origins: List[str]
    trusted_proxies: List[str]

    # The tokens and the sessions.
    access_token_minutes: int
    refresh_token_days: int
    refresh_cookie_enabled: bool
    cookie_secure: bool

    # The rate limiter.
    login_rate_limit: int
    register_rate_limit: int
    upload_rate_limit: int
    rate_limit_window_seconds: float

    # The queue and the workers.
    training_in_api: bool
    training_concurrency: int
    training_heartbeat_seconds: float
    training_stale_seconds: float
    queue_poll_seconds: float

    # The retention of the artifacts.
    janitor_enabled: bool

    # Non-configurable secrets are read elsewhere; they are listed here only
    # so the effective configuration can say whether they were provided.
    secret_key_provided: bool
    secret_keys_count: int
    database_url_provided: bool

    @classmethod
    def from_env(cls) -> "Settings":
        """Read, validate and return the configuration. Raises ConfigError."""
        app_env = _one_of("APP_ENV", {"development", "production"}, os.getenv("ENVIRONMENT", "development"))
        registration_mode = _one_of("REGISTRATION_MODE", {"open", "approval", "invite"}, "open")

        training_concurrency = _int("TRAINING_CONCURRENCY", 1, minimum=1)
        training_heartbeat = _float("TRAINING_HEARTBEAT_SECONDS", 5.0, minimum=0.5)
        training_stale = _float("TRAINING_STALE_SECONDS", 30.0, minimum=1.0)
        if training_stale < 2 * training_heartbeat:
            raise ConfigError(
                f"TRAINING_STALE_SECONDS ({training_stale}) must be at least twice "
                f"TRAINING_HEARTBEAT_SECONDS ({training_heartbeat}): a worker that "
                "misses one beat must not have its run failed."
            )
        queue_poll = _float("QUEUE_POLL_SECONDS", 5.0, minimum=0.0)
        rate_window = _float("RATE_LIMIT_WINDOW_SECONDS", 60.0, minimum=1.0)
        access_minutes = _int("ACCESS_TOKEN_MINUTES", 15, minimum=1)
        refresh_days = _int("REFRESH_TOKEN_DAYS", 7, minimum=1)

        cors_origins = _csv("CORS_ORIGINS") or ["http://localhost:3000", "http://127.0.0.1:3000"]
        training_in_api_raw = (os.getenv("TRAINING_IN_API") or "1").strip()
        if training_in_api_raw not in {"0", "1"}:
            raise ConfigError(
                f"TRAINING_IN_API={training_in_api_raw!r} is not one of ['0', '1']."
            )

        return cls(
            app_env=app_env,
            registration_mode=registration_mode,
            cors_origins=cors_origins,
            trusted_proxies=_csv("TRUSTED_PROXIES"),
            access_token_minutes=access_minutes,
            refresh_token_days=refresh_days,
            refresh_cookie_enabled=(os.getenv("REFRESH_COOKIE_ENABLED", "1") != "0"),
            cookie_secure=(os.getenv("COOKIE_SECURE", "0") == "1"),
            login_rate_limit=_int("LOGIN_RATE_LIMIT", 10, minimum=0),
            register_rate_limit=_int("REGISTER_RATE_LIMIT", 20, minimum=0),
            upload_rate_limit=_int("UPLOAD_RATE_LIMIT", 20, minimum=0),
            rate_limit_window_seconds=rate_window,
            training_in_api=(training_in_api_raw == "1"),
            training_concurrency=training_concurrency,
            training_heartbeat_seconds=training_heartbeat,
            training_stale_seconds=training_stale,
            queue_poll_seconds=queue_poll,
            janitor_enabled=(os.getenv("JANITOR_ENABLED", "1") != "0"),
            secret_key_provided=bool((os.getenv("SECRET_KEY") or "").strip()),
            secret_keys_count=len([k for k in _csv("SECRET_KEYS") if k]),
            database_url_provided=bool((os.getenv("DATABASE_URL") or "").strip()),
        )

    def effective_non_secret(self) -> Dict[str, Any]:
        """The configuration an operator may see: everything but the secrets.

        A variable that names a secret is reported as provided-or-not and
        never as a value. The CORS origins and the proxies are not secrets.
        """
        return {
            "app_env": self.app_env,
            "registration_mode": self.registration_mode,
            "cors_origins": self.cors_origins,
            "trusted_proxies": self.trusted_proxies,
            "access_token_minutes": self.access_token_minutes,
            "refresh_token_days": self.refresh_token_days,
            "refresh_cookie_enabled": self.refresh_cookie_enabled,
            "cookie_secure": self.cookie_secure,
            "login_rate_limit": self.login_rate_limit,
            "register_rate_limit": self.register_rate_limit,
            "upload_rate_limit": self.upload_rate_limit,
            "rate_limit_window_seconds": self.rate_limit_window_seconds,
            "training_in_api": self.training_in_api,
            "training_concurrency": self.training_concurrency,
            "training_heartbeat_seconds": self.training_heartbeat_seconds,
            "training_stale_seconds": self.training_stale_seconds,
            "queue_poll_seconds": self.queue_poll_seconds,
            "janitor_enabled": self.janitor_enabled,
            "secret_key_provided": self.secret_key_provided,
            "secret_keys_count": self.secret_keys_count,
            "database_url_provided": self.database_url_provided,
        }
