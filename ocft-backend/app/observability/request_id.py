"""请求 ID：读取或生成 X-Request-Id，写入响应头与上下文变量，并记录访问日志。

@why 纯 ASGI 中间件而非 BaseHTTPMiddleware：后者会缓冲流式响应，SSE 无法实时推送。
"""
import re
import time
import uuid
from contextvars import ContextVar

HEADER = "X-Request-Id"
_VALID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    return _request_id.get()


def new_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:16]


class RequestIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = None
        for key, value in scope.get("headers", []):
            if key.decode("latin-1").lower() == HEADER.lower():
                incoming = value.decode("latin-1").strip()
                break
        # 外部传入的 ID 只接受安全字符，防日志注入
        request_id = incoming if incoming and _VALID.match(incoming) else new_request_id()
        token = _request_id.set(request_id)
        started = time.monotonic()
        status = {"code": 500}

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((HEADER.encode("latin-1"), request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            from .logging import get_logger, log_event  # 避免循环导入
            log_event(get_logger("http"), "request", request_id=request_id,
                      method=scope.get("method"), path=scope.get("path"),
                      status=status["code"],
                      durationMs=int((time.monotonic() - started) * 1000))
            _request_id.reset(token)
