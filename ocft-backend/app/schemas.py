"""Pydantic 请求/响应模型 — DB snake_case 进，API camelCase 出（FastAPI 默认 by_alias）。

@why 契约即代码：这些模型驱动 /docs Swagger 页，与 contracts/agent-api.md 一一对应。
     早期五个场景的直连路由（credit/risk/claims/chat/docs）已下线，
     所有答题统一走 /api/agent/runs（红线：唯一 pipeline、无模板化降级）。
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .agent.scenarios import DEFAULT_SCENARIO_ID


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class CsvImportFileIn(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    file_name: str = Field(min_length=1, max_length=100)
    content: str = Field(max_length=2_000_000)


class CsvImportIn(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    files: list[CsvImportFileIn] = Field(min_length=1, max_length=9)


# ---- Agent 基座（契约 contracts/agent-api.md） ----

class AgentAttachmentIn(CamelModel):
    """多模态附件（契约 §多模态输入约定）：MVP 仅 image_url。"""
    type: Literal["image_url"]
    image_url: str = Field(min_length=1)


class CatalogColumnOut(CamelModel):
    key: str
    label: str


class CatalogOut(CamelModel):
    """当前场景的业务事实目录，不含结论与评测标签。"""
    scenario_id: str
    title: str
    note: str
    kind: str = "applications"
    query: str = ""
    approval_status: str = ""
    total: int
    matched: int
    limit: int
    columns: list[CatalogColumnOut]
    rows: list[dict]
    # 审批表：pending / approved / rejected / decided 计数，便于筛选
    status_counts: dict[str, int] = Field(default_factory=dict)


class CatalogRecordOut(CamelModel):
    id: int
    kind: str
    row: dict


class CatalogDeleteOut(CamelModel):
    id: int
    kind: str
    deleted: bool = True


class AgentRunCreateIn(CamelModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    scenario_id: str = DEFAULT_SCENARIO_ID
    # sync：执行完返回终态（默认，评测用）；async：立即返回 202 + runId，过程经 SSE 实时推送
    mode: Literal["sync", "async"] = "sync"
    attachments: list[AgentAttachmentIn] | None = None


class AgentUsageOut(CamelModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AgentToolTraceOut(CamelModel):
    sequence: int
    tool_name: str
    status: str
    args: dict
    duration_ms: int
    error_code: str | None


class AgentRunOut(CamelModel):
    run_id: str
    conversation_id: str
    scenario_id: str
    question: str
    status: str
    answer: str | None
    answer_version: int | None
    model: str
    usage: AgentUsageOut
    data_version: int
    error_code: str | None
    error_message: str | None
    evidence_ids: list[str] = []
    created_at: str


class AgentRunDetailOut(AgentRunOut):
    tool_traces: list[AgentToolTraceOut] = []
    # 上下文快照：历史范围、压缩区间、工具摘要、实体槽位、确认原因（契约 §GET /runs/{runId}）
    context_snapshot: dict = {}
    # 节点级耗时：合规、每轮模型调用、每次工具调用、整个 run
    timings: list[dict] = []
    started_at: str | None
    finished_at: str | None


class AgentMessageOut(CamelModel):
    id: int
    role: str
    content: str
    run_id: str | None
    created_at: str


class AgentConversationOut(CamelModel):
    conversation_id: str
    scenario_id: str
    title: str
    updated_at: str
    turn_count: int
    last_status: str | None = None


class AgentConversationListOut(CamelModel):
    conversations: list[AgentConversationOut] = []
    total: int = 0
    limit: int = 30
    offset: int = 0
    has_more: bool = False


class AgentConversationMessagesOut(CamelModel):
    conversation_id: str
    messages: list[AgentMessageOut] = []


class AgentConfirmationIn(CamelModel):
    answer_version: int = Field(ge=1)
    action: Literal["confirm", "reject"]
    comment: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=64)


class AgentConfirmationOut(CamelModel):
    confirmation_id: int
    run_id: str
    answer_version: int
    action: str
    actor_id: str
    created_at: str


class AgentAuditEventOut(CamelModel):
    id: int
    event_type: str
    actor_id: str
    answer_version: int | None
    payload: dict
    created_at: str


class AgentAuditOut(CamelModel):
    events: list[AgentAuditEventOut] = []


class AgentLlmCallOut(CamelModel):
    id: int
    round: int
    purpose: str
    model: str
    status: str
    error_code: str | None
    message_count: int
    request_sha256: str
    request_preview: list
    tool_names: list
    response_preview: dict
    usage: dict
    duration_ms: int
    started_at: str


class AgentLlmCallListOut(CamelModel):
    calls: list[AgentLlmCallOut] = []


class MemoryConclusionOut(CamelModel):
    run_id: str
    answer_version: int
    answer: str
    confirmed_by: str
    confirmed_at: str


class MemoryEventOut(CamelModel):
    id: int
    event_type: str
    actor_id: str
    payload: dict
    created_at: str


class ConversationMemoryOut(CamelModel):
    conversation_id: str
    scenario_id: str | None
    entities: dict[str, list[str]]
    allowed_keys: list[str]
    history_from_message_id: int | None
    total_messages: int
    carried_messages: int
    confirmed_conclusions: list[MemoryConclusionOut]
    version: int
    updated_by: str | None
    updated_at: str | None
    events: list[MemoryEventOut]


class ConversationMemoryPatchIn(CamelModel):
    # 只改出现的键；空数组表示删除该键
    entities: dict[str, list[str]] = Field(min_length=1, max_length=10)
    expected_version: int | None = None


class AgentEvidenceOut(CamelModel):
    evidence_id: str
    source_type: str
    source_ref: dict
    snapshot: dict | list
    content_hash: str
    data_version: int
    created_at: str


class AgentEvidenceListOut(CamelModel):
    evidence: list[AgentEvidenceOut] = []


class AgentStatsOut(CamelModel):
    total_runs: int
    status_counts: dict[str, int]
    blocked_by_category: dict[str, int]
    conclusion_runs: int
    conclusions_with_evidence: int
    evidence_count: int
    tool_usage: dict[str, int]
    confirmations: dict[str, int]
    avg_duration_ms: int
    p95_duration_ms: int
    avg_total_tokens: int
    generated_at: str


class DdStepIn(CamelModel):
    """单步尽调核对请求：按维度直接跑对应工具。"""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    step: Literal["business", "finance", "opinion", "fraud", "credit-risk", "report"]
    enterprise_id: str | None = Field(default=None, max_length=64)
    application_id: str | None = Field(default=None, max_length=64)


class DdStepToolOut(CamelModel):
    tool_name: str
    status: Literal["ok", "error", "skipped"]
    error_code: str | None = None
    message: str | None = None
    data: object | None = None


class DdStepOut(CamelModel):
    step: str
    label: str
    status: Literal["ok", "partial", "error"]
    enterprise_id: str | None = None
    application_id: str | None = None
    tools: list[DdStepToolOut]
    note: str

class WorkspaceAssetOut(CamelModel):
    apply_amount: float | None = None
    report_generated_at: str
    id: str
    scenario_id: str
    application_id: str | None
    enterprise_id: str | None
    enterprise_name: str | None
    conversation_id: str | None
    run_id: str
    kind: str
    title: str
    summary: str | None
    evidence_count: int
    content_sha256: str | None
    created_by: str
    created_at: str
    updated_at: str


class WorkspaceAssetListOut(CamelModel):
    assets: list[WorkspaceAssetOut] = []
    total: int
    limit: int
    offset: int
    has_more: bool


class WorkspaceAssetDetailOut(WorkspaceAssetOut):
    """报告详情：与列表同一投影（报告不再有状态与流转记录）。"""
