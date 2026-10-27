"""企业尽调工具 — 查数与规则计算。结论只来自库内事实和场景配置。"""
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from ..domain.errors import ToolError
from ..domain.types import EvidenceRecord, ToolResult
from ..models import (EnterpriseBasic, EnterpriseFinance, EnterpriseGuarantee,
                      EnterpriseLawsuit, EnterprisePublicOpinion, EnterpriseRelated,
                      EnterpriseRisk, EnterpriseShareholder, LoanApplication)
from . import dd_calc
from .dd_config import load_config
from .registry import register_tool

_LOAN_FIELDS = ["application_id", "enterprise_id", "apply_amount", "loan_purpose",
                "loan_term_months", "apply_date", "guarantee_type", "status"]
_BASIC_FIELDS = ["enterprise_id", "enterprise_name", "credit_code", "legal_person",
                 "legal_person_id", "register_capital", "registered_capital_paid",
                 "establish_date", "enterprise_type", "industry", "register_address",
                 "business_scope", "employee_count", "related_enterprise_count",
                 "business_status", "legal_person_dishonest", "legal_person_consumption_limit",
                 "actual_controller"]
_SHARE_FIELDS = ["enterprise_id", "shareholder_name", "shareholder_type",
                 "shareholding_ratio", "contribution_amount", "contribution_ratio"]
_FINANCE_FIELDS = ["enterprise_id", "year", "revenue", "net_profit", "total_assets",
                   "total_liabilities", "operating_cashflow", "accounts_receivable",
                   "inventory", "fixed_assets", "short_term_loan", "long_term_loan",
                   "accounts_payable", "other_receivable", "prepayment", "owners_equity",
                   "rd_expense", "sales_expense", "admin_expense", "finance_expense",
                   "audit_opinion"]
_LAWSUIT_FIELDS = ["enterprise_id", "case_id", "case_number", "case_type", "cause",
                   "filing_date", "case_status", "litigation_role", "amount"]
_OPINION_FIELDS = ["enterprise_id", "event_id", "event_date", "event_type", "event_source",
                   "event_content", "sentiment", "impact_level"]
_RELATED_FIELDS = ["enterprise_id", "related_enterprise_name", "relation_type",
                   "shareholding_ratio", "is_guarantee_circle"]
_GUARANTEE_FIELDS = ["enterprise_id", "guaranteed_party", "guarantee_amount",
                     "guarantee_type", "guarantee_period", "is_overdue"]
# @why 不含 risk_level_summary：它与公开答案的评级 10/10 一致，运行时一律不读（ADR-0008 决策 1），
#      一致性对照只在 eval/ 里做
_RISK_FIELDS = ["enterprise_id", "existing_loan_balance", "overdue_count", "overdue_amount",
                "external_guarantee_amount", "public_opinion_score", "abnormal_operation"]


def _dump(row, fields: list[str]) -> dict:
    return {name: getattr(row, name) for name in fields}


def _camel(data: dict) -> dict:
    return {to_camel(key): value for key, value in data.items()}


def _evidence(table: str, keys: dict, snapshot, run_ctx: dict, calc: str | None = None) -> EvidenceRecord:
    source_ref = {"table": table, "keys": keys}
    source_type = "db_query"
    if calc:
        source_type = "calculation"
        source_ref["calc"] = calc
    return EvidenceRecord(source_type=source_type, source_ref=source_ref,
                          snapshot=snapshot, data_version=run_ctx["data_version"])


def _loan(db: Session, application_id: str) -> LoanApplication | None:
    return db.query(LoanApplication).filter(LoanApplication.application_id == application_id).first()


def _basic(db: Session, enterprise_id: str) -> EnterpriseBasic | None:
    return db.query(EnterpriseBasic).filter(EnterpriseBasic.enterprise_id == enterprise_id).first()


