"""业务目录单行增删改：可写 kind 按内部 id 维护；schema_relationships 拒绝写入。"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy import Float, Integer, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..api_errors import ApiError
from ..compliance.pii import redact_obj
from ..models import (
    CsvImportAudit,
    EnterpriseBasic,
    EnterpriseFinance,
    EnterpriseGuarantee,
    EnterpriseLawsuit,
    EnterprisePublicOpinion,
    EnterpriseRelated,
    EnterpriseRisk,
    EnterpriseShareholder,
    LoanApplication,
)
from .csv_import_service import _normalize_date

# kind → (Model, 业务唯一键属性名…)
_WRITABLE: dict[str, tuple[type, tuple[str, ...]]] = {
    "enterprises": (EnterpriseBasic, ("enterprise_id",)),
    "applications": (LoanApplication, ("application_id",)),
    "shareholders": (EnterpriseShareholder, ("enterprise_id", "shareholder_name", "shareholder_type")),
    "finances": (EnterpriseFinance, ("enterprise_id", "year")),
    "public_opinions": (EnterprisePublicOpinion, ("event_id",)),
    "lawsuits": (EnterpriseLawsuit, ("case_id",)),
    "related": (EnterpriseRelated, ("enterprise_id", "related_enterprise_name", "relation_type")),
    "guarantees": (EnterpriseGuarantee, ("enterprise_id", "guaranteed_party", "guarantee_type", "guarantee_period")),
    "risks": (EnterpriseRisk, ("enterprise_id",)),
}

# JSON camelCase → ORM attr；风险汇总不允许经写接口改外部评级列
_FIELD_MAP: dict[str, dict[str, str]] = {
    "enterprises": {
        "enterpriseId": "enterprise_id", "enterpriseName": "enterprise_name",
        "creditCode": "credit_code", "legalPerson": "legal_person",
        "legalPersonId": "legal_person_id", "registerCapital": "register_capital",
        "registeredCapitalPaid": "registered_capital_paid", "establishDate": "establish_date",
        "enterpriseType": "enterprise_type", "industry": "industry",
        "registerAddress": "register_address", "businessScope": "business_scope",
        "employeeCount": "employee_count", "relatedEnterpriseCount": "related_enterprise_count",
        "businessStatus": "business_status", "legalPersonDishonest": "legal_person_dishonest",
        "legalPersonConsumptionLimit": "legal_person_consumption_limit",
        "actualController": "actual_controller",
    },
    "applications": {
        "applicationId": "application_id", "enterpriseId": "enterprise_id",
        "applyAmount": "apply_amount", "loanPurpose": "loan_purpose",
        "loanTermMonths": "loan_term_months", "applyDate": "apply_date",
        "guaranteeType": "guarantee_type", "status": "status",
        # 审核原因：走审核接口时必填；也可随 PATCH 一并写入
        "reviewReason": "review_reason",
    },
    "shareholders": {
        "enterpriseId": "enterprise_id", "shareholderName": "shareholder_name",
        "shareholderType": "shareholder_type", "shareholdingRatio": "shareholding_ratio",
        "contributionAmount": "contribution_amount", "contributionRatio": "contribution_ratio",
    },
    "finances": {
        "enterpriseId": "enterprise_id", "year": "year", "revenue": "revenue",
        "netProfit": "net_profit", "totalAssets": "total_assets",
        "totalLiabilities": "total_liabilities", "operatingCashflow": "operating_cashflow",
        "accountsReceivable": "accounts_receivable", "inventory": "inventory",
        "fixedAssets": "fixed_assets", "shortTermLoan": "short_term_loan",
        "longTermLoan": "long_term_loan", "accountsPayable": "accounts_payable",
        "otherReceivable": "other_receivable", "prepayment": "prepayment",
        "ownersEquity": "owners_equity", "rdExpense": "rd_expense",
        "salesExpense": "sales_expense", "adminExpense": "admin_expense",
        "financeExpense": "finance_expense", "auditOpinion": "audit_opinion",
    },
    "public_opinions": {
        "enterpriseId": "enterprise_id", "eventId": "event_id", "eventDate": "event_date",
        "eventType": "event_type", "eventSource": "event_source",
        "eventContent": "event_content", "sentiment": "sentiment",
        "impactLevel": "impact_level",
    },
    "lawsuits": {
        "enterpriseId": "enterprise_id", "caseId": "case_id", "caseNumber": "case_number",
        "caseType": "case_type", "cause": "cause", "filingDate": "filing_date",
        "caseStatus": "case_status", "litigationRole": "litigation_role", "amount": "amount",
    },
    "related": {
        "enterpriseId": "enterprise_id", "relatedEnterpriseName": "related_enterprise_name",
        "relationType": "relation_type", "shareholdingRatio": "shareholding_ratio",
        "isGuaranteeCircle": "is_guarantee_circle",
    },
    "guarantees": {
        "enterpriseId": "enterprise_id", "guaranteedParty": "guaranteed_party",
        "guaranteeAmount": "guarantee_amount", "guaranteeType": "guarantee_type",
        "guaranteePeriod": "guarantee_period", "isOverdue": "is_overdue",
    },
    "risks": {
        "enterpriseId": "enterprise_id", "existingLoanBalance": "existing_loan_balance",
        "overdueCount": "overdue_count", "overdueAmount": "overdue_amount",
        "externalGuaranteeAmount": "external_guarantee_amount",
        "publicOpinionScore": "public_opinion_score",
        "abnormalOperation": "abnormal_operation",
        # risk_level_summary 故意不映射：运行时不经目录维护答案列
    },
}

# 贷款申请状态：待处理 / 待审核 / 审核通过 / 审核不通过
_APP_STATUSES = frozenset({"pending", "pending_review", "approved", "rejected"})


def _coerce(column, value: Any) -> Any:
    if value is None or value == "":
        if column.nullable:
            return None
        raise ApiError(400, "invalid_args", f"字段 {column.name} 必填")
    if isinstance(column.type, (Integer, Float)):
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, AttributeError) as exc:
            raise ApiError(400, "invalid_args", f"字段 {column.name} 需要有效数字") from exc
        if not number.is_finite():
            raise ApiError(400, "invalid_args", f"字段 {column.name} 不允许 NaN 或无穷")
        if isinstance(column.type, Integer):
            if number != number.to_integral_value():
                raise ApiError(400, "invalid_args", f"字段 {column.name} 需要整数")
            return int(number)
        return float(number)
    text = str(value).strip()
    if isinstance(column.type, String) and column.type.length and len(text) > column.type.length:
        raise ApiError(400, "invalid_args", f"字段 {column.name} 超长")
    if column.name.endswith("_date"):
        try:
            return _normalize_date(text)
        except ValueError as exc:
            raise ApiError(400, "invalid_args", str(exc)) from exc
    return text


def _parse_fields(kind: str, payload: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    mapping = _FIELD_MAP.get(kind)
    if mapping is None:
        raise ApiError(400, "invalid_args", "该表不支持写入")
    model, _ = _WRITABLE[kind]
    table_cols = {c.name: c for c in model.__table__.columns}
    out: dict[str, Any] = {}
    unknown = [k for k in payload if k not in mapping and k != "id"]
    if unknown:
        raise ApiError(400, "invalid_args", f"不支持的字段：{', '.join(unknown[:8])}")
    for camel, attr in mapping.items():
        if camel not in payload:
            if partial:
                continue
            col = table_cols[attr]
            if not col.nullable and col.default is None and col.server_default is None:
                raise ApiError(400, "invalid_args", f"缺少字段 {camel}")
            continue
        # 审批表 status：缺省或空串视为待处理，不报必填错
        if kind == "applications" and attr == "status" and payload[camel] in (None, ""):
            out[attr] = "pending"
            continue
        out[attr] = _coerce(table_cols[attr], payload[camel])
    if not partial and kind == "risks" and "risk_level_summary" not in out:
        out["risk_level_summary"] = ""
    if not partial and kind == "applications" and "status" not in out:
        out["status"] = "pending"
    if kind == "applications" and "status" in out and out["status"] not in _APP_STATUSES:
        raise ApiError(400, "invalid_args",
                       "status 只能是 pending / pending_review / approved / rejected")
    if not out and partial:
        raise ApiError(400, "invalid_args", "没有可更新的字段")
    return out


def _row_out(kind: str, row: Any) -> dict:
    mapping = _FIELD_MAP[kind]
    data = {"id": row.id}
    for camel, attr in mapping.items():
        data[camel] = getattr(row, attr)
    if kind == "applications":
        # 审核人 / 审核时间由服务端写入，只读输出，不回写客户端字段映射
        data["reviewedBy"] = row.reviewed_by
        data["reviewedAt"] = row.reviewed_at
    return redact_obj(data)


def _now_z() -> str:
    """当前 UTC 时间的 ISO 8601 形式（带 Z，与接口时间约定一致）。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _audit(db: Session, actor_id: str, status: str, kind: str, record_id: int, keys: dict) -> None:
    db.add(CsvImportAudit(
        id=f"cat_{uuid4().hex}",
        actor_id=actor_id[:64],
        status=status,
        summary={"kind": kind, "recordId": record_id, "keys": keys},
    ))


