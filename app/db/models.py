"""ORM models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    admin = "admin"
    teacher = "teacher"


class User(Base):
    """A per-user login account. Distinct from the shared TEACHER_API_KEY —
    this table exists so evaluations can eventually be attributed to the
    specific person who graded or overrode them, rather than just "someone
    with the key." The first account ever registered becomes admin; every
    account after that must be created by an admin (see routes_auth.py)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default=UserRole.teacher.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EvaluationRecord(Base):
    """A single graded answer, as originally returned by the model plus
    whatever a teacher has since overridden. The original AI output is
    preserved (criteria_original) even after an override, so there's
    always an audit trail of what the model said versus what a human
    changed and why."""

    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    question_number: Mapped[str] = mapped_column(String(64))
    question_text: Mapped[str] = mapped_column(Text)
    model_answer: Mapped[str] = mapped_column(Text)
    rubric_json: Mapped[str] = mapped_column(Text)

    criteria_json: Mapped[str] = mapped_column(Text)  # current (possibly overridden)
    criteria_original_json: Mapped[str] = mapped_column(Text)  # as first graded

    total_awarded: Mapped[float] = mapped_column(Float)
    total_max: Mapped[float] = mapped_column(Float)
    grade: Mapped[str] = mapped_column(String(16))
    overall_feedback: Mapped[str] = mapped_column(Text)
    transcription: Mapped[str] = mapped_column(Text)
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)

    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
