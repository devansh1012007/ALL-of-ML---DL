"""The declarative base of the ORM.

``Base`` lives in its own module so that importing the ORM models does not
import the database module: the models register their tables on the metadata
of this base, and nothing else. The Alembic environment imports the models to
compare the database with the metadata, and it must not create an engine for
the application while it does so.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
