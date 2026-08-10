from app.schemas.evaluation import GradingRequest, RubricCriterion
from app.services.prompt import build_grading_prompt, build_verification_prompt, system_prompt


def _request():
    return GradingRequest(
        question_number="2a",
        question_text="Define osmosis.",
        model_answer="Movement of solvent across a semi-permeable membrane.",
        rubric=[
            RubricCriterion(name="Accuracy", max_marks=5, description="Correct definition"),
            RubricCriterion(name="Completeness", max_marks=3, description=""),
        ],
    )


class TestPromptBuilder:
    def test_prompt_includes_question_text(self):
        prompt = build_grading_prompt(_request())
        assert "Define osmosis." in prompt

    def test_prompt_includes_model_answer(self):
        prompt = build_grading_prompt(_request())
        assert "semi-permeable membrane" in prompt

    def test_prompt_includes_all_rubric_criteria(self):
        prompt = build_grading_prompt(_request())
        assert "Accuracy" in prompt
        assert "Completeness" in prompt
        assert "max 5 marks" in prompt
        assert "max 3 marks" in prompt

    def test_prompt_handles_missing_criterion_description(self):
        prompt = build_grading_prompt(_request())
        assert "no additional description provided" in prompt

    def test_prompt_includes_question_number(self):
        prompt = build_grading_prompt(_request())
        assert "2a" in prompt

    def test_system_prompt_requires_json_only(self):
        sp = system_prompt()
        assert "JSON" in sp
        assert "evidence" in sp

    def test_system_prompt_requires_evidence_per_mark(self):
        sp = system_prompt()
        assert "cite specific evidence" in sp or "evidence" in sp.lower()

    def test_verification_prompt_includes_previous_json(self):
        previous = '{"total_awarded": 5}'
        prompt = build_verification_prompt(_request(), previous_json=previous)
        assert previous in prompt

    def test_verification_prompt_includes_base_prompt_content(self):
        previous = '{"total_awarded": 5}'
        prompt = build_verification_prompt(_request(), previous_json=previous)
        assert "Define osmosis." in prompt
