from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ...core.auth import hash_password
from ...core.db import get_engine


class DuplicateEmail(ValueError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(email: str, password: str) -> dict[str, Any]:
    normalized = normalize_email(email)
    user_id = str(uuid4())
    statement = text(
        """
        INSERT INTO users (user_id, email, password_hash)
        VALUES (:user_id, :email, :password_hash)
        """
    )
    try:
        with get_engine().begin() as connection:
            connection.execute(
                statement,
                {
                    "user_id": user_id,
                    "email": normalized,
                    "password_hash": hash_password(password),
                },
            )
    except IntegrityError as exc:
        raise DuplicateEmail(normalized) from exc
    return {"user_id": user_id, "email": normalized}


def load_user_by_email(email: str) -> dict[str, Any] | None:
    statement = text(
        """
        SELECT user_id, email, password_hash
        FROM users
        WHERE email = :email
        """
    )
    with get_engine().connect() as connection:
        row = connection.execute(statement, {"email": normalize_email(email)}).mappings().first()
    return dict(row) if row is not None else None
