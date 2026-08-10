"""
Centralized application settings.

Loaded once as a singleton (`get_settings()`), validated at startup rather
than failing deep inside a request — a missing API key should surface
immediately when the server boots, not on the first upload a student makes.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = Field(
        default="",
        description="API key for the vision-capable grading model. Not "
        "required when mock_grading is enabled.",
    )
    grading_model: str = Field(default="claude-sonnet-4-6")
    mock_grading: bool = Field(
        default=False,
        description="When true, the grading engine returns a canned "
        "EvaluationResult instead of calling the model. Exists so the "
        "full upload -> preprocess -> respond -> render pipeline can be "
        "exercised in CI or a demo without live API credentials or cost. "
        "Never enable this in production — set MOCK_GRADING=false there.",
    )

    max_upload_mb: int = Field(default=10)
    max_image_dimension: int = Field(
        default=2000,
        description="Longest edge, in pixels, images are downscaled to before "
        "grading. Keeps requests fast and cheap without hurting legibility.",
    )

    grading_temperature: float = Field(default=0.0)
    grading_max_retries: int = Field(
        default=2,
        description="Retries on a schema-invalid or malformed model response, "
        "not on network errors (those are retried separately with backoff).",
    )
    grading_timeout_seconds: int = Field(default=60)

    log_level: str = Field(default="INFO")

    database_url: str = Field(
        default="sqlite:///./scriptgrader.db",
        description="SQLAlchemy connection string. docker-compose points "
        "this at the postgres service; local dev defaults to a SQLite file.",
    )

    teacher_api_key: str = Field(
        default="",
        description="Shared API key required (as an X-API-Key header) to "
        "grade, review, or override evaluations. Single-key auth is "
        "appropriate for a small deployment behind trusted access (a "
        "school's own network, a small team) — swap for per-user auth "
        "(e.g. OAuth via a provider) before opening this to the public "
        "internet with many independent users.",
    )

    allowed_origins_raw: str = Field(
        default="http://localhost:8000",
        alias="ALLOWED_ORIGINS",
        description="Comma-separated origins allowed to call the API "
        "cross-origin. Stored raw and parsed via allowed_origins below — "
        "pydantic-settings JSON-decodes list-typed env vars before "
        "validators run, which breaks plain comma-separated input.",
    )

    rate_limit_grade: str = Field(
        default="10/minute",
        description="Rate limit on /api/grade per client, in slowapi "
        "syntax. Each graded answer costs two model calls (draft + "
        "verify) — this exists to cap runaway cost, not just abuse.",
    )

    def model_post_init(self, __context) -> None:
        if not self.mock_grading and not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required unless MOCK_GRADING=true. "
                "Set it in .env, or set MOCK_GRADING=true to run against "
                "canned responses for local development and testing."
            )
        if not self.teacher_api_key:
            raise ValueError(
                "TEACHER_API_KEY is required — it protects grading and "
                "review endpoints. Set any non-empty secret string in .env."
            )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins_raw.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
