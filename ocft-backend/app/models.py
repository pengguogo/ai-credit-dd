"""ORM 模型 — 演示业务表、赛题 04 尽调事实表 + Agent 执行表。

@why 业务表时间戳存 ISO8601 字符串（与样本数据一致）；
     Agent 表时间戳用 UTC DateTime（设计 §6），API 层输出带 Z 的 ISO 8601。
     业务表只存原始字段：评测标签与预存结论（is_fraud / decision / extracted_kpis 等）
     不进运行时库，见 eval/fixtures/sample_labels.json（红线 R4/R5）。
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class CreditApplication(Base):
    __tablename__ = "credit_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(20))
    business_type: Mapped[str] = mapped_column(String(10))
    apply_amount: Mapped[int] = mapped_column(Integer)
    term_months: Mapped[int] = mapped_column(Integer)
    credit_score: Mapped[int] = mapped_column(Integer)
    debt_ratio: Mapped[float] = mapped_column(Float)
    collateral: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_tags: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(10))
    applied_at: Mapped[str] = mapped_column(String(30))


class RiskTransaction(Base):
    __tablename__ = "risk_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    txn_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    account_id: Mapped[str] = mapped_column(String(20), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    amount: Mapped[float] = mapped_column(Float)
    city: Mapped[str] = mapped_column(String(10))
    device_fingerprint: Mapped[str | None] = mapped_column(String(20), nullable=True)
    minutes_since_last_txn: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[str] = mapped_column(String(30))


class ClaimCase(Base):
    __tablename__ = "claim_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    insurant: Mapped[str] = mapped_column(String(20))
    insurance_type: Mapped[str] = mapped_column(String(10))
    incident_date: Mapped[str] = mapped_column(String(10))
    reported_at: Mapped[str] = mapped_column(String(30))
    claim_amount: Mapped[int] = mapped_column(Integer)
    materials: Mapped[list] = mapped_column(JSON, default=list)
    missing_materials: Mapped[list] = mapped_column(JSON, default=list)


class FinDoc(Base):
    __tablename__ = "fin_docs"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    doc_type: Mapped[str] = mapped_column(String(10))
    company: Mapped[str] = mapped_column(String(30))
    period: Mapped[str] = mapped_column(String(20))
    raw_text: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(60))


# ---- 赛题 04 企业尽调事实表。risk_level_summary 是外部输入汇总，不是本系统结论。 ----


class LoanApplication(Base):
    __tablename__ = "loan_application"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    enterprise_id: Mapped[str] = mapped_column(String(32), index=True)
    apply_amount: Mapped[float] = mapped_column(Float)
    loan_purpose: Mapped[str] = mapped_column(String(200))
    loan_term_months: Mapped[int] = mapped_column(Integer)
    apply_date: Mapped[str] = mapped_column(String(20))
    guarantee_type: Mapped[str] = mapped_column(String(40))
    # pending 待处理（初始） | pending_review 待审核 | approved 审核通过 | rejected 审核不通过
    # 业务状态，非评测标签：生成尽调报告后 待处理 -> 待审核，人工审核后 -> 审核通过 / 审核不通过
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # 人工审核结论的留痕：审核原因、审核人、审核时间（ISO 8601 带 Z）。未审核时为空。
    # @why 审核必须说明理由：贷款申请列表的审核弹窗要求填写原因，与状态写在同一事务里。
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(String(30), nullable=True)


class EnterpriseBasic(Base):
    __tablename__ = "enterprise_basic"

    id: Mapped[int] = mapped_column(primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    enterprise_name: Mapped[str] = mapped_column(String(120))
    credit_code: Mapped[str] = mapped_column(String(32))
    legal_person: Mapped[str] = mapped_column(String(40))
    legal_person_id: Mapped[str] = mapped_column(String(40))
    register_capital: Mapped[float] = mapped_column(Float)
    registered_capital_paid: Mapped[float] = mapped_column(Float)
    establish_date: Mapped[str] = mapped_column(String(20))
    enterprise_type: Mapped[str] = mapped_column(String(40))
    industry: Mapped[str] = mapped_column(String(40))
    register_address: Mapped[str] = mapped_column(String(200))
    business_scope: Mapped[str] = mapped_column(Text)
    employee_count: Mapped[int] = mapped_column(Integer)
    related_enterprise_count: Mapped[int] = mapped_column(Integer)
    business_status: Mapped[str] = mapped_column(String(20))
    legal_person_dishonest: Mapped[str] = mapped_column(String(8))
    legal_person_consumption_limit: Mapped[str] = mapped_column(String(8))
    actual_controller: Mapped[str] = mapped_column(String(40))


class EnterpriseShareholder(Base):
    __tablename__ = "enterprise_shareholder"

    id: Mapped[int] = mapped_column(primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(32), index=True)
    shareholder_name: Mapped[str] = mapped_column(String(120))
    shareholder_type: Mapped[str] = mapped_column(String(40))
    shareholding_ratio: Mapped[float] = mapped_column(Float)
    contribution_amount: Mapped[float] = mapped_column(Float)
    contribution_ratio: Mapped[float] = mapped_column(Float)


class EnterpriseFinance(Base):
    __tablename__ = "enterprise_finance"
    __table_args__ = (UniqueConstraint("enterprise_id", "year", name="uq_finance_enterprise_year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(32), index=True)
    year: Mapped[int] = mapped_column(Integer)
    revenue: Mapped[float] = mapped_column(Float)
    net_profit: Mapped[float] = mapped_column(Float)
    total_assets: Mapped[float] = mapped_column(Float)
    total_liabilities: Mapped[float] = mapped_column(Float)
    operating_cashflow: Mapped[float] = mapped_column(Float)
    accounts_receivable: Mapped[float] = mapped_column(Float)
    inventory: Mapped[float] = mapped_column(Float)
    fixed_assets: Mapped[float] = mapped_column(Float)
    short_term_loan: Mapped[float] = mapped_column(Float)
    long_term_loan: Mapped[float] = mapped_column(Float)
    accounts_payable: Mapped[float] = mapped_column(Float)
    other_receivable: Mapped[float] = mapped_column(Float)
    prepayment: Mapped[float] = mapped_column(Float)
    owners_equity: Mapped[float] = mapped_column(Float)
    rd_expense: Mapped[float] = mapped_column(Float)
    sales_expense: Mapped[float] = mapped_column(Float)
    admin_expense: Mapped[float] = mapped_column(Float)
    finance_expense: Mapped[float] = mapped_column(Float)
    audit_opinion: Mapped[str] = mapped_column(String(40))


class EnterpriseLawsuit(Base):
    __tablename__ = "enterprise_lawsuit"

    id: Mapped[int] = mapped_column(primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(32), index=True)
    case_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    case_number: Mapped[str] = mapped_column(String(80))
    case_type: Mapped[str] = mapped_column(String(40))
    cause: Mapped[str] = mapped_column(String(80))
    filing_date: Mapped[str] = mapped_column(String(20))
    case_status: Mapped[str] = mapped_column(String(20))
    litigation_role: Mapped[str] = mapped_column(String(20))
    amount: Mapped[float] = mapped_column(Float)


class EnterprisePublicOpinion(Base):
    __tablename__ = "enterprise_public_opinion"

    id: Mapped[int] = mapped_column(primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(32), index=True)
    event_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    event_date: Mapped[str] = mapped_column(String(20))
    event_type: Mapped[str] = mapped_column(String(40))
    event_source: Mapped[str] = mapped_column(String(80))
    event_content: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[str] = mapped_column(String(8))
    impact_level: Mapped[str] = mapped_column(String(8))


class EnterpriseRelated(Base):
    __tablename__ = "enterprise_related"

    id: Mapped[int] = mapped_column(primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(32), index=True)
    related_enterprise_name: Mapped[str] = mapped_column(String(120))
    relation_type: Mapped[str] = mapped_column(String(40))
    shareholding_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_guarantee_circle: Mapped[str] = mapped_column(String(8))


class EnterpriseGuarantee(Base):
    __tablename__ = "enterprise_guarantee"

    id: Mapped[int] = mapped_column(primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(32), index=True)
    guaranteed_party: Mapped[str] = mapped_column(String(120))
    guarantee_amount: Mapped[float] = mapped_column(Float)
    guarantee_type: Mapped[str] = mapped_column(String(40))
    guarantee_period: Mapped[str] = mapped_column(String(40))
    is_overdue: Mapped[str] = mapped_column(String(8))


class EnterpriseRisk(Base):
    """外部风险汇总。risk_level_summary 只作对照，评分卡不得把它当作结论。"""

    __tablename__ = "enterprise_risk"

    id: Mapped[int] = mapped_column(primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    existing_loan_balance: Mapped[float] = mapped_column(Float)
    overdue_count: Mapped[int] = mapped_column(Integer)
    overdue_amount: Mapped[float] = mapped_column(Float)
    external_guarantee_amount: Mapped[float] = mapped_column(Float)
    public_opinion_score: Mapped[float] = mapped_column(Float)
    risk_level_summary: Mapped[str] = mapped_column(String(20))
    abnormal_operation: Mapped[str] = mapped_column(String(80))


class SchemaRelationship(Base):
    __tablename__ = "schema_relationships"

    id: Mapped[int] = mapped_column(primary_key=True)
    main_table: Mapped[str] = mapped_column(String(40))
    primary_key: Mapped[str] = mapped_column(String(80))
    child_table: Mapped[str] = mapped_column(String(40))
    foreign_key: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(String(200))


# ---- Agent 执行表（设计 §6：会话 / 执行 / 轨迹 / 证据 / 审计） ----


class CsvImportAudit(Base):
    """只追加的导入操作审计；不占用或伪造 Agent run。"""
    __tablename__ = "csv_import_audits"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16))
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    # 会话从第一次提问起绑定场景；历史列表按它分组。空值只出现在迁移回填之前。
    scenario_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    context_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    # assistant 消息关联产生它的 run，支持溯源
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    # run_ + uuid 短码
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    scenario_id: Mapped[str] = mapped_column(String(32), default="enterprise_dd")
    question: Mapped[str] = mapped_column(Text)
    # running | succeeded | needs_confirmation | needs_clarification | blocked | insufficient_evidence | failed
    status: Mapped[str] = mapped_column(String(24), default="running")
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 上下文快照：本次 run 传入模型的消息范围等，可复核
    context_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    model: Mapped[str] = mapped_column(String(40))
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    data_version: Mapped[int] = mapped_column(Integer, default=1)
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ToolTrace(Base):
    __tablename__ = "tool_traces"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String(64))
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    # 结果引用：证据 ID 列表或摘要文本
    result_ref: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16))  # ok | error
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Evidence(Base):
    __tablename__ = "evidence"

    # ev_ + uuid 短码
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    source_type: Mapped[str] = mapped_column(String(24))  # db_query | document | calculation
    # 表/主键/过滤条件，或文档 ID — 设计 §6：足以重现变化前数据
    source_ref: Mapped[dict] = mapped_column(JSON, default=dict)
    # 当次结果快照（行/片段原文）
    snapshot: Mapped[dict | list] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    data_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AnswerConfirmation(Base):
    """结论确认（设计 §7 confirmations）：绑定 run + 答案版本，幂等可查。

    @why 确认人可以不是提问人（业务复核角色），故不做 owner 校验，
         身份以 X-Actor-Id 落 actor_id 字段留痕。
    """

    __tablename__ = "answer_confirmations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    answer_version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(8))  # confirm | reject
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    # 幂等键：相同 key 重复提交返回同一 confirmationId
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AuditLog(Base):
    """追加式审计事件：只 INSERT，禁止 UPDATE/DELETE（应用层约定）。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    # run_started | run_finished | compliance_blocked | pii_redacted | confirmation_created | confirmation_rejected
    event_type: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(String(64))
    answer_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RunEvent(Base):
    """run 阶段事件（SSE 与节点耗时的持久化来源），只追加。

    @why 与 run / trace / audit 同事务写入；执行中的实时推送走内存事件总线，
         结束后从本表重放，二者事件序号一致，支持 Last-Event-ID 续传。
    """

    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    event_index: Mapped[int] = mapped_column(Integer)
    # run_started | compliance_checked | compliance_blocked | llm_call_finished |
    # tool_started | tool_finished | run_finished
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LlmCall(Base):
    """外部大模型调用审计（待办 0-5；通用纪律第 2 条：外部调用的入参、时间、用途须留存）。只追加。

    @why 不存完整 messages：送出前已脱敏，但全文体量大且含系统提示；
         存每条消息的脱敏预览 + 整个请求体的 sha256，评审抽查时既能看到外送了什么，
         又能用 hash 证明预览对应的就是那一次请求。与 run 同事务写入。
    """

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    round: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(32))          # tool_loop 等
    model: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16))           # ok | error
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer)
    request_sha256: Mapped[str] = mapped_column(String(64))
    # [{role, chars, preview}]，preview 为脱敏后的截断文本
    request_preview: Mapped[list] = mapped_column(JSON, default=list)
    tool_names: Mapped[list] = mapped_column(JSON, default=list)   # 本次声明给模型的工具
    # {content, toolCalls:[{name, args}]}，均为脱敏后的截断文本
    response_preview: Mapped[dict] = mapped_column(JSON, default=dict)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ConversationMemory(Base):
    """会话当前记忆（待办 0-6：记忆可查看、可纠正、可清除）。

    @why 记忆 = 实体槽位 + 带入模型的历史范围。每次 run 结束后同步槽位；
         人工纠正 / 清除只改这里，不改历史 run 的 context_snapshot（快照保持可复核）。
         _build_history 优先读本表，没有记录的旧会话退回读最近一次 run 的快照。
    """

    __tablename__ = "conversation_memories"

    conversation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entities: Mapped[dict] = mapped_column(JSON, default=dict)
    # 只把 id >= 该值的消息带入模型；None 表示不截断。清除历史时设为当前最大消息 id + 1
    history_from_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 乐观锁：纠正时可带 expectedVersion，避免覆盖别人刚做的修改
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class MemoryEvent(Base):
    """记忆变更审计：只追加。memory_corrected | memory_cleared。payload 记前后值（已脱敏）。"""

    __tablename__ = "memory_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ---- 系统管理：角色 / 用户 / 会话（演示登录；密码只存哈希） ----


