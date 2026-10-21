"""Authentication: the signing key, the password hashing and the token.

The signing key is the most important value in this module. The token's "sub"
claim is the only thing that is verified, so anybody who knows the key can
mint a valid token for any existing user - a complete impersonation. The key
therefore never has a published default:

* ``SECRET_KEY`` from the environment always wins;
* in production (``APP_ENV=production``) a missing key is a hard error, so a
  deployment can never start with a guessable key;
* in development a random key is generated once and persisted in
  ``<repo>/.secret_key`` (git-ignored), so restarts and multiple workers agree
  on it. If the file cannot be written, the key is random per process, which
  invalidates the tokens of the previous run on every restart.
"""

from datetime import datetime, timedelta, timezone
from jose import jwt
import bcrypt
import os
import secrets
import warnings
from pathlib import Path
from typing import Optional

from .settings import REPO_ROOT

ALGORITHM = "HS256"

# The file the development key is persisted in. It lives in the repository
# root, next to the application, and is git-ignored. The location can be
# overridden, because in a container the repository root is not necessarily
# the place that survives a restart.
SECRET_KEY_FILE = Path(
    os.getenv("SECRET_KEY_FILE", str(Path(REPO_ROOT) / ".secret_key"))
)

# The environment that turns the missing key into a hard error. An empty
# value counts as "not set": a container that sets APP_ENV="" must not fall
# back to the development key by accident.
_IS_PRODUCTION = any(
    os.getenv(name, "").strip().lower() in {"production", "prod"}
    for name in ("APP_ENV", "ENVIRONMENT")
)

# bcrypt only ever looks at the first 72 bytes of a password and raises
# ValueError for anything longer.
BCRYPT_MAX_BYTES = 72

# The policy for a new account. The length is the part that matters: a short
# password is crackable in seconds, and the cost of a long one is a moment of
# typing.
MIN_PASSWORD_LENGTH = 8
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 64

# The usernames that are reserved. "anonymous" was the shared account of the
# token-less fallback, which is removed: an account with that name would
# otherwise be able to take over the history of every unauthenticated caller.
# The names are refused at the registration *and* at the login, because a row
# with that name may still exist in a database that predates the change.
RESERVED_USERNAMES = frozenset({"anonymous", "admin", "root", "system"})


def is_reserved_username(username: str) -> bool:
    """Whether the name is reserved and must not be used or logged into."""
    return username.strip().lower() in RESERVED_USERNAMES


def _load_secret_key() -> str:
    """Resolve the JWT signing key.

    The environment wins. In production a missing key is a hard error. In
    development a random key is generated once and persisted, so that the
    tokens survive a restart.
    """
    key = os.getenv("SECRET_KEY")
    if key and key.strip():
        return key

    if _IS_PRODUCTION:
        raise RuntimeError(
            "SECRET_KEY must be set when the application runs in production. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )

    try:
        if SECRET_KEY_FILE.exists():
            stored = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
            if stored:
                return stored
        key = secrets.token_urlsafe(48)
        # The file is created with the restrictive mode from the start: a key
        # that is briefly world-readable is a key that is briefly readable by
        # everybody. O_EXCL makes the creation atomic, so two processes that
        # start at the same time cannot write two different keys - the loser
        # of the race reads the winner's key.
        try:
            descriptor = os.open(
                SECRET_KEY_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError:
            # Another process created the file between the check and the
            # creation: use its key.
            return SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(key)
        warnings.warn(
            f"SECRET_KEY is not set: a random development key was written to "
            f"{SECRET_KEY_FILE}. Set SECRET_KEY explicitly in any shared or "
            f"production environment.",
            RuntimeWarning,
            stacklevel=2,
        )
        return key
    except OSError:
        key = secrets.token_urlsafe(48)
        warnings.warn(
            "SECRET_KEY is not set and the development key file could not be "
            "written: a random per-process key is used, so every restart "
            "invalidates the tokens that were issued before.",
            RuntimeWarning,
            stacklevel=2,
        )
        return key


SECRET_KEY = _load_secret_key()


def _bcrypt_secret(password: str) -> bytes:
    """Return the exact bytes that are hashed for a password.

    Registration truncates the password to 72 characters before hashing (see
    main.py) and bcrypt refuses passwords longer than 72 bytes, so the
    characters are truncated first and the result is then capped at the byte
    limit. Hashing and verification must use the same bytes, otherwise a valid
    login would be rejected.
    """
    return password[:72].encode('utf-8')[:BCRYPT_MAX_BYTES]

def hash_pass(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(_bcrypt_secret(password), salt)
    return hashed_bytes.decode('utf-8')

def verify_pass(plain: str, hashed: str) -> bool:
    """Whether the password matches the stored hash.

    A stored value that is not a bcrypt hash (a row that was written by hand,
    or by an older version of the application) must not crash the login: it
    simply does not match.
    """
    try:
        return bcrypt.checkpw(_bcrypt_secret(plain), hashed.encode('utf-8'))
    except (ValueError, TypeError):
        return False


# The hash of a password that nobody knows. It is verified against when the
# login names a user that does not exist, so that the answer takes the same
# time in both cases: otherwise the response time tells an attacker which
# usernames are real.
#
# It is computed on the first use and then kept: hashing costs about a third
# of a second, which is too slow for the import of the module (every test
# run and every restart would pay for it) and too slow to do per request.
_dummy_password_hash: Optional[str] = None


def dummy_password_hash() -> str:
    """A valid bcrypt hash that no password matches."""
    global _dummy_password_hash
    if _dummy_password_hash is None:
        _dummy_password_hash = hash_pass("this-password-is-never-valid")
    return _dummy_password_hash

def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=2)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def validate_credentials(username: str, password: str) -> Optional[str]:
    """Check a new account against the credential policy.

    Returns the reason the account was rejected, or ``None`` when it is
    acceptable. The policy is deliberately small: a name that is not empty and
    not reserved, and a password that is long enough.
    """
    if not username or not username.strip():
        return "The username must not be empty."
    if is_reserved_username(username):
        return f"The username '{username}' is reserved."
    if len(username.strip()) < MIN_USERNAME_LENGTH:
        return f"The username must have at least {MIN_USERNAME_LENGTH} characters."
    if len(username) > MAX_USERNAME_LENGTH:
        return f"The username must not be longer than {MAX_USERNAME_LENGTH} characters."
    if not password:
        return "The password must not be empty."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"The password must have at least {MIN_PASSWORD_LENGTH} characters."
    # bcrypt hashes at most 72 *bytes*, so a password of multi-byte characters
    # is silently truncated at that limit: two different passwords would then
    # be interchangeable. The policy therefore counts bytes, not characters.
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        return (
            f"The password must not be longer than {BCRYPT_MAX_BYTES} bytes "
            f"when encoded as UTF-8."
        )
    return None
