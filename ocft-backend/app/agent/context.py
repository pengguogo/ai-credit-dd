"""上下文管理 — 工具结果摘要、实体槽位、历史预算压缩（待办 1-2）。

@why 多轮对话只传文本会丢掉上一轮查到的数据（如"她"指哪笔申请）。
     这里把每个 run 的工具结果压成短摘要随历史带给模型，完整数据仍只在
     evidence 表；超出 token 预算时把最旧的消息压成摘要并注明覆盖范围。
     本模块是纯函数，不访问数据库与模型，便于单测。
"""
import json
import math
from dataclasses import dataclass, field

# 单个实体槽位最多保留的取值数（新值在前）
MAX_SLOT_VALUES = 5
# 压缩摘要里每条消息保留的字符数
COMPRESSED_LINE_CHARS = 60
# 工具结果里列表最多保留的元素数
SUMMARY_LIST_ITEMS = 5


def estimate_tokens(text: str | None) -> int:
    """粗略估算：中文约 1~1.5 字/token，按 1.5 字/token 向上取整。只用于预算判断。"""
    return math.ceil(len(text or "") / 1.5)


def summarize_tool_call(tool_name: str, args: dict, is_success: bool, data: object,
                        error_code: str | None, evidence_ids: list[str],
                        max_chars: int) -> dict:
    """一次工具调用的摘要：保留参数、成功与否、关键数据（列表截断）、证据 ID。"""
    if is_success:
        result = json.dumps(_compact(data), ensure_ascii=False, default=str)
    else:
        result = f"失败[{error_code}]"
    if len(result) > max_chars:
        result = result[:max_chars] + "…（已截断）"
    return {"toolName": tool_name, "args": args, "isSuccess": is_success,
            "result": result, "evidenceIds": list(evidence_ids)}


def _compact(value: object, depth: int = 0) -> object:
    """列表截断、嵌套过深时只留类型提示：摘要只为让模型记得查过什么。"""
    if isinstance(value, dict):
        if depth >= 3:
            return "{…}"
        return {k: _compact(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        items = [_compact(v, depth + 1) for v in value[:SUMMARY_LIST_ITEMS]]
        if len(value) > SUMMARY_LIST_ITEMS:
            items.append(f"…共 {len(value)} 项")
        return items
    return value


def extract_entities(keys: tuple[str, ...], sources: list[object]) -> dict[str, list[str]]:
    """从工具参数与结果中按键名收集实体值（字符串），后出现的排在前面。"""
    found: dict[str, list[str]] = {}
    if not keys:
        return found

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in keys and isinstance(v, str) and v.strip():
                    found.setdefault(k, []).append(v.strip())
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for source in sources:
        walk(source)
    return {k: _dedupe(list(reversed(v)))[:MAX_SLOT_VALUES] for k, v in found.items()}


def merge_entities(newer: dict[str, list[str]],
                   older: dict[str, list[str]]) -> dict[str, list[str]]:
    keys = list(newer) + [k for k in older if k not in newer]
    return {k: _dedupe(newer.get(k, []) + older.get(k, []))[:MAX_SLOT_VALUES] for k in keys}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    return [v for v in values if not (v in seen or seen.add(v))]


@dataclass
class HistoryMessage:
    """历史中的一条消息；tool_summaries 来自产生该 assistant 消息的 run。"""
    message_id: int
    role: str
    content: str
    run_id: str | None = None
    tool_summaries: list[dict] = field(default_factory=list)


def build_history(rows: list[HistoryMessage], *, entities: dict[str, list[str]],
                  max_recent: int, token_budget: int) -> tuple[list[dict], dict]:
    """组装传给模型的历史消息，返回 (messages, meta)。

    - 最近 max_recent 条原样保留；assistant 消息前插入该 run 的工具结果摘要；
    - 更早的消息、以及超出 token 预算时最旧的近期消息，压缩为一条摘要（注明消息 ID 范围）；
    - 会话已知实体放在最前，供模型解析指代。
    """
    recent = rows[-max_recent:] if max_recent > 0 else []
    older = rows[:len(rows) - len(recent)]

    def cost(items: list[HistoryMessage]) -> int:
        return sum(estimate_tokens(m.content) + sum(
            estimate_tokens(s["result"]) for s in m.tool_summaries) for m in items)

    # 预算不足时从最旧处逐条移入压缩区，至少保留最后一条
    while len(recent) > 1 and cost(recent) > token_budget:
        older.append(recent.pop(0))

    messages: list[dict] = []
    if entities:
        slots = "；".join(f"{k}: {'、'.join(v)}" for k, v in entities.items())
        messages.append({"role": "system",
                         "content": f"会话已知实体（来自此前的工具结果，新值在前）：{slots}"})
    compressed_range = None
    if older:
        compressed_range = {"fromMessageId": older[0].message_id,
                            "toMessageId": older[-1].message_id, "count": len(older)}
        messages.append({"role": "system", "content": _compress(older, token_budget // 4)})
    summary_runs: list[str] = []
    for row in recent:
        if row.role == "assistant" and row.tool_summaries:
            summary_runs.append(row.run_id or "")
            messages.append({"role": "system", "content": _render_summaries(row)})
        messages.append({"role": row.role, "content": row.content})
    meta = {
        "historyMessages": len(recent),
        "compressedRange": compressed_range,
        "toolSummaryRuns": summary_runs,
        "estimatedHistoryTokens": sum(estimate_tokens(m["content"]) for m in messages),
    }
    return messages, meta


def _render_summaries(row: HistoryMessage) -> str:
    lines = [f"此前工具结果摘要（run {row.run_id}，完整数据见证据表；"
             "需要给出结论时仍应重新调用工具取证）："]
    for s in row.tool_summaries:
        args = json.dumps(s.get("args") or {}, ensure_ascii=False, default=str)
        evid = "、".join(s.get("evidenceIds") or []) or "无"
        lines.append(f"- {s['toolName']} {args} → {s['result']}（证据：{evid}）")
    return "\n".join(lines)


def _compress(rows: list[HistoryMessage], token_cap: int) -> str:
    """抽取式压缩：每条消息截取开头，不调模型（不耗 token、结果可复现）。"""
    head = (f"早期对话摘要（消息 #{rows[0].message_id}–#{rows[-1].message_id}，"
            f"共 {len(rows)} 条，已压缩；如需细节请让用户重述或重新查询）：")
    lines: list[str] = []
    for row in reversed(rows):  # 从新到旧取，超出上限时丢最旧的
        who = "用户" if row.role == "user" else "助手"
        text = row.content.replace("\n", " ")
        if len(text) > COMPRESSED_LINE_CHARS:
            text = text[:COMPRESSED_LINE_CHARS] + "…"
        line = f"#{row.message_id} {who}：{text}"
        if estimate_tokens(head + "".join(lines) + line) > max(token_cap, 1) and lines:
            break
        lines.insert(0, line)
    return head + "\n" + "\n".join(lines)