class SysRole(Base):
    __tablename__ = "sys_roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(200), default="")
    # 权限码列表，如 ["admin", "workbench", "dd_steps"]
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class SysUser(Base):
    __tablename__ = "sys_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(200))
    role_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | disabled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class SysSession(Base):
    __tablename__ = "sys_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---- 任务与资产：尽调任务的建档、检索、状态跟踪与归档（评审维度②「会议与资产管理」） ----


class WorkspaceAsset(Base):
    """一次尽调任务的产出物档案：报告正文摘要 + 同 run 证据。

    @why 报告本身不需要状态：报告是尽调的产出物，审核结论记在贷款申请（loan_application.status），
          这里只负责建档与检索。正文不复制，档案指向 runId，报告版本与证据始终以 run/evidence 为准。
    """

    __tablename__ = "workspace_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(40), index=True)
    application_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    enterprise_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    run_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="report")  # report | evidence | export
    title: Mapped[str] = mapped_column(String(200))
    # 历史列：早期版本用于报告复核流转，现已不对内对外暴露；保留列以免破坏既有库与历史行。
    status: Mapped[str] = mapped_column(String(20), default="pending_review", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkspaceAssetEvent(Base):
    """历史列：早期报告复核流转事件（只追加）。报告不再有状态，不再写入新事件。"""

    __tablename__ = "workspace_asset_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str] = mapped_column(String(64))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