def _keys(kind: str, row: Any) -> dict:
    _, key_attrs = _WRITABLE[kind]
    return {attr: getattr(row, attr) for attr in key_attrs}


def _require_writable(kind: str) -> tuple[type, tuple[str, ...]]:
    if kind == "schema_relationships":
        raise ApiError(400, "invalid_args", "表关系只读，不支持增删改")
    spec = _WRITABLE.get(kind)
    if spec is None:
        raise ApiError(400, "invalid_args", f"未知 kind：{kind}")
    return spec


def create_record(db: Session, scenario_id: str, kind: str, payload: dict, actor_id: str) -> dict:
    if scenario_id != "enterprise_dd":
        raise ApiError(404, "unknown_scenario", f"未知场景: {scenario_id}")
    model, _ = _require_writable(kind)
    values = _parse_fields(kind, payload, partial=False)
    row = model(**values)
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "conflict", "业务键冲突，无法新增") from exc
    _audit(db, actor_id, "catalog_created", kind, row.id, _keys(kind, row))
    db.commit()
    db.refresh(row)
    return {"id": row.id, "kind": kind, "row": _row_out(kind, row)}


def update_record(db: Session, scenario_id: str, kind: str, record_id: int,
                  payload: dict, actor_id: str) -> dict:
    if scenario_id != "enterprise_dd":
        raise ApiError(404, "unknown_scenario", f"未知场景: {scenario_id}")
    model, _ = _require_writable(kind)
    row = db.get(model, record_id)
    if row is None:
        raise ApiError(404, "not_found", "记录不存在")
    values = _parse_fields(kind, payload, partial=True)
    # @why 只在实际改变结论时记录审核留痕；编辑用途、金额等字段会整行回传 status，
    #      不能因此覆盖上一次审核人与审核时间。
    previous_status = row.status if kind == "applications" else None
    for attr, value in values.items():
        setattr(row, attr, value)
    if (kind == "applications" and previous_status != row.status
            and row.status in ("approved", "rejected")):
        row.reviewed_by = actor_id[:64]
        row.reviewed_at = _now_z()
        # 通用编辑接口不强制原因；没有随本次提交原因时清空旧理由，避免张冠李戴
        row.review_reason = values.get("review_reason") or None
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "conflict", "业务键冲突，无法更新") from exc
    _audit(db, actor_id, "catalog_updated", kind, row.id, _keys(kind, row))
    db.commit()
    db.refresh(row)
    return {"id": row.id, "kind": kind, "row": _row_out(kind, row)}


