"""系统管理：角色与用户。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin_session
from ..models import SysRole, SysUser
from ..services import admin_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


class RoleIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    permissions: list[str] = Field(default_factory=list)


class UserCreateIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    displayName: str = ""
    password: str = Field(min_length=6, max_length=128)
    roleCode: str = Field(min_length=1, max_length=32)


class UserPatchIn(BaseModel):
    displayName: str | None = None
    roleCode: str | None = None
    status: str | None = None
    password: str | None = None


@router.get("/roles")
def get_roles(_: tuple[SysUser, SysRole] = Depends(require_admin_session),
              db: Session = Depends(get_db)):
    return {"roles": admin_service.list_roles(db)}


@router.post("/roles")
def post_role(payload: RoleIn, _: tuple[SysUser, SysRole] = Depends(require_admin_session),
              db: Session = Depends(get_db)):
    return admin_service.create_role(
        db, code=payload.code, name=payload.name,
        description=payload.description, permissions=payload.permissions)


@router.get("/users")
def get_users(_: tuple[SysUser, SysRole] = Depends(require_admin_session),
              db: Session = Depends(get_db)):
    return {"users": admin_service.list_users(db)}


@router.post("/users")
def post_user(payload: UserCreateIn, _: tuple[SysUser, SysRole] = Depends(require_admin_session),
              db: Session = Depends(get_db)):
    return admin_service.create_user(
        db, username=payload.username, display_name=payload.displayName,
        password=payload.password, role_code=payload.roleCode)


@router.patch("/users/{user_id}")
def patch_user(user_id: int, payload: UserPatchIn,
               _: tuple[SysUser, SysRole] = Depends(require_admin_session),
               db: Session = Depends(get_db)):
    return admin_service.update_user(
        db, user_id, display_name=payload.displayName, role_code=payload.roleCode,
        status=payload.status, password=payload.password)
