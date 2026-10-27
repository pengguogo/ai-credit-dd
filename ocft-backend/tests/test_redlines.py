"""红线回归：运行时数据与接口不含评测标签 / 预存结论，答题入口只有 /api/agent/runs。"""
from sqlalchemy import inspect

from app import seed
from app.db import engine

LABEL_FIELDS = {"is_fraud", "fraud_type", "decision", "decision_reason", "extracted_kpis"}
LABEL_KEYS = {"isFraud", "fraudType", "decision", "decisionReason", "extractedKpis"}


def test_runtime_tables_have_no_label_columns(client):
    inspector = inspect(engine)
    for table in ("credit_applications", "risk_transactions", "claim_cases", "fin_docs"):
        columns = {c["name"] for c in inspector.get_columns(table)}
        assert not (columns & LABEL_FIELDS), f"{table} 含评测标签列: {columns & LABEL_FIELDS}"


def test_seed_has_no_label_keys():
    for rows in (seed.CREDIT_APPLICATIONS, seed.TRANSACTIONS, seed.CLAIMS, seed.FIN_DOCS):
        for row in rows:
            assert not (set(row) & LABEL_KEYS), f"种子含评测标签: {set(row) & LABEL_KEYS}"
    # 历史审批结论不暴露：申请状态统一为 pending
    assert {r["status"] for r in seed.CREDIT_APPLICATIONS} == {"pending"}


def test_legacy_routes_removed(client):
    for method, path in [("post", "/api/credit/applications/APP-2026-1003/review"),
                         ("post", "/api/claims/cases/CLM-2026-0301/adjudicate"),
                         ("post", "/api/risk/transactions/TXN-88421004/assess"),
                         ("post", "/api/chat/stream"),
                         ("post", "/api/docs/DOC-2026-001/extract")]:
        assert getattr(client, method)(path).status_code == 404, path
