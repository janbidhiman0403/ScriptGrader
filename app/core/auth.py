"""
Authentication.

Single shared-secret API key, checked via constant-time comparison against
the configured TEACHER_API_KEY. This is intentionally the simplest thing
that actually protects the endpoints — appropriate for a small, trusted
deployment (a school's own infrastructure, a small team). It is NOT
per-user auth: everyone with the key has full access, and there's no way
to tell which teacher performed which override.

If you need per-user accounts, audit trails by user, or public multi-tenant
access, replace this with real auth (e.g. OAuth via an identity provider)
before deploying — don't scale this shared-key approach past a small,
trusted group.
"""

import hmac

from fastapi import Header, HTTPException

from app.core.config import get_settings


def require_teacher_auth(x_api_key: str = Header(default="")) -> None:
    settings = get_settings()
    if not hmac.compare_digest(x_api_key, settings.teacher_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")
