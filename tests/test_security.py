import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.security.auth import (
    JWT_ALGORITHM,
    JWT_SECRET,
    get_current_user
)


def test_valid_jwt():
    token = jwt.encode(
        {
            "sub": "user-123",
            "role": "order_writer"
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token
    )

    user = get_current_user(credentials)

    assert user["user_id"] == "user-123"
    assert user["role"] == "order_writer"


def test_invalid_jwt():
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="invalid-token"
    )

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials)

    assert exc.value.status_code == 401