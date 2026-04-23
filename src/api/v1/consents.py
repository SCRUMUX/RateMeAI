"""Consent management endpoints (POST/GET/REVOKE)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_auth_user, get_db, get_redis
from src.models.db import User
from src.services.consent import (
    CURRENT_CONSENT_VERSION,
    REQUIRED_CONSENT_KINDS,
    ActiveConsent,
    get_active_consents,
    grant_consent,
    hash_marker,
    revoke_consent,
)

logger = logging.getLogger(__name__)

router = APIRouter()


_ALLOWED_KINDS = set(REQUIRED_CONSENT_KINDS)


class ConsentGrantRequest(BaseModel):
    kinds: list[str] = Field(..., min_length=1)
    version: str = Field(default=CURRENT_CONSENT_VERSION, max_length=16)
    source: str = Field(default="web", max_length=32)

    @field_validator("kinds")
    @classmethod
    def _validate_kinds(cls, v: list[str]) -> list[str]:
        clean = [k.strip() for k in v if k and k.strip()]
        unknown = [k for k in clean if k not in _ALLOWED_KINDS]
        if unknown:
            raise ValueError(f"unknown consent kinds: {unknown}")
        return sorted(set(clean))


class ConsentRevokeRequest(BaseModel):
    kinds: list[str] = Field(..., min_length=1)

    @field_validator("kinds")
    @classmethod
    def _validate_kinds(cls, v: list[str]) -> list[str]:
        clean = [k.strip() for k in v if k and k.strip()]
        unknown = [k for k in clean if k not in _ALLOWED_KINDS]
        if unknown:
            raise ValueError(f"unknown consent kinds: {unknown}")
        return sorted(set(clean))


def _serialize(active: dict[str, ActiveConsent]) -> dict[str, Any]:
    return {
        "required": list(REQUIRED_CONSENT_KINDS),
        "granted": {
            kind: {
                "version": item.version,
                "granted_at": item.granted_at.isoformat(),
                "source": item.source,
            }
            for kind, item in active.items()
        },
        "missing": [k for k in REQUIRED_CONSENT_KINDS if k not in active],
        "current_version": CURRENT_CONSENT_VERSION,
    }


@router.get("/users/me/consents")
async def get_my_consents(
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    active = await get_active_consents(db, redis, user.id)
    return _serialize(active)


@router.post("/users/me/consents")
async def grant_my_consents(
    payload: ConsentGrantRequest,
    request: Request,
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    client_ip = request.client.host if request.client else None
    active = await grant_consent(
        db,
        redis,
        user.id,
        payload.kinds,
        version=payload.version,
        source=payload.source,
        ip_hash=hash_marker(client_ip),
        user_agent_hash=hash_marker(request.headers.get("user-agent")),
    )
    logger.info(
        "consent.granted",
        extra={
            "user_id": str(user.id),
            "kinds": payload.kinds,
            "source": payload.source,
        },
    )
    return _serialize(active)


@router.post("/users/me/consents/revoke")
async def revoke_my_consents(
    payload: ConsentRevokeRequest,
    user: User = Depends(get_auth_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    active = await revoke_consent(db, redis, user.id, payload.kinds)
    logger.info(
        "consent.revoked",
        extra={"user_id": str(user.id), "kinds": payload.kinds},
    )
    if not payload.kinds:
        raise HTTPException(400, "no kinds to revoke")
    return _serialize(active)
