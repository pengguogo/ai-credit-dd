"""离线交付：有前端构建产物时由后端提供页面（待办 4-7）。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import main
from app.config import settings


@pytest.fixture
def frontend_client(tmp_path):
    (tmp_path / "index.html").write_text('<div id="root">workbench</div>', encoding="utf-8")
    (tmp_path / "report-preview.html").write_text("<div>preview</div>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('asset')", encoding="utf-8")
    app = FastAPI()
    app.mount("/", main._FrontendFiles(directory=tmp_path, html=True), name="frontend")
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("path", [
    "/login", "/admin", "/tables", "/tables/enterprise", "/workspace", "/workspace/",
    "/report", "/report/business?enterpriseId=E001", "/report/finance/",
])
def test_frontend_routes_refresh_to_workbench(frontend_client, path):
    response = frontend_client.get(path)
    assert response.status_code == 200
    assert "workbench" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_frontend_route_head_has_no_body(frontend_client):
    response = frontend_client.head("/report/business?enterpriseId=E001")
    assert response.status_code == 200
    assert response.content == b""


@pytest.mark.parametrize("path", [
    "/assets/missing.js", "/report/missing.js", "/missing.html",
    "/no-such-page", "/report/business/extra", "/workspace/extra", "/report/../missing",
])
def test_missing_files_and_unknown_pages_stay_404(frontend_client, path):
    response = frontend_client.get(path)
    assert response.status_code == 404
    assert "workbench" not in response.text


@pytest.mark.parametrize("path", ["/api", "/api/no-such-route"])
def test_unknown_api_routes_never_receive_workbench(frontend_client, path):
    for method in ("get", "post"):
        response = getattr(frontend_client, method)(path)
        assert response.status_code == 404
        assert "workbench" not in response.text


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_frontend_route_write_methods_stay_405(frontend_client, method):
    response = getattr(frontend_client, method)("/report/business")
    assert response.status_code == 405
    assert "workbench" not in response.text


def test_existing_files_are_not_replaced_with_workbench(frontend_client):
    assert "preview" in frontend_client.get("/report-preview.html").text
    assert frontend_client.get("/assets/app.js").text == "console.log('asset')"


def test_frontend_dist_detected_only_with_index(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "frontend_dist_dir", str(tmp_path))
    assert main._frontend_dist() is None          # 没有 index.html 不挂载
    (tmp_path / "index.html").write_text("<div id=\"root\"></div>", encoding="utf-8")
    assert main._frontend_dist() == tmp_path


def test_relative_dist_resolves_from_backend_root(monkeypatch):
    monkeypatch.setattr(settings, "frontend_dist_dir", "no-such-dir-for-test")
    assert main._frontend_dist() is None


def test_api_routes_take_precedence_over_frontend(client):
    # 无论 dist 是否存在，/api 路由都先于静态页面匹配
    assert client.get("/api/health/live").json()["status"] == "ok"


def test_unknown_api_path_is_404_with_frontend_mounted(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    (tmp_path / "index.html").write_text("<div id=\"root\"></div>", encoding="utf-8")
    app = FastAPI()
    app.mount("/", main._FrontendFiles(directory=tmp_path, html=True), name="frontend")
    with TestClient(app) as c:
        assert c.get("/").status_code == 200 and "root" in c.get("/").text
        assert c.post("/api/no-such-route").status_code == 404
        assert c.get("/api/no-such-route").status_code == 404
