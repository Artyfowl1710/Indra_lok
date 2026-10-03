"""
Admin key management endpoints.
POST /v1/admin/keys
GET  /v1/admin/keys
DELETE /v1/admin/keys/{key_id}
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.core.auth import generate_key, hash_key, require_admin
from server.core.schemas import KeyCreateRequest, KeyCreateResponse, KeyListItem
from server.db import ApiKey, get_db

import secrets

router = APIRouter(prefix="/v1/admin/keys", tags=["admin-keys"])


@router.post("", response_model=KeyCreateResponse)
def create_key(
    req: KeyCreateRequest,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    plaintext = generate_key()
    key_id = secrets.token_hex(8)
    row = ApiKey(
        key_id=key_id,
        key_hash=hash_key(plaintext),
        owner=req.owner,
        scope=req.scope,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return KeyCreateResponse(api_key=plaintext)


@router.get("", response_model=list[KeyListItem])
def list_keys(
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    rows = db.query(ApiKey).all()
    return [
        KeyListItem(
            id=r.key_id,
            owner=r.owner,
            scope=r.scope,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            revoked=r.revoked,
        )
        for r in rows
    ]


@router.delete("/{key_id}", status_code=204)
def revoke_key(
    key_id: str,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    row = db.query(ApiKey).filter(ApiKey.key_id == key_id).first()
    if row is None:
        raise HTTPException(404, "Key not found")
    row.revoked = True
    db.commit()
