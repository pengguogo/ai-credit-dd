"""登录与会话 — 密码 pbkdf2 哈希；会话 token 只存 sha256。"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..api_errors import ApiError
from ..models import AgentRun, Conversation, SysRole, SysSession, SysUser

_PBKDF2_ROUNDS = 120_000
_SESSION_DAYS = 7

# 演示账号（仅种子；密码不明文落库）
DEMO_USERS = (
    {"username": "admin", "display_name": "系统管理员", "password": "Admin@123", "role": "admin"},
    {"username": "account_manager", "display_name": "客户经理", "password": "Demo@123", "role": "account_manager"},
    {"username": "viewer", "display_name": "只读访客", "password": "View@123", "role": "viewer"},
)

# 权限码：admin 系统管理；workbench 智能尽调；dd_steps 尽调1–5步；
# catalog 企业基础信息等列表；applications 审批表；confirm 确认/驳回；catalog_write 增删改导入
DEMO_ROLES = (
    {
        "code": "admin",
        "name": "系统管理员",
        "description": "全部权限：系统管理、智能尽调、审批表通过/驳回、结论确认、数据写、尽调五步（演示主账号）",
        "permissions": [
            "admin", "workbench", "dd_steps", "catalog",
            "applications", "confirm", "catalog_write",
        ],
    },
    {
        "code": "account_manager",
        "name": "客户经理",
        "description": "负责发起尽调、业务资料维护、审批表办理与结论确认；无系统管理权限",
        "permissions": [
            "workbench", "dd_steps", "catalog",
            "applications", "confirm", "catalog_write",
        ],
    },
    {
        "code": "viewer",
        "name": "只读访客",
        "description": "智能尽调（含企业基础信息）+ 尽调1–5步，共6项菜单；无数据列表/审批/系统管理",
        "permissions": ["workbench", "dd_steps", "catalog"],
    },
)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS
    ).hex()
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds_s, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        rounds = int(rounds_s)
    except ValueError:
        return False
    check = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds
    ).hex()
    return secrets.compare_digest(check, digest)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_seed_users(db: Session) -> None:
    """幂等写入演示角色与用户，并把旧业务复核角色平滑迁移为客户经理。"""
    legacy_role = db.query(SysRole).filter(SysRole.code == "reviewer").first()
    account_manager = db.query(SysRole).filter(SysRole.code == "account_manager").first()
    if legacy_role is not None and account_manager is None:
        # 保留 role_id，避免已有用户、会话及历史业务归属断裂。
        legacy_role.code = "account_manager"
        account_manager = legacy_role
        db.flush()

    for role in DEMO_ROLES:
        row = db.query(SysRole).filter(SysRole.code == role["code"]).first()
        if row is None:
            db.add(SysRole(
                code=role["code"], name=role["name"], description=role["description"],
                permissions=list(role["permissions"]),
            ))
        else:
            row.name = role["name"]
            row.description = role["description"]
            row.permissions = list(role["permissions"])
    db.flush()

    roles = {r.code: r for r in db.query(SysRole).all()}
    legacy_role = roles.get("reviewer")
    account_manager = roles.get("account_manager")
    if legacy_role is not None and account_manager is not None:
        # 若两种编码曾并存，先保全用户关联，再移除已停用的种子角色。
        db.query(SysUser).filter(SysUser.role_id == legacy_role.id).update(
            {SysUser.role_id: account_manager.id}, synchronize_session=False)
        db.delete(legacy_role)
        db.flush()
        roles.pop("reviewer", None)

    legacy_username = "reviewer_demo"
    account_manager_username = "account_manager"
    legacy_user = db.query(SysUser).filter(SysUser.username == legacy_username).first()
    account_manager_user = db.query(SysUser).filter(
        SysUser.username == account_manager_username).first()
    if legacy_user is not None:
        # owner_id 是会话与 run 的访问控制字段；同步改名以保留历史访问。
        # 追加式审计、确认和资产事件保留原操作者文本，不改写历史。
        db.query(Conversation).filter(Conversation.owner_id == legacy_username).update(
            {Conversation.owner_id: account_manager_username}, synchronize_session=False)
        db.query(AgentRun).filter(AgentRun.owner_id == legacy_username).update(
            {AgentRun.owner_id: account_manager_username}, synchronize_session=False)
        if account_manager_user is None:
            legacy_user.username = account_manager_username
        else:
            db.query(SysSession).filter(SysSession.user_id == legacy_user.id).update(
                {SysSession.user_id: account_manager_user.id}, synchronize_session=False)
            db.delete(legacy_user)
        db.flush()

    for item in DEMO_USERS:
        role = roles.get(item["role"])
        if role is None:
            continue
        user = db.query(SysUser).filter(SysUser.username == item["username"]).first()
        if user is None:
            db.add(SysUser(
                username=item["username"],
                display_name=item["display_name"],
                password_hash=hash_password(item["password"]),
                role_id=role.id,
                status="active",
            ))
        else:
            user.display_name = item["display_name"]
            user.role_id = role.id
    db.commit()


def login(db: Session, username: str, password: str) -> dict:
    name = (username or "").strip()
    if not name or not password:
        raise ApiError(400, "invalid_args", "请输入用户名和密码")
    user = db.query(SysUser).filter(SysUser.username == name).first()
    if user is None or not verify_password(password, user.password_hash):
        raise ApiError(401, "invalid_credentials", "用户名或密码错误")
    if user.status != "active":
        raise ApiError(403, "user_disabled", "账号已停用")
    role = db.query(SysRole).filter(SysRole.id == user.role_id).first()
    if role is None:
        raise ApiError(500, "role_missing", "用户角色不存在")
    token = secrets.token_urlsafe(32)
    db.add(SysSession(
        token_hash=_token_hash(token),
        user_id=user.id,
        expires_at=_utcnow() + timedelta(days=_SESSION_DAYS),
    ))
    db.commit()
    return {
        "token": token,
        "expiresInSeconds": _SESSION_DAYS * 24 * 3600,
        "user": user_view(user, role),
    }


def logout(db: Session, token: str | None) -> None:
    if not token:
        return
    row = db.query(SysSession).filter(SysSession.token_hash == _token_hash(token)).first()
    if row and row.revoked_at is None:
        row.revoked_at = _utcnow()
        db.commit()


def resolve_token(db: Session, token: str | None) -> tuple[SysUser, SysRole] | None:
    if not token:
        return None
    row = db.query(SysSession).filter(SysSession.token_hash == _token_hash(token)).first()
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at < _utcnow():
        return None
    user = db.query(SysUser).filter(SysUser.id == row.user_id).first()
    if user is None or user.status != "active":
        return None
    role = db.query(SysRole).filter(SysRole.id == user.role_id).first()
    if role is None:
        return None
    return user, role


def user_view(user: SysUser, role: SysRole) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "displayName": user.display_name,
        "status": user.status,
        "roleCode": role.code,
        "roleName": role.name,
        "permissions": list(role.permissions or []),
    }


def role_permissions(role: SysRole) -> set[str]:
    perms = set(role.permissions or [])
    if role.code == "admin":
        perms.add("admin")
    return perms


def require_permission(role: SysRole, code: str, *, message: str | None = None) -> None:
    if code in role_permissions(role) or role.code == "admin":
        return
    raise ApiError(403, "forbidden", message or f"需要权限：{code}")


def require_admin(user: SysUser, role: SysRole) -> None:
    require_permission(role, "admin", message="需要系统管理员权限")
