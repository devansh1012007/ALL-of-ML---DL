"""The configuration of the application.

The database URL is resolved here and nowhere else, so that the application
and the Alembic migrations cannot drift apart: both read the same value, and
importing this module has no side effect (it creates no engine, opens no
connection).
"""

import os

# The URL of the database. It is read once, at import time, because the engine
# is built from it. ``DATABASE_URL`` always wins; the fallback is the local
# SQLite file, which makes a fresh checkout runnable without any setup.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./backend.db")
