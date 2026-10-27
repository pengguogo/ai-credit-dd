"""结构化 JSON 日志。

@why 日志只记录标识、状态、耗时与计数：问题、答案、工具数据可能含 PII，
     一律不进日志（需要内容时查有权限控制的 run / audit 接口）。
"""
import json
import logging
import sys
from datetime import datetime, timezone

from .request_id import current_request_id

LOGGER_NAME = "ocft"
_configured = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc)
                  .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or current_request_id()
        if request_id:
            entry["requestId"] = request_id
        entry.update(getattr(record, "fields", {}) or {})
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """幂等：只给 ocft 命名空间挂 JSON handler，不改动第三方库日志。"""
    global _configured
    if _configured:
        return
    logger = logging.getLogger(LOGGER_NAME)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def log_event(logger: logging.Logger, msg: str, *, level: int = logging.INFO,
              request_id: str | None = None, **fields) -> None:
    logger.log(level, msg, extra={"fields": fields, "request_id": request_id})
