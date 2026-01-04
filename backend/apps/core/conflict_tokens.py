"""JWT helpers for conflict email links.

These tokens are separate from login tokens: they are purpose-scoped and short-lived,
intended for email deep-links (mobile/PC) to view/resolve a specific conflict.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from jose import JWTError, jwt

from apps.core.config import get_settings


def create_conflict_token(
    conflict_id: int,
    purpose: str = "view",
    expires_minutes: Optional[int] = None,
) -> str:
    settings = get_settings()
    exp_minutes = int(expires_minutes or settings.conflict_token_expire_minutes)

    now = datetime.utcnow()
    payload = {
        "scope": "conflict_link",
        "purpose": str(purpose),
        "conflict_id": int(conflict_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_minutes)).timestamp()),
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_conflict_token(token: str) -> Optional[dict[str, Any]]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("scope") != "conflict_link":
            return None
        return payload
    except JWTError:
        return None


def validate_conflict_token(
    token: str,
    *,
    conflict_id: int,
    purpose: Optional[str] = None,
) -> dict[str, Any]:
    payload = decode_conflict_token(token)
    if not payload:
        raise ValueError("invalid token")

    if int(payload.get("conflict_id") or -1) != int(conflict_id):
        raise ValueError("token conflict_id mismatch")

    if purpose is not None and str(payload.get("purpose")) != str(purpose):
        raise ValueError("token purpose mismatch")

    return payload
