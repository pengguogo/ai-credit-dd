"""工具注册表与信贷规则引擎单测。"""
import json

import pytest

from app.db import SessionLocal
from app.tools import registry

CTX = {"run_id": "run_test", "data_version": 1}


@pytest.fixture
def db(client):  # client 保证已建表并灌入种子
    session = SessionLocal()
    yield session
    session.close()


def _call(db, name, args):
    return registry.execute_tool(db, CTX, name, json.dumps(args))


def test_unknown_tool_rejected(db):
    result, records, _ = _call(db, "no_such_tool", {})
    assert not result.is_success and result.error.code == "not_allowed" and records == []


@pytest.mark.parametrize("arguments, code", [
    ("not json", "invalid_args"),
    (json.dumps({"applicationId": "X", "extra": 1}), "invalid_args"),
    (json.dumps({}), "invalid_args"),
    (json.dumps({"applicationId": 123}), "invalid_args"),
])
def test_invalid_args_rejected(db, arguments, code):
    result, _, _ = registry.execute_tool(db, CTX, "get_credit_application", arguments)
    assert not result.is_success and result.error.code == code


def test_not_found(db):
    result, records, _ = _call(db, "get_credit_application", {"applicationId": "APP-0000"})
    assert result.error.code == "not_found" and records == []


def test_get_application_returns_whitelisted_fields_with_evidence(db):
    result, records, _ = _call(db, "get_credit_application", {"applicationId": "APP-2026-1003"})
    assert result.is_success
    assert set(result.data) == {"applicationId", "customerName", "businessType", "applyAmount",
                                "termMonths", "creditScore", "debtRatio", "collateral",
                                "riskTags", "status", "appliedAt"}
    assert records[0].source_ref == {"table": "credit_applications",
                                     "keys": {"applicationId": "APP-2026-1003"}}


@pytest.mark.parametrize("application_id, expected", [
    ("APP-2026-1004", "approved"),       # 全部规则通过
    ("APP-2026-1002", "manual_review"),  # 仅 R003 多头借贷
    ("APP-2026-1003", "rejected"),       # R002 + R003 两项 warn
    ("APP-2026-1009", "rejected"),       # R001 征信 601 < 620（block）
])
def test_credit_rules_computed_at_runtime(db, application_id, expected):
    """结论由规则引擎根据原始字段实时计算；种子中不存在任何结论字段。"""
    result, records, _ = _call(db, "run_credit_rules", {"applicationId": application_id})
    assert result.is_success
    assert result.data["decision"] == expected
    assert {r["ruleId"] for r in result.data["ruleResults"]} == {"R001", "R002", "R003", "R004", "R005"}
    assert records[0].source_type == "calculation"
