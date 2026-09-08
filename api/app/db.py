"""Database engine + session wiring.

Creating the Engine does not open a connection — the first request does. That is
deliberate: the container must start even if Postgres is not up yet, and report
its state through /ready instead of crash-looping.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # survives Postgres restarts / idle connection reaping
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency — one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
