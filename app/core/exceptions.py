"""
Domain exceptions.

Kept separate from HTTP concerns on purpose: the grading engine doesn't know
it's running behind FastAPI, so it raises these instead of HTTPException. The
API layer (app/api/routes.py) is the single place that translates them into
status codes — that mapping only needs to exist once.
"""


class ScriptGraderError(Exception):
    """Base class for all application errors."""


class InvalidImageError(ScriptGraderError):
    """The uploaded file isn't a readable image, or failed preprocessing."""


class UploadTooLargeError(ScriptGraderError):
    """The uploaded file exceeds the configured size limit."""


class GradingModelError(ScriptGraderError):
    """The grading model call failed after all retries — network error,
    timeout, or the provider returned an error response."""


class InvalidGradingResponseError(ScriptGraderError):
    """The model responded, but its output didn't parse into a valid
    EvaluationResult even after retries (bad JSON, schema violation, or
    marks that don't add up)."""
