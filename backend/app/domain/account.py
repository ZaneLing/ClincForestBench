from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.domain.session import utc_now


class PhysicianAccount(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password_plaintext: str = Field(min_length=4, max_length=128)
    created_at: datetime = Field(default_factory=utc_now)


class AuthSession(BaseModel):
    token: str
    username: str
    created_at: datetime = Field(default_factory=utc_now)
