"""CSV 增量导入：日期格式兼容（2008/5/12、2008.5.12 规范化为 ISO）。"""
from uuid import uuid4

import pytest

from app.services.csv_import_service import _normalize_date

HEADERS = {"X-Actor-Id": "tester"}

BASIC_HEADER = ("enterprise_id,enterprise_name,credit_code,legal_person,legal_person_id,"
                "register_capital,registered_capital_paid,establish_date,enterprise_type,"
                "industry,register_address,business_scope,employee_count,"
                "related_enterprise_count,business_status,legal_person_dishonest,"
                "legal_person_consumption_limit,actual_controller")


def _basic_csv(enterprise_id: str, establish_date: str) -> str:
    row = (f"{enterprise_id},测试企业{enterprise_id},91310000TEST{enterprise_id},张三,"
           f"310***********0000,1000,1000,{establish_date},有限责任公司,制造业,上海市,"
           f"测试,10,0,在业,否,否,张三")
    return f"{BASIC_HEADER}\n{row}\n"


@pytest.mark.parametrize("raw, expected", [
    ("2008-05-12", "2008-05-12"),
    ("2008/5/12", "2008-05-12"),
    ("2008/05/12", "2008-05-12"),
    ("2008.5.12", "2008-05-12"),
    ("2008-5-2", "2008-05-02"),
])
def test_normalize_date_accepts_common_formats(raw, expected):
    assert _normalize_date(raw) == expected


@pytest.mark.parametrize("raw", [
    "2008/5-12",      # 分隔符混用
    "2008/2/30",      # 不存在的日期
    "12/5/2008",      # 年不在前
    "2008年5月12日",
    "20080512",
])
def test_normalize_date_rejects_invalid(raw):
    with pytest.raises(ValueError, match="日期格式无效"):
        _normalize_date(raw)


def test_import_stores_slash_and_dot_dates_as_iso(client):
    slash_id, dot_id = f"T{uuid4().hex[:8]}", f"T{uuid4().hex[:8]}"
    files = [{"fileName": "enterprise_basic.csv",
              "content": _basic_csv(slash_id, "2008/5/12")
              + _basic_csv(dot_id, "2008.5.12").split("\n", 1)[1]}]
    resp = client.post("/api/agent/data/imports", json={"files": files}, headers=HEADERS)
    assert resp.status_code == 200, resp.json()
    assert resp.json()["added"] == 2

    from app.db import SessionLocal
    from app.models import EnterpriseBasic
    with SessionLocal() as db:
        dates = {e.enterprise_id: e.establish_date for e in db.query(EnterpriseBasic)
                 .filter(EnterpriseBasic.enterprise_id.in_([slash_id, dot_id]))}
    assert dates == {slash_id: "2008-05-12", dot_id: "2008-05-12"}

    # 已存 ISO 后，再用另一种写法导入同一天视为完全相同，跳过而不是冲突
    again = [{"fileName": "enterprise_basic.csv", "content": _basic_csv(slash_id, "2008-05-12")}]
    resp = client.post("/api/agent/data/imports", json={"files": again}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["skipped"] == 1 and resp.json()["added"] == 0


def test_import_rejects_invalid_date_with_row_location(client):
    files = [{"fileName": "enterprise_basic.csv",
              "content": _basic_csv(f"T{uuid4().hex[:8]}", "2008/2/30")}]
    resp = client.post("/api/agent/data/imports", json={"files": files}, headers=HEADERS)
    assert resp.status_code == 422
    errors = resp.json()["errors"]
    assert errors and errors[0]["row"] == 2 and errors[0]["field"] == "establish_date"


_LOAN_HEADER_NO_STATUS = (
    "application_id,enterprise_id,apply_amount,loan_purpose,"
    "loan_term_months,apply_date,guarantee_type"
)


def test_loan_application_without_status_defaults_pending(client):
    """官方原始审批表可不带 status；缺列时默认 pending，不报 invalid_columns。"""
    app_id = f"LA{uuid4().hex[:8]}"
    ent_id = f"E{uuid4().hex[:8]}"
    files = [
        {"fileName": "enterprise_basic.csv", "content": _basic_csv(ent_id, "2020-01-01")},
        {"fileName": "loan_application.csv",
         "content": (f"{_LOAN_HEADER_NO_STATUS}\n"
                     f"{app_id},{ent_id},100,扩产,12,2024-01-01,抵押担保\n")},
    ]
    resp = client.post("/api/agent/data/imports", json={"files": files}, headers=HEADERS)
    assert resp.status_code == 200, resp.json()
    assert resp.json()["added"] == 2

    from app.db import SessionLocal
    from app.models import LoanApplication
    with SessionLocal() as db:
        row = db.query(LoanApplication).filter_by(application_id=app_id).one()
        assert row.status == "pending"


def test_loan_application_blank_status_defaults_pending(client):
    app_id = f"LA{uuid4().hex[:8]}"
    ent_id = f"E{uuid4().hex[:8]}"
    header = _LOAN_HEADER_NO_STATUS + ",status"
    files = [
        {"fileName": "enterprise_basic.csv", "content": _basic_csv(ent_id, "2020-01-01")},
        {"fileName": "loan_application.csv",
         "content": f"{header}\n{app_id},{ent_id},100,扩产,12,2024-01-01,抵押担保,\n"},
    ]
    resp = client.post("/api/agent/data/imports", json={"files": files}, headers=HEADERS)
    assert resp.status_code == 200, resp.json()
    from app.db import SessionLocal
    from app.models import LoanApplication
    with SessionLocal() as db:
        assert db.query(LoanApplication).filter_by(application_id=app_id).one().status == "pending"


def test_loan_application_rejects_invalid_status(client):
    app_id = f"LA{uuid4().hex[:8]}"
    ent_id = f"E{uuid4().hex[:8]}"
    header = _LOAN_HEADER_NO_STATUS + ",status"
    files = [
        {"fileName": "enterprise_basic.csv", "content": _basic_csv(ent_id, "2020-01-01")},
        {"fileName": "loan_application.csv",
         "content": f"{header}\n{app_id},{ent_id},100,扩产,12,2024-01-01,抵押担保,weird\n"},
    ]
    resp = client.post("/api/agent/data/imports", json={"files": files}, headers=HEADERS)
    assert resp.status_code == 422
    err = resp.json()["errors"][0]
    assert err["field"] == "status" and err["errorCode"] == "invalid_value"
