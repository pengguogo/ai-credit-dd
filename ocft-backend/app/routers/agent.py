"""Agent 基座路由 — 契约 contracts/agent-api.md 的 HTTP 形态。

@why POST /runs 同步执行（受 60s 时限）：def 路由跑在线程池不阻塞事件循环；
     SSE 从持久化数据重放真实事件，无预演专用路径。
"""
import json
import re

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import ActorContext, enforce_session_permission, require_actor, require_actor_ctx
from ..schemas import (AgentAuditEventOut, AgentAuditOut, CatalogOut,
                       CatalogDeleteOut, CatalogRecordOut,
                       AgentConfirmationIn, AgentConfirmationOut,
                       AgentConversationListOut, AgentConversationMessagesOut,
                       AgentConversationOut, AgentEvidenceListOut,
                       AgentEvidenceOut, AgentMessageOut,
                       AgentRunCreateIn, AgentRunDetailOut, AgentRunOut,
                       AgentStatsOut, AgentToolTraceOut, AgentUsageOut,
                       AgentLlmCallListOut, AgentLlmCallOut,
                       ConversationMemoryOut, ConversationMemoryPatchIn,
                       CsvImportIn, DdStepIn, DdStepOut,
                       WorkspaceAssetDetailOut, WorkspaceAssetListOut)
from ..services import (catalog, catalog_write, csv_import_service, dd_step, memory_service,
                        run_service, workspace_service)
from ..api_errors import ApiError

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/data/imports")
def import_csv(payload: CsvImportIn, db: Session = Depends(get_db),
               ctx: ActorContext = Depends(require_actor_ctx)):
    enforce_session_permission(ctx, "catalog_write", message="当前角色不能导入业务数据")
    result, status = csv_import_service.import_csv_files(db, payload, ctx.actor_id)
    return JSONResponse(status_code=status, content=result)


@router.post("/runs", response_model=AgentRunOut)
def create_run(payload: AgentRunCreateIn, db: Session = Depends(get_db),
               actor_id: str = Depends(require_actor)):
    if payload.mode == "async":
        live = run_service.start_run_async(
            db, question=payload.question, conversation_id=payload.conversation_id,
            scenario_id=payload.scenario_id, actor_id=actor_id,
            attachments=payload.attachments)
        return JSONResponse(status_code=202, content=_running_out(
            live["runId"], live["conversationId"], live["scenarioId"], live["question"]))
    run = run_service.create_run(
        db, question=payload.question, conversation_id=payload.conversation_id,
        scenario_id=payload.scenario_id, actor_id=actor_id,
        attachments=payload.attachments)
    _, _, evidence_ids = run_service.get_run(db, run.id, actor_id)
    return _to_run_out(run, evidence_ids)


@router.get("/runs/{run_id}", response_model=AgentRunDetailOut)
def get_run(run_id: str, db: Session = Depends(get_db),
            actor_id: str = Depends(require_actor)):
    live = run_service.live_run(run_id, actor_id)
    if live is not None:
        # 异步执行中尚未落库：只返回 running 状态，过程看 SSE
        data = _running_out(live["runId"], live["conversationId"], live["scenarioId"],
                            live["question"])
        data.update(toolTraces=[], contextSnapshot={}, timings=[],
                    startedAt=data["createdAt"], finishedAt=None)
        return data
    run, traces, evidence_ids = run_service.get_run(db, run_id, actor_id)
    data = _to_run_out(run, evidence_ids)
    ids = run_service.run_enterprise_ids(run)
    data["answer"] = run_service.public_answer(db, run.scenario_id, data.get("answer"), ids)
    data["errorMessage"] = run_service.public_answer(db, run.scenario_id, data.get("errorMessage"), ids)
    data["toolTraces"] = [
        AgentToolTraceOut(sequence=t.sequence, tool_name=t.tool_name, status=t.status,
                          # 工具入参由模型生成，可能带号码：界面输出前掩码（自查第 10 条）
                          args=run_service.masked_args(t.args), duration_ms=t.duration_ms,
                          error_code=t.error_code).model_dump(by_alias=True)
        for t in traces]
    data["contextSnapshot"] = run.context_snapshot or {}
    data["timings"] = run_service.build_timings(run_service.load_events(db, run))
    data["startedAt"] = run_service.iso_z(run.started_at)
    data["finishedAt"] = run_service.iso_z(run.finished_at)
    return data


