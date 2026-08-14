"""Application entrypoint. Run with: uvicorn app.main:app --reload"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import router
from app.api.routes_auth import router as auth_router
from app.core.config import get_settings
from app.core.exceptions import (
    GradingModelError,
    InvalidGradingResponseError,
    InvalidImageError,
    ScriptGraderError,
    UploadTooLargeError,
)
from app.core.limiter import limiter
from app.core.logging import configure_logging
from app.db.database import init_db

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(settings)
    logger.info("Database initialized at %s", settings.database_url)
    yield


app = FastAPI(
    title="ScriptGrader",
    description="AI-based handwritten answer sheet evaluation, with "
    "evidence-backed per-criterion feedback.",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["X-API-Key", "Authorization", "Content-Type"],
)

app.include_router(router)
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.mount("/", StaticFiles(directory="static", html=True), name="static")


# --- Centralized error mapping -------------------------------------------
# Every domain exception is mapped to an HTTP response exactly once, here.
# Route handlers raise the domain exception and don't think about status
# codes at all.

_STATUS_BY_EXCEPTION = {
    InvalidImageError: 400,
    UploadTooLargeError: 413,
    InvalidGradingResponseError: 502,
    GradingModelError: 502,
}


@app.exception_handler(ScriptGraderError)
async def handle_script_grader_error(request: Request, exc: ScriptGraderError):
    status_code = 500
    for exc_type, code in _STATUS_BY_EXCEPTION.items():
        if isinstance(exc, exc_type):
            status_code = code
            break

    if status_code >= 500:
        logger.error("Unhandled domain error: %s", exc, exc_info=exc)
    else:
        logger.info("Request rejected: %s", exc)

    return JSONResponse(
        status_code=status_code,
        content={"error": type(exc).__name__, "message": str(exc)},
    )


@app.exception_handler(ValidationError)
async def handle_validation_error(request: Request, exc: ValidationError):
    logger.info("Validation error: %s", exc)
    return JSONResponse(
        status_code=422,
        content={"error": "ValidationError", "message": str(exc)},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    logger.error("Unexpected error: %s", exc, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "Something went wrong on our end. Please try again.",
        },
    )
