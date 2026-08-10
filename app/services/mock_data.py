"""
Canned grading response for MOCK_GRADING mode.

This exists so the entire pipeline — upload, preprocessing, the API
contract, and the frontend's rendering of that contract — can be exercised
without live API credentials or the cost/latency/non-determinism of a real
model call. It is not a substitute for testing against the real model
before shipping a grading-quality change; it's a substitute for "does the
plumbing work."
"""

from app.schemas.evaluation import CriterionResult, EvaluationResult

MOCK_EVALUATION = EvaluationResult(
    question_number="1",
    criteria=[
        CriterionResult(
            name="Concept accuracy",
            max_marks=5,
            awarded=4,
            evidence="wrote 'osmosis moves water through a membrane from "
            "weak to strong solution'",
            reason="Correct direction and mechanism, but 'weak/strong "
            "solution' is imprecise phrasing for solute concentration — "
            "minor deduction for terminology.",
            bounding_box={"x": 0.12, "y": 0.18, "width": 0.55, "height": 0.09},
        ),
        CriterionResult(
            name="Completeness",
            max_marks=5,
            awarded=3,
            evidence="did not mention equilibrium or the semi-permeable "
            "nature of the membrane",
            reason="Two of the three expected key points are missing: the "
            "membrane's selectivity and the equilibrium endpoint.",
            bounding_box={"x": 0.12, "y": 0.30, "width": 0.60, "height": 0.07},
        ),
    ],
    total_awarded=7,
    total_max=10,
    grade="B",
    overall_feedback="Good grasp of the basic direction of osmosis. To "
    "reach full marks, mention that the membrane is semi-permeable and "
    "state that movement continues until equilibrium is reached on both "
    "sides.",
    transcription="Osmosis moves water through a membrane from weak to "
    "strong solution until it evens out.",
    low_confidence=False,
)
