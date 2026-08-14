"""Per-user account registration and login.

Mounted in app/main.py at prefix /api/auth. The very first account ever
registered becomes admin; after that, registration is closed and only an
admin can create further accounts via POST /api/auth/users.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_role
from app.core.security import create_access_token, hash_password, verify_password
from app.db.database import get_session
from app.db.models import User, UserRole
from app.schemas.auth import Token, UserCreate, UserOut

router = APIRouter()


def _to_user_out(user: User) -> UserOut:
    return UserOut(id=str(user.id), username=user.username, role=user.role, is_active=user.is_active)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_session)):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    is_first_user = db.query(User).count() == 0
    if not is_first_user:
        raise HTTPException(
            status_code=403,
            detail="Registration is closed — ask an admin to create your account "
            "via POST /api/auth/users (admin-only).",
        )

    user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        role=(UserRole.admin if is_first_user else UserRole.teacher).value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_user_out(user)


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.admin.value))],
)
def create_user(payload: UserCreate, db: Session = Depends(get_session)):
    """Admin-only: create additional teacher accounts."""
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        role=UserRole.teacher.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_user_out(user)


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_session)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=user.username, role=user.role)
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)):
    return _to_user_out(current_user)
