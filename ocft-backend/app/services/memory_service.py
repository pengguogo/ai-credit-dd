"""会话记忆：查看、纠正、清除（待办 0-6；9 题评审维度②"记忆内容可查看、可纠正、可清除"）。

记忆由两部分组成，都会在下一轮送给模型：
  - 实体槽位（entities）：从工具参数 / 结果提取的编号、名称，作为 system 消息"会话已知实体"；
  - 历史范围（history_from_message_id）：哪些历史消息（及其工具摘要）还会带入。
已确认结论来自 answer_confirmations，只读展示（它们本身就在历史消息里）。

@why 纠正值会直接进入 system 消息：限定键为场景声明的实体键、限长、去换行、做 PII 掩码与输入合规检查，
     防止借纠正记忆注入指令或把原始敏感信息送给模型。变更写 memory_events（只追加），与修改同事务。
"""
from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..agent.scenarios import SCENARIOS
from ..api_errors import ApiError
from ..compliance.checker import check_input
from ..compliance.pii import redact
from ..models import (AgentRun, AnswerConfirmation, Conversation, ConversationMemory,
                      MemoryEvent, Message)

MAX_VALUES = 5
MAX_VALUE_CHARS = 64
ANSWER_PREVIEW_CHARS = 200
_CONTROL = re.compile(r"[\r\n\t\x00-\x1f]")
CLEAR_SCOPES = ("entities", "history", "all")


