"""HTTP 层统一错误 — 契约约定的 {errorCode, message} 结构。

@why 契约 §通用约定：所有 4xx/5xx 返回 camelCase 错误体，
     errorCode 取稳定枚举，前端据此分支提示而非解析中文 message。
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                             content={"errorCode": exc.error_code, "message": exc.message})
