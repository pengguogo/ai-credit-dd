"""Run 编排服务 — 契约 §POST /api/agent/runs 的落库与引擎调用。

@why 全部写入（run / trace / evidence / message / audit）在同一事务：
     引擎执行失败也落终态，绝不留下 running 悬挂行；commit 一次提交。
"""
import contextvars
import hashlib
import json
import logging
import threading
import time
import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..agent import context as ctx
from ..agent import engine
from ..agent.scenarios import DEFAULT_SCENARIO_ID, SCENARIOS, Scenario
from ..api_errors import ApiError
from ..compliance.checker import check_input, check_output
from ..compliance.citations import check_regulation_citations
from ..compliance.pii import redact as redact_pii
from ..compliance.pii import redact_obj
from ..config import settings
from ..domain import types as T
from ..domain.types import EvidenceRecord
from ..db import SessionLocal
from ..models import (AgentRun, AnswerConfirmation, AuditLog, Conversation,
                      Evidence, LlmCall, Message, RunEvent, ToolTrace, WorkspaceAsset, _utcnow)
from ..observability.events import RunEventRecorder, bus
from ..observability.logging import get_logger, log_event
from ..observability.request_id import current_request_id
from ..schemas import AgentAttachmentIn
from . import memory_service

_log = get_logger("run")

# 契约 §多模态输入约定的硬限制起点值：单次 ≤4 张、单张解码后 ≤32MB。
# @why base64 按 4/3 换算成字符上限做入口校验，避免解码大图占内存。
_MAX_ATTACHMENTS = 4
_MAX_IMAGE_BASE64_CHARS = 32 * 1024 * 1024 * 4 // 3


def _get_scenario(scenario_id: str) -> Scenario:
    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        raise ApiError(404, "unknown_scenario", f"未知场景: {scenario_id}")
    return scenario


def _public_question(db: Session, scenario: Scenario, question: str) -> str:
    """记录提问时也隐藏库内已知人名；企业名仍能在本地业务界面识别。"""
    masker = scenario.build_masker(db) if scenario.build_masker else None
    return masker.restore_names(masker.mask(question)) if masker else question


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def create_run(db: Session, *, question: str, conversation_id: str | None,
               scenario_id: str, actor_id: str, run_id: str | None = None,
               new_conversation_id: str | None = None,
               request_id: str | None = None,
               attachments: list[AgentAttachmentIn] | None = None) -> AgentRun:
    """同步执行一次 run 并在同一事务落库。

    run_id / new_conversation_id 由异步模式预先分配（客户端先拿到 runId 再订阅 SSE）；
    request_id 缺省取当前 HTTP 请求的 X-Request-Id。
    """
    started = time.monotonic()
    scenario = _get_scenario(scenario_id)
    image_urls = _validate_attachments(attachments)
    request_id = request_id or current_request_id()
    run_id = run_id or _new_id("run_")
    recorder = RunEventRecorder(run_id)
    # @why 先查合规再脱敏：敏感内容判定用原文；脱敏后的文本才进入会话、run、审计与模型
    check_started = time.monotonic()
    input_decision = check_input(question)
    question, pii_counts = redact_pii(question)
    question = _public_question(db, scenario, question)
    input_check_ms = _elapsed_ms(check_started)
    conversation = _resolve_conversation(db, conversation_id, actor_id, question,
                                         scenario.scenario_id, new_conversation_id)
    history, history_meta = _build_history(db, conversation.id)
    # user 消息也关联 run：被输入合规拦截的提问据此排除出后续轮次的模型历史
    db.add(Message(conversation_id=conversation.id, role="user", content=question,
                   run_id=run_id))
    run = AgentRun(
        id=run_id, conversation_id=conversation.id,
        scenario_id=scenario.scenario_id, question=question, status=T.RUNNING,
        model=settings.llm_model, usage={}, data_version=settings.data_version,
        owner_id=actor_id,
        context_snapshot={**history_meta, "requestId": request_id,
                          "maxHistoryMessages": settings.context_max_history_messages,
                          "historyTokenBudget": settings.context_history_token_budget})
    db.add(run)
    db.flush()
    # @why 图片不落库：审计只在 run_started 留数量，Message 仍只存脱敏文本
    _audit(db, run.id, "run_started", actor_id,
           {"scenarioId": scenario.scenario_id, "question": question,
            "requestId": request_id, "attachmentCount": len(image_urls)})
    recorder.emit("run_started", {"scenarioId": scenario.scenario_id, "question": question,
                                  "conversationId": conversation.id,
                                  "attachmentCount": len(image_urls)})
    recorder.emit("compliance_checked", {"stage": "input", "isClean": input_decision.is_clean,
                                         "durationMs": input_check_ms})
    if pii_counts:
        _audit(db, run.id, "pii_redacted", actor_id, {"stage": "input", "counts": pii_counts})
    if not input_decision.is_clean:
        # 输入违规：不调引擎不耗模型，终态 blocked + 审计留痕（契约 §违规输入）
        blocked_payload = {"stage": "input", "code": input_decision.code,
                           "category": input_decision.category,
                           "reason": _redacted(input_decision.reason)}
        _audit(db, run.id, "compliance_blocked", actor_id, blocked_payload)
        recorder.emit("compliance_blocked", {"payload": blocked_payload})
        outcome = engine.RunOutcome(status=T.BLOCKED,
                                    error_code=input_decision.code,
                                    error_message=input_decision.user_message)
    else:
        try:
            outcome = engine.run(
                db, scenario=scenario, question=question, history=history,
                attachments=image_urls,
                run_ctx={"run_id": run.id, "data_version": settings.data_version},
                persist_evidence=_make_persist_evidence(db, run.id),
                emit=recorder.emit, redact=redact_pii)
        except Exception as exc:  # 引擎意外异常也要落终态
            _log.exception("engine_error", extra={"fields": {"runId": run.id}})
            # @why 异常原文可能带 SQL、数据行或内部路径，不给用户看（输出合规 / 自查第 10 条）；
            #      详情在服务端日志，按 runId 排查
            outcome = engine.RunOutcome(status=T.FAILED, error_code="execution_failed",
                                        error_message=f"执行出错（{type(exc).__name__}），"
                                                      f"请稍后重试；排查请提供 runId {run.id}")
    _apply_outcome(db, run, outcome, actor_id, recorder)
    duration_ms = _elapsed_ms(started)
    recorder.emit("run_finished", {"status": run.status, "errorCode": run.error_code,
                                   "answerVersion": run.answer_version,
                                   "durationMs": duration_ms})
    for event_type, data in recorder.events:
        db.add(RunEvent(run_id=run.id, event_index=data["eventIndex"],
                        event_type=event_type, payload=data))
    db.commit()
    db.refresh(run)
    log_event(_log, "run_finished", request_id=request_id, runId=run.id,
              scenarioId=run.scenario_id, status=run.status, errorCode=run.error_code,
              durationMs=duration_ms, rounds=outcome.rounds, toolCalls=len(outcome.traces),
              totalTokens=(run.usage or {}).get("totalTokens", 0))
    return run


