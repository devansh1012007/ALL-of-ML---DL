import sys
import os
import asyncio
from logging.config import fileConfig
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import pool

from alembic import context

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import Base
from app.database import DATABASE_URL
target_metadata = Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def _resolved_db_url() -> str:
    """The database the migrations run against.

    The URL comes from the ``DATABASE_URL`` environment variable, or - when
    that is not set - from the application's own default, so Alembic and the
    application always talk to the same database. The value in ``alembic.ini``
    is a leftover of the previous "notes" project and must never decide where
    the schema is created.
    """
    return os.getenv("DATABASE_URL") or DATABASE_URL


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = _resolved_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run the migrations against the configured database.

    The URL is never taken from ``alembic.ini``: it comes from the
    ``DATABASE_URL`` environment variable, or - when that is not set - from the
    application's own default, so Alembic and the application always talk to
    the same database. The stale URL in ``alembic.ini`` (a leftover of the
    previous "notes" project) must not decide where the schema is created.
    """

    db_url = _resolved_db_url()
    # "%%" is required because ConfigParser treats a bare "%" as interpolation
    # syntax: a password with a "%" in it would otherwise crash the parser.
    config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

    connectable = create_async_engine(db_url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