def _bundle(db: Session, enterprise_id: str) -> dict | None:
    basic = _basic(db, enterprise_id)
    if basic is None:
        return None
    def rows(model, fields):
        return [_dump(row, fields) for row in db.query(model).filter(model.enterprise_id == enterprise_id).all()]
    risk = db.query(EnterpriseRisk).filter(EnterpriseRisk.enterprise_id == enterprise_id).first()
    return {
        "basic": _dump(basic, _BASIC_FIELDS),
        "shareholders": rows(EnterpriseShareholder, _SHARE_FIELDS),
        "finances": rows(EnterpriseFinance, _FINANCE_FIELDS),
        "lawsuits": rows(EnterpriseLawsuit, _LAWSUIT_FIELDS),
        "opinions": rows(EnterprisePublicOpinion, _OPINION_FIELDS),
        "related": rows(EnterpriseRelated, _RELATED_FIELDS),
        "guarantees": rows(EnterpriseGuarantee, _GUARANTEE_FIELDS),
        "risk": _dump(risk, _RISK_FIELDS) if risk else None,
    }


def _pipeline(db: Session, application: LoanApplication) -> dict:
    bundle = _bundle(db, application.enterprise_id)
    if bundle is None:
        raise ToolError("not_found", f"企业 {application.enterprise_id} 不存在")
    loan = _dump(application, _LOAN_FIELDS)
    finance = dd_calc.analyze_financials(
        bundle["finances"], load_config("metrics.yaml"), loan.get("apply_date") or None)
    business = dd_calc.verify_business(bundle, load_config("scorecard.yaml"))
    opinion = dd_calc.scan_public_opinion(bundle, load_config("opinion.yaml"), loan.get("apply_date"))
    fraud = dd_calc.detect_fraud(bundle, finance, load_config("fraud_rules.yaml"))
    rating = dd_calc.rate_risk(bundle, finance, business, opinion, fraud, load_config("scorecard.yaml"))
    credit = dd_calc.calc_credit_limit(loan, bundle, finance, rating, load_config("credit_model.yaml"))
    report = dd_calc.build_report(loan, bundle, finance, business, opinion, fraud, rating, credit)
    return {"loan": loan, "bundle": bundle, "finance": finance, "business": business,
            "opinion": opinion, "fraud": fraud, "rating": rating, "credit": credit, "report": report}


def _require_enterprise(db: Session, enterprise_id: str | None = None,
                        application_id: str | None = None) -> tuple[str, LoanApplication | None]:
    if application_id:
        loan = _loan(db, application_id)
        if loan is None:
            raise ToolError("not_found", f"申请 {application_id} 不存在")
        return loan.enterprise_id, loan
    if enterprise_id:
        if _basic(db, enterprise_id) is None:
            raise ToolError("not_found", f"企业 {enterprise_id} 不存在")
        loan = (db.query(LoanApplication)
                .filter(LoanApplication.enterprise_id == enterprise_id)
                .order_by(LoanApplication.apply_date.desc())
                .first())
        return enterprise_id, loan
    raise ToolError("invalid_args", "需要 applicationId 或 enterpriseId")


@register_tool(
    "get_loan_application",
    "按申请编号读取一笔贷款申请的原始字段（金额单位万元）。做尽调前先定位申请。",
    {"type": "object", "properties": {
        "applicationId": {"type": "string", "description": "贷款申请编号"},
    }, "required": ["applicationId"]},
)
def get_loan_application(db: Session, run_ctx: dict, applicationId: str):
    row = _loan(db, applicationId)
    if row is None:
        return ToolResult.failure("not_found", f"申请 {applicationId} 不存在"), [], {"applicationId": applicationId}
    data = _camel(_dump(row, _LOAN_FIELDS))
    basic = _basic(db, row.enterprise_id)
    if basic is not None:
        data["enterpriseName"] = basic.enterprise_name
    return (ToolResult.success(data),
            [_evidence("loan_application", {"applicationId": applicationId}, data, run_ctx)],
            {"applicationId": applicationId})


