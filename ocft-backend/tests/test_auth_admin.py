"""登录与系统管理 API。"""
from tests.conftest import HEADERS


def test_login_and_me(client):
    bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401

    ok = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@123"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["user"]["roleCode"] == "admin"
    token = body["token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "admin"

    # Bearer 可替代 X-Actor-Id 访问 agent 接口
    conv = client.get("/api/agent/conversations", headers={"Authorization": f"Bearer {token}"})
    assert conv.status_code == 200


def test_admin_users_roles(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@123"}).json()
    headers = {"Authorization": f"Bearer {login['token']}"}

    roles = client.get("/api/admin/roles", headers=headers)
    assert roles.status_code == 200
    codes = {r["code"] for r in roles.json()["roles"]}
    assert "admin" in codes and "account_manager" in codes

    created = client.post("/api/admin/users", headers=headers, json={
        "username": "ops_demo",
        "displayName": "运维演示",
        "password": "Ops@123456",
        "roleCode": "viewer",
    })
    assert created.status_code == 200
    assert created.json()["username"] == "ops_demo"

    # 非管理员不可进系统管理
    viewer = client.post("/api/auth/login", json={"username": "viewer", "password": "View@123"}).json()
    denied = client.get("/api/admin/users", headers={"Authorization": f"Bearer {viewer['token']}"})
    assert denied.status_code == 403


def test_legacy_actor_header_still_works(client):
    res = client.get("/api/agent/conversations", headers=HEADERS)
    assert res.status_code == 200


def test_viewer_cannot_see_applications_or_confirm(client):
    viewer = client.post("/api/auth/login", json={"username": "viewer", "password": "View@123"}).json()
    headers = {"Authorization": f"Bearer {viewer['token']}"}
    perms = set(viewer["user"]["permissions"])
    assert "dd_steps" in perms
    assert "confirm" not in perms
    assert "applications" not in perms

    denied_app = client.get(
        "/api/agent/catalog/enterprise_dd",
        params={"kind": "applications"},
        headers=headers,
    )
    assert denied_app.status_code == 403

    ok_ent = client.get(
        "/api/agent/catalog/enterprise_dd",
        params={"kind": "enterprises"},
        headers=headers,
    )
    assert ok_ent.status_code == 200

    denied_confirm = client.post(
        "/api/agent/runs/run_missing/confirmations",
        headers=headers,
        json={
            "answerVersion": 1,
            "action": "confirm",
            "idempotencyKey": "viewer-confirm-denied",
        },
    )
    assert denied_confirm.status_code == 403


def test_account_manager_sees_applications(client):
    login = client.post(
        "/api/auth/login", json={"username": "account_manager", "password": "Demo@123"}
    ).json()
    headers = {"Authorization": f"Bearer {login['token']}"}
    assert "confirm" in login["user"]["permissions"]
    assert "applications" in login["user"]["permissions"]
    res = client.get(
        "/api/agent/catalog/enterprise_dd",
        params={"kind": "applications"},
        headers=headers,
    )
    assert res.status_code == 200
