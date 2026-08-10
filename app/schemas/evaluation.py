"""
Structured output contract for the grading engine.

An LLM asked to "grade this and explain" will happily return inconsistent
free text. Forcing this schema means every mark awarded or deducted is
traceable to a specific piece of evidence, a specific rubric criterion, and
a specific reason — and the numbers are guaranteed to add up, because the
validators reject a response otherwise.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class BoundingBox(BaseModel):
    """Approximate location of evidence on the page, as a fraction of image
    width/height (0.0-1.0). The model's spatial grounding is best-effort, not
    pixel-perfect — the frontend clamps and treats this as an approximate
    highlight region, never a hard crop boundary."""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)


class CriterionResult(BaseModel):
    name: str = Field(min_length=1)
    max_marks: float = Field(gt=0)
    awarded: float = Field(ge=0)
    evidence: str = Field(
        min_length=1,
        description="Direct quote or close paraphrase of what the student wrote "
        "that this score is based on. An unevidenced score is invalid output.",
    )
    reason: str = Field(
        min_length=1,
        description="Why marks were awarded or withheld, phrased so a student "
        "can act on it.",
    )
    bounding_box: BoundingBox | None = None

    @model_validator(mode="after")
    def awarded_within_max(self) -> "CriterionResult":
        if self.awarded > self.max_marks + 1e-6:
            raise ValueError(
                f"criterion '{self.name}': awarded ({self.awarded}) exceeds "
                f"max_marks ({self.max_marks})"
            )
        return self


class EvaluationResult(BaseModel):
    question_number: str
    criteria: list[CriterionResult] = Field(min_length=1)
    total_awarded: float
    total_max: float
    grade: str = Field(min_length=1)
    overall_feedback: str = Field(
        min_length=1,
        description="2-4 sentences: what was strong, what to improve, phrased "
        "directly to the student.",
    )
    transcription: str = Field(
        description="Best-effort transcription of the handwritten answer, kept "
        "so a teacher can sanity-check what the model actually read even "
        "though there's no separate OCR stage."
    )
    low_confidence: bool = Field(
        default=False,
        description="True when handwriting was hard to read and grading "
        "confidence is reduced. Surfaced to the teacher, never silently hidden.",
    )

    @model_validator(mode="after")
    def totals_are_consistent(self) -> "EvaluationResult":
        computed_max = sum(c.max_marks for c in self.criteria)
        computed_awarded = sum(c.awarded for c in self.criteria)

        if abs(computed_max - self.total_max) > 0.01:
            raise ValueError(
                f"total_max ({self.total_max}) doesn't match sum of criteria "
                f"max_marks ({computed_max})"
            )
        if abs(computed_awarded - self.total_awarded) > 0.01:
            raise ValueError(
                f"total_awarded ({self.total_awarded}) doesn't match sum of "
                f"criteria awarded ({computed_awarded})"
            )
        return self

    @property
    def percentage(self) -> float:
        if self.total_max == 0:
            return 0.0
        return round((self.total_awarded / self.total_max) * 100, 1)


class RubricCriterion(BaseModel):
    name: str = Field(min_length=1)
    max_marks: float = Field(gt=0)
    description: str = Field(
        default="", description="What this criterion is looking for, in plain terms."
    )


class GradingRequest(BaseModel):
    """Everything the engine needs, independent of transport (used internally
    once the image bytes have been read off the multipart upload)."""

    question_number: str
    question_text: str = Field(min_length=1)
    model_answer: str = Field(min_length=1)
    rubric: list[RubricCriterion] = Field(min_length=1)

    @field_validator("rubric")
    @classmethod
    def rubric_not_empty(cls, v: list[RubricCriterion]) -> list[RubricCriterion]:
        if not v:
            raise ValueError("rubric must contain at least one criterion")
        return v


class EvaluationRecordOut(BaseModel):
    """An evaluation as returned by the persistence/review endpoints —
    the graded result plus review state, distinct from EvaluationResult
    which is what the grading engine itself produces."""

    id: str
    question_number: str
    question_text: str
    model_answer: str
    criteria: list[CriterionResult]
    criteria_original: list[CriterionResult]
    total_awarded: float
    total_max: float
    grade: str
    overall_feedback: str
    transcription: str
    low_confidence: bool
    reviewed: bool
    review_note: str | None
    batch_id: str | None
    created_at: str
    updated_at: str

    @property
    def percentage(self) -> float:
        if self.total_max == 0:
            return 0.0
        return round((self.total_awarded / self.total_max) * 100, 1)


class BatchGradeItem(BaseModel):
    """One entry in a batch grading response. Exactly one of `result` or
    `error` is set — a batch never fails as a whole because one image was
    bad, it reports that item's failure inline instead."""

    index: int
    filename: str | None = None
    result: EvaluationResult | None = None
    error: str | None = None


class CriterionOverride(BaseModel):
    name: str = Field(min_length=1)
    awarded: float = Field(ge=0)


class OverrideRequest(BaseModel):
    """A teacher's correction to a graded evaluation. Only awarded marks
    are editable — evidence, reasons, and max_marks stay as the model
    produced them, since those describe what happened, not a judgment
    call a teacher is overriding."""

    criteria: list[CriterionOverride] = Field(min_length=1)
    review_note: str | None = Field(
        default=None, description="Optional note explaining the override."
    )