@register_tool(
    "find_enterprise",
    "按申请编号、企业编号或企业名称定位企业。名称先精确匹配，唯一模糊命中才返回；"
    "多个候选时不要自行挑选。未给条件时列出最近的申请。",
    {"type": "object", "properties": {
        "applicationId": {"type": "string", "description": "贷款申请编号"},
        "enterpriseId": {"type": "string", "description": "企业编号"},
        "name": {"type": "string", "description": "企业名称，精确或唯一模糊"},
        "limit": {"type": "integer", "description": "列表条数，默认 10，最大 20"},
    }, "required": []},
)
def find_enterprise(db: Session, run_ctx: dict, applicationId: str | None = None,
                    enterpriseId: str | None = None, name: str | None = None, limit: int = 10):
    limit = max(1, min(int(limit or 10), 20))
    args = {"applicationId": applicationId, "enterpriseId": enterpriseId, "name": name, "limit": limit}
    if applicationId:
        loan = _loan(db, applicationId)
        if loan is None:
            return ToolResult.failure("not_found", f"申请 {applicationId} 不存在"), [], args
        return _one_enterprise(db, run_ctx, loan.enterprise_id, args)
    if enterpriseId:
        if _basic(db, enterpriseId) is None:
            return ToolResult.failure("not_found", f"企业 {enterpriseId} 不存在"), [], args
        return _one_enterprise(db, run_ctx, enterpriseId, args)
    if name:
        exact = db.query(EnterpriseBasic).filter(EnterpriseBasic.enterprise_name == name).all()
        needle = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        matched = exact or db.query(EnterpriseBasic).filter(
            EnterpriseBasic.enterprise_name.like(f"%{needle}%", escape="\\")).limit(limit).all()
        if not matched:
            return ToolResult.failure("not_found", f"没有名称匹配「{name}」的企业"), [], args
        if len(matched) > 1:
            candidates = [_summary(db, row) for row in matched]
            return (ToolResult.success({"matchStatus": "ambiguous", "candidates": candidates}),
                    [_evidence("enterprise_basic", {"name": name}, candidates, run_ctx)], args)
        return _one_enterprise(db, run_ctx, matched[0].enterprise_id, args)
    loans = db.query(LoanApplication).order_by(LoanApplication.apply_date.desc()).limit(limit).all()
    listed = []
    for loan in loans:
        basic = _basic(db, loan.enterprise_id)
        listed.append({**_camel(_dump(loan, _LOAN_FIELDS)),
                       "enterpriseName": basic.enterprise_name if basic else None})
    return (ToolResult.success({"matchStatus": "listed", "total": len(listed), "applications": listed}),
            [_evidence("loan_application", {"limit": limit}, listed, run_ctx)], args)


def _summary(db: Session, basic: EnterpriseBasic) -> dict:
    loans = db.query(LoanApplication).filter(LoanApplication.enterprise_id == basic.enterprise_id).all()
    return {"enterpriseId": basic.enterprise_id, "enterpriseName": basic.enterprise_name,
            "applicationIds": [row.application_id for row in loans]}


def _one_enterprise(db: Session, run_ctx: dict, enterprise_id: str, args: dict):
    basic = _basic(db, enterprise_id)
    data = _summary(db, basic)
    data["matchStatus"] = "unique"
    if len(data["applicationIds"]) == 1:
        data["applicationId"] = data["applicationIds"][0]
    return (ToolResult.success(data),
            [_evidence("enterprise_basic", {"enterpriseId": enterprise_id}, data, run_ctx)], args)


@register_tool(
    "verify_business_info",
    "工商核验：经营状态、法人失信/限高、实缴比例、实控人与第一大股东、关联企业数、担保逾期和担保圈。",
    {"type": "object", "properties": {
        "applicationId": {"type": "string", "description": "贷款申请编号"},
        "enterpriseId": {"type": "string", "description": "企业编号"},
    }, "required": []},
)
def verify_business_info(db: Session, run_ctx: dict, applicationId: str | None = None,
                         enterpriseId: str | None = None):
    try:
        enterprise_id, _loan_row = _require_enterprise(db, enterpriseId, applicationId)
        bundle = _bundle(db, enterprise_id)
        data = dd_calc.verify_business(bundle, load_config("scorecard.yaml"))
    except ToolError as exc:
        return ToolResult.failure(exc.code, exc.message), [], {"applicationId": applicationId, "enterpriseId": enterpriseId}
    return (ToolResult.success(data),
            [_evidence("enterprise_basic", {"enterpriseId": enterprise_id}, data, run_ctx, "verify_business_info")],
            {"applicationId": applicationId, "enterpriseId": enterprise_id})


