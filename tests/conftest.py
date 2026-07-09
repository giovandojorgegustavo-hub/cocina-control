"""Pytest configuration and fixtures for cocina-control tests."""

import os
import shutil
from collections.abc import Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Test environment defaults — set BEFORE any cocina_control module is imported.
# The Settings singleton is lazy (created on first get_settings() call), so
# setting env vars here guarantees they are present when the singleton forms.
#
# COCINA_DATABASE_URL is set to a placeholder so that Settings() validates
# without error.  The actual database connection for tests comes from the
# db_engine fixture (which calls build_engine(postgres_url) directly); the
# module-level engine singleton in db.py is never used in tests because
# every test overrides the get_session dependency.
# ---------------------------------------------------------------------------
os.environ.setdefault("COCINA_JWT_SECRET", "test-secret-not-for-prod-min-32-chars-1234")
os.environ.setdefault(
    "COCINA_DATABASE_URL", "postgresql+psycopg://test:test@localhost/test_placeholder"
)

# Speed up bcrypt for tests: 4 rounds instead of 12.
# This is safe because the reduced work factor only applies during the test
# run; production always uses the default (12 rounds from passwords.py).
import cocina_control.security.passwords as _pw_module  # noqa: E402

_pw_module.BCRYPT_ROUNDS = 4

from cocina_control.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# pytest-postgresql: ephemeral process fixture (session-scoped).
#
# Only postgresql_proc is registered at module level.  The DB creation is
# done inside the postgres_url fixture to stay session-scoped.
# ---------------------------------------------------------------------------

# Resolve pg_ctl path: env override → PATH lookup → known fallback.
PG_CTL_PATH = (
    os.getenv("PGCTL_PATH")
    or shutil.which("pg_ctl")
    or "/usr/lib/postgresql/16/bin/pg_ctl"
)

try:
    from pytest_postgresql.factories import postgresql_proc

    postgresql_proc = postgresql_proc(  # type: ignore[assignment]
        executable=PG_CTL_PATH,
        host="127.0.0.1",
        port=None,  # random port — avoids collisions in parallel runs
        user="fiax",
    )

    _PYTEST_PG_AVAILABLE = True

except ImportError:
    _PYTEST_PG_AVAILABLE = False


# ---------------------------------------------------------------------------
# postgres_url: session-scoped URL for the test database.
# ---------------------------------------------------------------------------

_TEST_DBNAME = "cocina_test"


@pytest.fixture(scope="session")
def postgres_url(request) -> str:  # type: ignore[return]
    """Return a PostgreSQL connection URL for the test session.

    Priority:
    1. pytest-postgresql ephemeral process  (preferred — zero config)
    2. TEST_DATABASE_URL env var
    3. COCINA_DATABASE_URL env var
    4. pytest.skip
    """
    if _PYTEST_PG_AVAILABLE:
        import psycopg

        proc = request.getfixturevalue("postgresql_proc")

        # The ephemeral cluster starts with only the default postgres DB.
        # We create our test DB explicitly using autocommit (DDL requires it).
        default_url = f"host={proc.host} port={proc.port} user={proc.user} dbname=postgres"
        with psycopg.connect(default_url, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_catalog.set_config('search_path', '', false)"
            )
            result = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (_TEST_DBNAME,)
            )
            if not result.fetchone():
                conn.execute(f'CREATE DATABASE "{_TEST_DBNAME}"')

        return (
            f"postgresql+psycopg://{proc.user}@{proc.host}:{proc.port}"
            f"/{_TEST_DBNAME}"
        )

    for var in ("TEST_DATABASE_URL", "COCINA_DATABASE_URL"):
        env_url = os.environ.get(var)
        if env_url:
            return env_url

    pytest.skip(
        "No PostgreSQL available: install pytest-postgresql or set TEST_DATABASE_URL"
    )


# ---------------------------------------------------------------------------
# db_engine: session-scoped SQLAlchemy engine + Alembic migration cycle.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def db_engine(postgres_url: str):
    """Create engine, run upgrade head; downgrade base and dispose on teardown."""
    from alembic import command
    from alembic.config import Config

    from cocina_control.db import build_engine

    engine = build_engine(postgres_url)

    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", postgres_url)

    command.upgrade(cfg, "head")

    yield engine

    command.downgrade(cfg, "base")
    engine.dispose()


# ---------------------------------------------------------------------------
# db_session: function-scoped session with SAVEPOINT rollback.
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    """Open a SAVEPOINT; roll back after each test so every test starts clean.

    The session is bound to a single connection that wraps everything in
    a transaction (outer) + savepoint (inner).  The conftest rolls back
    the outer transaction in teardown — it does NOT re-open the savepoint
    automatically.  Tests that need to catch an IntegrityError must wrap
    the failing flush in their own ``with db_session.begin_nested():`` block
    so the inner savepoint absorbs the error and the outer transaction stays
    alive.  Calling ``session.commit()`` directly from a test bypasses the
    outer transaction and breaks isolation.
    """
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    connection = db_engine.connect()
    outer_tx = connection.begin()
    session = factory(bind=connection)
    session.begin_nested()  # SAVEPOINT

    yield session

    session.close()
    if outer_tx.is_active:
        outer_tx.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# client: async HTTP client wired to the test database.
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(db_session: Session) -> AsyncClient:  # type: ignore[return]
    """AsyncClient wired to the test database session."""
    from cocina_control.db import get_session

    def _override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.pop(get_session, None)
