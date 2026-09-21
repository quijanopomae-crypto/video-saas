from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...core.auth import Principal, create_access_token, get_current_principal, verify_password
from .persistence import DuplicateEmail, create_user, load_user_by_email

router = APIRouter(prefix="/auth", tags=["auth"])
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    email: Annotated[str, Field(min_length=3, max_length=320)]
    password: Annotated[str, Field(min_length=12, max_length=256)]

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL.fullmatch(normalized):
            raise ValueError("invalid email")
        return normalized


class UserResponse(BaseModel):
    user_id: str
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> UserResponse:
    try:
        user = create_user(payload.email, payload.password)
    except DuplicateEmail as exc:
        raise HTTPException(status_code=409, detail="email already registered") from exc
    return UserResponse(**user)


@router.post("/token", response_model=TokenResponse)
def token(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    user = load_user_by_email(form.username)
    if user is None or not verify_password(form.password, str(user["password_hash"])):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(user_id=str(user["user_id"]), email=str(user["email"]))
    )


@router.get("/me", response_model=UserResponse)
def me(principal: Principal = Depends(get_current_principal)) -> UserResponse:
    return UserResponse(user_id=principal.user_id, email=principal.email)
