"""Identitas aplikasi capture dan pengelolaan token oleh admin."""

import hashlib
import re
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from server import auth
from server.db import DB, AppToken

PREFIX = "app:"
TOKEN_PREFIX = "eut_"
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
router = APIRouter(prefix="/api/app-tokens")


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def is_app_identity(identity: str) -> bool:
    return identity.startswith(PREFIX)


def create_token(s: Session, name: str, created_by: str) -> str:
    if NAME.fullmatch(name) is None:
        raise ValueError("token name must match ^[a-z0-9][a-z0-9-]{0,39}$")
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    s.add(AppToken(name=name, token_hash=hash_token(raw), created_by=created_by))
    try:
        s.commit()
    except IntegrityError as e:
        s.rollback()
        raise ValueError("token name is already in use") from e
    return raw


def revoke_token(s: Session, name: str) -> bool:
    token = s.exec(select(AppToken).where(AppToken.name == name).with_for_update()).one_or_none()
    if token is None:
        return False
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
    s.commit()
    return True


def _bearer(authorization: str | None) -> str | None:
    parts = (authorization or "").split(maxsplit=1)
    if not parts or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() if len(parts) == 2 else ""


def has_app_bearer(authorization: str | None) -> bool:
    return (_bearer(authorization) or "").startswith(TOKEN_PREFIX)


def identity_from_bearer(s: Session, authorization: str | None) -> str | None:
    raw = _bearer(authorization)
    if raw is None:
        return None
    stmt = select(AppToken).where(AppToken.token_hash == hash_token(raw)).with_for_update()
    token = s.exec(stmt).one_or_none()
    if token is None:
        raise auth.AuthError(401, "invalid app token")
    if token.revoked_at is not None:
        raise auth.AuthError(403, "app token has been revoked")
    identity = PREFIX + token.name
    token.last_used_at = datetime.now(UTC)
    s.commit()
    return identity


def capture_identity(s: Session, headers: Mapping[str, str]) -> str:
    normalized = {key.lower(): value for key, value in headers.items()}
    identity = identity_from_bearer(s, normalized.get("authorization"))
    return (
        identity
        if identity is not None
        else auth.email_from_token(normalized.get(auth.HEADER.lower()))
    )


def capture_user(request: Request, s: DB) -> str:
    try:
        return capture_identity(s, request.headers)
    except auth.AuthError as e:
        raise HTTPException(e.status, e.message) from e


CaptureUser = Annotated[str, Depends(capture_user)]


def _require_admin(user: Annotated[str, Depends(auth.current_user)]) -> str:
    if not auth.is_admin(user):
        raise HTTPException(403, "only admins can manage app tokens")
    return user


Admin = Annotated[str, Depends(_require_admin)]


class TokenInfo(BaseModel):
    name: str
    created_by: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class TokenIn(BaseModel):
    name: str


@router.get("")
def list_tokens(user: Admin, s: DB) -> list[TokenInfo]:
    return [
        TokenInfo.model_validate(row, from_attributes=True)
        for row in s.exec(select(AppToken).order_by(AppToken.name))
    ]


@router.post("", status_code=201)
def new_token(body: TokenIn, user: Admin, s: DB, response: Response) -> dict:
    try:
        raw = create_token(s, body.name, user)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    response.headers["Cache-Control"] = "no-store"
    return {"name": body.name, "token": raw}


@router.delete("/{name}")
def delete_token(name: str, user: Admin, s: DB) -> dict:
    if not revoke_token(s, name):
        raise HTTPException(404, "app token not found")
    return {"name": name, "revoked": True}
