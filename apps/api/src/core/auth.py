from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from .config import get_settings

PASSWORD_HASH = PasswordHash.recommended()
OAUTH2_SCHEME = OAuth2PasswordBearer(tokenUrl="/auth/token")
JWT_ALGORITHM = "HS256"


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str


def _secret() -> str:
    secret = get_settings().auth_jwt_secret
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication is not configured",
        )
    return secret


def hash_password(password: str) -> str:
    return PASSWORD_HASH.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return PASSWORD_HASH.verify(password, password_hash)


def create_access_token(*, user_id: str, email: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.auth_access_token_minutes),
        "iss": settings.auth_jwt_issuer,
        "aud": settings.auth_jwt_audience,
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def get_current_principal(token: str = Depends(OAUTH2_SCHEME)) -> Principal:
    settings = get_settings()
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[JWT_ALGORITHM],
            audience=settings.auth_jwt_audience,
            issuer=settings.auth_jwt_issuer,
            options={"require": ["sub", "email", "iat", "exp"]},
        )
    except (InvalidTokenError, HTTPException):
        raise credentials_error
    user_id = payload.get("sub")
    email = payload.get("email")
    if not isinstance(user_id, str) or not user_id or not isinstance(email, str) or not email:
        raise credentials_error
    return Principal(user_id=user_id, email=email)
