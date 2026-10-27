"""业务目录只返回原始字段，不计算尽调结论。"""
from uuid import uuid4

from tests.conftest import HEADERS

LIST_KINDS = (
    "applications", "shareholders", "finances", "public_opinions", "lawsuits",
    "related", "guarantees", "risks", "schema_relationships",
)


def test_dd_catalog_lists_applications(client):
    resp = client.get("/api/agent/catalog/enterprise_dd", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenarioId"] == "enterprise_dd"
    assert body["kind"] == "applications"
    assert body["rows"]
    assert {col["key"] for col in body["columns"]} >= {"applicationId", "enterpriseName", "status"}
    assert body["columns"][0]["label"] == "贷款编号"
    assert body["rows"][0]["status"] in {"pending", "pending_review", "approved", "rejected"}
    counts = body["statusCounts"]
    assert sum(counts[key] for key in ("pending", "pending_review", "approved", "rejected")) == body["total"]
    assert "riskLevel" not in body["rows"][0]
    # 外部汇总评级与公开答案一致，目录不展示（ADR-0008 决策 1）
    assert "externalRiskLevel" not in body["rows"][0]
    assert "externalRiskLevel" not in {col["key"] for col in body["columns"]}


def test_application_approval_status_filter_and_decide(client):
    listed = client.get("/api/agent/catalog/enterprise_dd",
                        params={"kind": "applications", "approvalStatus": "pending"},
                        headers=HEADERS)
    assert listed.status_code == 200
    body = listed.json()
    assert body["matched"] == body["statusCounts"]["pending"]
    assert body["rows"]
    assert all(row["status"] == "pending" for row in body["rows"])

    login = client.post("/api/auth/login",
                        json={"username": "account_manager", "password": "Demo@123"}).json()
    headers = {"Authorization": f"Bearer {login['token']}"}
    target = body["rows"][0]
    patched = client.patch(
        f"/api/agent/catalog/enterprise_dd/applications/records/{target['id']}",
        headers=headers,
        json={"status": "approved"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["row"]["status"] == "approved"
    rejected = client.patch(
        f"/api/agent/catalog/enterprise_dd/applications/records/{body['rows'][1]['id']}",
        headers=headers,
        json={"status": "rejected"},
    )
    assert rejected.status_code == 200

    all_rows = client.get("/api/agent/catalog/enterprise_dd",
                          params={"kind": "applications"}, headers=headers)
    assert all_rows.status_code == 200
    for status in ("pending", "pending_review", "approved", "rejected"):
        response = client.get("/api/agent/catalog/enterprise_dd",
                              params={"kind": "applications", "approvalStatus": status},
                              headers=headers)
        assert response.status_code == 200
        result = response.json()
        expected_ids = {row["id"] for row in all_rows.json()["rows"] if row["status"] == status}
        assert result["approvalStatus"] == status
        assert result["total"] == all_rows.json()["total"]
        assert result["matched"] == result["statusCounts"][status] == len(expected_ids)
        assert {row["id"] for row in result["rows"]} == expected_ids

    searched = client.get("/api/agent/catalog/enterprise_dd",
                          params={"kind": "applications", "q": "审核通过"},
                          headers=headers)
    assert searched.status_code == 200
    assert searched.json()["matched"] == all_rows.json()["statusCounts"]["approved"]
    assert all(row["status"] == "approved" for row in searched.json()["rows"])

    # 关键词与状态必须同时满足，不能因为关键词命中就越过审批状态。
    missed = client.get("/api/agent/catalog/enterprise_dd",
                        params={"kind": "applications", "approvalStatus": "pending",
                                "q": target["applicationId"]}, headers=headers)
    assert missed.status_code == 200
    assert missed.json()["rows"] == []
    assert missed.json()["matched"] == 0
    assert missed.json()["total"] == all_rows.json()["total"]


def test_application_status_filter_rejects_invalid_parameters(client):
    for params in ({"kind": "applications", "approvalStatus": "unknown"},
                   {"kind": "enterprises", "approvalStatus": "pending"}):
        response = client.get("/api/agent/catalog/enterprise_dd", params=params, headers=HEADERS)
        assert response.status_code == 400
        assert response.json()["errorCode"] == "invalid_args"


def test_dd_catalog_lists_enterprises(client):
    resp = client.get("/api/agent/catalog/enterprise_dd",
                      params={"kind": "enterprises"}, headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "enterprises"
    assert body["rows"]
    assert {col["key"] for col in body["columns"]} >= {"enterpriseId", "industry"}
    assert "applicationId" not in body["rows"][0]
    assert "riskLevel" not in body["rows"][0]


def test_dd_catalog_lists_list_page_tables(client):
    assert len(LIST_KINDS) == 9
    for kind in LIST_KINDS:
        resp = client.get("/api/agent/catalog/enterprise_dd",
                          params={"kind": kind}, headers=HEADERS)
        assert resp.status_code == 200, kind
        body = resp.json()
        assert body["kind"] == kind
        assert body["columns"]
        assert body["total"] >= 0
        if body["rows"] and kind != "schema_relationships":
            assert "enterpriseId" in body["rows"][0] or "applicationId" in body["rows"][0]
            assert "riskLevel" not in body["rows"][0]


def test_dd_catalog_filters_in_database(client):
    resp = client.get("/api/agent/catalog/enterprise_dd", params={"q": "LA001"}, headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "LA001"
    assert body["total"] > body["matched"] > 0
    assert {row["applicationId"] for row in body["rows"]} == {"LA001"}


def test_dd_catalog_enterprise_filter(client):
    resp = client.get("/api/agent/catalog/enterprise_dd",
                      params={"kind": "enterprises", "q": "E001"}, headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] >= 1
    assert {row["enterpriseId"] for row in body["rows"]} == {"E001"}


def test_dd_catalog_finance_filter(client):
    resp = client.get("/api/agent/catalog/enterprise_dd",
                      params={"kind": "finances", "q": "E001"}, headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] >= 1
    assert {row["enterpriseId"] for row in body["rows"]} == {"E001"}


def test_dd_catalog_filter_miss(client):
    resp = client.get("/api/agent/catalog/enterprise_dd", params={"q": "不存在的编号"}, headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []
    assert body["matched"] == 0
    assert body["total"] > 0


def test_dd_catalog_invalid_kind(client):
    resp = client.get("/api/agent/catalog/enterprise_dd",
                      params={"kind": "unknown"}, headers=HEADERS)
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "invalid_args"


def test_unknown_catalog_scenario(client):
    resp = client.get("/api/agent/catalog/credit_review", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "unknown_scenario"


def test_application_open_filter_lists_only_pending_and_pending_review(client):
    """智能尽调列表用 open：只返回待处理与待审核，不含已审结的申请。"""
    body = client.get("/api/agent/catalog/enterprise_dd",
                      params={"kind": "applications", "approvalStatus": "open"},
                      headers=HEADERS).json()
    counts = body["statusCounts"]
    assert body["approvalStatus"] == "open"
    assert body["matched"] == counts["pending"] + counts["pending_review"]
    assert all(row["status"] in {"pending", "pending_review"} for row in body["rows"])


def _login(client, username: str = "account_manager", password: str = "Demo@123") -> dict:
    login = client.post("/api/auth/login",
                        json={"username": username, "password": password}).json()
    return {"Authorization": f"Bearer {login['token']}"}


def _create_application(client, headers: dict, application_id: str) -> int:
    created = client.post(
        "/api/agent/catalog/enterprise_dd/applications/records",
        headers=headers,
        json={
            "applicationId": application_id, "enterpriseId": "E001",
            "applyAmount": 500, "loanPurpose": "人工审核回归",
            "loanTermMonths": 12, "applyDate": "2026-10-01",
            "guaranteeType": "信用担保", "status": "pending",
        },
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _review_url(record_id: int) -> str:
    return f"/api/agent/catalog/enterprise_dd/applications/records/{record_id}/review"


def test_application_rows_expose_has_report_and_review_fields(client):
    """智能尽调的「查看报告」按 hasReport 决定可点 / 置灰，审核留痕随行返回。"""
    body = client.get("/api/agent/catalog/enterprise_dd",
                      params={"kind": "applications"}, headers=HEADERS).json()
    assert body["rows"]
    row = body["rows"][0]
    assert isinstance(row["hasReport"], bool)
    for key in ("reviewReason", "reviewedBy", "reviewedAt"):
        assert key in row


def test_application_review_requires_reason_and_records_decision(client):
    """审核只针对待审核申请；通过 / 拒绝必须填原因，并记录审核人与时间。"""
    headers = _login(client)
    application_id = "LA9R" + uuid4().hex[:5].upper()
    record_id = _create_application(client, headers, application_id)

    # 待处理（尚无尽调报告）不能直接审核
    early = client.post(_review_url(record_id), headers=headers,
                        json={"decision": "approved", "reason": "先斩后奏"})
    assert early.status_code == 409
    assert early.json()["errorCode"] == "invalid_state"

    advanced = client.patch(
        f"/api/agent/catalog/enterprise_dd/applications/records/{record_id}",
        headers=headers, json={"status": "pending_review"})
    assert advanced.status_code == 200, advanced.text

    missing = client.post(_review_url(record_id), headers=headers,
                          json={"decision": "approved", "reason": "   "})
    assert missing.status_code == 400
    assert missing.json()["errorCode"] == "invalid_args"

    invalid = client.post(_review_url(record_id), headers=headers,
                          json={"decision": "maybe", "reason": "结论非法"})
    assert invalid.status_code == 400

    reviewed = client.post(_review_url(record_id), headers=headers,
                           json={"decision": "approved", "reason": "材料齐全，同意放款"})
    assert reviewed.status_code == 200, reviewed.text
    row = reviewed.json()["row"]
    assert row["status"] == "approved"
    assert row["reviewReason"] == "材料齐全，同意放款"
    assert row["reviewedBy"] == "account_manager"
    assert row["reviewedAt"].endswith("Z")

    listed = client.get("/api/agent/catalog/enterprise_dd",
                        params={"kind": "applications", "q": application_id},
                        headers=headers).json()
    assert listed["rows"][0]["status"] == "approved"
    assert listed["rows"][0]["reviewReason"] == "材料齐全，同意放款"

    # 已审结的申请不再出现在智能尽调的未审结列表
    pending_only = client.get("/api/agent/catalog/enterprise_dd",
                              params={"kind": "applications", "approvalStatus": "open",
                                      "q": application_id},
                              headers=headers).json()
    assert pending_only["rows"] == []

    again = client.post(_review_url(record_id), headers=headers,
                        json={"decision": "rejected", "reason": "重复审核"})
    assert again.status_code == 409

    # 审核与审计同一事务：审计表 status 是 VARCHAR(16)，值不能超长（MySQL 会报 1406）
    from app.db import SessionLocal
    from app.models import CsvImportAudit

    with SessionLocal() as db:
        audit = (db.query(CsvImportAudit)
                 .filter(CsvImportAudit.status == "catalog_reviewed")
                 .order_by(CsvImportAudit.created_at.desc(), CsvImportAudit.id.desc())
                 .first())
        assert audit is not None
        assert audit.summary["keys"]["applicationId"] == application_id
        assert audit.summary["keys"]["reviewDecision"] == "approved"
        assert audit.summary["keys"]["reason"] == "材料齐全，同意放款"
        assert len("catalog_reviewed") <= CsvImportAudit.__table__.c.status.type.length


def test_application_review_requires_confirm_permission(client):
    """只读角色不能审核贷款申请。"""
    viewer = _login(client, "viewer", "View@123")
    denied = client.post(_review_url(1), headers=viewer,
                         json={"decision": "approved", "reason": "越权审核"})
    assert denied.status_code == 403
