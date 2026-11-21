"""Shared session, role and validation policies for owner and staff routes."""

import os
import hashlib
import time
import secrets

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from .db import database
from .domain import fail

COOKIE = "pet_session"
SESSION_TTL = 60 * 60 * 24 * 14


def current(request: Request):
    token = request.cookies.get(COOKIE)
    if token and len(token) < 160:
        with database() as db:
            return db.one(
                "SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>?",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            )
    return None


def authenticated(user=Depends(current)):
    if not user:
        fail(401, "请先登录")
    return user


def staff(user=Depends(authenticated)):
    if user["role"] not in {"admin", "operator"}:
        fail(403, "此页面仅供运营人员访问")
    return user


def admin(user=Depends(staff)):
    if user["role"] != "admin":
        fail(403, "此操作需要管理员权限")
    return user


def session(db, user_id, response):
    token = secrets.token_urlsafe(40)
    db.execute("DELETE FROM sessions WHERE expires<=?", (time.time(),))
    db.execute(
        "INSERT INTO sessions VALUES(?,?,?)",
        (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time() + SESSION_TTL),
    )
    secure = os.getenv("PET_COOKIE_SECURE", "").lower() == "true" or os.getenv(
        "PET_PUBLIC_URL", ""
    ).startswith("https://")
    response.set_cookie(
        COOKIE, token, max_age=SESSION_TTL, httponly=True, samesite="lax", secure=secure, path="/"
    )


class Body(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class Revision(Body):
    feedback: str = Field(min_length=1, max_length=1000)
    photo_ids: list[str] | None = Field(default=None, max_length=4)