def start_run_async(db: Session, *, question: str, conversation_id: str | None,
                    scenario_id: str, actor_id: str,
                    attachments: list[AgentAttachmentIn] | None = None) -> dict:
    """异步模式：校验后立即返回 {runId, conversationId, scenarioId, question}，后台线程执行，执行中经 SSE 实时推送。

    @why 参数与权限错误在请求线程同步返回 4xx；后台线程用独立会话，
         run 的全部写入仍在其自身事务内一次提交。
    """
    scenario = _get_scenario(scenario_id)
    _validate_attachments(attachments)  # 附件超限在请求线程同步返回 422
    if conversation_id:
        _resolve_conversation(db, conversation_id, actor_id, question,
                              scenario.scenario_id)  # 只校验存在、归属与场景
        target_conversation, new_conversation_id = conversation_id, None
    else:
        new_conversation_id = str(uuid.uuid4())
        target_conversation = new_conversation_id
    run_id = _new_id("run_")
    request_id = current_request_id()
    meta = {"runId": run_id, "conversationId": target_conversation,
            "scenarioId": scenario.scenario_id,
            "question": _public_question(db, scenario, redact_pii(question)[0])}
    bus.open(run_id, actor_id, meta)

    def work() -> None:
        try:
            with SessionLocal() as session:
                create_run(session, question=question, conversation_id=conversation_id,
                           scenario_id=scenario_id, actor_id=actor_id, run_id=run_id,
                           new_conversation_id=new_conversation_id, request_id=request_id,
                           attachments=attachments)
            # @why 先提交再关闭通道：关闭后的读者转向数据库，必须已能读到
        except Exception as exc:  # 落库本身失败：推送失败终态，不留悬挂的"执行中"
            log_event(_log, "run_crashed", level=logging.ERROR, request_id=request_id,
                      runId=run_id, error=type(exc).__name__)
            channel = bus.get(run_id)
            bus.publish(run_id, ("run_finished", {
                "eventIndex": len(channel.events) + 1 if channel else 1, "runId": run_id,
                "status": T.FAILED, "errorCode": "execution_failed", "answerVersion": None}))
        finally:
            bus.close(run_id)

    threading.Thread(target=contextvars.copy_context().run, args=(work,),
                     name=f"run-{run_id}", daemon=True).start()
    return meta


