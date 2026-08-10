"""
Grading engine.

Two passes, both against the same image:
  1. Draft — model transcribes + scores against the rubric.
  2. Verify — model is shown its own draft and asked to check it against the
     image again before finalizing.

The second pass exists because a single-pass vision-LLM read of messy
handwriting is exactly the kind of task where a model can misread a word,
score confidently against the misreading, and never notice. Asking it to
re-check its own output against the source catches a meaningful share of
these without doubling latency-sensitive user-facing work (verification is
short — it's reviewing, not re-deriving).

Retries only cover "model responded but the JSON didn't parse or didn't
satisfy the schema" — a different failure mode from network/timeout errors,
which the Anthropic SDK's own retry handling covers.
"""

from __future__ import annotations

import json
import logging

import anthropic
from anthropic import APIError, APIStatusError, APITimeoutError

from app.core.config import Settings
from app.core.exceptions import GradingModelError, InvalidGradingResponseError
from app.schemas.evaluation import EvaluationResult, GradingRequest
from app.services.prompt import build_grading_prompt, build_verification_prompt, system_prompt

logger = logging.getLogger(__name__)


class GradingEngine:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = (
            None
            if settings.mock_grading
            else anthropic.Anthropic(
                api_key=settings.anthropic_api_key,
                timeout=settings.grading_timeout_seconds,
            )
        )

    def grade(self, request: GradingRequest, image_bytes: bytes) -> EvaluationResult:
        if self._settings.mock_grading:
            return self._mock_grade(request)

        image_block = _image_block(image_bytes)

        draft = self._run_pass(
            prompt=build_grading_prompt(request),
            image_block=image_block,
        )
        logger.info(
            "Draft grade for Q%s: %s/%s",
            request.question_number,
            draft.total_awarded,
            draft.total_max,
        )

        verified = self._run_pass(
            prompt=build_verification_prompt(
                request, previous_json=draft.model_dump_json()
            ),
            image_block=image_block,
        )
        if verified.total_awarded != draft.total_awarded:
            logger.info(
                "Verification pass changed score for Q%s: %s -> %s",
                request.question_number,
                draft.total_awarded,
                verified.total_awarded,
            )
        return verified

    def _mock_grade(self, request: GradingRequest) -> EvaluationResult:
        """Returns a canned response shaped from the real request (question
        number carried through) so callers can tell mock output apart from
        a stale fixture, while everything else in the pipeline — schema
        validation, JSON serialization, the HTTP response — runs for real."""
        from app.services.mock_data import MOCK_EVALUATION

        logger.info("MOCK_GRADING enabled — returning canned evaluation, no model call made")
        data = MOCK_EVALUATION.model_dump()
        data["question_number"] = request.question_number
        return EvaluationResult.model_validate(data)

    def _run_pass(self, prompt: str, image_block: dict) -> EvaluationResult:
        last_error: Exception | None = None

        for attempt in range(1, self._settings.grading_max_retries + 2):
            raw_text = self._call_model(prompt, image_block)
            try:
                return _parse_response(raw_text)
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "Grading response failed validation (attempt %d/%d): %s",
                    attempt,
                    self._settings.grading_max_retries + 1,
                    exc,
                )

        raise InvalidGradingResponseError(
            f"Model did not return a valid evaluation after "
            f"{self._settings.grading_max_retries + 1} attempts: {last_error}"
        )

    def _call_model(self, prompt: str, image_block: dict) -> str:
        try:
            response = self._client.messages.create(
                model=self._settings.grading_model,
                max_tokens=2048,
                temperature=self._settings.grading_temperature,
                system=system_prompt(),
                messages=[
                    {
                        "role": "user",
                        "content": [image_block, {"type": "text", "text": prompt}],
                    }
                ],
            )
        except APITimeoutError as exc:
            raise GradingModelError("Grading request timed out.") from exc
        except APIStatusError as exc:
            raise GradingModelError(
                f"Grading provider returned an error (status {exc.status_code})."
            ) from exc
        except APIError as exc:
            raise GradingModelError(f"Grading request failed: {exc}") from exc

        return "".join(
            block.text for block in response.content if block.type == "text"
        )


def _image_block(image_bytes: bytes) -> dict:
    import base64

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.b64encode(image_bytes).decode("utf-8"),
        },
    }


def _parse_response(raw_text: str) -> EvaluationResult:
    cleaned = raw_text.strip()
    # Models occasionally wrap JSON in markdown fences despite instructions
    # not to — strip defensively rather than fail the whole request on it.
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    data = json.loads(cleaned)  # json.JSONDecodeError bubbles to caller
    return EvaluationResult.model_validate(data)  # ValueError bubbles to caller
