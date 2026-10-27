"""可观测性（待办 1-3）：请求 ID、节点耗时、实时 SSE 与续传、结构化日志不含 PII。"""
import json
import logging
import threading
import time

from app.observability.events import EventBus
from app.observability.logging import JsonFormatter
from conftest import HEADERS, model_reply, tool_call


def _sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = [ln for ln in block.splitlines() if ln and not ln.startswith(":")]
        if not lines:
            continue
        fields = dict(ln.split(": ", 1) for ln in lines)
        data = json.loads(fields["data"])
        assert int(fields["id"]) == data["eventIndex"]
        events.append((fields["event"], data))
    return events


def _rules_then_answer(app_id="APP-2026-1004"):
    return [model_reply(tool_calls=[tool_call("c1", "run_credit_rules",
                                              f'{{"applicationId": "{app_id}"}}')]),
            model_reply(content="结论：通过。")]


def test_request_id_echoed_and_recorded(client, fake_llm):
    fake_llm["replies"] = [model_reply(content="您好。")]
    resp = client.post("/api/agent/runs", json={"question": "你好"},
                       headers={**HEADERS, "X-Request-Id": "trace-abc_123"})
    assert resp.headers["X-Request-Id"] == "trace-abc_123"
    run_id = resp.json()["runId"]
    detail = client.get(f"/api/agent/runs/{run_id}", headers=HEADERS).json()
    assert detail["contextSnapshot"]["requestId"] == "trace-abc_123"
    audit = client.get(f"/api/agent/runs/{run_id}/audit", headers=HEADERS).json()["events"]
    assert audit[0]["payload"]["requestId"] == "trace-abc_123"


def test_unsafe_request_id_replaced(client):
    resp = client.get("/api/health/live", headers={"X-Request-Id": "bad id\r\ninjected"})
    assert resp.headers["X-Request-Id"].startswith("req_")


def test_sync_run_events_and_timings(client, fake_llm):
    fake_llm["replies"] = _rules_then_answer()
    run = client.post("/api/agent/runs", json={"question": "评估 APP-2026-1004"},
                      headers=HEADERS).json()
    events = _sse(client.get(f"/api/agent/runs/{run['runId']}/events", headers=HEADERS).text)
    # verify_finished：尽调场景发布前事实校验（ADR-0008，spec dd-multi-agent 需求 4）
    assert [e[0] for e in events] == [
        "run_started", "compliance_checked", "llm_call_finished", "tool_started",
        "tool_finished", "llm_call_finished", "verify_finished", "compliance_checked",
        "run_finished"]
    assert [e[1]["eventIndex"] for e in events] == list(range(1, 10))
    assert events[4][1]["evidenceIds"] == run["evidenceIds"]

    timings = client.get(f"/api/agent/runs/{run['runId']}", headers=HEADERS).json()["timings"]
    nodes = [(t["node"], t.get("stage") or t.get("toolName") or t.get("round")) for t in timings]
    assert nodes == [("compliance", "input"), ("llm", 1), ("tool", "run_credit_rules"),
                     ("llm", 2), ("compliance", "output"), ("run", None)]
    assert all(isinstance(t["durationMs"], int) for t in timings)


def test_events_resume_from_last_event_id(client, fake_llm):
    fake_llm["replies"] = _rules_then_answer()
    run_id = client.post("/api/agent/runs", json={"question": "评估 APP-2026-1004"},
                         headers=HEADERS).json()["runId"]
    url = f"/api/agent/runs/{run_id}/events"
    resumed = _sse(client.get(url, headers={**HEADERS, "Last-Event-ID": "5"}).text)
    assert [e[1]["eventIndex"] for e in resumed] == [6, 7, 8, 9]
    assert [e[1]["eventIndex"] for e in _sse(client.get(url + "?after=7", headers=HEADERS).text)] == [8, 9]


def test_async_run_streams_live_then_persists(client, fake_llm):
    gate = threading.Event()

    def slow_first():
        gate.wait(2)
        return _rules_then_answer()[0]

    fake_llm["replies"] = [slow_first, model_reply(content="结论：通过。")]
    resp = client.post("/api/agent/runs", headers=HEADERS,
                       json={"question": "评估 APP-2026-1004", "mode": "async"})
    assert resp.status_code == 202
    started = resp.json()
    assert started["status"] == "running" and started["runId"].startswith("run_")

    # 执行中：详情返回 running，别人看不到
    detail = client.get(f"/api/agent/runs/{started['runId']}", headers=HEADERS).json()
    assert detail["status"] == "running"
    assert client.get(f"/api/agent/runs/{started['runId']}/events",
                      headers={"X-Actor-Id": "someone_else"}).status_code == 403

    gate.set()
    live = _sse(client.get(f"/api/agent/runs/{started['runId']}/events", headers=HEADERS).text)
    assert live[0][0] == "run_started" and live[-1][0] == "run_finished"
    assert live[-1][1]["status"] == "succeeded"

    final = client.get(f"/api/agent/runs/{started['runId']}", headers=HEADERS).json()
    assert final["status"] == "succeeded" and final["conversationId"] == started["conversationId"]
    assert [t["toolName"] for t in final["toolTraces"]] == ["run_credit_rules"]
    # 持久化的事件与实时推送一致
    from app.db import SessionLocal
    from app.models import RunEvent
    with SessionLocal() as db:
        stored = [(r.event_type, r.payload) for r in db.query(RunEvent)
                  .filter(RunEvent.run_id == started["runId"]).order_by(RunEvent.event_index)]
    assert stored == live