def _owned(db: Session, conversation_id: str, actor_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise ApiError(404, "conversation_not_found", f"会话 {conversation_id} 不存在")
    if conversation.owner_id != actor_id:
        raise ApiError(403, "conversation_forbidden", "无权访问该会话")
    return conversation


def _latest_snapshot_entities(db: Session, conversation_id: str) -> dict[str, list[str]]:
    run = (db.query(AgentRun).filter(AgentRun.conversation_id == conversation_id,
                                     AgentRun.finished_at.isnot(None))
           .order_by(AgentRun.finished_at.desc()).first())
    return dict((run.context_snapshot or {}).get("entities") or {}) if run else {}


def get_memory_row(db: Session, conversation_id: str) -> ConversationMemory | None:
    return db.get(ConversationMemory, conversation_id)


def current_entities(db: Session, conversation_id: str) -> dict[str, list[str]]:
    """下一轮要带给模型的实体槽位：有记忆记录用记录，否则退回最近一次 run 的快照。"""
    row = get_memory_row(db, conversation_id)
    return dict(row.entities or {}) if row else _latest_snapshot_entities(db, conversation_id)


def history_from(db: Session, conversation_id: str) -> int | None:
    row = get_memory_row(db, conversation_id)
    return row.history_from_message_id if row else None


def sync_after_run(db: Session, conversation_id: str, entities: dict[str, list[str]]) -> None:
    """run 结束后把本轮合并后的槽位写回记忆（同一事务，由 run_service 调用）。"""
    row = get_memory_row(db, conversation_id)
    if row is None:
        db.add(ConversationMemory(conversation_id=conversation_id, entities=entities,
                                  version=1, updated_by="agent"))
        return
    if row.entities != entities:
        row.entities = entities
        row.version += 1
        row.updated_by = "agent"


def view(db: Session, conversation_id: str, actor_id: str) -> dict:
    conversation = _owned(db, conversation_id, actor_id)
    row = get_memory_row(db, conversation_id)
    cutoff = row.history_from_message_id if row else None
    total = db.query(func.count(Message.id)).filter(Message.conversation_id == conversation_id).scalar() or 0
    carried_q = db.query(func.count(Message.id)).filter(Message.conversation_id == conversation_id)
    if cutoff is not None:
        carried_q = carried_q.filter(Message.id >= cutoff)
    scenario = SCENARIOS.get(conversation.scenario_id or "")
    confirmed = (db.query(AnswerConfirmation, AgentRun)
                 .join(AgentRun, AgentRun.id == AnswerConfirmation.run_id)
                 .filter(AgentRun.conversation_id == conversation_id,
                         AnswerConfirmation.action == "confirm")
                 .order_by(AnswerConfirmation.created_at).all())
    events = (db.query(MemoryEvent).filter(MemoryEvent.conversation_id == conversation_id)
              .order_by(MemoryEvent.id.desc()).limit(20).all())
    return {
        "conversation_id": conversation_id,
        "scenario_id": conversation.scenario_id,
        "entities": current_entities(db, conversation_id),
        "allowed_keys": list(scenario.entity_keys) if scenario else [],
        "history_from_message_id": cutoff,
        "total_messages": total,
        "carried_messages": carried_q.scalar() or 0,
        "confirmed_conclusions": [{
            "run_id": run.id, "answer_version": conf.answer_version,
            "answer": _preview(run.answer), "confirmed_by": conf.actor_id,
            "confirmed_at": conf.created_at} for conf, run in confirmed],
        "version": row.version if row else 0,
        "updated_by": row.updated_by if row else None,
        "updated_at": row.updated_at if row else None,
        "events": [{"id": e.id, "event_type": e.event_type, "actor_id": e.actor_id,
                    "payload": e.payload or {}, "created_at": e.created_at} for e in events],
    }


def _preview(text: str | None) -> str:
    text = redact(text or "")[0]
    return text if len(text) <= ANSWER_PREVIEW_CHARS else text[:ANSWER_PREVIEW_CHARS] + "…"


def _clean_values(key: str, values: object) -> list[str]:
    if not isinstance(values, list) or len(values) > MAX_VALUES:
        raise ApiError(422, "invalid_memory", f"{key} 需为字符串数组，最多 {MAX_VALUES} 个")
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ApiError(422, "invalid_memory", f"{key} 的取值必须是字符串")
        value = _CONTROL.sub(" ", value).strip()
        if not value:
            continue
        if len(value) > MAX_VALUE_CHARS:
            raise ApiError(422, "invalid_memory", f"{key} 的单个取值不超过 {MAX_VALUE_CHARS} 字")
        decision = check_input(value)
        if not decision.is_clean:
            raise ApiError(422, "memory_blocked", decision.user_message)
        value = redact(value)[0]
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


def _row_for_update(db: Session, conversation_id: str, expected_version: int | None) -> ConversationMemory:
    row = get_memory_row(db, conversation_id)
    if row is None:
        row = ConversationMemory(conversation_id=conversation_id,
                                 entities=_latest_snapshot_entities(db, conversation_id), version=0)
        db.add(row)
    if expected_version is not None and expected_version != row.version:
        raise ApiError(409, "memory_version_conflict",
                       f"记忆已被修改（当前版本 {row.version}），请刷新后再改")
    return row


def correct(db: Session, conversation_id: str, actor_id: str, entities: dict,
            expected_version: int | None) -> dict:
    """纠正槽位：只改请求里出现的键；空数组表示删除该键。"""
    conversation = _owned(db, conversation_id, actor_id)
    if not isinstance(entities, dict) or not entities:
        raise ApiError(422, "invalid_memory", "entities 不能为空")
    scenario = SCENARIOS.get(conversation.scenario_id or "")
    allowed = set(scenario.entity_keys) if scenario else set()
    unknown = sorted(set(entities) - allowed)
    if unknown:
        raise ApiError(422, "invalid_memory",
                       f"不支持的记忆项 {unknown}，本场景可纠正：{sorted(allowed)}")
    row = _row_for_update(db, conversation_id, expected_version)
    before = dict(row.entities or {})
    after = dict(before)
    changed: list[str] = []
    for key, values in entities.items():
        cleaned = _clean_values(key, values)
        if cleaned != before.get(key, []):
            changed.append(key)
        if cleaned:
            after[key] = cleaned
        else:
            after.pop(key, None)
    # @why 同一场景的实体描述的是同一个对象（如申请编号 + 客户名）。只改其中一项会留下互相矛盾的槽位，
    #      模型下一轮会转去澄清。所以有项被改动时，本次请求没有一并给出的同场景其他实体一律清空，
    #      下一轮由工具按新值重新查询补上，而不是让旧值和新值混在一起
    dropped = [key for key in allowed if changed and key not in entities and key in after]
    for key in dropped:
        after.pop(key)
    row.entities = after
    row.version += 1
    row.updated_by = actor_id
    db.add(MemoryEvent(conversation_id=conversation_id, event_type="memory_corrected",
                       actor_id=actor_id, payload={"before": before, "after": after,
                                                   "dropped": sorted(dropped),
                                                   "version": row.version}))
    db.commit()
    return view(db, conversation_id, actor_id)


def clear(db: Session, conversation_id: str, actor_id: str, scope: str,
          expected_version: int | None) -> dict:
    """清除：entities 清空槽位；history 让现有消息不再带入模型（消息本身保留，可查看、可审计）。"""
    _owned(db, conversation_id, actor_id)
    if scope not in CLEAR_SCOPES:
        raise ApiError(422, "invalid_memory", f"scope 只能是 {list(CLEAR_SCOPES)}")
    row = _row_for_update(db, conversation_id, expected_version)
    payload: dict = {"scope": scope}
    if scope in ("entities", "all"):
        payload["entitiesBefore"] = dict(row.entities or {})
        row.entities = {}
    if scope in ("history", "all"):
        last_id = (db.query(func.max(Message.id))
                   .filter(Message.conversation_id == conversation_id).scalar())
        payload["historyFromBefore"] = row.history_from_message_id
        row.history_from_message_id = (last_id or 0) + 1
        payload["historyFromAfter"] = row.history_from_message_id
    row.version += 1
    row.updated_by = actor_id
    payload["version"] = row.version
    db.add(MemoryEvent(conversation_id=conversation_id, event_type="memory_cleared",
                       actor_id=actor_id, payload=payload))
    db.commit()
    return view(db, conversation_id, actor_id)
