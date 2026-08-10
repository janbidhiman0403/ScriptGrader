import os

import pytest

# Must be set before app.core.config.get_settings() is ever called, since
# Settings() reads the environment at construction time and get_settings()
# caches the result via lru_cache for the process lifetime.
os.environ.setdefault("MOCK_GRADING", "true")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("TEACHER_API_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_scriptgrader.db")
# Deliberately permissive so the test suite's own request volume never
# trips the limiter — rate limiting itself is tested separately with an
# explicit low value. Set unconditionally (not setdefault) so a stray
# RATE_LIMIT_GRADE in a developer's local .env can't make this suite flaky.
os.environ["RATE_LIMIT_GRADE"] = "10000/minute"


@pytest.fixture(autouse=True)
def _clean_database():
    """Ensures each test starts with an empty evaluations table, so
    list/count assertions aren't affected by evaluations another test
    created. Runs before every test automatically."""
    from app.core.config import get_settings
    from app.db.database import get_session, init_db
    from app.db.models import EvaluationRecord

    init_db(get_settings())
    session = next(get_session())
    try:
        session.query(EvaluationRecord).delete()
        session.commit()
    finally:
        session.close()
    yield


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-secret"}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def valid_form_fields():
    return {
        "question_number": "1",
        "question_text": "Define osmosis.",
        "model_answer": "Movement of solvent across a semi-permeable membrane.",
        "rubric_json": '[{"name":"Accuracy","max_marks":5},{"name":"Completeness","max_marks":5}]',
    }


@pytest.fixture
def valid_image_bytes():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(buf, format="JPEG")
    return buf.getvalue()
