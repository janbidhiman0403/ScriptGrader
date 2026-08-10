import pytest
from pydantic import ValidationError

from app.schemas.evaluation import CriterionResult, EvaluationResult, GradingRequest, RubricCriterion


def _criterion(**overrides):
    defaults = dict(name="Accuracy", max_marks=5, awarded=3, evidence="wrote X", reason="partially correct")
    defaults.update(overrides)
    return CriterionResult(**defaults)


def _evaluation(**overrides):
    defaults = dict(
        question_number="1",
        criteria=[_criterion()],
        total_awarded=3,
        total_max=5,
        grade="C",
        overall_feedback="Decent attempt.",
        transcription="student wrote X",
    )
    defaults.update(overrides)
    return EvaluationResult(**defaults)


class TestCriterionResult:
    def test_valid_criterion(self):
        c = _criterion()
        assert c.awarded == 3

    def test_awarded_cannot_exceed_max(self):
        with pytest.raises(ValidationError, match="exceeds"):
            _criterion(awarded=10, max_marks=5)

    def test_awarded_can_equal_max(self):
        c = _criterion(awarded=5, max_marks=5)
        assert c.awarded == c.max_marks

    def test_evidence_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            _criterion(evidence="")

    def test_reason_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            _criterion(reason="")

    def test_negative_awarded_rejected(self):
        with pytest.raises(ValidationError):
            _criterion(awarded=-1)

    def test_zero_max_marks_rejected(self):
        with pytest.raises(ValidationError):
            _criterion(max_marks=0)

    def test_bounding_box_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            _criterion(bounding_box={"x": 1.5, "y": 0, "width": 0.1, "height": 0.1})

    def test_bounding_box_is_optional(self):
        c = _criterion(bounding_box=None)
        assert c.bounding_box is None


class TestEvaluationResult:
    def test_valid_evaluation(self):
        e = _evaluation()
        assert e.percentage == 60.0

    def test_total_awarded_must_match_sum_of_criteria(self):
        with pytest.raises(ValidationError, match="total_awarded"):
            _evaluation(criteria=[_criterion(awarded=3, max_marks=5)], total_awarded=99, total_max=5)

    def test_total_max_must_match_sum_of_criteria(self):
        with pytest.raises(ValidationError, match="total_max"):
            _evaluation(criteria=[_criterion(awarded=3, max_marks=5)], total_awarded=3, total_max=99)

    def test_multi_criteria_totals_sum_correctly(self):
        e = _evaluation(
            criteria=[
                _criterion(name="A", awarded=2, max_marks=5),
                _criterion(name="B", awarded=4, max_marks=5),
            ],
            total_awarded=6,
            total_max=10,
        )
        assert e.percentage == 60.0

    def test_percentage_handles_zero_total_max(self):
        # Guards against a ZeroDivisionError if a rubric is ever malformed
        # to have zero total marks.
        e = EvaluationResult.model_construct(
            question_number="1",
            criteria=[],
            total_awarded=0,
            total_max=0,
            grade="N/A",
            overall_feedback="",
            transcription="",
            low_confidence=False,
        )
        assert e.percentage == 0.0

    def test_criteria_list_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            _evaluation(criteria=[])

    def test_low_confidence_defaults_false(self):
        e = _evaluation()
        assert e.low_confidence is False


class TestGradingRequest:
    def test_valid_request(self):
        req = GradingRequest(
            question_number="1",
            question_text="What is osmosis?",
            model_answer="Movement of solvent across a membrane.",
            rubric=[RubricCriterion(name="Accuracy", max_marks=5)],
        )
        assert len(req.rubric) == 1

    def test_rubric_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            GradingRequest(
                question_number="1",
                question_text="Q",
                model_answer="A",
                rubric=[],
            )

    def test_question_text_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            GradingRequest(
                question_number="1",
                question_text="",
                model_answer="A",
                rubric=[RubricCriterion(name="X", max_marks=5)],
            )
