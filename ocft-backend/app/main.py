"""FastAPI 入口 — 启动校验/建表/幂等种子 + CORS（现场演示）+ 错误契约 + health live/ready。"""
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException

from . import llm
from .api_errors import register_error_handlers
from .config import REQUIRED_MODEL, settings
from .db import engine, init_db, seed_business_data
from .observability.logging import configure_logging
from .observability.request_id import RequestIdMiddleware
from .routers import admin, agent, auth
from .secret_box import SecretError
from db.config import ConfigError
from db.redis import ping as redis_ping


@asynccontextmanager
async def lifespan(_: FastAPI):
    # @why P0-1 fail-fast：模型名不等于比赛锁定值时拒绝启动，而非静默换模型
    settings.validate_runtime()
    init_db()
    seed_business_data()
    yield


configure_logging()

app = FastAPI(title="金融壹账通 AI 马拉松后端", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)
# 最外层：所有响应（含 CORS 预检与错误响应）都带 X-Request-Id
app.add_middleware(RequestIdMiddleware)

register_error_handlers(app)

# @why 唯一答题入口：早期场景直连路由（含模板化降级回复）已下线，
#      HTTP / SSE / 批量评测全部经 /api/agent/runs（红线 R4，唯一 pipeline）
app.include_router(agent.router)
app.include_router(auth.router)
app.include_router(admin.router)


@app.get("/api/health/live")
def health_live() -> dict:
    """进程存活探针：恒 200，不做任何依赖检查。"""
    return {"status": "ok", "service": "ocft-backend"}


@app.get("/api/health/ready")
def health_ready():
    """就绪检查：模型锁定 / 数据库连通 / Redis 连通 / 近期模型连通（契约 §health）。

    @why llm 状态为"近期真实调用结果"而非主动探测：未配置或近期失败即未就绪，
         503 + errorCode 说明原因，不做假健康。
    """
    model_ok = settings.llm_model == REQUIRED_MODEL
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    # @why Redis 与数据库同级：不通即整体未就绪（503）；配置错误或密文解不开也按不通处理
    try:
        redis_ok = redis_ping()
    except (ConfigError, SecretError):
        redis_ok = False
    recent = llm.recent_status()
    # unknown = 已配置但尚无调用：视为就绪，真实调用后再回写状态
    llm_ok = recent["status"] in ("ok", "unknown")

    checks = {
        "modelLock": {"ok": model_ok, "model": settings.llm_model, "required": REQUIRED_MODEL},
        "database": {"ok": db_ok},
        "redis": {"ok": redis_ok},
        "llm": {"ok": llm_ok, "status": recent["status"],
                "errorCode": recent.get("error_code"), "checkedAt": recent.get("checked_at")},
    }
    ready = model_ok and db_ok and redis_ok and llm_ok
    body = {"status": "ok" if ready else "unavailable",
            "service": "ocft-backend", "checks": checks}
    if not ready:
        failed = [name for name, item in checks.items() if not item["ok"]]
        body["errorCode"] = "service_not_ready"
        body["reason"] = "未通过就绪检查: " + ", ".join(failed)
        return JSONResponse(status_code=503, content=body)
    return body


def _frontend_dist() -> Path | None:
    path = Path(settings.frontend_dist_dir)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path if (path / "index.html").is_file() else None


# @why 离线交付（提交材料说明 1.1）：有前端构建产物时由后端同源提供页面，评测机不需要 Node.js。
#      必须最后挂载：/api 与 /docs 路由先注册，优先匹配；开发时仍用 5173 的 Vite dev server。
class _FrontendFiles(StaticFiles):
    """@why 未注册的 /api/* 路径必须仍是 404（与不挂载页面时一致），
    不能落到静态文件处理器上变成 405 或返回 index.html。"""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and (scope["path"] == "/api" or scope["path"].startswith("/api/")):
            await JSONResponse({"detail": "Not Found"}, status_code=404)(scope, receive, send)
            return
        await super().__call__(scope, receive, send)

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            response = None
        if response is not None and response.status_code != 404:
            return response
        # @why 只为已知 SPA 页面回退，缺失资源、未知页面和写请求不能伪装成成功。
        # @why Starlette 按 os.path.normpath 生成 path：Windows 上分隔符是反斜杠
        #      （/report/finance → report\finance），先统一成 / 再匹配，否则子路由刷新会 404
        route = path.replace("\\", "/")
        if scope["method"] in ("GET", "HEAD") and re.fullmatch(
            r"(?:login|admin|workspace|(?:tables|report)(?:/[^/.]+)?)/?", route
        ):
            return await super().get_response("index.html", scope)
        if response is not None:
            return response
        raise HTTPException(status_code=404)


_dist = _frontend_dist()
if _dist is not None:
    app.mount("/", _FrontendFiles(directory=_dist, html=True), name="frontend")
