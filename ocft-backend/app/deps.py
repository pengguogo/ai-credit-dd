"""共享依赖 — 身份解析：Bearer 会话优先，其次 X-Actor-Id（兼容评测/旧调用）。"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from .api_errors import ApiError
from .db import get_db
from .models import SysRole, SysUser
from .services import auth_service


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


@dataclass(frozen=True)
class ActorContext:
    """登录会话带 role；仅 X-Actor-Id 时 role 为 None（评测旁路，不套 RBAC）。"""
    actor_id: str
    role: SysRole | None


def require_actor_ctx(
    x_actor_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ActorContext:
    resolved = auth_service.resolve_token(db, _bearer_token(authorization))
    if resolved is not None:
        user, role = resolved
        return ActorContext(actor_id=user.username, role=role)
    if x_actor_id and x_actor_id.strip():
        return ActorContext(actor_id=x_actor_id.strip(), role=None)
    raise ApiError(400, "actor_id_required", "缺少登录凭证或 X-Actor-Id 请求头")


def require_actor(
    ctx: ActorContext = Depends(require_actor_ctx),
) -> str:
    """Agent 接口身份：登录 token → username；否则允许演示头 X-Actor-Id。"""
    return ctx.actor_id


def enforce_session_permission(ctx: ActorContext, code: str, *, message: str | None = None) -> None:
    """仅对 Bearer 登录会话校验权限；X-Actor-Id 评测调用不拦截。"""
    if ctx.role is None:
        return
    auth_service.require_permission(ctx.role, code, message=message)


def require_session(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> tuple[SysUser, SysRole]:
    resolved = auth_service.resolve_token(db, _bearer_token(authorization))
    if resolved is None:
        raise ApiError(401, "unauthorized", "请先登录")
    return resolved


def require_admin_session(
    pair: tuple[SysUser, SysRole] = Depends(require_session),
) -> tuple[SysUser, SysRole]:
    user, role = pair
    auth_service.require_admin(user, role)
    return pair
