"""
API routes.

Grading endpoints (single + batch) call the model and persist a result.
Evaluation endpoints (list/get/override) manage what's already been graded.
All of it sits behind require_teacher_auth except health — see
app/core/auth.py for what that does and doesn't protect against.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import require_teacher_auth
from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidImageError, UploadTooLargeError
from app.core.limiter import limiter
from app.db.database import get_session
from app.schemas.evaluation import (
    BatchGradeItem,
    EvaluationRecordOut,
    EvaluationResult,
    GradingRequest,
    OverrideRequest,
    RubricCriterion,
)
from app.services.engine import GradingEngine
from app.services.persistence import (
    EvaluationNotFoundError,
    OverrideValidationError,
    apply_override,
    get_evaluation,
    list_evaluations,
    save_evaluation,
    to_out_schema,
)
from app.services.preprocess import preprocess_image

logger = logging.getLogger(__name__)
router = APIRouter()


def get_engine(settings: Settings = Depends(get_settings)) -> GradingEngine:
    return GradingEngine(settings)


def _parse_rubric(rubric_json: str) -> list[RubricCriterion]:
    try:
        rubric_data = json.loads(rubric_json)
    except json.JSONDecodeError as exc:
        raise InvalidImageError(f"rubric_json is not valid JSON: {exc}") from exc
    return [RubricCriterion.model_validate(item) for item in rubric_data]


def _validate_and_preprocess(raw_bytes: bytes, settings: Settings) -> bytes:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise UploadTooLargeError(
            f"Image is {len(raw_bytes) / 1_048_576:.1f} MB, "
            f"limit is {settings.max_upload_mb} MB."
        )
    if not raw_bytes:
        raise InvalidImageError("Uploaded file is empty.")
    return preprocess_image(raw_bytes, settings.max_image_dimension)


@router.post(
    "/api/grade",
    response_model=EvaluationResult,
    dependencies=[Depends(require_teacher_auth)],
)
@limiter.limit(lambda: get_settings().rate_limit_grade)
async def grade_answer(
    request: Request,  # required by slowapi to key the rate limit
    sheet_image: UploadFile = File(
        ..., description="Photo or scan of the handwritten answer."
    ),
    question_number: str = Form(...),
    question_text: str = Form(...),
    model_answer: str = Form(...),
    rubric_json: str = Form(
        ...,
        description='JSON array: [{"name": str, "max_marks": number, '
        '"description": str}, ...]',
    ),
    settings: Settings = Depends(get_settings),
    engine: GradingEngine = Depends(get_engine),
    db: Session = Depends(get_session),
) -> EvaluationResult:
    raw_bytes = await sheet_image.read()
    processed_bytes = _validate_and_preprocess(raw_bytes, settings)

    grading_request = GradingRequest(
        question_number=question_number,
        question_text=question_text,
        model_answer=model_answer,
        rubric=_parse_rubric(rubric_json),
    )

    logger.info("Grading question %s (%d bytes)", question_number, len(processed_bytes))
    result = engine.grade(grading_request, processed_bytes)
    logger.info(
        "Graded question %s: %s/%s (%s%%)",
        question_number, result.total_awarded, result.total_max, result.percentage,
    )

    save_evaluation(db, grading_request, result)
    return result


@router.post(
    "/api/grade/batch",
    response_model=list[BatchGradeItem],
    dependencies=[Depends(require_teacher_auth)],
)
@limiter.limit(lambda: get_settings().rate_limit_grade)
async def grade_batch(
    request: Request,
    sheet_images: list[UploadFile] = File(
        ..., description="Multiple scanned answers, same question and rubric."
    ),
    question_number: str = Form(...),
    question_text: str = Form(...),
    model_answer: str = Form(...),
    rubric_json: str = Form(...),
    settings: Settings = Depends(get_settings),
    engine: GradingEngine = Depends(get_engine),
    db: Session = Depends(get_session),
) -> list[BatchGradeItem]:
    """Grades multiple answer sheets against the same question/rubric in
    one call. Each sheet is graded independently — one bad image doesn't
    fail the whole batch, it's reported inline (error field) so a teacher
    grading 30 scripts doesn't lose the other 29 to one bad scan."""
    rubric = _parse_rubric(rubric_json)
    batch_id = str(uuid.uuid4())
    results: list[BatchGradeItem] = []

    for idx, sheet_image in enumerate(sheet_images):
        raw_bytes = await sheet_image.read()
        try:
            processed_bytes = _validate_and_preprocess(raw_bytes, settings)
            grading_request = GradingRequest(
                question_number=question_number,
                question_text=question_text,
                model_answer=model_answer,
                rubric=rubric,
            )
            result = engine.grade(grading_request, processed_bytes)
            save_evaluation(db, grading_request, result, batch_id=batch_id)
            results.append(BatchGradeItem(index=idx, filename=sheet_image.filename, result=result))
        except Exception as exc:  # noqa: BLE001 — one failure must not abort the batch
            logger.warning("Batch item %d (%s) failed: %s", idx, sheet_image.filename, exc)
            results.append(BatchGradeItem(index=idx, filename=sheet_image.filename, error=str(exc)))

    return results


@router.get(
    "/api/evaluations",
    response_model=list[EvaluationRecordOut],
    dependencies=[Depends(require_teacher_auth)],
)
async def get_evaluations(
    limit: int = 50,
    offset: int = 0,
    batch_id: str | None = None,
    db: Session = Depends(get_session),
) -> list[EvaluationRecordOut]:
    records = list_evaluations(db, limit=limit, offset=offset, batch_id=batch_id)
    return [to_out_schema(r) for r in records]


@router.get(
    "/api/evaluations/{evaluation_id}",
    response_model=EvaluationRecordOut,
    dependencies=[Depends(require_teacher_auth)],
)
async def get_evaluation_by_id(
    evaluation_id: str, db: Session = Depends(get_session)
) -> EvaluationRecordOut:
    try:
        record = get_evaluation(db, evaluation_id)
    except EvaluationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return to_out_schema(record)


@router.patch(
    "/api/evaluations/{evaluation_id}",
    response_model=EvaluationRecordOut,
    dependencies=[Depends(require_teacher_auth)],
)
async def override_evaluation(
    evaluation_id: str, body: OverrideRequest, db: Session = Depends(get_session)
) -> EvaluationRecordOut:
    """A teacher's correction. Totals are always recomputed server-side
    from the (possibly-overridden) criteria — never trusted from the
    request body — so a stored record can never have an internally
    inconsistent total."""
    try:
        record = apply_override(db, evaluation_id, body.criteria, body.review_note)
    except EvaluationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OverrideValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return to_out_schema(record)


@router.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
