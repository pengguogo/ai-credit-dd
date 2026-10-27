"""尽调单步核对 — 按维度直接跑对应工具，供前端单维度页核对与报告导出。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..api_errors import ApiError
from ..compliance.pii import redact_obj
from ..config import settings
from ..models import LoanApplication
from ..tools import due_diligence as dd

# 与前端 report-dims slug 对齐
STEP_TOOLS: dict[str, list[str]] = {
    "business": ["verify_business_info"],
    "finance": ["analyze_financials"],
    "opinion": ["scan_public_opinion"],
    "fraud": ["detect_fraud_signals"],
    "credit-risk": ["rate_risk", "calc_credit_limit"],
    "report": ["build_dd_report"],
}

STEP_LABELS = {
    "business": "工商核验",
    "finance": "财报解析",
    "opinion": "舆情扫描",
    "fraud": "反欺诈检测",
    "credit-risk": "额度测算",
    "report": "尽调报告",
}


def run_step(db: Session, *, step: str, enterprise_id: str | None,
             application_id: str | None) -> dict:
    if step not in STEP_TOOLS:
        raise ApiError(400, "invalid_args", f"未知步骤: {step}")
    eid = (enterprise_id or "").strip() or None
    aid = (application_id or "").strip() or None
    if not eid and not aid:
        raise ApiError(400, "invalid_args", "需要 enterpriseId")
    # 前端只选企业：额度步自动取该企业最近一笔申请
    if eid and not aid:
        aid = _latest_application_id(db, eid)

    run_ctx = {"run_id": "dd_step_preview", "data_version": settings.data_version}
    tool_outs: list[dict] = []
    resolved_enterprise = eid
    resolved_application = aid

    for tool_name in STEP_TOOLS[step]:
        if tool_name == "calc_credit_limit" and not aid:
            tool_outs.append({
                "toolName": tool_name,
                "status": "skipped",
                "errorCode": "application_required",
                "message": "该企业暂无贷款申请，无法测算额度；风险评级仍可核对",
                "data": None,
            })
            continue
        if tool_name == "build_dd_report" and not aid:
            tool_outs.append({
                "toolName": tool_name,
                "status": "skipped",
                "errorCode": "application_required",
                "message": "该企业暂无贷款申请，无法汇总尽调报告",
                "data": None,
            })
            continue
        result, _evidence, args = _invoke(db, run_ctx, tool_name, eid, aid)
        if result.is_success:
            data = redact_obj(result.data) if isinstance(result.data, (dict, list)) else result.data
            tool_outs.append({
                "toolName": tool_name,
                "status": "ok",
                "errorCode": None,
                "message": None,
                "data": data,
            })
            if isinstance(result.data, dict):
                resolved_enterprise = result.data.get("enterpriseId") or resolved_enterprise
                resolved_application = result.data.get("applicationId") or resolved_application
            if isinstance(args, dict):
                resolved_enterprise = args.get("enterpriseId") or resolved_enterprise
                resolved_application = args.get("applicationId") or resolved_application
        else:
            err = result.error
            tool_outs.append({
                "toolName": tool_name,
                "status": "error",
                "errorCode": err.code if err else "execution_failed",
                "message": err.message if err else "工具执行失败",
                "data": None,
            })

    statuses = {item["status"] for item in tool_outs}
    if statuses == {"ok"}:
        status = "ok"
    elif "ok" in statuses:
        status = "partial"
    else:
        status = "error"

    return {
        "step": step,
        "label": STEP_LABELS[step],
        "status": status,
        "enterpriseId": resolved_enterprise,
        "applicationId": resolved_application,
        "tools": tool_outs,
        "note": "单步核对：结果与 Agent 同工具同源；不写证据库、不读评测答案。",
    }


def _latest_application_id(db: Session, enterprise_id: str) -> str | None:
    loan = (db.query(LoanApplication)
            .filter(LoanApplication.enterprise_id == enterprise_id)
            .order_by(LoanApplication.apply_date.desc())
            .first())
    return loan.application_id if loan else None


def _invoke(db: Session, run_ctx: dict, tool_name: str,
            enterprise_id: str | None, application_id: str | None):
    if tool_name == "verify_business_info":
        return dd.verify_business_info(
            db, run_ctx, applicationId=application_id, enterpriseId=enterprise_id)
    if tool_name == "analyze_financials":
        return dd.analyze_financials(
            db, run_ctx, applicationId=application_id, enterpriseId=enterprise_id)
    if tool_name == "scan_public_opinion":
        return dd.scan_public_opinion(
            db, run_ctx, applicationId=application_id, enterpriseId=enterprise_id)
    if tool_name == "detect_fraud_signals":
        return dd.detect_fraud_signals(
            db, run_ctx, applicationId=application_id, enterpriseId=enterprise_id)
    if tool_name == "rate_risk":
        return dd.rate_risk(
            db, run_ctx, applicationId=application_id, enterpriseId=enterprise_id)
    if tool_name == "calc_credit_limit":
        return dd.calc_credit_limit(db, run_ctx, applicationId=application_id)
    if tool_name == "build_dd_report":
        return dd.build_dd_report(db, run_ctx, applicationId=application_id)
    raise ApiError(500, "execution_failed", f"未接线的工具: {tool_name}")
