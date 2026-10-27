"""系统管理 — 角色与用户 CRUD（管理员）。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..api_errors import ApiError
from ..models import SysRole, SysUser
from . import auth_service


def list_roles(db: Session) -> list[dict]:
    rows = db.query(SysRole).order_by(SysRole.id.asc()).all()
    return [_role_view(r) for r in rows]


def create_role(db: Session, *, code: str, name: str, description: str,
                permissions: list[str]) -> dict:
    code = (code or "").strip()
    name = (name or "").strip()
    if not code or not name:
        raise ApiError(400, "invalid_args", "角色编码与名称必填")
    if db.query(SysRole).filter(SysRole.code == code).first():
        raise ApiError(409, "role_exists", f"角色 {code} 已存在")
    row = SysRole(
        code=code, name=name, description=(description or "").strip(),
        permissions=list(permissions or []),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _role_view(row)


def list_users(db: Session) -> list[dict]:
    roles = {r.id: r for r in db.query(SysRole).all()}
    users = db.query(SysUser).order_by(SysUser.id.asc()).all()
    out = []
    for u in users:
        role = roles.get(u.role_id)
        if role is None:
            continue
        out.append(auth_service.user_view(u, role))
    return out


def create_user(db: Session, *, username: str, display_name: str, password: str,
                role_code: str) -> dict:
    username = (username or "").strip()
    display_name = (display_name or "").strip() or username
    role_code = (role_code or "").strip()
    if not username or not password:
        raise ApiError(400, "invalid_args", "用户名与密码必填")
    if len(password) < 6:
        raise ApiError(400, "invalid_args", "密码至少 6 位")
    if db.query(SysUser).filter(SysUser.username == username).first():
        raise ApiError(409, "user_exists", f"用户 {username} 已存在")
    role = db.query(SysRole).filter(SysRole.code == role_code).first()
    if role is None:
        raise ApiError(404, "role_not_found", f"角色 {role_code} 不存在")
    user = SysUser(
        username=username,
        display_name=display_name,
        password_hash=auth_service.hash_password(password),
        role_id=role.id,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return auth_service.user_view(user, role)


def update_user(db: Session, user_id: int, *, display_name: str | None = None,
                role_code: str | None = None, status: str | None = None,
                password: str | None = None) -> dict:
    user = db.query(SysUser).filter(SysUser.id == user_id).first()
    if user is None:
        raise ApiError(404, "user_not_found", "用户不存在")
    if display_name is not None:
        user.display_name = display_name.strip() or user.display_name
    if status is not None:
        if status not in ("active", "disabled"):
            raise ApiError(400, "invalid_args", "status 只能是 active 或 disabled")
        user.status = status
    if role_code is not None:
        role = db.query(SysRole).filter(SysRole.code == role_code.strip()).first()
        if role is None:
            raise ApiError(404, "role_not_found", f"角色 {role_code} 不存在")
        user.role_id = role.id
    if password is not None and password != "":
        if len(password) < 6:
            raise ApiError(400, "invalid_args", "密码至少 6 位")
        user.password_hash = auth_service.hash_password(password)
    db.commit()
    db.refresh(user)
    role = db.query(SysRole).filter(SysRole.id == user.role_id).first()
    if role is None:
        raise ApiError(500, "role_missing", "用户角色不存在")
    return auth_service.user_view(user, role)


def _role_view(role: SysRole) -> dict:
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "permissions": list(role.permissions or []),
        "createdAt": role.created_at.isoformat() + "Z" if role.created_at else None,
    }
