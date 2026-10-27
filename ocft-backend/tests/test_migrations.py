"""版本化迁移（待办 2-3）与统一数据库层（待办 2-2）。"""
import pytest
from sqlalchemy import create_engine, inspect, text

from app import migrations
from app.migrations import Migration, add_column_if_missing, applied_versions, run_migrations


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")
    yield eng
    eng.dispose()


_APPLIED = [1, 2, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15]


def test_baseline_creates_all_tables_and_is_idempotent(engine):
    assert run_migrations(engine) == _APPLIED
    tables = set(inspect(engine).get_table_names())
    assert {"credit_applications", "risk_transactions", "claim_cases", "fin_docs",
            "loan_application", "enterprise_basic", "enterprise_finance",
            "agent_runs", "evidence", "audit_logs", "run_events", "llm_calls", "conversation_memories", "memory_events", "workspace_assets", "workspace_asset_events", "schema_migrations"} <= tables
    assert not {"credit_decisions", "fraud_decisions", "claim_decisions"} & tables
    assert "scenario_id" in {c["name"] for c in inspect(engine).get_columns("conversations")}
    loan_columns = {c["name"] for c in inspect(engine).get_columns("loan_application")}
    assert {"status", "review_reason", "reviewed_by", "reviewed_at"} <= loan_columns
    assert run_migrations(engine) == []          # 第二次什么都不做
    assert applied_versions(engine) == _APPLIED


def test_new_migration_adds_column_once_and_keeps_data(engine):
    run_migrations(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO fin_docs (doc_id, doc_type, company, period, raw_text, difficulty) "
                          "VALUES ('D1', '年报', 'X', '2026', '正文', '')"))
    next_ver = max(_APPLIED) + 1
    extra = migrations.MIGRATIONS + (Migration(
        next_ver, "fin_docs 增加 source_url",
        lambda c: add_column_if_missing(c, "fin_docs", "source_url", "VARCHAR(200) NULL")),)
    assert run_migrations(engine, extra) == [next_ver]
    assert run_migrations(engine, extra) == []
    cols = {c["name"] for c in inspect(engine).get_columns("fin_docs")}
    assert "source_url" in cols
    with engine.connect() as conn:
        assert conn.execute(text("SELECT doc_id FROM fin_docs")).scalar() == "D1"   # 已有数据保留


def test_migration_versions_must_increase(engine):
    bad = (Migration(2, "b", lambda c: None), Migration(1, "a", lambda c: None))
    with pytest.raises(ValueError, match="递增"):
        run_migrations(engine, bad)


def test_failed_migration_is_not_recorded(engine):
    run_migrations(engine)

    def boom(_conn):
        raise RuntimeError("迁移失败")
    next_ver = max(_APPLIED) + 1
    with pytest.raises(RuntimeError):
        run_migrations(engine, migrations.MIGRATIONS + (Migration(next_ver, "boom", boom),))
    assert applied_versions(engine) == _APPLIED       # 失败的版本不登记，修好后可重跑


def test_add_column_rejects_unsafe_identifiers(engine):
    run_migrations(engine)
    with engine.begin() as conn, pytest.raises(ValueError, match="非法标识符"):
        add_column_if_missing(conn, "fin_docs; DROP TABLE x", "c", "INT")


def test_db_seed_cli_runs_against_configured_database(client, capsys):
    """python -m db.seed 走 app.db 的同一个引擎：迁移已执行、样例已导入时重跑无副作用。"""
    from db.seed import main
    main()
    out = capsys.readouterr().out
    assert f"已执行版本 {_APPLIED}" in out and "跳过" in out

