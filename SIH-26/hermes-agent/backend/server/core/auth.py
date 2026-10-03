"""
Authentication: argon2 key hashing, bearer-token verification, scope enforcement.
No network calls. No sessions. No login flow.
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from server.db import ApiKey, get_db

_ph = PasswordHasher()
_bearer = HTTPBearer(auto_error=True)

Scope = Literal["admin", "user"]
_KEY_PREFIX = "wb_live_"
_KEY_CHARS = string.ascii_letters + string.digits
_KEY_RANDOM_LEN = 32


def generate_key() -> str:
    """Return a new plaintext key. Called once; caller must store the hash."""
    random_part = "".join(secrets.choice(_KEY_CHARS) for _ in range(_KEY_RANDOM_LEN))
    return f"{_KEY_PREFIX}{random_part}"


def hash_key(plaintext: str) -> str:
    return _ph.hash(plaintext)


def verify_key(plaintext: str, stored_hash: str) -> bool:
    try:
        return _ph.verify(stored_hash, plaintext)
    except VerifyMismatchError:
        return False


# ── FastAPI dependency ────────────────────────────────────────────────────────

def _resolve_key(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: Session = Depends(get_db),
) -> ApiKey:
    token = credentials.credentials
    rows: list[ApiKey] = db.query(ApiKey).filter(ApiKey.revoked == False).all()  # noqa: E712
    for row in rows:
        if verify_key(token, row.key_hash):
            row.last_used_at = datetime.utcnow()
            db.commit()
            db.refresh(row)   # reload all attributes while session is open
            db.expunge(row)   # detach cleanly — attributes stay accessible
            return row
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key")


def require_auth(key: ApiKey = Depends(_resolve_key)) -> ApiKey:
    """Any valid (non-revoked) key."""
    return key


def require_admin(key: ApiKey = Depends(_resolve_key)) -> ApiKey:
    if key.scope != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin scope required")
    return key
