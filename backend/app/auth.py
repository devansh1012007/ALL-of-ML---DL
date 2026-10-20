from datetime import datetime, timedelta
from jose import jwt
import bcrypt
import os

# The default is kept byte-identical so tokens issued before the override was
# introduced keep validating; deployments can supply their own SECRET_KEY.
# `or` instead of a plain default so an empty SECRET_KEY environment variable
# cannot silently downgrade the signing key to an empty string (python-jose signs
# and verifies with an empty key without complaining).
SECRET_KEY = os.getenv("SECRET_KEY") or "SUPER_SECRET_KEY_FOR_ASSIGNMENT"
ALGORITHM = "HS256"

# bcrypt only ever looks at the first 72 bytes of a password and raises
# ValueError for anything longer.
BCRYPT_MAX_BYTES = 72

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
    return bcrypt.checkpw(_bcrypt_secret(plain), hashed.encode('utf-8'))

def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=2)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)