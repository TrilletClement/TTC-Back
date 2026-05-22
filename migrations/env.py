from __future__ import with_statement

from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

import os
import sys

# Ensure app package on path
MIGRATIONS_DIR = os.path.dirname(__file__)
FASTAPI_ROOT = os.path.abspath(os.path.join(MIGRATIONS_DIR, ".."))
REPO_ROOT = os.path.abspath(os.path.join(MIGRATIONS_DIR, "..", ".."))
sys.path.append(FASTAPI_ROOT)
sys.path.append(REPO_ROOT)

from app.orm_models.db import Base, engine  # noqa: E402
from app.orm_models import models  # noqa: F401,E402
from app.core.config import settings  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

target_metadata = Base.metadata

def _get_database_url() -> str:
    return settings.DATABASE_URL


def run_migrations_offline():
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    database_url = _get_database_url()
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
