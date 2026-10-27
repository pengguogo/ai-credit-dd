"""业务事实目录 — 按场景只读列出原始字段，供智能尽调页表格展示。

不含评测标签，也不计算审批/拦截/核赔结论。客服场景没有业务表。
筛选在数据库里完成，避免一次拉出整表。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Query, Session

from ..api_errors import ApiError
from ..compliance.pii import redact_obj
from ..models import (
    EnterpriseBasic,
    EnterpriseFinance,
    EnterpriseGuarantee,
    EnterpriseLawsuit,
    EnterprisePublicOpinion,
    EnterpriseRelated,
    EnterpriseRisk,
    EnterpriseShareholder,
    LoanApplication,
    SchemaRelationship,
    WorkspaceAsset,
)

# 智能尽调页一次最多展示这么多行；matched 仍是筛选后的全量条数。
_ROW_LIMIT = 100
# 贷款申请状态：待处理（尚未生成尽调报告）-> 待审核（已生成报告、等待人工审核）
# -> 审核通过 / 审核不通过。旧词（待尽调 / 待审批 / 已通过 / 已驳回）保留为搜索别名。
_STATUS_WORDS = {
    "待处理": "pending", "pending": "pending", "待尽调": "pending", "pending_dd": "pending",
    "待审核": "pending_review", "pending_review": "pending_review", "待审批": "pending_review",
    "审核通过": "approved", "approved": "approved", "已通过": "approved",
    "审核不通过": "rejected", "rejected": "rejected", "已驳回": "rejected",
}
# 筛选值 → 命中的状态集合；open = 未审结（待处理 + 待审核），供智能尽调列表只看可尽调的申请
_APP_STATUS_FILTERS: dict[str, tuple[str, ...]] = {
    "pending": ("pending",), "pending_review": ("pending_review",),
    "approved": ("approved",), "rejected": ("rejected",),
    "open": ("pending", "pending_review"),
}
_APP_STATUS_FILTER_NAMES = "pending / pending_review / approved / rejected / open"


@dataclass(frozen=True)
class _TableSpec:
    kind: str
    title: str
    note: str
    columns: tuple[tuple[str, str], ...]
    build: Callable[[Session, str], tuple[int, int, list[dict]]]


def _like(column, keyword: str):
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return cast(column, String).like(f"%{escaped}%", escape="\\")


def _apply_keyword(query: Query, keyword: str, columns: list, status_column=None) -> Query:
    if not keyword:
        return query
    clauses = [_like(column, keyword) for column in columns]
    compact = keyword.replace(",", "").replace("，", "")
    if compact.isdigit() and compact != keyword:
        clauses.extend(_like(column, compact) for column in columns)
    status = _STATUS_WORDS.get(keyword)
    if status_column is not None and status is not None:
        clauses.append(status_column == status)
    return query.filter(or_(*clauses))


def _pack(spec: _TableSpec, rows: list[dict], total: int, matched: int, query: str,
          *, approval_status: str = "", status_counts: dict[str, int] | None = None) -> dict:
    return {
        "title": spec.title,
        "note": spec.note,
        "kind": spec.kind,
        "query": query,
        "approval_status": approval_status,
        "total": total,
        "matched": matched,
        "limit": _ROW_LIMIT,
        "columns": [{"key": key, "label": label} for key, label in spec.columns],
        "rows": redact_obj(rows),
        "status_counts": status_counts or {},
    }


def _load(query: Query, keyword: str, columns: list, to_row) -> tuple[int, int, list[dict]]:
    total = query.order_by(None).count()
    filtered = _apply_keyword(query, keyword, columns, None)
    matched = filtered.order_by(None).count()
    rows = [to_row(row) for row in filtered.limit(_ROW_LIMIT).all()]
    return total, matched, rows


def _dump(row: Any, fields: list[tuple[str, str]]) -> dict:
    """fields: (jsonKey, attr_name)。附带内部 id，供列表编辑/删除（不在 columns 中展示）。"""
    return {"id": row.id, **{key: getattr(row, attr) for key, attr in fields}}


def _application_status_counts(db: Session) -> dict[str, int]:
    rows = db.query(LoanApplication.status).all()
    counts = {"pending": 0, "pending_review": 0, "approved": 0, "rejected": 0}
    for (status,) in rows:
        # 未知/历史状态按初始态计数，避免总数对不上
        counts[status if status in counts else "pending"] += 1
    return counts


def _applications(db: Session, keyword: str,
                  approval_status: str = "") -> tuple[int, int, list[dict]]:
    # @why 不展示、不检索 risk_level_summary：它与公开答案评级一致，运行时一律不读（ADR-0008 决策 1）
    query = (db.query(LoanApplication, EnterpriseBasic)
             .join(EnterpriseBasic, LoanApplication.enterprise_id == EnterpriseBasic.enterprise_id)
             .order_by(LoanApplication.apply_date.desc()))
    total = query.order_by(None).count()
    if approval_status in _APP_STATUS_FILTERS:
        query = query.filter(LoanApplication.status.in_(_APP_STATUS_FILTERS[approval_status]))
    filtered = _apply_keyword(
        query, keyword,
        [LoanApplication.application_id, LoanApplication.enterprise_id,
         EnterpriseBasic.enterprise_name, LoanApplication.loan_purpose,
         LoanApplication.guarantee_type, LoanApplication.apply_date,
         LoanApplication.status],
        LoanApplication.status,
    )
    matched = filtered.order_by(None).count()
    rows = [{
        "id": loan.id,
        "applicationId": loan.application_id,
        "enterpriseId": loan.enterprise_id,
        "enterpriseName": basic.enterprise_name,
        "applyAmount": loan.apply_amount,
        "loanPurpose": loan.loan_purpose,
        "loanTermMonths": loan.loan_term_months,
        "guaranteeType": loan.guarantee_type,
        "applyDate": loan.apply_date,
        "status": loan.status or "pending",
        # 人工审核留痕（未审核时为空），供列表展示审核理由
        "reviewReason": loan.review_reason,
        "reviewedBy": loan.reviewed_by,
        "reviewedAt": loan.reviewed_at,
    } for loan, basic in filtered.limit(_ROW_LIMIT).all()]
    _attach_has_report(db, rows)
    return total, matched, rows


def _attach_has_report(db: Session, rows: list[dict]) -> None:
    """补 hasReport：该申请是否已建档尽调报告。

    @why 智能尽调列表的「查看报告」按报告是否已生成决定可点 / 置灰，不做前端猜测；
         一次 IN 查询覆盖当前页，避免逐行查询。
    """
    application_ids = [row["applicationId"] for row in rows if row.get("applicationId")]
    if not application_ids:
        for row in rows:
            row["hasReport"] = False
        return
    reported = {
        application_id for (application_id,) in
        db.query(WorkspaceAsset.application_id)
        .filter(WorkspaceAsset.application_id.in_(application_ids),
                WorkspaceAsset.kind == "report")
        .distinct().all()
    }
    for row in rows:
        row["hasReport"] = row.get("applicationId") in reported


def _enterprises(db: Session, keyword: str) -> tuple[int, int, list[dict]]:
    query = db.query(EnterpriseBasic).order_by(EnterpriseBasic.enterprise_id.asc())
    fields = [
        ("enterpriseId", "enterprise_id"), ("enterpriseName", "enterprise_name"),
        ("industry", "industry"), ("enterpriseType", "enterprise_type"),
        ("establishDate", "establish_date"), ("registerCapital", "register_capital"),
        ("businessStatus", "business_status"), ("employeeCount", "employee_count"),
    ]
    return _load(
        query, keyword,
        [EnterpriseBasic.enterprise_id, EnterpriseBasic.enterprise_name,
         EnterpriseBasic.industry, EnterpriseBasic.enterprise_type,
         EnterpriseBasic.establish_date, EnterpriseBasic.business_status],
        lambda row: _dump(row, fields),
    )


def _simple(db: Session, model, keyword: str, order_cols, filter_cols, fields: list[tuple[str, str]]):
    query = db.query(model).order_by(*order_cols)
    return _load(query, keyword, filter_cols, lambda row: _dump(row, fields))


_SPECS: dict[str, _TableSpec] = {
    "enterprises": _TableSpec(
        "enterprises", "企业基础信息",
        "工商基础字段只供对照；尽调结论由工具实时计算。",
        (
            ("enterpriseId", "企业编号"), ("enterpriseName", "企业名称"),
            ("industry", "行业"), ("enterpriseType", "企业类型"),
            ("establishDate", "成立日期"), ("registerCapital", "注册资本(万)"),
            ("businessStatus", "经营状态"), ("employeeCount", "员工人数"),
        ),
        _enterprises,
    ),
    "applications": _TableSpec(
        "applications", "审批表",
        "金额单位为万元。状态为业务流转（待处理 / 待审核 / 审核通过 / 审核不通过），风险评级由评分卡实时计算不在此展示。",
        (
            ("applicationId", "贷款编号"), ("enterpriseId", "企业编号"),
            ("enterpriseName", "企业名称"), ("applyAmount", "申请额(万元)"),
            ("loanPurpose", "用途"), ("loanTermMonths", "期限(月)"),
            ("guaranteeType", "担保"), ("applyDate", "申请日期"),
            ("status", "状态"),
        ),
        lambda db, kw: _applications(db, kw),
    ),
    "shareholders": _TableSpec(
        "shareholders", "股东信息",
        "enterprise_shareholder：股东与出资比例，金额单位万元。",
        (
            ("enterpriseId", "企业编号"), ("shareholderName", "股东名称"),
            ("shareholderType", "股东类型"), ("shareholdingRatio", "持股比例"),
            ("contributionAmount", "出资金额"), ("contributionRatio", "出资比例"),
        ),
        lambda db, kw: _simple(
            db, EnterpriseShareholder, kw,
            [EnterpriseShareholder.enterprise_id.asc(), EnterpriseShareholder.shareholding_ratio.desc()],
            [EnterpriseShareholder.enterprise_id, EnterpriseShareholder.shareholder_name,
             EnterpriseShareholder.shareholder_type],
            [("enterpriseId", "enterprise_id"), ("shareholderName", "shareholder_name"),
             ("shareholderType", "shareholder_type"), ("shareholdingRatio", "shareholding_ratio"),
             ("contributionAmount", "contribution_amount"), ("contributionRatio", "contribution_ratio")],
        ),
    ),
    "finances": _TableSpec(
        "finances", "财务数据",
        "enterprise_finance：近三年科目，金额单位万元。",
        (
            ("enterpriseId", "企业编号"), ("year", "年份"),
            ("revenue", "营收"), ("netProfit", "净利润"),
            ("totalAssets", "总资产"), ("totalLiabilities", "总负债"),
            ("operatingCashflow", "经营现金流"), ("accountsReceivable", "应收账款"),
            ("inventory", "存货"), ("ownersEquity", "所有者权益"),
            ("auditOpinion", "审计意见"),
        ),
        lambda db, kw: _simple(
            db, EnterpriseFinance, kw,
            [EnterpriseFinance.enterprise_id.asc(), EnterpriseFinance.year.desc()],
            [EnterpriseFinance.enterprise_id, EnterpriseFinance.year, EnterpriseFinance.audit_opinion],
            [("enterpriseId", "enterprise_id"), ("year", "year"), ("revenue", "revenue"),
             ("netProfit", "net_profit"), ("totalAssets", "total_assets"),
             ("totalLiabilities", "total_liabilities"), ("operatingCashflow", "operating_cashflow"),
             ("accountsReceivable", "accounts_receivable"), ("inventory", "inventory"),
             ("ownersEquity", "owners_equity"), ("auditOpinion", "audit_opinion")],
        ),
    ),
    "public_opinions": _TableSpec(
        "public_opinions", "舆情事件",
        "enterprise_public_opinion：舆情事件与情感、影响等级。",
        (
            ("enterpriseId", "企业编号"), ("eventId", "事件编号"),
            ("eventDate", "事件日期"), ("eventType", "事件类型"),
            ("eventSource", "来源"), ("sentiment", "情感"),
            ("impactLevel", "影响等级"), ("eventContent", "内容"),
        ),
        lambda db, kw: _simple(
            db, EnterprisePublicOpinion, kw,
            [EnterprisePublicOpinion.enterprise_id.asc(), EnterprisePublicOpinion.event_date.desc()],
            [EnterprisePublicOpinion.enterprise_id, EnterprisePublicOpinion.event_id,
             EnterprisePublicOpinion.event_type, EnterprisePublicOpinion.sentiment,
             EnterprisePublicOpinion.event_content],
            [("enterpriseId", "enterprise_id"), ("eventId", "event_id"), ("eventDate", "event_date"),
             ("eventType", "event_type"), ("eventSource", "event_source"),
             ("sentiment", "sentiment"), ("impactLevel", "impact_level"),
             ("eventContent", "event_content")],
        ),
    ),
    "lawsuits": _TableSpec(
        "lawsuits", "涉诉案件",
        "enterprise_lawsuit：诉讼案件，金额单位万元。",
        (
            ("enterpriseId", "企业编号"), ("caseId", "案件编号"),
            ("caseNumber", "案号"), ("caseType", "案件类型"),
            ("cause", "案由"), ("filingDate", "立案日期"),
            ("caseStatus", "状态"), ("litigationRole", "诉讼地位"),
            ("amount", "金额"),
        ),
        lambda db, kw: _simple(
            db, EnterpriseLawsuit, kw,
            [EnterpriseLawsuit.enterprise_id.asc(), EnterpriseLawsuit.filing_date.desc()],
            [EnterpriseLawsuit.enterprise_id, EnterpriseLawsuit.case_id,
             EnterpriseLawsuit.case_number, EnterpriseLawsuit.case_type,
             EnterpriseLawsuit.cause, EnterpriseLawsuit.case_status],
            [("enterpriseId", "enterprise_id"), ("caseId", "case_id"), ("caseNumber", "case_number"),
             ("caseType", "case_type"), ("cause", "cause"), ("filingDate", "filing_date"),
             ("caseStatus", "case_status"), ("litigationRole", "litigation_role"),
             ("amount", "amount")],
        ),
    ),
    "related": _TableSpec(
        "related", "关联企业",
        "enterprise_related：关联方与是否担保圈。",
        (
            ("enterpriseId", "企业编号"), ("relatedEnterpriseName", "关联企业"),
            ("relationType", "关系类型"), ("shareholdingRatio", "持股比例"),
            ("isGuaranteeCircle", "担保圈"),
        ),
        lambda db, kw: _simple(
            db, EnterpriseRelated, kw,
            [EnterpriseRelated.enterprise_id.asc()],
            [EnterpriseRelated.enterprise_id, EnterpriseRelated.related_enterprise_name,
             EnterpriseRelated.relation_type, EnterpriseRelated.is_guarantee_circle],
            [("enterpriseId", "enterprise_id"), ("relatedEnterpriseName", "related_enterprise_name"),
             ("relationType", "relation_type"), ("shareholdingRatio", "shareholding_ratio"),
             ("isGuaranteeCircle", "is_guarantee_circle")],
        ),
    ),
    "guarantees": _TableSpec(
        "guarantees", "对外担保",
        "enterprise_guarantee：担保金额单位万元。",
        (
            ("enterpriseId", "企业编号"), ("guaranteedParty", "被担保方"),
            ("guaranteeAmount", "担保金额"), ("guaranteeType", "担保类型"),
            ("guaranteePeriod", "担保期限"), ("isOverdue", "是否逾期"),
        ),
        lambda db, kw: _simple(
            db, EnterpriseGuarantee, kw,
            [EnterpriseGuarantee.enterprise_id.asc()],
            [EnterpriseGuarantee.enterprise_id, EnterpriseGuarantee.guaranteed_party,
             EnterpriseGuarantee.guarantee_type, EnterpriseGuarantee.is_overdue],
            [("enterpriseId", "enterprise_id"), ("guaranteedParty", "guaranteed_party"),
             ("guaranteeAmount", "guarantee_amount"), ("guaranteeType", "guarantee_type"),
             ("guaranteePeriod", "guarantee_period"), ("isOverdue", "is_overdue")],
        ),
    ),
    "risks": _TableSpec(
        "risks", "风险汇总",
        # @why 不含外部汇总评级 risk_level_summary：与公开答案评级一致，运行时不展示、不检索（ADR-0008 决策 1）
        "enterprise_risk：存量贷款、逾期、对外担保等风险事实。",
        (
            ("enterpriseId", "企业编号"), ("existingLoanBalance", "存量贷款"),
            ("overdueCount", "逾期次数"), ("overdueAmount", "逾期金额"),
            ("externalGuaranteeAmount", "对外担保"), ("publicOpinionScore", "舆情评分"),
            ("abnormalOperation", "经营异常"),
        ),
        lambda db, kw: _simple(
            db, EnterpriseRisk, kw,
            [EnterpriseRisk.enterprise_id.asc()],
            [EnterpriseRisk.enterprise_id, EnterpriseRisk.abnormal_operation],
            [("enterpriseId", "enterprise_id"), ("existingLoanBalance", "existing_loan_balance"),
             ("overdueCount", "overdue_count"), ("overdueAmount", "overdue_amount"),
             ("externalGuaranteeAmount", "external_guarantee_amount"),
             ("publicOpinionScore", "public_opinion_score"),
             ("abnormalOperation", "abnormal_operation")],
        ),
    ),
    "schema_relationships": _TableSpec(
        "schema_relationships", "表关系",
        "schema_relationships：业务表主外键关系说明。",
        (
            ("mainTable", "主表"), ("primaryKey", "主键"),
            ("childTable", "子表"), ("foreignKey", "外键"),
            ("note", "说明"),
        ),
        lambda db, kw: _simple(
            db, SchemaRelationship, kw,
            [SchemaRelationship.main_table.asc(), SchemaRelationship.child_table.asc()],
            [SchemaRelationship.main_table, SchemaRelationship.child_table,
             SchemaRelationship.primary_key, SchemaRelationship.foreign_key,
             SchemaRelationship.note],
            [("mainTable", "main_table"), ("primaryKey", "primary_key"),
             ("childTable", "child_table"), ("foreignKey", "foreign_key"),
             ("note", "note")],
        ),
    ),
}

# 数据列表页：除企业基础信息外的 9 张业务表
LIST_KINDS = (
    "applications",
    "shareholders",
    "finances",
    "public_opinions",
    "lawsuits",
    "related",
    "guarantees",
    "risks",
    "schema_relationships",
)


def list_catalog(db: Session, scenario_id: str, q: str | None = None,
                 kind: str | None = None, approval_status: str | None = None) -> dict:
    keyword = (q or "").strip()[:100]
    status_filter = (approval_status or "").strip().lower()
    if scenario_id != "enterprise_dd":
        raise ApiError(404, "unknown_scenario", f"未知场景: {scenario_id}")
    table = (kind or "applications").strip().lower()
    spec = _SPECS.get(table)
    if spec is None:
        raise ApiError(
            400, "invalid_args",
            "kind 只能是 " + " / ".join(_SPECS.keys()),
        )
    if status_filter and status_filter not in _APP_STATUS_FILTERS:
        raise ApiError(
            400, "invalid_args",
            f"approvalStatus 只能是 {_APP_STATUS_FILTER_NAMES}",
        )
    if table == "applications":
        total, matched, rows = _applications(db, keyword, status_filter)
        return _pack(
            spec, rows, total, matched, keyword,
            approval_status=status_filter,
            status_counts=_application_status_counts(db),
        )
    if status_filter:
        raise ApiError(400, "invalid_args", "approvalStatus 仅用于审批表")
    total, matched, rows = spec.build(db, keyword)
    return _pack(spec, rows, total, matched, keyword)