@register_tool(
    "analyze_financials",
    "解析申请日期之前完整年度的科目和财务指标，并做资产=负债+所有者权益勾稽校验。金额单位万元。"
    "周转指标以营业收入为分母。",
    {"type": "object", "properties": {
        "applicationId": {"type": "string", "description": "贷款申请编号"},
        "enterpriseId": {"type": "string", "description": "企业编号"},
    }, "required": []},
)
def analyze_financials(db: Session, run_ctx: dict, applicationId: str | None = None,
                       enterpriseId: str | None = None):
    try:
        enterprise_id, loan = _require_enterprise(db, enterpriseId, applicationId)
        bundle = _bundle(db, enterprise_id)
        data = dd_calc.analyze_financials(
            bundle["finances"], load_config("metrics.yaml"), loan.apply_date if loan else None)
        data["enterpriseId"] = enterprise_id
    except ToolError as exc:
        return ToolResult.failure(exc.code, exc.message), [], {"applicationId": applicationId, "enterpriseId": enterpriseId}
    return (ToolResult.success(data),
            [_evidence("enterprise_finance", {"enterpriseId": enterprise_id}, data, run_ctx, "analyze_financials")],
            {"applicationId": applicationId, "enterpriseId": enterprise_id})


@register_tool(
    "scan_public_opinion",
    "扫描舆情事件和涉诉，按类型、影响、情感和时间衰减打分，并汇总未结被告金额。",
    {"type": "object", "properties": {
        "applicationId": {"type": "string", "description": "贷款申请编号"},
        "enterpriseId": {"type": "string", "description": "企业编号"},
    }, "required": []},
)
def scan_public_opinion(db: Session, run_ctx: dict, applicationId: str | None = None,
                        enterpriseId: str | None = None):
    try:
        enterprise_id, loan = _require_enterprise(db, enterpriseId, applicationId)
        bundle = _bundle(db, enterprise_id)
        as_of = loan.apply_date if loan else None
        data = dd_calc.scan_public_opinion(bundle, load_config("opinion.yaml"), as_of)
    except ToolError as exc:
        return ToolResult.failure(exc.code, exc.message), [], {"applicationId": applicationId, "enterpriseId": enterpriseId}
    return (ToolResult.success(data),
            [_evidence("enterprise_public_opinion", {"enterpriseId": enterprise_id}, data, run_ctx, "scan_public_opinion")],
            {"applicationId": applicationId, "enterpriseId": enterprise_id})


@register_tool(
    "detect_fraud_signals",
    "按反欺诈规则检查现金流背离、存货与应收增长、其他应收款占比、长期背离和担保圈。"
    "每条给出规则编号、命中值、阈值和置信度。",
    {"type": "object", "properties": {
        "applicationId": {"type": "string", "description": "贷款申请编号"},
        "enterpriseId": {"type": "string", "description": "企业编号"},
    }, "required": []},
)
def detect_fraud_signals(db: Session, run_ctx: dict, applicationId: str | None = None,
                         enterpriseId: str | None = None):
    try:
        enterprise_id, loan = _require_enterprise(db, enterpriseId, applicationId)
        bundle = _bundle(db, enterprise_id)
        finance = dd_calc.analyze_financials(
            bundle["finances"], load_config("metrics.yaml"), loan.apply_date if loan else None)
        data = dd_calc.detect_fraud(bundle, finance, load_config("fraud_rules.yaml"))
    except ToolError as exc:
        return ToolResult.failure(exc.code, exc.message), [], {"applicationId": applicationId, "enterpriseId": enterpriseId}
    return (ToolResult.success(data),
            [_evidence("enterprise_finance", {"enterpriseId": enterprise_id}, data, run_ctx, "detect_fraud_signals")],
            {"applicationId": applicationId, "enterpriseId": enterprise_id})


