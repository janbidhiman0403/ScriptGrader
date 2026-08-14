"""
Authentication.

Two layers, deliberately kept separate:

1. `require_teacher_auth` — a single shared-secret API key, checked via
   constant-time comparison against TEACHER_API_KEY. This protects the
   grading/review endpoints and is unchanged from the original design —
   appropriate for a small, trusted deployment.

2. `get_current_user` / `require_role` — per-user JWT authentication
   (see routes_auth.py for register/login). This exists so individual
   accounts can be created and identified, as a foundation for eventually
   attributing overrides to a specific person. It does not yet replace
   the shared key on the grading endpoints — see the roadmap.
"""

import hmac

from fastapi import Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.database import get_session


def require_teacher_auth(x_api_key: str = Header(default="")) -> None:
    settings = get_settings()
    if not hmac.compare_digest(x_api_key, settings.teacher_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")


# --- Per-user JWT auth -----------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_session),
):
    # Imported here (not at module load) to avoid a circular import with
    # app.db.models, which itself doesn't depend on this module.
    from app.db.models import User

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def require_role(role: str):
    def _check(current_user=Depends(get_current_user)):
        if current_user.role != role:
            raise HTTPException(status_code=403, detail=f"Requires {role} role")
        return current_user

    return _check
