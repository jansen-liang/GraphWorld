from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import new_access_token, verify_password
from backend.app.db.models import AccessToken, User
from backend.app.db.session import get_db
from backend.app.schemas.auth import UserRead


TOKEN_TTL_DAYS = 7


def user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(db: Session, user: User) -> AccessToken:
    token = AccessToken(
        token=new_access_token(),
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> User:
    scheme, _, token_value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token_value:
        raise HTTPException(status_code=401, detail="Missing access token")
    token = db.get(AccessToken, token_value)
    now = datetime.now(timezone.utc)
    if token is None or token.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Invalid access token")
    expires_at = token.expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is not None and expires_at < now:
        raise HTTPException(status_code=401, detail="Access token expired")
    user = token.user
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive user")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def revoke_current_token(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> None:
    _, _, token_value = authorization.partition(" ")
    token = db.get(AccessToken, token_value)
    if token is not None and token.revoked_at is None:
        token.revoked_at = datetime.now(timezone.utc)
        db.commit()
