"""Database connection pool. SQLAlchemy 2.0 + psycopg3."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
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


@contextmanager
def try_advisory_lock(name: str) -> Iterator[bool]:
    """Non-blocking Postgres session-level advisory lock. Yields True if
    acquired, False if another holder exists — caller decides what a
    no-acquire means (e.g. duplicate cron trigger → fast no-op).

    The lock lives on a dedicated connection held open for the duration of
    the with-block; it is released explicitly on exit and implicitly if the
    connection dies (Postgres frees session-level advisory locks on
    disconnect), so a crashed run can never wedge the next one.

    **Why the commit() after acquiring (CS-14, 2026-06-15):** SQLAlchemy
    2.0 future-mode opens an implicit transaction on the first
    `execute()`. Without committing, the lock connection sits
    *idle-in-transaction* for the whole run. Neon's
    `idle_in_transaction_session_timeout` (~5 min) then kills it mid-run;
    an 8-11 min ingest_daily reliably tripped this. The kill silently
    dropped the lock AND made the end-of-run `pg_advisory_unlock` throw,
    propagating out of the context manager → the JOB exited code 1 even
    though all 14 steps had already succeeded (Cloud Run flagged the run
    "Failed" on a benign teardown error). #140 suppressed the unlock
    exception (stops the crash); committing here removes the root cause —
    a plain-idle connection is not reaped, so the lock actually protects
    the full run and the unlock runs on a live connection. SESSION-level
    advisory locks survive a commit (only pg_advisory_unlock / disconnect
    release them), so committing does not drop the lock.
    """
    conn = get_engine().connect()
    acquired = False
    try:
        acquired = bool(conn.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:name))"),
            {"name": name},
        ).scalar())
        # End the implicit transaction → connection goes plain-idle for the
        # run's duration (lock persists). See docstring / CS-14.
        conn.commit()
        yield acquired
    finally:
        try:
            if acquired:
                with contextlib.suppress(Exception):
                    # Defensive belt-and-suspenders (#140): if the
                    # connection died anyway, the server frees the lock on
                    # disconnect — never crash teardown over a failed
                    # unlock; the run already succeeded by the time we're
                    # here.
                    conn.execute(
                        text("SELECT pg_advisory_unlock(hashtext(:name))"),
                        {"name": name},
                    )
                    conn.commit()
        finally:
            conn.close()