@register_tool(
    "rate_risk",
    "用评分卡计算风险档位。失信、限高、未结逾期，或高置信反欺诈命中达到配置条数时一票否决为高风险。",
    {"type": "object", "properties": {
        "applicationId": {"type": "string", "description": "贷款申请编号"},
        "enterpriseId": {"type": "string", "description": "企业编号"},
    }, "required": []},
)
def rate_risk(db: Session, run_ctx: dict, applicationId: str | None = None,
              enterpriseId: str | None = None):
    try:
        enterprise_id, loan = _require_enterprise(db, enterpriseId, applicationId)
        if loan is None and applicationId is None:
            loan = (db.query(LoanApplication).filter(LoanApplication.enterprise_id == enterprise_id)
                    .order_by(LoanApplication.apply_date.desc()).first())
        if applicationId and loan is None:
            raise ToolError("not_found", f"申请 {applicationId} 不存在")
        application = loan or LoanApplication(application_id="", enterprise_id=enterprise_id,
                                              apply_amount=0, loan_purpose="", loan_term_months=12,
                                              apply_date="", guarantee_type="")
        data = _pipeline(db, application)["rating"]
        if loan:
            data["applicationId"] = loan.application_id
    except ToolError as exc:
        return ToolResult.failure(exc.code, exc.message), [], {"applicationId": applicationId, "enterpriseId": enterpriseId}
    return (ToolResult.success(data),
            [_evidence("enterprise_risk", {"enterpriseId": enterprise_id}, data, run_ctx, "rate_risk")],
            {"applicationId": applicationId, "enterpriseId": enterprise_id})


@register_tool(
    "calc_credit_limit",
    "按本次融资模拟政策：营收/净资产能力经评级与现金流调整后按申请额封顶；"
    "存量/担保列为核验条件，不全额扣减。高风险或否决输出 0。"
    "返回每一步公式和取值。金额单位万元。",
    {"type": "object", "properties": {
        "applicationId": {"type": "string", "description": "贷款申请编号"},
    }, "required": ["applicationId"]},
)
def calc_credit_limit(db: Session, run_ctx: dict, applicationId: str):
    loan = _loan(db, applicationId)
    if loan is None:
        return ToolResult.failure("not_found", f"申请 {applicationId} 不存在"), [], {"applicationId": applicationId}
    try:
        data = _pipeline(db, loan)["credit"]
    except ToolError as exc:
        return ToolResult.failure(exc.code, exc.message), [], {"applicationId": applicationId}
    return (ToolResult.success(data),
            [_evidence("loan_application", {"applicationId": applicationId}, data, run_ctx, "calc_credit_limit")],
            {"applicationId": applicationId})


@register_tool(
    "build_dd_report",
    "汇总五部分尽调报告结构：企业概况、财务分析、风险提示、额度建议、风控条件。数字来自其他计算，不要改写。",
    {"type": "object", "properties": {
        "applicationId": {"type": "string", "description": "贷款申请编号"},
    }, "required": ["applicationId"]},
)
def build_dd_report(db: Session, run_ctx: dict, applicationId: str):
    loan = _loan(db, applicationId)
    if loan is None:
        return ToolResult.failure("not_found", f"申请 {applicationId} 不存在"), [], {"applicationId": applicationId}
    try:
        packed = _pipeline(db, loan)
    except ToolError as exc:
        return ToolResult.failure(exc.code, exc.message), [], {"applicationId": applicationId}
    data = packed["report"]
    evidence = [
        _evidence("loan_application", {"applicationId": applicationId}, data, run_ctx, "build_dd_report"),
        _evidence("enterprise_finance", {"enterpriseId": loan.enterprise_id}, packed["finance"], run_ctx, "analyze_financials"),
        _evidence("enterprise_basic", {"enterpriseId": loan.enterprise_id}, packed["business"], run_ctx, "verify_business_info"),
    ]
    return ToolResult.success(data), evidence, {"applicationId": applicationId}
