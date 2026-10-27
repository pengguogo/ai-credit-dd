"""登录 / 登出 / 当前用户。"""
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_session
from ..models import SysRole, SysUser
from ..services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    return auth_service.login(db, payload.username, payload.password)


@router.post("/logout")
def logout(authorization: str | None = Header(default=None),
           db: Session = Depends(get_db)):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    auth_service.logout(db, token)
    return {"ok": True}


@router.get("/me")
def me(pair: tuple[SysUser, SysRole] = Depends(require_session)):
    user, role = pair
    return {"user": auth_service.user_view(user, role)}
