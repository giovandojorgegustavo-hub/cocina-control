from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def build_session_factory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


# Module-level engine and factory are created lazily so that importing
# this module does not fail when COCINA_DATABASE_URL is not set (e.g.
# during unit tests that use a fixture-provided URL).
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        from cocina_control.config import get_settings

        _engine = build_engine(get_settings().database_url)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = build_session_factory(get_engine())
    return _SessionLocal


def get_session() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
