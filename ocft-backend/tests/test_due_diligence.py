"""赛题 04 尽调工具：数字来自库内事实，外部汇总评级不参与计分。"""
import json

from app.db import SessionLocal
from app.models import EnterpriseFinance
from app.tools import registry

CTX = {"run_id": "run_dd", "data_version": 1, "sql_tables": ()}


def _call(db, name, args):
    return registry.execute_tool(db, CTX, name, json.dumps(args, ensure_ascii=False))


def test_financials_match_stored_subjects_and_balance(client):
    db = SessionLocal()
    try:
        result, records, _ = _call(db, "analyze_financials", {"enterpriseId": "E001"})
        assert result.is_success and records
        latest = result.data["years"][-1]
        row = (db.query(EnterpriseFinance)
               .filter(EnterpriseFinance.enterprise_id == "E001",
                       EnterpriseFinance.year == latest["year"]).one())
        assert latest["subjects"]["revenue"] == row.revenue
        assert latest["metrics"]["assetLiabilityRatio"]["value"] == round(
            row.total_liabilities / row.total_assets, 4)
        assert latest["balanceCheck"]["balanced"] is True
        assert "流动比率" not in json.dumps(result.data, ensure_ascii=False)
    finally:
        db.close()


def test_consumption_limit_is_high_risk_without_copying_external_summary(client):
    db = SessionLocal()
    try:
        result, records, _ = _call(db, "rate_risk", {"enterpriseId": "E003"})
        assert result.is_success and records[0].source_ref["calc"] == "rate_risk"
        data = result.data
        assert data["riskLevel"] == "高风险"
        assert not {"externalRiskLevel", "externalUsedInScore", "externalConsistent"} & set(data)
        assert any("限高" in item for item in data["vetoes"])
        assert all(item["source"] == "calculated" for item in data["dimensions"])
        credit, _, _ = _call(db, "calc_credit_limit", {"applicationId": "LA003"})
        assert credit.data["suggestedCreditAmount"] == "0"
        assert credit.data["riskLevel"] == "高风险"
        assert credit.data["steps"]
    finally:
        db.close()


def test_missing_application_and_unknown_args(client):
    db = SessionLocal()
    try:
        missing, records, _ = _call(db, "get_loan_application", {"applicationId": "LA999"})
        assert missing.error.code == "not_found" and records == []
        invalid, _, _ = registry.execute_tool(
            db, CTX, "get_loan_application", json.dumps({"applicationId": "LA001", "extra": 1}))
        assert invalid.error.code == "invalid_args"
        report, evidence, _ = _call(db, "build_dd_report", {"applicationId": "LA001"})
        assert report.is_success
        assert set(report.data["sections"]) == {
            "overview", "financialAnalysis", "riskAlerts", "creditSuggestion", "riskConditions"}
        assert report.data["riskLevel"] in {"低风险", "低-中风险", "中风险", "高风险"}
        assert "externalRiskLevel" not in report.data["sections"]["riskAlerts"]
        assert any(item.source_ref.get("calc") == "build_dd_report" for item in evidence)
    finally:
        db.close()