@router.get("/runs/{run_id}/events")
def run_events(run_id: str, db: Session = Depends(get_db),
               actor_id: str = Depends(require_actor),
               last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
               after: int | None = Query(default=None, ge=0,
                                         description="只返回 eventIndex 大于该值的事件")):
    """执行中实时推送，结束后从持久化事件重放；Last-Event-ID 或 after 续传。"""
    resume_from = after if after is not None else _parse_event_id(last_event_id)
    events = run_service.stream_events(db, run_id, actor_id, resume_from)

    def stream():
        for item in events:
            if item is None:  # 心跳：注释行，客户端忽略
                yield ": keepalive\n\n"
                continue
            event_type, data = item
            yield (f"id: {data['eventIndex']}\n"
                   f"event: {event_type}\n"
                   f"data: {json.dumps(data, ensure_ascii=False)}\n\n")

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/conversations", response_model=AgentConversationListOut)
def list_conversations(
    db: Session = Depends(get_db),
    actor_id: str = Depends(require_actor),
    scenario_id: str | None = Query(default=None, alias="scenarioId", max_length=32),
    q: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    page = run_service.list_conversations(
        db, actor_id, scenario_id, q=q, limit=limit, offset=offset)
    return AgentConversationListOut(
        conversations=[AgentConversationOut(**row) for row in page["conversations"]],
        total=page["total"],
        limit=page["limit"],
        offset=page["offset"],
        has_more=page["has_more"],
    )


@router.get("/conversations/{conversation_id}/messages",
            response_model=AgentConversationMessagesOut)
def list_messages(conversation_id: str, db: Session = Depends(get_db),
                  actor_id: str = Depends(require_actor)):
    conversation, rows = run_service.list_messages(db, conversation_id, actor_id)
    scenario_id = getattr(conversation, "scenario_id", None)
    entity_ids = run_service.message_enterprise_ids(db, rows)
    return AgentConversationMessagesOut(
        conversation_id=conversation_id,
        messages=[AgentMessageOut(
            id=row.id, role=row.role,
            content=(run_service.public_answer(db, scenario_id, row.content, entity_ids.get(row.run_id))
                     if row.role == "assistant" else row.content),
            run_id=row.run_id,
            created_at=run_service.iso_z(row.created_at) or "") for row in rows])


def _memory_out(data: dict) -> ConversationMemoryOut:
    iso = run_service.iso_z
    return ConversationMemoryOut(**{
        **data,
        "updated_at": iso(data["updated_at"]) if data["updated_at"] else None,
        "confirmed_conclusions": [{**c, "confirmed_at": iso(c["confirmed_at"]) or ""}
                                  for c in data["confirmed_conclusions"]],
        "events": [{**e, "created_at": iso(e["created_at"]) or ""} for e in data["events"]],
    })


@router.get("/conversations/{conversation_id}/memory", response_model=ConversationMemoryOut)
def get_memory(conversation_id: str, db: Session = Depends(get_db),
               actor_id: str = Depends(require_actor)):
    """会话记忆：下一轮带给模型的实体槽位、历史范围，以及已确认结论（只读）。"""
    return _memory_out(memory_service.view(db, conversation_id, actor_id))


@router.patch("/conversations/{conversation_id}/memory", response_model=ConversationMemoryOut)
def patch_memory(conversation_id: str, payload: ConversationMemoryPatchIn,
                 db: Session = Depends(get_db), actor_id: str = Depends(require_actor)):
    return _memory_out(memory_service.correct(db, conversation_id, actor_id, payload.entities,
                                              payload.expected_version))


@router.delete("/conversations/{conversation_id}/memory", response_model=ConversationMemoryOut)
def delete_memory(conversation_id: str,
                  scope: str = Query(default="all", pattern="^(entities|history|all)$"),
                  expected_version: int | None = Query(default=None, alias="expectedVersion"),
                  db: Session = Depends(get_db), actor_id: str = Depends(require_actor)):
    return _memory_out(memory_service.clear(db, conversation_id, actor_id, scope, expected_version))


@router.post("/runs/{run_id}/confirmations", response_model=AgentConfirmationOut)
def create_confirmation(run_id: str, payload: AgentConfirmationIn,
                        db: Session = Depends(get_db),
                        ctx: ActorContext = Depends(require_actor_ctx)):
    enforce_session_permission(ctx, "confirm", message="当前角色不能确认或驳回结论")
    confirmation = run_service.create_confirmation(
        db, run_id=run_id, answer_version=payload.answer_version,
        action=payload.action, comment=payload.comment,
        idempotency_key=payload.idempotency_key, actor_id=ctx.actor_id)
    return AgentConfirmationOut(
        confirmation_id=confirmation.id, run_id=confirmation.run_id,
        answer_version=confirmation.answer_version, action=confirmation.action,
        actor_id=confirmation.actor_id,
        created_at=run_service.iso_z(confirmation.created_at) or "")


@router.get("/runs/{run_id}/evidence", response_model=AgentEvidenceListOut)
def get_run_evidence(run_id: str, db: Session = Depends(get_db),
                     actor_id: str = Depends(require_actor)):
    rows = run_service.list_evidence(db, run_id, actor_id)
    return AgentEvidenceListOut(evidence=[
        AgentEvidenceOut(
            # 输出侧掩码（待办 0-7）；content_hash 仍是原始快照的哈希，供库内复核
            evidence_id=row.id, source_type=row.source_type,
            source_ref=run_service.masked_source_ref(row),
            snapshot=run_service.masked_snapshot(row),
            content_hash=row.content_hash, data_version=row.data_version,
            created_at=run_service.iso_z(row.created_at) or "")
        for row in rows])


@router.get("/runs/{run_id}/llm-calls", response_model=AgentLlmCallListOut)
def get_run_llm_calls(run_id: str, db: Session = Depends(get_db),
                      actor_id: str = Depends(require_actor)):
    """外部大模型调用审计：每次调用的时间、用途、脱敏后的入参预览与请求体 sha256。"""
    rows = run_service.list_llm_calls(db, run_id, actor_id)
    return AgentLlmCallListOut(calls=[
        AgentLlmCallOut(
            id=row.id, round=row.round, purpose=row.purpose, model=row.model,
            status=row.status, error_code=row.error_code, message_count=row.message_count,
            request_sha256=row.request_sha256, request_preview=row.request_preview or [],
            tool_names=row.tool_names or [], response_preview=row.response_preview or {},
            usage=row.usage or {}, duration_ms=row.duration_ms,
            started_at=run_service.iso_z(row.started_at) or "")
        for row in rows])


@router.get("/catalog/{scenario_id}", response_model=CatalogOut)
def get_catalog(scenario_id: str, q: str | None = Query(default=None, max_length=100),
                kind: str | None = Query(default="applications", max_length=32),
                approval_status: str | None = Query(default=None, alias="approvalStatus", max_length=16),
                db: Session = Depends(get_db),
                ctx: ActorContext = Depends(require_actor_ctx)):
    """当前场景的业务事实表。kind=enterprises|applications；q 在库内筛选可见字段，不计算结论。
    审批表可用 approvalStatus=pending|pending_review|approved|rejected|open 筛选审批状态（open=待处理+待审核）。"""
    enforce_session_permission(ctx, "catalog", message="当前角色不能查看业务数据")
    # viewer 仅企业基础信息；带 applications 的角色可看审批表及其余业务表
    if kind and kind != "enterprises":
        enforce_session_permission(
            ctx, "applications",
            message="当前角色只能查看企业基础信息",
        )
    data = catalog.list_catalog(db, scenario_id, q, kind, approval_status)
    data["scenario_id"] = scenario_id
    return data


@router.post("/catalog/{scenario_id}/{kind}/records", response_model=CatalogRecordOut)
def create_catalog_record(scenario_id: str, kind: str, payload: dict,
                          db: Session = Depends(get_db),
                          ctx: ActorContext = Depends(require_actor_ctx)):
    """单行新增业务事实（不含表关系）。"""
    enforce_session_permission(ctx, "catalog_write", message="当前角色不能修改业务数据")
    if kind == "applications":
        enforce_session_permission(ctx, "applications", message="当前角色不能修改审批表")
    return CatalogRecordOut(**catalog_write.create_record(
        db, scenario_id, kind, payload, ctx.actor_id))


@router.patch("/catalog/{scenario_id}/{kind}/records/{record_id}", response_model=CatalogRecordOut)
def update_catalog_record(scenario_id: str, kind: str, record_id: int, payload: dict,
                          db: Session = Depends(get_db),
                          ctx: ActorContext = Depends(require_actor_ctx)):
    """按内部 id 更新业务事实。改审批状态需 confirm 权限。"""
    enforce_session_permission(ctx, "catalog_write", message="当前角色不能修改业务数据")
    if kind == "applications":
        enforce_session_permission(ctx, "applications", message="当前角色不能修改审批表")
        if "status" in payload or "Status" in payload:
            enforce_session_permission(ctx, "confirm", message="当前角色不能审批申请")
    return CatalogRecordOut(**catalog_write.update_record(
        db, scenario_id, kind, record_id, payload, ctx.actor_id))


@router.post("/catalog/{scenario_id}/applications/records/{record_id}/review",
             response_model=CatalogRecordOut)
def review_loan_application(scenario_id: str, record_id: int, payload: dict,
                            db: Session = Depends(get_db),
                            ctx: ActorContext = Depends(require_actor_ctx)):
    """人工审核贷款申请：通过 / 拒绝 + 必填原因，写审核人与时间并追加审计。"""
    enforce_session_permission(ctx, "applications", message="当前角色不能审核审批表")
    enforce_session_permission(ctx, "confirm", message="当前角色不能审批申请")
    return CatalogRecordOut(**catalog_write.review_application(
        db, scenario_id, record_id, payload.get("decision"), payload.get("reason"),
        ctx.actor_id))


@router.delete("/catalog/{scenario_id}/{kind}/records/{record_id}", response_model=CatalogDeleteOut)
def delete_catalog_record(scenario_id: str, kind: str, record_id: int,
                          db: Session = Depends(get_db),
                          ctx: ActorContext = Depends(require_actor_ctx)):
    """按内部 id 删除业务事实。"""
    enforce_session_permission(ctx, "catalog_write", message="当前角色不能修改业务数据")
    if kind == "applications":
        enforce_session_permission(ctx, "applications", message="当前角色不能修改审批表")
    return CatalogDeleteOut(**catalog_write.delete_record(
        db, scenario_id, kind, record_id, ctx.actor_id))


@router.post("/dd/steps", response_model=DdStepOut)
def analyze_dd_step(payload: DdStepIn, db: Session = Depends(get_db),
                    ctx: ActorContext = Depends(require_actor_ctx)):
    """单步尽调核对：不经模型，只跑当前步骤工具，供前端单维度页展示。"""
    enforce_session_permission(ctx, "dd_steps", message="当前角色不能使用尽调五步")
    return dd_step.run_step(
        db,
        step=payload.step,
        enterprise_id=payload.enterprise_id,
        application_id=payload.application_id,
    )


@router.get("/assets", response_model=WorkspaceAssetListOut)
def list_workspace_assets(
    db: Session = Depends(get_db),
    ctx: ActorContext = Depends(require_actor_ctx),
    keyword: str | None = Query(default=None, max_length=80),
    application_id: str | None = Query(default=None, alias="applicationId", max_length=40),
    enterprise_id: str | None = Query(default=None, alias="enterpriseId", max_length=40),
    kind: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """报告检索：按企业 / 申请 / 关键词过滤。报告本身没有状态。"""
    # 报告权限只在列表与详情处控制；进入报告后查看轨迹与证据不再校验
    enforce_session_permission(ctx, "confirm", message="当前角色不能查看报告列表")
    return WorkspaceAssetListOut(**workspace_service.list_assets(
        db, keyword=keyword, application_id=application_id,
        enterprise_id=enterprise_id, kind=kind, limit=limit, offset=offset))


@router.get("/assets/{asset_id}", response_model=WorkspaceAssetDetailOut)
def get_workspace_asset(asset_id: str, db: Session = Depends(get_db),
                        ctx: ActorContext = Depends(require_actor_ctx)):
    """报告详情：摘要、关联 runId 与证据条数（报告不再有状态流转记录）。"""
    enforce_session_permission(ctx, "confirm", message="当前角色不能查看报告列表")
    return WorkspaceAssetDetailOut(**workspace_service.view_asset(db, asset_id))


@router.get("/stats", response_model=AgentStatsOut)
def get_stats(db: Session = Depends(get_db), _actor_id: str = Depends(require_actor)):
    """运行统计：状态分布、合规拦截分类、证据覆盖、耗时（只有计数，无内容）。"""
    return AgentStatsOut(**_snake_keys(run_service.build_stats(db)))


@router.get("/runs/{run_id}/audit", response_model=AgentAuditOut)
def get_run_audit(run_id: str, db: Session = Depends(get_db),
                  actor_id: str = Depends(require_actor)):
    logs = run_service.list_audit(db, run_id, actor_id)
    return AgentAuditOut(events=[
        AgentAuditEventOut(
            id=log.id, event_type=log.event_type, actor_id=log.actor_id,
            answer_version=log.answer_version, payload=log.payload or {},
            created_at=run_service.iso_z(log.created_at) or "")
        for log in logs])


def _snake_keys(data: dict) -> dict:
    return {re.sub(r"(?<!^)(?=[A-Z])", "_", k).lower(): v for k, v in data.items()}


def _parse_event_id(value: str | None) -> int:
    try:
        return max(int(value), 0) if value else 0
    except ValueError:
        return 0


def _running_out(run_id: str, conversation_id: str, scenario_id: str, question: str) -> dict:
    """异步模式下尚未落库的 run 视图（question 已做 PII 掩码）。"""
    return AgentRunOut(
        run_id=run_id, conversation_id=conversation_id, scenario_id=scenario_id,
        question=question, status="running", answer=None, answer_version=None,
        model=settings.llm_model, usage=AgentUsageOut(), data_version=settings.data_version,
        error_code=None, error_message=None, evidence_ids=[],
        created_at=run_service.utcnow_iso()).model_dump(by_alias=True)


def _to_run_out(run, evidence_ids: list[str] | None = None) -> dict:
    usage = run.usage or {}
    return AgentRunOut(
        run_id=run.id, conversation_id=run.conversation_id,
        scenario_id=run.scenario_id, question=run.question, status=run.status,
        answer=run.answer, answer_version=run.answer_version, model=run.model,
        usage=AgentUsageOut(
            prompt_tokens=usage.get("promptTokens", 0),
            completion_tokens=usage.get("completionTokens", 0),
            total_tokens=usage.get("totalTokens", 0)),
        data_version=run.data_version, error_code=run.error_code,
        error_message=run.error_message,
        evidence_ids=evidence_ids or [],
        created_at=run_service.iso_z(run.started_at) or "").model_dump(by_alias=True)
