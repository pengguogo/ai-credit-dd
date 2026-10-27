"""报告列表（评审维度②「会议与资产管理」）：建档、检索。

报告本身不再有状态：确认 / 驳回 / 归档已从接口与页面移除，审核结论记在贷款申请
（待处理 → 待审核 → 审核通过 / 审核不通过）。
"""
from types import SimpleNamespace
from uuid import uuid4

from app.db import SessionLocal
from app.models import EnterpriseBasic, Evidence, LoanApplication, WorkspaceAsset
from app.services import workspace_service

HEADERS = {"X-Actor-Id": "tester"}


REPORT = ("# 企业智能信贷尽调报告\n\n**尽调结论**：测试结论，额度 600-800 万元。\n\n"
          "## 企业概况\n\n## 财务分析\n\n## 风险提示\n\n## 额度建议\n\n## 风控条件\n")


def _run(run_id: str, application_id: str, answer: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=run_id, scenario_id="enterprise_dd", conversation_id="conv-" + run_id,
        answer=answer if answer is not None else REPORT,
        context_snapshot={"entities": {"applicationId": [application_id],
                                       "enterpriseId": ["E" + application_id[-3:]]}},
    )


def _seed_asset(application_id: str | None = None, evidence_count: int = 2):
    run_id = "run_ast_" + uuid4().hex[:10]
    application_id = application_id or "LA9" + uuid4().hex[:2]
    with SessionLocal() as db:
        for index in range(evidence_count):
            db.add(Evidence(id=f"ev_{uuid4().hex[:12]}", run_id=run_id,
                            source_type="calculation", source_ref={"calc": "test"},
                            snapshot={"index": index}, content_hash="hash", data_version=1))
        asset = workspace_service.register_asset(db, _run(run_id, application_id), "tester")
        db.commit()
        return asset.id, run_id, application_id


def _seed_application(status: str) -> str:
    application_id = "LA9" + uuid4().hex[:6]
    with SessionLocal() as db:
        db.add(LoanApplication(
            application_id=application_id, enterprise_id="E" + application_id[-3:],
            apply_amount=100.0, loan_purpose="测试", loan_term_months=12,
            apply_date="2026-01-01", guarantee_type="信用担保", status=status))
        db.commit()
    return application_id


def test_register_is_idempotent_and_indexes_scope(client):
    asset_id, run_id, application_id = _seed_asset()
    with SessionLocal() as db:
        again = workspace_service.register_asset(db, _run(run_id, application_id), "tester")
        db.commit()
        assert again.id == asset_id
        page = workspace_service.list_assets(db, keyword=application_id)
        assert page["total"] == 1 and page["assets"][0]["id"] == asset_id
        assert page["assets"][0]["evidenceCount"] == 2
        assert application_id in page["assets"][0]["title"]


def test_followup_answer_is_not_registered_as_asset(client):
    run_id = "run_ast_" + uuid4().hex[:10]
    with SessionLocal() as db:
        asset = workspace_service.register_asset(
            db, _run(run_id, "LA900", answer="建议额度 600-800 万元，测算建议非授信审批。"), "t")
        db.commit()
        assert asset is None


def test_register_advances_pending_application_to_pending_review(client):
    application_id = _seed_application("pending")
    _seed_asset(application_id=application_id)
    with SessionLocal() as db:
        assert db.query(LoanApplication).filter_by(
            application_id=application_id).one().status == "pending_review"


def test_register_does_not_override_decided_application(client):
    application_id = _seed_application("approved")
    _seed_asset(application_id=application_id)
    with SessionLocal() as db:
        assert db.query(LoanApplication).filter_by(
            application_id=application_id).one().status == "approved"


def test_report_has_no_status_or_events(client):
    asset_id, _, application_id = _seed_asset()
    listed = client.get("/api/agent/assets", headers=HEADERS,
                        params={"applicationId": application_id}).json()
    assert listed["total"] == 1
    item = listed["assets"][0]
    for key in ("status", "statusLabel", "version", "archivedAt", "events",
                "statusCounts", "pendingCount"):
        assert key not in item and key not in listed
    detail = client.get(f"/api/agent/assets/{asset_id}", headers=HEADERS).json()
    for key in ("status", "statusLabel", "version", "archivedAt", "events"):
        assert key not in detail
    # 报告状态操作接口已移除（路由不存在）
    assert client.post(f"/api/agent/assets/{asset_id}/status",
                       json={"action": "confirm"}, headers=HEADERS).status_code in (404, 405)


def test_workspace_api_list_and_detail(client):
    asset_id, _, application_id = _seed_asset()
    listed = client.get("/api/agent/assets",
                        params={"applicationId": application_id}, headers=HEADERS)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 1 and body["assets"][0]["id"] == asset_id

    detail = client.get(f"/api/agent/assets/{asset_id}", headers=HEADERS)
    assert detail.status_code == 200
    assert detail.json()["runId"].startswith("run_ast_")
    assert detail.json()["summary"].startswith("尽调结论")

    missing = client.get("/api/agent/assets/ast_missing", headers=HEADERS)
    assert missing.status_code == 404


def test_workspace_enterprise_name_and_search(client):
    """TC-WA-08：新旧档案读取真实企业名称，名称检索先过滤再分页。"""
    asset_ids = [_seed_asset()[0], _seed_asset()[0]]
    with SessionLocal() as db:
        template = db.query(EnterpriseBasic).first()
        fields = {column.name: getattr(template, column.name)
                  for column in EnterpriseBasic.__table__.columns if column.name != "id"}
        fields.update(enterprise_id="E_UI_" + uuid4().hex[:10],
                      enterprise_name="中文界面回归企业" + uuid4().hex[:10])
        enterprise = EnterpriseBasic(**fields)
        db.add(enterprise)
        for asset_id in asset_ids:
            db.get(WorkspaceAsset, asset_id).enterprise_id = enterprise.enterprise_id
        db.commit()
        enterprise_name = enterprise.enterprise_name

    listed = client.get("/api/agent/assets", headers=HEADERS,
                        params={"enterpriseId": fields["enterprise_id"]}).json()
    assert {item["id"] for item in listed["assets"]} == set(asset_ids)
    assert all(item["enterpriseName"] == enterprise_name for item in listed["assets"])

    first = client.get("/api/agent/assets", headers=HEADERS,
                       params={"keyword": enterprise_name, "limit": 1}).json()
    second = client.get("/api/agent/assets", headers=HEADERS,
                        params={"keyword": enterprise_name, "limit": 1, "offset": 1}).json()
    assert first["total"] == second["total"] == 2
    assert first["hasMore"] is True and second["hasMore"] is False
    assert {first["assets"][0]["id"], second["assets"][0]["id"]} == set(asset_ids)

    detail = client.get(f"/api/agent/assets/{asset_ids[0]}", headers=HEADERS).json()
    assert detail["enterpriseName"] == enterprise_name


def test_workspace_missing_enterprise_keeps_archive(client):
    """TC-WA-09：企业资料缺失仍返回档案，读取时不重写历史标题。"""
    asset_id, run_id, application_id = _seed_asset()
    with SessionLocal() as db:
        asset = db.get(WorkspaceAsset, asset_id)
        asset.enterprise_id = "missing_" + uuid4().hex[:10]
        original_title = asset.title
        db.commit()

    listed = client.get("/api/agent/assets", headers=HEADERS,
                        params={"applicationId": application_id}).json()
    assert listed["total"] == 1
    assert listed["assets"][0]["enterpriseName"] is None
    detail = client.get(f"/api/agent/assets/{asset_id}", headers=HEADERS).json()
    assert detail["enterpriseName"] is None
    assert detail["applyAmount"] is None
    assert detail["reportGeneratedAt"] == detail["createdAt"]
    assert detail["runId"] == run_id and detail["title"] == original_title
    with SessionLocal() as db:
        assert db.get(WorkspaceAsset, asset_id).title == original_title


def test_report_listing_amount_snapshot_and_generation_time(client):
    """报告列表金额来自各自快照，生成时间不随档案更新变化。"""
    from datetime import datetime
    from app.models import AgentRun

    asset_ids = [_seed_asset()[0], _seed_asset()[0], _seed_asset()[0]]
    finished_at = datetime(2026, 10, 24, 8, 30)
    with SessionLocal() as db:
        for index, asset_id in enumerate(asset_ids):
            asset = db.get(WorkspaceAsset, asset_id)
            asset.enterprise_id = 'same_borrower'
            asset.updated_at = datetime(2026, 10, 25, 9, 0)
            db.add(AgentRun(id=asset.run_id, conversation_id='test-report-list',
                            scenario_id='enterprise_dd', question='测试报告', status='succeeded',
                            model='test', owner_id='tester', finished_at=finished_at))
            if index < 2:
                db.add(Evidence(id='ev_' + uuid4().hex[:12], run_id=asset.run_id,
                                source_type='calculation', source_ref={'calc': 'calc_credit_limit'},
                                snapshot={'applyAmount': 9999}, content_hash='test', data_version=1))
                db.add(Evidence(id='ev_' + uuid4().hex[:12], run_id=asset.run_id,
                                source_type='calculation', source_ref={'calc': 'build_dd_report'},
                                snapshot={'creditSuggestion': {'applyAmount': [1250.5, 0][index]}},
                                content_hash='test', data_version=1))
        db.commit()
    for index, asset_id in enumerate(asset_ids):
        detail = client.get(f'/api/agent/assets/{asset_id}', headers=HEADERS).json()
        assert detail['applyAmount'] == [1250.5, 0, None][index]
        assert detail['reportGeneratedAt'] == '2026-10-24T08:30:00Z'
        assert detail['updatedAt'] != detail['reportGeneratedAt']
        page = client.get('/api/agent/assets', headers=HEADERS,
                          params={'applicationId': detail['applicationId']}).json()
        listed = next(row for row in page['assets'] if row['id'] == asset_id)
        assert listed['applyAmount'] == detail['applyAmount']
        assert listed['reportGeneratedAt'] == detail['reportGeneratedAt']


def test_catalog_application_has_report_flag(client):
    """智能尽调「查看报告」按是否已建档报告启用/置灰，不靠状态猜。"""
    application_id = "LA9" + uuid4().hex[:6]
    with SessionLocal() as db:
        db.add(LoanApplication(
            application_id=application_id, enterprise_id="E001", apply_amount=100.0,
            loan_purpose="报告标记回归", loan_term_months=12, apply_date="2026-01-01",
            guarantee_type="信用担保", status="pending"))
        db.commit()

    def row() -> dict:
        body = client.get("/api/agent/catalog/enterprise_dd",
                          params={"kind": "applications", "q": application_id},
                          headers=HEADERS).json()
        assert body["matched"] == 1
        return body["rows"][0]

    assert row()["hasReport"] is False
    assert row()["status"] == "pending"

    _seed_asset(application_id=application_id)
    updated = row()
    assert updated["hasReport"] is True
    assert updated["status"] == "pending_review"


def test_archived_report_trace_and_evidence_open_for_other_users(client):
    """已建档报告：他人也能打开运行详情、证据与事件；未建档的对话 run 仍只限本人。"""
    from app.models import AgentRun
    from app.services import run_service

    def add_run(run_id: str) -> None:
        with SessionLocal() as db:
            db.add(AgentRun(id=run_id, conversation_id="conv-" + run_id, scenario_id="enterprise_dd",
                            question="尽调", status="succeeded", answer=REPORT, model="test",
                            owner_id="tester", context_snapshot={}, usage={}))
            db.commit()

    _asset_id, run_id, _ = _seed_asset()
    add_run(run_id)
    loose_id = "run_loose_" + uuid4().hex[:8]
    add_run(loose_id)
    reviewer = {"X-Actor-Id": "reviewer"}
    assert client.get(f"/api/agent/runs/{run_id}", headers=reviewer).status_code == 200
    evidence = client.get(f"/api/agent/runs/{run_id}/evidence", headers=reviewer)
    assert evidence.status_code == 200 and len(evidence.json()["evidence"]) == 2
    assert client.get(f"/api/agent/runs/{run_id}/events", headers=reviewer).status_code == 200
    assert client.get(f"/api/agent/runs/{loose_id}", headers=reviewer).status_code == 403
    assert client.get(f"/api/agent/runs/{loose_id}", headers=HEADERS).status_code == 200
