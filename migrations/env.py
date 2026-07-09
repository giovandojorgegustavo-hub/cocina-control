import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure the src layout is importable when running alembic from repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import all models so they are registered in Base.metadata before autogenerate.
import cocina_control.models  # noqa: F401, E402
from cocina_control.config import Settings
from cocina_control.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Return the database URL.

    Priority:
    1. sqlalchemy.url set explicitly in the Alembic Config object
       (used by test fixtures via cfg.set_main_option)
    2. COCINA_DATABASE_URL env var via Settings (CLI / production)
    """
    url_in_config = config.get_main_option("sqlalchemy.url")
    if url_in_config and not url_in_config.startswith("driver://"):
        # A real URL was injected (e.g. by a test fixture).
        return url_in_config
    # Fall back to Settings — fails fast with a clear error if the env var is absent.
    s = Settings()
    return s.database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
