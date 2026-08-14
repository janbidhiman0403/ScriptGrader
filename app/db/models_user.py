"""
ADD THIS to app/db/models.py (don't create as a separate module — SQLAlchemy
needs it registered on the same Base your existing EvaluationRecord model uses).

Adjust the `from app.db.database import Base` import if your Base lives
somewhere else, and adjust `evaluations = relationship(...)` only if you
want overrides attributed to a user (optional — see routes_auth.py note).
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, TypeDecorator

from app.db.database import Base  # <-- adjust if your Base is imported differently


class GUID(TypeDecorator):
    """Platform-independent UUID: uses Postgres UUID, falls back to CHAR(36) on SQLite."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return uuid.UUID(str(value))


class UserRole(str, enum.Enum):
    admin = "admin"
    teacher = "teacher"


class User(Base):
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    username = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.teacher)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    