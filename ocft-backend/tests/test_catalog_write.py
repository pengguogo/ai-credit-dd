"""数据列表单行增删改（catalog-crud）。"""
HEADERS = {"X-Actor-Id": "tester"}


def test_catalog_rows_include_id(client):
    resp = client.get("/api/agent/catalog/enterprise_dd", params={"kind": "guarantees"}, headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"]
    assert isinstance(body["rows"][0]["id"], int)


def test_schema_relationships_rejects_write(client):
    resp = client.post(
        "/api/agent/catalog/enterprise_dd/schema_relationships/records",
        headers=HEADERS,
        json={"mainTable": "a", "childTable": "b"},
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "invalid_args"


def test_create_update_delete_guarantee(client):
    create = client.post(
        "/api/agent/catalog/enterprise_dd/guarantees/records",
        headers=HEADERS,
        json={
            "enterpriseId": "E001",
            "guaranteedParty": "CRUD测试担保方",
            "guaranteeAmount": 12.5,
            "guaranteeType": "连带责任",
            "guaranteePeriod": "2026-2027",
            "isOverdue": "否",
        },
    )
    assert create.status_code == 200, create.text
    record_id = create.json()["id"]

    patch = client.patch(
        f"/api/agent/catalog/enterprise_dd/guarantees/records/{record_id}",
        headers=HEADERS,
        json={"guaranteeAmount": 20},
    )
    assert patch.status_code == 200
    assert patch.json()["row"]["guaranteeAmount"] == 20

    delete = client.delete(
        f"/api/agent/catalog/enterprise_dd/guarantees/records/{record_id}",
        headers=HEADERS,
    )
    assert delete.status_code == 200
    assert delete.json()["deleted"] is True

    gone = client.delete(
        f"/api/agent/catalog/enterprise_dd/guarantees/records/{record_id}",
        headers=HEADERS,
    )
    assert gone.status_code == 404
