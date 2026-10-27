"""sql_query Agent 工具单测（待办 1-7 / 1-10）：只读语义 + 表白名单 + 场景收窄 + 上限 + 证据。"""
import json

import pytest

from app.db import SessionLocal
from app.tools import registry

CTX = {"run_id": "run_test", "data_version": 1}


@pytest.fixture
def db(client):
    """client 夹具执行迁移并灌入 app/seed.py 样例数据（临时 SQLite）。"""
    session = SessionLocal()
    yield session
    session.close()


def _call(db, args, ctx=CTX):
    return registry.execute_tool(db, ctx, "sql_query", json.dumps(args))


@pytest.mark.parametrize("sql", [
    "SELECT * FROM evidence",                                 # Agent 执行表
    "SELECT * FROM agent_runs",                               # Agent 执行表
    "SELECT * FROM tool_traces",                              # Agent 执行表
    "SELECT * FROM schema_migrations",                        # 迁移记录表
    "SELECT * FROM expected",                                 # 评测数据
    "SELECT * FROM credit_decisions",                         # 已废弃的副本表（待办 2-2）
    "DELETE FROM credit_applications",                        # 写语句
    "UPDATE credit_applications SET credit_score = 999",      # 写语句
    "INSERT INTO credit_applications (application_id) VALUES ('X')",  # 写语句
    "SELECT 1; DROP TABLE credit_applications",               # 多语句
    "SELECT load_file('/etc/passwd')",                        # 危险函数
    "SELECT sleep(5)",                                        # 危险函数
    "SHOW TABLES",                                            # 非白名单语句类型
])
def test_forbidden_sql_rejected(db, sql):
    """完成标准：越权表、写语句、多语句均被拒绝。"""
    result, records, _ = _call(db, {"sql": sql})
    assert not result.is_success
    assert result.error.code == "not_allowed"
    assert records == []


def test_invalid_args_rejected(db):
    result, _, _ = registry.execute_tool(db, CTX, "sql_query", json.dumps({}))
    assert not result.is_success and result.error.code == "invalid_args"


def test_valid_sql_returns_rows_and_evidence(db):
    result, records, _ = _call(db, {
        "sql": "SELECT application_id, credit_score FROM credit_applications "
               "WHERE application_id = 'APP-2026-1003'"})
    assert result.is_success
    assert result.data["rowCount"] == 1
    assert result.data["truncated"] is False
    assert result.data["tables"] == ["credit_applications"]
    assert result.data["rows"] == [{"applicationId": "APP-2026-1003", "creditScore": 640}]
    assert records[0].source_type == "db_query"
    assert records[0].source_ref["table"] == "credit_applications"
    assert records[0].source_ref["filters"]["sql"].startswith("SELECT")
    assert records[0].snapshot == result.data["rows"]
    assert records[0].data_version == CTX["data_version"]


def test_join_between_allowed_tables(db):
    """不限场景时，白名单内的业务表之间可以 JOIN。"""
    result, _, _ = _call(db, {
        "sql": "SELECT a.application_id, t.txn_id FROM credit_applications a "
               "JOIN risk_transactions t ON 1 = 0"})
    assert result.is_success
    assert result.data["tables"] == ["credit_applications", "risk_transactions"]


def test_scenario_tables_narrow_whitelist(db):
    """待办 1-10：场景声明 sql_tables 后只能查这些表，其余业务表也被拒绝。"""
    ctx = {**CTX, "sql_tables": ("credit_applications",)}
    ok, _, _ = _call(db, {"sql": "SELECT COUNT(*) AS n FROM credit_applications"}, ctx)
    assert ok.is_success and ok.data["rows"] == [{"n": 12}]
    denied, records, _ = _call(db, {"sql": "SELECT * FROM fin_docs"}, ctx)
    assert not denied.is_success and denied.error.code == "not_allowed"
    assert "fin_docs" in denied.error.message and records == []
    # 场景声明里混入全局白名单之外的表也不放行
    sneaky = {**CTX, "sql_tables": ("credit_applications", "evidence")}
    assert not _call(db, {"sql": "SELECT * FROM evidence"}, sneaky)[0].is_success


def test_scenario_description_lists_only_scenario_tables():
    from app.tools.sql_query import describe_for
    text = describe_for(("risk_transactions",))
    assert "risk_transactions" in text
    assert "credit_applications" not in text and "fin_docs" not in text


def test_row_limit_truncates(monkeypatch, db):
    from app.tools import sql_query as sql_query_module
    monkeypatch.setattr(sql_query_module, "_MAX_ROWS", 1)
    result, _, _ = _call(db, {
        "sql": "SELECT application_id FROM credit_applications ORDER BY application_id"})
    assert result.is_success
    assert result.data["rowCount"] == 1
    assert result.data["truncated"] is True


def test_standalone_function_uses_app_engine(db):
    """命令行 / 独立调用复用 app.db 的唯一引擎（待办 2-2）。"""
    from app.tools.sql_query import sql_query
    out = sql_query("SELECT doc_id FROM fin_docs ORDER BY doc_id LIMIT 1")
    assert out["output"] == [{"docId": "DOC-2026-001"}]
    with pytest.raises(ValueError):
        sql_query("DELETE FROM fin_docs")


def test_driver_values_become_jsonable():
    """MySQL 驱动返回的 Decimal / 日期 / bytes 要转成可写入证据快照 JSON 的值（真实库评测 pub-007 回归）。"""
    from datetime import date, datetime
    from decimal import Decimal

    from app.tools.sql_query import _jsonable

    values = [_jsonable(v) for v in (
        Decimal("95000"), Decimal("0.26"), date(2026, 10, 10),
        datetime(2026, 10, 10, 9, 38), b"abc", "text", None)]
    assert values == [95000, 0.26, "2026-10-10", "2026-10-10T09:38:00", "abc", "text", None]
    json.dumps(values)
