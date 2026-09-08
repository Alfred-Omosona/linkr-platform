"""ORM models. This is the single source of truth for the schema in v0.1."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# BIGINT is what we want in Postgres; SQLite can't autoincrement a BIGINT
# primary key, so unit tests get a plain INTEGER instead.
_PK = BigInteger().with_variant(Integer, "sqlite")
_COUNTER = BigInteger().with_variant(Integer, "sqlite")


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    hits: Mapped[int] = mapped_column(_COUNTER, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_hit_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Link {self.code} -> {self.target_url[:40]}>"