def live_run(run_id: str, actor_id: str) -> dict | None:
    """执行中的异步 run（尚未落库）的只读视图；不存在或已结束返回 None。"""
    channel = bus.get(run_id)
    if channel is None or channel.done:
        return None
    if channel.owner_id != actor_id:
        raise ApiError(403, "run_forbidden", "无权访问该 run")
    return dict(channel.meta)


def utcnow_iso() -> str:
    return iso_z(_utcnow()) or ""


def stream_events(db: Session, run_id: str, actor_id: str, after: int):
    """SSE 事件来源：执行中走内存总线（实时），否则从 run_events 表重放。"""
    channel = bus.get(run_id)
    if channel is not None:
        if channel.owner_id != actor_id:
            raise ApiError(403, "run_forbidden", "无权访问该 run")
        return bus.iter_events(run_id, after,
                               keepalive_seconds=settings.sse_keepalive_seconds,
                               # 不限总时限时等到 run 结束（后台线程 finally 必定关闭通道）
                               max_wait_seconds=(settings.run_timeout_seconds + 30
                                                 if settings.run_timeout_seconds is not None
                                                 else float("inf")))
    run, _, _ = get_run(db, run_id, actor_id)
    return iter([e for e in load_events(db, run) if e[1]["eventIndex"] > after])


def load_events(db: Session, run: AgentRun) -> list[tuple[str, dict]]:
    rows = (db.query(RunEvent).filter(RunEvent.run_id == run.id)
            .order_by(RunEvent.event_index).all())
    if rows:
        return [(row.event_type, row.payload) for row in rows]
    return build_events(db, run)  # 早于 run_events 表的历史 run


def build_timings(events: list[tuple[str, dict]]) -> list[dict]:
    """节点级耗时：合规、每轮模型调用、每次工具调用、整个 run。"""
    out: list[dict] = []
    for event_type, data in events:
        if event_type == "compliance_checked":
            out.append({"node": "compliance", "stage": data["stage"],
                        "durationMs": data["durationMs"]})
        elif event_type == "llm_call_finished":
            out.append({"node": "llm", "round": data["round"], "status": data["status"],
                        "durationMs": data["durationMs"]})
        elif event_type == "tool_finished":
            out.append({"node": "tool", "sequence": data["sequence"],
                        "toolName": data["toolName"], "status": data["status"],
                        "durationMs": data["durationMs"]})
        elif event_type == "run_finished" and "durationMs" in data:
            out.append({"node": "run", "durationMs": data["durationMs"]})
    return out


def _can_view_run(db: Session, run: AgentRun, actor_id: str) -> bool:
    """本人的 run 可看；已建档到「任务与资产」的报告 run 对所有人可看。

    @why 资产的访问权限只在资产列表 / 详情接口控制（confirm 权限），进入档案后查看报告轨迹与证据
         不再按 owner 拦截，否则复核人员打不开他人生成的报告。普通对话 run 仍只有本人可看。
    """
    if run.owner_id == actor_id:
        return True
    return db.query(WorkspaceAsset.id).filter(WorkspaceAsset.run_id == run.id).first() is not None


def get_run(db: Session, run_id: str, actor_id: str) -> tuple[AgentRun, list[ToolTrace], list[str]]:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise ApiError(404, "run_not_found", f"run {run_id} 不存在")
    if not _can_view_run(db, run, actor_id):
        raise ApiError(403, "run_forbidden", "无权访问该 run")
    traces = (db.query(ToolTrace).filter(ToolTrace.run_id == run_id)
              .order_by(ToolTrace.sequence).all())
    evidence_ids = [row[0] for row in (db.query(Evidence.id)
                      .filter(Evidence.run_id == run_id)
                      .order_by(Evidence.id).all())]
    return run, traces, evidence_ids


_CONVERSATION_PAGE_DEFAULT = 30
_CONVERSATION_PAGE_MAX = 100


