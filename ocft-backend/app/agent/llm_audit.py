"""外部大模型调用审计记录（待办 0-5）— 纯函数，不访问数据库。

graph.model_node 每次调用模型前后用这里的函数生成一条记录，暂存在 RunOutcome.llm_calls，
由服务层与 run 同事务写入 llm_calls 表。

@why 通用纪律第 2 条要求外部调用的入参、时间、用途可审计，自查第 9 条要抽查调用日志确认
     入参不含未脱敏的敏感字段。记录里只放脱敏后的截断预览 + 请求体 sha256：
     预览用于人工抽查，hash 用于证明预览对应的是哪一次真实请求。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable

PREVIEW_CHARS = 200
PURPOSE_TOOL_LOOP = "tool_loop"   # 有界工具循环中的一轮：决定调用工具或给出结论

Redact = Callable[[str], tuple[str, dict[str, int]]]


def request_sha256(messages: list[dict], tools: list[dict]) -> str:
    """实际发出的请求体（messages + tools）的 sha256。须在调用前计算（之后 messages 会被追加）。"""
    payload = json.dumps({"messages": messages, "tools": tools},
                         ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text_of(content: object) -> str:
    """消息内容转预览文本：多模态数组里的图片只记占位，不展开 data URL。"""
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            else:
                parts.append("[图片]")
        return " ".join(parts)
    return "" if content is None else str(content)


def _preview(text: str, redact: Redact) -> str:
    masked = redact(text)[0]
    return masked if len(masked) <= PREVIEW_CHARS else masked[:PREVIEW_CHARS] + "…"


def request_preview(messages: list[dict], redact: Redact) -> list[dict]:
    """每条消息：角色、原长度、脱敏后的截断预览；assistant 的工具调用只列名称。"""
    rows = []
    for message in messages:
        text = _text_of(message.get("content"))
        row = {"role": message.get("role"), "chars": len(text), "preview": _preview(text, redact)}
        calls = message.get("tool_calls") or []
        if calls:
            row["toolCalls"] = [c.get("function", {}).get("name") for c in calls]
        rows.append(row)
    return rows


def response_preview(resp: dict | None, redact: Redact) -> dict:
    if not resp:
        return {}
    calls = [{"name": c["function"]["name"],
              "args": _preview(c["function"].get("arguments") or "", redact)}
             for c in resp.get("tool_calls") or []]
    return {"content": _preview(resp.get("content") or "", redact), "toolCalls": calls,
            "finishReason": resp.get("finish_reason")}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_record(*, round_no: int, purpose: str, model: str, messages: list[dict],
                 tools: list[dict], sha256: str, started_at: datetime, duration_ms: int,
                 resp: dict | None, error_code: str | None, redact: Redact) -> dict:
    """一条审计记录（键与 LlmCall 列名一致）。"""
    return {
        "round": round_no, "purpose": purpose, "model": model,
        "status": "ok" if error_code is None else "error", "error_code": error_code,
        "message_count": len(messages), "request_sha256": sha256,
        "request_preview": request_preview(messages, redact),
        "tool_names": [t["function"]["name"] for t in tools],
        "response_preview": response_preview(resp, redact),
        "usage": (resp or {}).get("usage") or {},
        "duration_ms": duration_ms, "started_at": started_at,
    }
