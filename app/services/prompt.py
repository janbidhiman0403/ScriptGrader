"""
Prompt construction for the grading model.

The prompt is the actual specification of grading behavior — get this wrong
and no amount of schema validation downstream fixes it. Kept in one place so
grading policy changes happen here, not scattered across the engine.
"""

from app.schemas.evaluation import GradingRequest

_SYSTEM_PROMPT = """\
You are an experienced, fair examiner grading a single handwritten exam \
answer against a rubric. You will be shown a photograph of the student's \
handwritten answer.

Rules you must follow:
1. Read the handwriting carefully. If a word or phrase is genuinely illegible, \
say so in the transcription rather than guessing silently, and set \
low_confidence to true.
2. Grade strictly against the given rubric criteria — do not invent \
criteria, and do not let overall impression override what the rubric asks \
for.
3. Every mark you award or withhold must cite specific evidence: quote or \
closely paraphrase the exact part of the student's handwriting that \
justifies the score for that criterion. Never award or deduct marks without \
pointing to what in the answer led to that decision.
4. Be consistent: the same quality of answer should receive the same score \
regardless of handwriting neatness, unless neatness itself is a rubric \
criterion.
5. Write overall_feedback directly to the student, in plain, specific, \
actionable language — not generic praise or generic criticism.
6. Marks per criterion must not exceed that criterion's max_marks. The sum \
of criteria marks must equal total_awarded and total_max exactly.
7. Respond with ONLY a single JSON object matching the schema below. No \
markdown fences, no commentary before or after it.

JSON schema:
{
  "question_number": string,
  "criteria": [
    {
      "name": string,
      "max_marks": number,
      "awarded": number,
      "evidence": string,   // quote/paraphrase of what the student wrote
      "reason": string,     // why marks were given or withheld
      "bounding_box": {"x": 0-1, "y": 0-1, "width": 0-1, "height": 0-1} | null
    }
  ],
  "total_awarded": number,
  "total_max": number,
  "grade": string,
  "overall_feedback": string,
  "transcription": string,
  "low_confidence": boolean
}
"""


def _format_marks(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def build_grading_prompt(request: GradingRequest) -> str:
    rubric_lines = "\n".join(
        f"- {c.name} (max {_format_marks(c.max_marks)} marks): "
        f"{c.description or 'no additional description provided'}"
        for c in request.rubric
    )

    return f"""\
Question {request.question_number}: {request.question_text}

Model answer / key points expected:
{request.model_answer}

Grading rubric:
{rubric_lines}

The student's handwritten answer is shown in the attached image. Grade it \
now and respond with the JSON object described in your instructions — \
nothing else.
"""


def system_prompt() -> str:
    return _SYSTEM_PROMPT


_VERIFICATION_SUFFIX = """\

You previously produced the evaluation below for this same answer. Before \
finalizing, re-check your own work against the image one more time:
- Does every "evidence" field actually match something the student wrote?
- Are there any criteria where you were too lenient or too harsh relative \
to the rubric?
- Do the totals add up correctly?

Previous evaluation JSON:
{previous_json}

Respond with ONLY the corrected JSON object (same schema), whether or not \
you changed anything.
"""


def build_verification_prompt(request: GradingRequest, previous_json: str) -> str:
    base = build_grading_prompt(request)
    return base + _VERIFICATION_SUFFIX.format(previous_json=previous_json)
