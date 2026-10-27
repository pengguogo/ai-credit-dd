"""credit_review 场景工具 — 查数 / 规则引擎（R001-R005）。

@why handler 形参名用 camelCase：与 LLM 协议参数名（契约 §内部 ToolResult）
     一一对应，省一层映射；仅此边界允许，内部字段仍按 snake_case 存取。
     字段白名单显式列举：未来新增列（含评测标签）不会意外泄漏给 LLM。
     R001-R005 规则只在本文件实现，结论运行时实时计算。
"""
from pydantic.alias_generators import to_camel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..domain.types import EvidenceRecord, ToolResult
from ..models import CreditApplication
from .registry import register_tool

# @why 近期查询频繁/经营流水下滑本质是多头借贷的前兆与伴生信号，并入 R003 判定
R003_TAGS = {"多头借贷", "近期查询频繁", "经营流水下滑"}

# 输出白名单：CreditApplication 原始业务字段。status 是申请流转状态（样本统一 pending），
# 不是审批结论；审批结论只由 run_credit_rules 实时计算
_FIELDS = ["application_id", "customer_name", "business_type", "apply_amount",
           "term_months", "credit_score", "debt_ratio", "collateral",
           "risk_tags", "status", "applied_at"]

TABLE = "credit_applications"


def _row_camel(row: CreditApplication) -> dict:
    return {to_camel(k): getattr(row, k) for k in _FIELDS}


def _find(db: Session, application_id: str) -> CreditApplication | None:
    return (db.query(CreditApplication)
            .filter(CreditApplication.application_id == application_id)
            .first())


def _evidence(row: CreditApplication, calc: str | None, run_ctx: dict) -> EvidenceRecord:
    source_ref = {"table": TABLE, "keys": {"applicationId": row.application_id}}
    source_type = "db_query"
    if calc:
        source_type = "calculation"
        source_ref["calc"] = calc
    return EvidenceRecord(source_type=source_type, source_ref=source_ref,
                          snapshot=_row_camel(row), data_version=run_ctx["data_version"])


@register_tool(
    "search_credit_applications",
    "按状态或关键词（客户姓名/申请编号）检索信贷申请，返回申请编号与概要。"
    "用户未提供申请编号时先用本工具定位。",
    {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "关键词，匹配客户姓名或申请编号"},
            "status": {"type": "string", "description": "申请状态过滤，如 pending"},
            "limit": {"type": "integer", "description": "返回条数上限，默认 10，最大 20"},
        },
        "required": [],
    },
)
def search_credit_applications(db: Session, run_ctx: dict,
                               keyword: str | None = None,
                               status: str | None = None,
                               limit: int = 10) -> tuple[ToolResult, list[EvidenceRecord], dict]:
    limit = max(1, min(int(limit), 20))
    query = db.query(CreditApplication)
    if status:
        query = query.filter(CreditApplication.status == status)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(CreditApplication.customer_name.like(like),
                                 CreditApplication.application_id.like(like)))
    rows = query.order_by(CreditApplication.applied_at.desc()).limit(limit).all()
    if not rows:
        return (ToolResult.success({"total": 0, "applications": []}), [],
                {"keyword": keyword, "status": status, "limit": limit})
    applications = [_row_camel(row) for row in rows]
    evidence = [EvidenceRecord(
        source_type="db_query",
        source_ref={"table": TABLE, "filters": {
            "keyword": keyword, "status": status, "limit": limit}},
        snapshot=applications, data_version=run_ctx["data_version"])]
    return (ToolResult.success({"total": len(applications), "applications": applications}),
            evidence, {"keyword": keyword, "status": status, "limit": limit})


@register_tool(
    "get_credit_application",
    "按申请编号获取单笔信贷申请的完整业务数据。",
    {
        "type": "object",
        "properties": {
            "applicationId": {"type": "string", "description": "申请编号，如 CA-2026-0189"},
        },
        "required": ["applicationId"],
    },
)
def get_credit_application(db: Session, run_ctx: dict,
                           applicationId: str) -> tuple[ToolResult, list[EvidenceRecord], dict]:
    row = _find(db, applicationId)
    if row is None:
        return (ToolResult.failure("not_found", f"申请 {applicationId} 不存在"),
                [], {"applicationId": applicationId})
    data = _row_camel(row)
    return (ToolResult.success(data), [_evidence(row, None, run_ctx)],
            {"applicationId": applicationId})


@register_tool(
    "run_credit_rules",
    "对指定信贷申请执行 R001-R005 审批规则引擎，返回逐条判定与规则引擎结论"
    "（approved / manual_review / rejected）。给出审批意见前必须调用。",
    {
        "type": "object",
        "properties": {
            "applicationId": {"type": "string", "description": "申请编号，如 CA-2026-0189"},
        },
        "required": ["applicationId"],
    },
)
def run_credit_rules(db: Session, run_ctx: dict,
                     applicationId: str) -> tuple[ToolResult, list[EvidenceRecord], dict]:
    row = _find(db, applicationId)
    if row is None:
        return (ToolResult.failure("not_found", f"申请 {applicationId} 不存在"),
                [], {"applicationId": applicationId})
    rule_results = _run_rules(row)
    decision = _decide(rule_results)
    data = {
        "applicationId": row.application_id,
        "decision": decision,
        "ruleResults": rule_results,
    }
    return (ToolResult.success(data), [_evidence(row, "R001-R005", run_ctx)],
            {"applicationId": applicationId})


def _run_rules(row: CreditApplication) -> list[dict]:
    """R001-R005 逐条判定 — 比赛当天在此追加新规则即可。"""
    ltv = (row.apply_amount / row.collateral) if row.collateral else None
    tags = row.risk_tags or []
    has_tag = lambda tag: tag in tags  # noqa: E731
    return [
        {"ruleId": "R001", "name": "征信评分下限", "severity": "block",
         "passed": row.credit_score >= 620,
         "detail": f"征信评分 {row.credit_score}，下限 620"},
        {"ruleId": "R002", "name": "负债收入比上限", "severity": "warn",
         "passed": row.debt_ratio <= 0.55,
         "detail": f"负债收入比 {row.debt_ratio:.2f}，上限 0.55"},
        {"ruleId": "R003", "name": "多头借贷检查", "severity": "warn",
         "passed": not (set(tags) & R003_TAGS),
         "detail": f"风险标签：{'、'.join(tags) if tags else '无'}"},
        {"ruleId": "R004", "name": "房抵贷抵押率", "severity": "block",
         "passed": ltv is None or ltv <= 0.7,
         "detail": "非房抵贷，不适用" if ltv is None else f"抵押率 {ltv:.2f}，上限 0.70"},
        {"ruleId": "R005", "name": "评估价虚高", "severity": "warn",
         "passed": not has_tag("评估价虚高风险"),
         "detail": "未触发人工评估复核" if not has_tag("评估价虚高风险") else "触发人工评估复核"},
    ]


def _decide(results: list[dict]) -> str:
    """block 失败直接拒绝；warn 失败 ≥2 视为综合风险过高同样拒绝。"""
    failed = [r for r in results if not r["passed"]]
    if any(r["severity"] == "block" for r in failed) or len(failed) >= 2:
        return "rejected"
    if failed:
        return "manual_review"
    return "approved"
