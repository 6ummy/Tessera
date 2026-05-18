"""Database connection pool. SQLAlchemy 2.0 + psycopg3."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from tessera_worker.config import get_settings

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _normalize_url(url: str) -> str:
    """Force SQLAlchemy to use psycopg (v3) driver. The URL stored in .env
    uses the plain `postgresql://` scheme so it works with psql + Neon CLI,
    but SQLAlchemy defaults to psycopg2 (v2) which we intentionally don't
    install. The `+psycopg` suffix selects the v3 dialect."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):  # heroku-style
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        s = get_settings()
        _engine = create_engine(
            _normalize_url(s.database_url),
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionFactory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a Session and commit on success, rollback on exception."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