def delete_record(db: Session, scenario_id: str, kind: str, record_id: int, actor_id: str) -> dict:
    if scenario_id != "enterprise_dd":
        raise ApiError(404, "unknown_scenario", f"未知场景: {scenario_id}")
    model, _ = _require_writable(kind)
    row = db.get(model, record_id)
    if row is None:
        raise ApiError(404, "not_found", "记录不存在")
    keys = _keys(kind, row)
    db.delete(row)
    _audit(db, actor_id, "catalog_deleted", kind, record_id, keys)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "conflict", "存在关联约束，无法删除") from exc
    return {"id": record_id, "kind": kind, "deleted": True}


# 人工审核可选的结论：通过 / 拒绝。与申请状态同一套取值，避免两套词。
_REVIEW_DECISIONS = frozenset({"approved", "rejected"})
_REVIEW_REASON_LIMIT = 500


def review_application(db: Session, scenario_id: str, record_id: int,
                       decision: Any, reason: Any, actor_id: str) -> dict:
    """人工审核一笔贷款申请：写结论、原因、审核人与时间，并追加审计（同一事务）。

    @why 审核是业务决策，必须留下理由：原因必填；只有待审核（已生成尽调报告）的申请可审核，
         待处理 / 已审结的申请返回 409，避免绕过尽调直接放款或重复覆盖结论。
    """
    if scenario_id != "enterprise_dd":
        raise ApiError(404, "unknown_scenario", f"未知场景: {scenario_id}")
    if not isinstance(decision, str) or decision not in _REVIEW_DECISIONS:
        raise ApiError(400, "invalid_args", "decision 只能是 approved / rejected")
    text = reason.strip() if isinstance(reason, str) else ""
    if not text:
        raise ApiError(400, "invalid_args", "请填写审核原因")
    if len(text) > _REVIEW_REASON_LIMIT:
        raise ApiError(400, "invalid_args", f"审核原因不能超过 {_REVIEW_REASON_LIMIT} 字")
    row = db.get(LoanApplication, record_id)
    if row is None:
        raise ApiError(404, "not_found", "记录不存在")
    if (row.status or "pending") != "pending_review":
        raise ApiError(409, "invalid_state", "只有待审核的申请可以审核")
    row.status = decision
    row.review_reason = text
    row.reviewed_by = actor_id[:64]
    row.reviewed_at = _now_z()
    # @why csv_import_audits.status 是 VARCHAR(16)：审核审计值必须控制在 16 字以内
    _audit(db, actor_id, "catalog_reviewed", "applications", row.id,
           {"applicationId": row.application_id, "reviewDecision": decision, "reason": text})
    db.commit()
    db.refresh(row)
    return {"id": row.id, "kind": "applications", "row": _row_out("applications", row)}
