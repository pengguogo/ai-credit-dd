"""ADR-0008 决策 1：enterprise_risk.risk_level_summary 与公开答案评级一致，运行时任何出口都不得读出。

覆盖：尽调工具结果（会作为 tool 消息送模型）、sql_query（显式引用、过滤条件、SELECT *）、
主控提示词、业务目录。只检查键名与 SQL 行为，不引用任何答案取值。
"""
import json

import pytest

from app.agent.scenarios import ENTERPRISE_DD_SYSTEM, SCENARIOS
from app.db import SessionLocal
from app.models import EnterpriseFinance, LoanApplication
from app.tools import registry
from tests.conftest import HEADERS

_LEAK_KEYS = {"risk_level_summary", "riskLevelSummary", "externalRiskLevel",
              "externalConsistent", "externalUsedInScore"}
_DD_TOOLS = ["verify_business_info", "analyze_financials", "scan_public_opinion",
             "detect_fraud_signals", "rate_risk", "calc_credit_limit", "build_dd_report"]


def _ctx():
    return {"run_id": "run_iso", "data_version": 1,
            "sql_tables": SCENARIOS["enterprise_dd"].sql_tables}


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def _call(db, name, args):
    return registry.execute_tool(db, _ctx(), name, json.dumps(args, ensure_ascii=False))


def test_dd_tool_results_and_evidence_never_carry_external_summary(client):
    db = SessionLocal()
    try:
        application_ids = [
            row[0]
            for row in db.query(LoanApplication.application_id)
            .join(EnterpriseFinance,
                  EnterpriseFinance.enterprise_id == LoanApplication.enterprise_id)
            .distinct()
            .all()
        ]
        assert application_ids
        for application_id in application_ids:
            for tool in _DD_TOOLS:
                result, records, _ = _call(db, tool, {"applicationId": application_id})
                assert result.is_success, (tool, application_id, result.error)
                assert not _keys(result.data) & _LEAK_KEYS, (tool, application_id)
                for record in records:
                    assert not _keys(record.snapshot) & _LEAK_KEYS, (tool, application_id)
    finally:
        db.close()


@pytest.mark.parametrize("sql", [
    "SELECT enterprise_id, risk_level_summary FROM enterprise_risk",
    "SELECT enterprise_id FROM enterprise_risk WHERE risk_level_summary = 'x'",
    "SELECT RISK_LEVEL_SUMMARY FROM enterprise_risk",
    "SELECT r.risk_level_summary FROM enterprise_risk r JOIN loan_application l "
    "ON r.enterprise_id = l.enterprise_id",
    "SELECT COUNT(*) FROM enterprise_risk GROUP BY risk_level_summary",
])
def test_sql_query_rejects_explicit_references(client, sql):
    db = SessionLocal()
    try:
        result, records, _ = _call(db, "sql_query", {"sql": sql})
        assert not result.is_success
        assert result.error.code == "not_allowed"
        assert records == []
    finally:
        db.close()


def test_sql_query_star_drops_forbidden_column(client):
    db = SessionLocal()
    try:
        result, records, _ = _call(db, "sql_query", {"sql": "SELECT * FROM enterprise_risk LIMIT 20"})
        assert result.is_success and result.data["rows"]
        assert not _keys(result.data) & _LEAK_KEYS
        assert "overdueCount" in result.data["rows"][0]  # 其他事实列照常返回
        assert not _keys(records[0].snapshot) & _LEAK_KEYS
    finally:
        db.close()


def test_prompt_and_catalog_do_not_reference_external_summary(client):
    assert "externalRiskLevel" not in ENTERPRISE_DD_SYSTEM
    assert "外部汇总" not in ENTERPRISE_DD_SYSTEM
    resp = client.get("/api/agent/catalog/enterprise_dd", headers=HEADERS)
    assert resp.status_code == 200
    assert not _keys(resp.json()) & _LEAK_KEYS
