"""Pytest configuration and fixtures for cocina-control tests."""

import os
from collections.abc import Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from cocina_control.main import app

# ---------------------------------------------------------------------------
# pytest-postgresql: ephemeral process fixture (session-scoped).
#
# Only postgresql_proc is registered at module level.  The DB creation is
# done inside the postgres_url fixture to stay session-scoped.
# ---------------------------------------------------------------------------

try:
    from pytest_postgresql.factories import postgresql_proc

    postgresql_proc = postgresql_proc(  # type: ignore[assignment]
        executable="/usr/lib/postgresql/16/bin/pg_ctl",
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
    a transaction (outer) + savepoint (inner).  If the test rolls back
    the savepoint (e.g. after an IntegrityError), we re-open a new one
    before yielding back — this keeps the outer transaction alive for the
    final rollback.  If the test rolls back the outer transaction itself
    (which is unusual), cleanup is a no-op.
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