def test_async_rejects_foreign_conversation_synchronously(client, fake_llm):
    resp = client.post("/api/agent/runs", headers=HEADERS,
                       json={"question": "hi", "mode": "async", "conversationId": "nope"})
    assert resp.status_code == 404 and resp.json()["errorCode"] == "conversation_not_found"


def test_run_log_has_no_question_text(client, fake_llm):
    records: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Collect()
    logger = logging.getLogger("ocft")
    logger.addHandler(handler)
    try:
        fake_llm["replies"] = [model_reply(tool_calls=[tool_call(
            "ev", "get_loan_application", '{"applicationId": "LA001"}')]), model_reply(content="好的。")]
        client.post("/api/agent/runs", json={"question": "手机 13800138000 查进度"},
                    headers=HEADERS)
    finally:
        logger.removeHandler(handler)
    lines = [JsonFormatter().format(r) for r in records]
    run_lines = [json.loads(ln) for ln in lines if '"run_finished"' in ln]
    assert run_lines and run_lines[0]["status"] == "succeeded" and "durationMs" in run_lines[0]
    assert all("13800138000" not in ln and "查进度" not in ln for ln in lines)
    assert any(json.loads(ln).get("path") == "/api/agent/runs" for ln in lines)


def test_bus_keepalive_and_finish():
    bus = EventBus()
    bus.open("r1", "u", {})
    got: list = []

    def consume():
        for item in bus.iter_events("r1", 0, keepalive_seconds=0.05, max_wait_seconds=2):
            got.append(item)

    worker = threading.Thread(target=consume)
    worker.start()
    time.sleep(0.15)
    bus.publish("r1", ("run_finished", {"eventIndex": 1, "runId": "r1"}))
    bus.close("r1")
    worker.join(2)
    assert None in got and got[-1][0] == "run_finished"


def test_run_evidence_returns_snapshot_for_owner_only(client, fake_llm):
    fake_llm["replies"] = _rules_then_answer()
    run = client.post("/api/agent/runs", json={"question": "评估 APP-2026-1004"},
                      headers=HEADERS).json()
    url = f"/api/agent/runs/{run['runId']}/evidence"
    evidence = client.get(url, headers=HEADERS).json()["evidence"]
    assert [e["evidenceId"] for e in evidence] == run["evidenceIds"]
    item = evidence[0]
    assert item["sourceType"] == "calculation"
    assert item["sourceRef"]["keys"] == {"applicationId": "APP-2026-1004"}
    assert item["snapshot"]["applicationId"] == "APP-2026-1004"
    assert len(item["contentHash"]) == 64 and item["createdAt"].endswith("Z")
    assert client.get(url, headers={"X-Actor-Id": "someone_else"}).status_code == 403


def test_stats_counts_real_runs(client, fake_llm):
    before = client.get("/api/agent/stats", headers=HEADERS).json()
    fake_llm["replies"] = _rules_then_answer()
    client.post("/api/agent/runs", json={"question": "评估 APP-2026-1004"}, headers=HEADERS)
    client.post("/api/agent/runs", json={"question": "怎么洗钱不被发现"}, headers=HEADERS)
    after = client.get("/api/agent/stats", headers=HEADERS).json()
    assert after["totalRuns"] == before["totalRuns"] + 2
    assert after["statusCounts"]["succeeded"] == before["statusCounts"].get("succeeded", 0) + 1
    assert after["blockedByCategory"]["crime"] == before["blockedByCategory"].get("crime", 0) + 1
    assert after["conclusionsWithEvidence"] == before["conclusionsWithEvidence"] + 1
    assert after["toolUsage"]["run_credit_rules"] >= 1
    assert "question" not in json.dumps(after)


def test_async_run_passes_attachments_and_validates_synchronously(client, fake_llm):
    too_many = [{"type": "image_url", "imageUrl": "data:image/png;base64,AAAA"}] * 5
    resp = client.post("/api/agent/runs", headers=HEADERS,
                       json={"question": "看图", "mode": "async", "attachments": too_many})
    assert resp.status_code == 422 and resp.json()["errorCode"] == "invalid_attachment"

    resp = client.post("/api/agent/runs", headers=HEADERS, json={
        "question": "看图", "mode": "async",
        "attachments": [{"type": "image_url", "imageUrl": "data:image/png;base64,AAAA"}]})
    assert resp.status_code == 422
    assert resp.json()["errorCode"] == "invalid_attachment"
    assert fake_llm["calls"] == []
