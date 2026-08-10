"""
Database engine and session management.

Uses SQLAlchemy's synchronous API deliberately — grading requests already
block on an external model call, so async DB access buys little here and
costs real complexity. If you outgrow this, swap to SQLAlchemy's async
engine + asyncpg without touching the ORM models.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(settings: Settings):
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        # Needed because SQLite defaults to one connection per thread, but
        # FastAPI's request handling can hop threads under sync routes.
        connect_args = {"check_same_thread": False}
    return create_engine(settings.database_url, connect_args=connect_args)


_engine = None
_SessionLocal: sessionmaker | None = None


def init_db(settings: Settings | None = None) -> None:
    """Create tables if they don't exist. Called once at app startup.

    This is intentionally simple (create_all, no migration history) —
    fine for a small deployment. If the schema needs to evolve on a
    database that already has real data in it, introduce Alembic at
    that point rather than paying its setup cost now.
    """
    global _engine, _SessionLocal
    settings = settings or get_settings()
    _engine = _make_engine(settings)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

    from app.db import models  # noqa: F401 — registers models on Base.metadata

    Base.metadata.create_all(bind=_engine)


def get_session() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
