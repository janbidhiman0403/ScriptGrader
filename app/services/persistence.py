"""
Persistence service.

One rule enforced throughout: totals are always recomputed from the
criteria server-side, never trusted from a client payload. A teacher
overriding one criterion's mark should never be able to (accidentally or
otherwise) submit a total that doesn't match the sum of criteria.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import ScriptGraderError
from app.db.models import EvaluationRecord
from app.schemas.evaluation import (
    CriterionOverride,
    CriterionResult,
    EvaluationRecordOut,
    EvaluationResult,
    GradingRequest,
)


class EvaluationNotFoundError(ScriptGraderError):
    pass


class OverrideValidationError(ScriptGraderError):
    pass


def save_evaluation(
    db: Session,
    request: GradingRequest,
    result: EvaluationResult,
    batch_id: str | None = None,
) -> EvaluationRecord:
    criteria_json = json.dumps([c.model_dump() for c in result.criteria])
    record = EvaluationRecord(
        question_number=request.question_number,
        question_text=request.question_text,
        model_answer=request.model_answer,
        rubric_json=json.dumps([r.model_dump() for r in request.rubric]),
        criteria_json=criteria_json,
        criteria_original_json=criteria_json,
        total_awarded=result.total_awarded,
        total_max=result.total_max,
        grade=result.grade,
        overall_feedback=result.overall_feedback,
        transcription=result.transcription,
        low_confidence=result.low_confidence,
        batch_id=batch_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_evaluation(db: Session, evaluation_id: str) -> EvaluationRecord:
    record = db.get(EvaluationRecord, evaluation_id)
    if record is None:
        raise EvaluationNotFoundError(f"No evaluation with id '{evaluation_id}'.")
    return record


def list_evaluations(
    db: Session, limit: int = 50, offset: int = 0, batch_id: str | None = None
) -> list[EvaluationRecord]:
    query = db.query(EvaluationRecord).order_by(EvaluationRecord.created_at.desc())
    if batch_id:
        query = query.filter(EvaluationRecord.batch_id == batch_id)
    return query.offset(offset).limit(limit).all()


def apply_override(
    db: Session,
    evaluation_id: str,
    overrides: list[CriterionOverride],
    review_note: str | None,
) -> EvaluationRecord:
    record = get_evaluation(db, evaluation_id)
    criteria = [CriterionResult(**c) for c in json.loads(record.criteria_json)]

    override_by_name = {o.name: o.awarded for o in overrides}
    unknown = set(override_by_name) - {c.name for c in criteria}
    if unknown:
        raise OverrideValidationError(
            f"Unknown criteria in override: {', '.join(sorted(unknown))}"
        )

    updated_criteria: list[CriterionResult] = []
    for c in criteria:
        if c.name in override_by_name:
            new_awarded = override_by_name[c.name]
            if new_awarded > c.max_marks + 1e-6:
                raise OverrideValidationError(
                    f"Override for '{c.name}' ({new_awarded}) exceeds "
                    f"max_marks ({c.max_marks})."
                )
            updated_criteria.append(c.model_copy(update={"awarded": new_awarded}))
        else:
            updated_criteria.append(c)

    record.criteria_json = json.dumps([c.model_dump() for c in updated_criteria])
    record.total_awarded = sum(c.awarded for c in updated_criteria)  # recomputed, never trusted from client
    record.reviewed = True
    record.review_note = review_note
    record.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(record)
    return record


def to_out_schema(record: EvaluationRecord) -> EvaluationRecordOut:
    return EvaluationRecordOut(
        id=record.id,
        question_number=record.question_number,
        question_text=record.question_text,
        model_answer=record.model_answer,
        criteria=[CriterionResult(**c) for c in json.loads(record.criteria_json)],
        criteria_original=[CriterionResult(**c) for c in json.loads(record.criteria_original_json)],
        total_awarded=record.total_awarded,
        total_max=record.total_max,
        grade=record.grade,
        overall_feedback=record.overall_feedback,
        transcription=record.transcription,
        low_confidence=record.low_confidence,
        reviewed=record.reviewed,
        review_note=record.review_note,
        batch_id=record.batch_id,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )
