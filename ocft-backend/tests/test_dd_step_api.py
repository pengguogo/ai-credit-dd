"""单步尽调核对 API：不经模型，只跑当前步骤工具。"""

HEADERS = {"X-Actor-Id": "account_manager"}


def test_dd_step_business_ok(client):
    resp = client.post(
        "/api/agent/dd/steps",
        headers=HEADERS,
        json={"step": "business", "enterpriseId": "E001"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["step"] == "business"
    assert body["status"] == "ok"
    assert body["tools"][0]["toolName"] == "verify_business_info"
    assert body["tools"][0]["status"] == "ok"
    assert body["tools"][0]["data"]
    assert "riskLevel" not in (body["tools"][0]["data"] or {})


def test_dd_step_credit_risk_resolves_latest_application(client):
    resp = client.post(
        "/api/agent/dd/steps",
        headers=HEADERS,
        json={"step": "credit-risk", "enterpriseId": "E001"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["applicationId"]
    names = {t["toolName"]: t for t in body["tools"]}
    assert names["rate_risk"]["status"] == "ok"
    assert names["calc_credit_limit"]["status"] == "ok"


def test_dd_step_report_ok(client):
    resp = client.post(
        "/api/agent/dd/steps",
        headers=HEADERS,
        json={"step": "report", "enterpriseId": "E001"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["step"] == "report"
    assert body["status"] == "ok"
    assert body["applicationId"]
    tool = body["tools"][0]
    assert tool["toolName"] == "build_dd_report"
    assert tool["status"] == "ok"
    assert tool["data"]["sections"]
    assert tool["data"]["riskLevel"]


def test_dd_step_requires_id(client):
    resp = client.post(
        "/api/agent/dd/steps",
        headers=HEADERS,
        json={"step": "finance"},
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "invalid_args"


def test_report_keeps_selected_loan_amount_when_company_has_newer_application(client):
    """同企业多笔申请：按所选申请出报告，不能替换为最近一笔。"""
    from app.db import SessionLocal
    from app.models import LoanApplication

    with SessionLocal() as db:
        original = db.query(LoanApplication).filter_by(enterprise_id="E001").first()
        application_id = original.application_id
        amount = original.apply_amount
        db.add(LoanApplication(
            application_id="SYNTHETIC-NEWER", enterprise_id="E001",
            apply_amount=99, loan_purpose="采购", loan_term_months=12,
            apply_date="2025-01-01", guarantee_type="信用担保", status="pending",
        ))
        db.commit()

    try:
        response = client.post("/api/agent/dd/steps", headers=HEADERS,
                               json={"step": "report", "applicationId": application_id})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["applicationId"] == application_id
        assert body["enterpriseId"] == "E001"
        credit = body["tools"][0]["data"]["sections"]["creditSuggestion"]
        assert credit["applyAmount"] == amount
        assert any(step["step"] == "申请额封顶" for step in credit["steps"])
    finally:
        with SessionLocal() as db:
            db.query(LoanApplication).filter_by(application_id="SYNTHETIC-NEWER").delete()
            db.commit()



def test_report_role_receives_selected_application_amount():
    """报告模型也必须拿到申请额，不能只有展示层有值。"""
    from app.agent.dd_roles import brief

    credit = {"applyAmount": 1234.0, "suggestedCreditAmount": "800-1000",
              "steps": [{"step": "申请额封顶", "value": 1000}]}
    result = brief("rating", {"rating": {}, "credit": credit})["credit"]
    assert result["applyAmount"] == 1234.0
    assert result["steps"] == credit["steps"]