def list_conversations(
    db: Session,
    actor_id: str,
    scenario_id: str | None = None,
    *,
    q: str | None = None,
    limit: int = _CONVERSATION_PAGE_DEFAULT,
    offset: int = 0,
) -> dict:
    """当前身份的历史会话：可按场景 / 标题关键词过滤，分页返回。只返回本人的会话。"""
    if scenario_id:
        _get_scenario(scenario_id)
    limit = max(1, min(int(limit), _CONVERSATION_PAGE_MAX))
    offset = max(0, int(offset))
    query = db.query(Conversation).filter(Conversation.owner_id == actor_id)
    if scenario_id:
        query = query.filter(Conversation.scenario_id == scenario_id)
    needle = (q or "").strip()
    if needle:
        # 标题前缀/包含匹配；过长截断，避免无意义超长 LIKE
        query = query.filter(Conversation.title.ilike(f"%{needle[:80]}%"))
    total = query.count()
    conversations = (
        query.order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    if not conversations:
        return {
            "conversations": [],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }
    ids = [row.id for row in conversations]
    turn_counts = dict(
        db.query(Message.conversation_id, func.count(Message.id))
        .filter(Message.conversation_id.in_(ids), Message.role == "user")
        .group_by(Message.conversation_id).all())
    runs = (db.query(AgentRun).filter(AgentRun.conversation_id.in_(ids))
            .order_by(AgentRun.started_at.desc()).all())
    latest: dict[str, AgentRun] = {}
    for run in runs:
        latest.setdefault(run.conversation_id, run)
    items = []
    for row in conversations:
        run = latest.get(row.id)
        items.append({
            "conversation_id": row.id,
            "scenario_id": row.scenario_id or (run.scenario_id if run else ""),
            "title": row.title or "未命名会话",
            "updated_at": iso_z(row.updated_at) or "",
            "turn_count": int(turn_counts.get(row.id, 0)),
            "last_status": run.status if run else None,
        })
    return {
        "conversations": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }


def list_messages(db: Session, conversation_id: str,
                  actor_id: str) -> tuple[Conversation, list[Message]]:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise ApiError(404, "conversation_not_found", f"会话 {conversation_id} 不存在")
    if conversation.owner_id != actor_id:
        raise ApiError(403, "conversation_forbidden", "无权访问该会话")
    rows = (db.query(Message).filter(Message.conversation_id == conversation_id)
            .order_by(Message.id).all())
    return conversation, rows


# 仅带可确认结论的终态可确认
CONFIRMABLE_STATUSES = (T.SUCCEEDED, T.NEEDS_CONFIRMATION)


def create_confirmation(db: Session, *, run_id: str, answer_version: int,
                        action: str, comment: str | None, idempotency_key: str,
                        actor_id: str) -> AnswerConfirmation:
    """结论确认/驳回（契约 §POST /runs/{runId}/confirmations）。

    @why 幂等优先于一切校验：重放请求即使 run 状态已变化也返回同一结果；
         确认与审计同事务写入，过时版本 409。
    """
    run = db.get(AgentRun, run_id)
    if run is None:
        raise ApiError(404, "run_not_found", f"run {run_id} 不存在")
    existing = (db.query(AnswerConfirmation)
                .filter(AnswerConfirmation.idempotency_key == idempotency_key)
                .first())
    if existing is not None:
        if (existing.run_id == run_id and existing.answer_version == answer_version
                and existing.action == action):
            return existing
        raise ApiError(409, "idempotency_conflict",
                       "idempotencyKey 已用于内容不同的确认请求")
    if run.status not in CONFIRMABLE_STATUSES:
        raise ApiError(409, "run_not_confirmable",
                       f"run 状态为 {run.status}，仅 succeeded/needs_confirmation 可确认")
    if run.answer_version != answer_version:
        raise ApiError(409, "answer_version_stale",
                       f"answerVersion 过时，当前为 {run.answer_version}")
    confirmation = AnswerConfirmation(
        run_id=run_id, answer_version=answer_version, action=action,
        comment=comment, actor_id=actor_id, idempotency_key=idempotency_key)
    db.add(confirmation)
    db.flush()
    event_type = "confirmation_created" if action == "confirm" else "confirmation_rejected"
    _audit(db, run_id, event_type, actor_id,
           payload={"confirmationId": confirmation.id, "comment": comment},
           answer_version=answer_version)
    db.commit()
    db.refresh(confirmation)
    return confirmation


def list_evidence(db: Session, run_id: str, actor_id: str) -> list[Evidence]:
    """run 的证据（含快照），越权 403。证据快照与 run 同权限：只有 owner 可看。"""
    get_run(db, run_id, actor_id)
    return (db.query(Evidence).filter(Evidence.run_id == run_id)
            .order_by(Evidence.created_at, Evidence.id).all())


def list_llm_calls(db: Session, run_id: str, actor_id: str) -> list[LlmCall]:
    """run 的外部大模型调用审计（契约 §GET /runs/{runId}/llm-calls），与 run 同权限，越权 403。"""
    get_run(db, run_id, actor_id)
    return (db.query(LlmCall).filter(LlmCall.run_id == run_id)
            .order_by(LlmCall.round, LlmCall.id).all())


def public_answer(db: Session, scenario_id: str | None, text: str | None,
                  enterprise_ids: list[str] | None = None) -> str | None:
    """回答 / 消息的输出视图：人员代号显示为保留姓的脱敏姓名（张*），并修复历史误遮罩。

    @why 库内回答保持原样（只追加、不改写历史）；旧版遮罩把「人员E001-1」误写成「****01-1」，
         发布前人员代号也未转为脱敏姓名，这里在输出时统一成「张*」。原名只在本地映射中，不外露。
    """
    if not text:
        return text
    scenario = SCENARIOS.get(scenario_id or "")
    if scenario is None or scenario.build_masker is None:
        return text
    masker = scenario.build_masker(db)
    return masker.display_persons(masker.repair_legacy_person_codes(text, enterprise_ids or []))


def message_enterprise_ids(db: Session, rows: list[Message]) -> dict[str, list[str]]:
    """会话消息对应运行的企业编号：{runId: [enterpriseId]}。"""
    run_ids = {row.run_id for row in rows if row.run_id}
    if not run_ids:
        return {}
    return {run.id: run_enterprise_ids(run)
            for run in db.query(AgentRun).filter(AgentRun.id.in_(run_ids)).all()}


def run_enterprise_ids(run) -> list[str]:
    """本次运行涉及的企业编号（实体识别结果），用于限定历史代号修复的范围。"""
    ids = ((run.context_snapshot or {}).get("entities") or {}).get("enterpriseId") or []
    return [str(i) for i in ids if i]


def masked_snapshot(row: Evidence) -> object:
    """证据快照的输出视图：PII 掩码（待办 0-7，自查第 10 条）。

    @why 库内保留原始快照供复核与 content_hash 校验；凡经 API / 界面 / 导出给人看的，一律走这里。
         返回新对象，不改 ORM 行（否则会在 commit 时把掩码值写回库）。
    """
    return redact_obj(row.snapshot) if row.snapshot is not None else {}


def masked_args(args: dict | None) -> dict:
    return redact_obj(args or {})


def masked_source_ref(row: Evidence) -> dict:
    return redact_obj(row.source_ref or {})


def build_stats(db: Session) -> dict:
    """全局运行统计（只有计数与耗时，不含问题、答案、证据内容）。

    @why 业务价值看板的数据只来自真实执行记录，不写死任何数字。
    """
    runs = db.query(AgentRun.id, AgentRun.status, AgentRun.started_at,
                    AgentRun.finished_at, AgentRun.usage).all()
    status_counts: dict[str, int] = {}
    durations: list[int] = []
    tokens: list[int] = []
    for row in runs:
        status_counts[row.status] = status_counts.get(row.status, 0) + 1
        if row.started_at and row.finished_at:
            durations.append(int((row.finished_at - row.started_at).total_seconds() * 1000))
        tokens.append(int((row.usage or {}).get("totalTokens", 0) or 0))
    blocked_by_category: dict[str, int] = {}
    for (payload,) in db.query(AuditLog.payload).filter(
            AuditLog.event_type == "compliance_blocked"):
        category = (payload or {}).get("category") or "other"
        blocked_by_category[category] = blocked_by_category.get(category, 0) + 1
    conclusion_ids = {row.id for row in runs
                      if row.status in (T.SUCCEEDED, T.NEEDS_CONFIRMATION)}
    with_evidence = {rid for (rid,) in db.query(Evidence.run_id).distinct()} & conclusion_ids
    confirmations = {"confirm": 0, "reject": 0}
    for (action,) in db.query(AnswerConfirmation.action):
        confirmations[action] = confirmations.get(action, 0) + 1
    tool_usage: dict[str, int] = {}
    for (name,) in db.query(ToolTrace.tool_name):
        tool_usage[name] = tool_usage.get(name, 0) + 1
    durations.sort()
    return {
        "totalRuns": len(runs),
        "statusCounts": status_counts,
        "blockedByCategory": blocked_by_category,
        "conclusionRuns": len(conclusion_ids),
        "conclusionsWithEvidence": len(with_evidence),
        "evidenceCount": db.query(Evidence).count(),
        "toolUsage": tool_usage,
        "confirmations": confirmations,
        "avgDurationMs": int(sum(durations) / len(durations)) if durations else 0,
        "p95DurationMs": durations[min(len(durations) - 1, int(len(durations) * 0.95))]
        if durations else 0,
        "avgTotalTokens": int(sum(tokens) / len(tokens)) if tokens else 0,
        "generatedAt": utcnow_iso(),
    }


def list_audit(db: Session, run_id: str, actor_id: str) -> list[AuditLog]:
    """追加式审计事件（契约 §GET /runs/{runId}/audit，越权 403）。"""
    run = db.get(AgentRun, run_id)
    if run is None:
        raise ApiError(404, "run_not_found", f"run {run_id} 不存在")
    if not _can_view_run(db, run, actor_id):
        raise ApiError(403, "run_forbidden", "无权访问该 run")
    return (db.query(AuditLog).filter(AuditLog.run_id == run_id)
            .order_by(AuditLog.id).all())


def build_events(db: Session, run: AgentRun) -> list[tuple[str, dict]]:
    """从持久化数据重建 SSE 事件流（契约 §GET /runs/{id}/events）。

    @why 重放而非实时推送：事件来自 audit + trace 真实记录，P0 同步执行
         即返回，SSE 用于前端过程可视与断线恢复，无伪造内容。
    """
    traces = (db.query(ToolTrace).filter(ToolTrace.run_id == run.id)
              .order_by(ToolTrace.sequence).all())
    audits = (db.query(AuditLog).filter(AuditLog.run_id == run.id)
              .order_by(AuditLog.id).all())
    events: list[tuple[str, dict]] = []

    def emit(event_type: str, data: dict) -> None:
        events.append((event_type, {"eventIndex": len(events) + 1, "runId": run.id, **data}))

    emit("run_started", {"scenarioId": run.scenario_id, "question": run.question})
    for trace in traces:
        emit("tool_started", {"sequence": trace.sequence, "toolName": trace.tool_name})
        emit("tool_finished", {"sequence": trace.sequence, "toolName": trace.tool_name,
                               "status": trace.status, "durationMs": trace.duration_ms,
                               "errorCode": trace.error_code,
                               "evidenceIds": _trace_evidence_ids(trace)})
    for log in audits:
        if log.event_type == "compliance_blocked":
            emit("compliance_blocked", {"payload": log.payload})
    emit("run_finished", {"status": run.status, "errorCode": run.error_code,
                          "answerVersion": run.answer_version})
    return events


def _trace_evidence_ids(trace: ToolTrace) -> list[str]:
    try:
        return json.loads(trace.result_ref or "{}").get("evidenceIds", [])
    except (json.JSONDecodeError, AttributeError):
        return []


def iso_z(dt: datetime | None) -> str | None:
    """naive UTC → ISO 8601 带 Z（契约时间约定）。"""
    if dt is None:
        return None
    return dt.replace(microsecond=0).isoformat() + "Z"


def _validate_attachments(attachments: list[AgentAttachmentIn] | None) -> list[str]:
    """附件入口校验（契约 §多模态输入约定）→ 返回 imageUrl 列表。"""
    if not attachments:
        return []
    if len(attachments) > _MAX_ATTACHMENTS:
        raise ApiError(422, "invalid_attachment",
                       f"附件数量超出上限 {_MAX_ATTACHMENTS} 张")
    for index, attachment in enumerate(attachments, start=1):
        url = attachment.image_url
        if len(url) > _MAX_IMAGE_BASE64_CHARS:
            raise ApiError(422, "invalid_attachment",
                           f"第 {index} 张图片超出 32MB 上限")
    # 没有本地图像脱敏能力时不能把像素/远端URL直接交给外部模型。
    raise ApiError(422, "invalid_attachment", "图片内容暂无法安全脱敏，请改用脱敏后的文本资料")


def _resolve_conversation(db: Session, conversation_id: str | None,
                          actor_id: str, question: str, scenario_id: str,
                          new_conversation_id: str | None = None) -> Conversation:
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise ApiError(404, "conversation_not_found", f"会话 {conversation_id} 不存在")
        if conversation.owner_id != actor_id:
            raise ApiError(403, "conversation_forbidden", "无权访问该会话")
        if conversation.scenario_id and conversation.scenario_id != scenario_id:
            raise ApiError(409, "conversation_scenario_mismatch",
                           "该会话属于其他场景，请从历史会话切换到对应场景后再继续")
        if not conversation.scenario_id:
            conversation.scenario_id = scenario_id
        conversation.updated_at = _utcnow()
        return conversation
    conversation = Conversation(id=new_conversation_id or str(uuid.uuid4()), owner_id=actor_id,
                                scenario_id=scenario_id, title=question[:60])
    db.add(conversation)
    db.flush()
    return conversation


def _build_history(db: Session, conversation_id: str) -> tuple[list[dict], dict]:
    """组装历史（待办 1-2）：近期消息 + 上一轮工具结果摘要 + 实体槽位 + 旧轮次压缩。

    返回 (传给模型的 messages, 写入 context_snapshot 的元信息)。
    """
    limit = settings.context_max_history_messages + settings.context_max_compressed_messages
    query = db.query(Message).filter(Message.conversation_id == conversation_id)
    cutoff = memory_service.history_from(db, conversation_id)
    if cutoff is not None:
        # 记忆被清除过：更早的消息不再带入模型（消息本身保留，界面可查看）
        query = query.filter(Message.id >= cutoff)
    rows = list(reversed(query.order_by(Message.id.desc()).limit(limit).all()))
    run_ids = {row.run_id for row in rows if row.run_id}
    runs = db.query(AgentRun).filter(AgentRun.id.in_(run_ids)).all() if run_ids else []
    snapshots = {run.id: run.context_snapshot or {} for run in runs}
    # @why 被合规拦截的提问不再送给模型：否则下一轮模型会"补答"违规问题
    blocked = {run.id for run in runs if run.status == T.BLOCKED}
    rows = [row for row in rows if row.run_id not in blocked]
    items = [ctx.HistoryMessage(
        message_id=row.id, role=row.role, content=row.content, run_id=row.run_id,
        tool_summaries=snapshots.get(row.run_id, {}).get("toolSummaries", [])
        if row.role == "assistant" else []) for row in rows]
    # 实体槽位以会话记忆为准（待办 0-6：可被人工纠正 / 清除）；旧会话没有记忆记录时退回最近 run 的快照
    entities = memory_service.current_entities(db, conversation_id)
    messages, meta = ctx.build_history(
        items, entities=entities,
        max_recent=settings.context_max_history_messages,
        token_budget=settings.context_history_token_budget)
    return messages, {**meta, "entities": entities}


def _make_persist_evidence(db: Session, run_id: str):
    def persist(record: EvidenceRecord) -> str:
        evidence_id = _new_id("ev_")
        db.add(Evidence(
            id=evidence_id, run_id=run_id, source_type=record.source_type,
            source_ref=record.source_ref, snapshot=record.snapshot,
            content_hash=_content_hash(record.snapshot),
            data_version=record.data_version))
        return evidence_id
    return persist


def _evidence_texts(db: Session, evidence_ids: list[str]) -> list[str]:
    """本次 run 证据快照原文（未掩码），供法规引述核验逐字比对。"""
    if not evidence_ids:
        return []
    rows = db.query(Evidence.snapshot).filter(Evidence.id.in_(evidence_ids)).all()
    return [json.dumps(snapshot, ensure_ascii=False, default=str) for (snapshot,) in rows]


def _apply_outcome(db: Session, run: AgentRun, outcome: engine.RunOutcome,
                   actor_id: str, recorder: RunEventRecorder) -> None:
    # 输出合规：凡是给用户看的模型文本（结论、澄清问题、证据不足说明）落库/发布前都检查
    if outcome.status in _MODEL_TEXT_STATUSES and outcome.answer:
        check_started = time.monotonic()
        output_decision = check_output(outcome.answer)
        if output_decision.is_clean:
            # 法规引述门禁（J02）：法名 / 条号 / 文号须能在本次证据原文中逐字找到，否则拦截转人工
            output_decision = check_regulation_citations(
                outcome.answer, _evidence_texts(db, outcome.evidence_ids))
        recorder.emit("compliance_checked", {"stage": "output",
                                             "isClean": output_decision.is_clean,
                                             "durationMs": _elapsed_ms(check_started)})
        if not output_decision.is_clean:
            blocked_payload = {"stage": "output", "code": output_decision.code,
                               "category": output_decision.category,
                               "reason": _redacted(output_decision.reason)}
            _audit(db, run.id, "compliance_blocked", actor_id, blocked_payload)
            recorder.emit("compliance_blocked", {"payload": blocked_payload})
            outcome.status = T.BLOCKED
            outcome.answer = None
            outcome.error_code = output_decision.code
            outcome.error_message = output_decision.user_message
        else:
            outcome.answer, out_counts = redact_pii(outcome.answer)
            if out_counts:
                _audit(db, run.id, "pii_redacted", actor_id,
                       {"stage": "output", "counts": out_counts})
    if outcome.status in (T.NEEDS_CLARIFICATION, T.INSUFFICIENT_EVIDENCE):
        # @why 契约：answer 只承载结论（succeeded / needs_confirmation）；
        #      澄清问题与证据不足说明走 errorMessage，同时作为 assistant 消息进入历史
        outcome.error_message = outcome.answer or outcome.error_message
        outcome.answer = None
    for call in outcome.llm_calls:
        # 外部大模型调用审计（待办 0-5）：与 run 同事务，只追加
        db.add(LlmCall(run_id=run.id, **call))
    if outcome.tool_pii_counts:
        # 工具结果送模型前已掩码（engine），这里留痕：哪类 PII、多少处
        _audit(db, run.id, "pii_redacted", actor_id,
               {"stage": "tool_result", "counts": outcome.tool_pii_counts})
    run.status = outcome.status
    run.answer = outcome.answer
    run.answer_version = 1 if (outcome.status in CONFIRMABLE_STATUSES and outcome.answer) else None
    run.usage = outcome.usage
    run.error_code = outcome.error_code
    run.error_message = outcome.error_message
    run.finished_at = _utcnow()
    previous_entities = run.context_snapshot.get("entities", {})
    run.context_snapshot = {
        **run.context_snapshot,
        "roundsExecuted": outcome.rounds,
        "toolCalls": len(outcome.traces),
        "toolSummaries": [_redact_summary(s) for s in outcome.tool_summaries],
        # @why 实体槽位取自工具原始结果，下一轮会作为 system 消息送模型，先掩码
        "entities": _redact_entities(ctx.merge_entities(outcome.entities, previous_entities)),
        "missingInfo": outcome.missing_info,
        "confirmationReasons": outcome.confirmation_reasons,
        # 本次 run 下发给模型的环节 Skill（name@version），报告可追溯到所用规则版本
        "skillsApplied": outcome.skills_applied,
    }
    memory_service.sync_after_run(db, run.conversation_id, run.context_snapshot["entities"])
    for trace in outcome.traces:
        db.add(ToolTrace(
            run_id=run.id, sequence=trace.sequence, tool_name=trace.tool_name,
            args=trace.args,
            result_ref=json.dumps({"evidenceIds": trace.evidence_ids,
                                   "isSuccess": trace.status == "ok"},
                                  ensure_ascii=False),
            status=trace.status, duration_ms=trace.duration_ms,
            error_code=trace.error_code))
    reply = run.answer or (run.error_message if run.status in
                           (T.NEEDS_CLARIFICATION, T.INSUFFICIENT_EVIDENCE) else None)
    if reply:
        db.add(Message(conversation_id=run.conversation_id, role="assistant",
                       content=reply, run_id=run.id))
    _audit(db, run.id, "run_finished", actor_id,
           {"status": run.status, "errorCode": run.error_code})
    # 任务与资产：有正文的终态 run 自动建档（待复核档案即业务待办），见 workspace_service
    from .workspace_service import register_asset
    try:
        register_asset(db, run, actor_id)
    except Exception as exc:  # noqa: BLE001 档案失败不能影响已完成的 run，但必须留痕
        _log.warning("asset_register_failed",
                     extra={"fields": {"runId": run.id, "error": type(exc).__name__}})


_MODEL_TEXT_STATUSES = (T.SUCCEEDED, T.NEEDS_CONFIRMATION,
                        T.NEEDS_CLARIFICATION, T.INSUFFICIENT_EVIDENCE)


def _redact_summary(summary: dict) -> dict:
    """工具摘要会随历史再次送模型并写入 context_snapshot，先做 PII 掩码。"""
    args = json.loads(redact_pii(json.dumps(summary.get("args") or {},
                                            ensure_ascii=False, default=str))[0])
    return {**summary, "args": args, "result": redact_pii(summary["result"])[0]}


def _redact_entities(entities: dict[str, list[str]]) -> dict[str, list[str]]:
    return {key: [redact_pii(v)[0] for v in values] for key, values in entities.items()}


def _audit(db: Session, run_id: str, event_type: str, actor_id: str,
           payload: dict, answer_version: int | None = None) -> None:
    db.add(AuditLog(run_id=run_id, event_type=event_type, actor_id=actor_id,
                    answer_version=answer_version, payload=payload))


def _redacted(text: str | None) -> str | None:
    """审计中的命中片段也可能含 PII，入库前掩码。"""
    return redact_pii(text)[0] if text else text


def _new_id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:12]


def _content_hash(snapshot: object) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
        .encode("utf-8")).hexdigest()
