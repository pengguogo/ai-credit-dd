"""历史会话列表：按身份隔离，并带上会话所属场景；支持搜索与分页。"""
from conftest import HEADERS, model_reply


def _create(client, question, **extra):
    resp = client.post("/api/agent/runs", json={"question": question, **extra}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_list_conversations_keeps_scenario_and_owner(client, fake_llm):
    fake_llm["replies"] = [
        model_reply(content="请提供申请编号。"),
        model_reply(content="可以继续看财务指标。"),
    ]
    first = _create(client, "这笔贷款怎么样", scenarioId="enterprise_dd")
    second = _create(client, "再看一笔申请", scenarioId="enterprise_dd")

    listed = client.get("/api/agent/conversations", headers=HEADERS)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] >= 2
    assert body["hasMore"] is False or body["total"] > body["limit"]
    by_id = {row["conversationId"]: row for row in body["conversations"]}
    assert by_id[first["conversationId"]]["scenarioId"] == "enterprise_dd"
    assert by_id[first["conversationId"]]["title"] == "这笔贷款怎么样"
    assert by_id[first["conversationId"]]["turnCount"] == 1
    assert by_id[second["conversationId"]]["scenarioId"] == "enterprise_dd"

    only_dd = client.get("/api/agent/conversations?scenarioId=enterprise_dd", headers=HEADERS).json()
    ids = [row["conversationId"] for row in only_dd["conversations"]]
    assert first["conversationId"] in ids and second["conversationId"] in ids
    assert {row["scenarioId"] for row in only_dd["conversations"]} == {"enterprise_dd"}

    other = client.get("/api/agent/conversations", headers={"X-Actor-Id": "someone_else"})
    assert other.json()["conversations"] == []
    assert other.json()["total"] == 0

    unknown = client.get("/api/agent/conversations?scenarioId=not_a_scenario", headers=HEADERS)
    assert unknown.status_code == 404 and unknown.json()["errorCode"] == "unknown_scenario"

    mismatch = client.post("/api/agent/runs", headers=HEADERS, json={
        "question": "继续",
        "conversationId": first["conversationId"],
        "scenarioId": "credit_review",
    })
    assert mismatch.status_code == 404
    assert mismatch.json()["errorCode"] == "unknown_scenario"


def test_list_conversations_search_and_pagination(client, fake_llm):
    fake_llm["replies"] = [model_reply(content="请补充信息。")] * 5
    a = _create(client, "偿债能力尽调", scenarioId="enterprise_dd")
    b = _create(client, "香蕉贸易授信", scenarioId="enterprise_dd")
    _create(client, "普通问询", scenarioId="enterprise_dd")

    hit = client.get("/api/agent/conversations?q=偿债", headers=HEADERS).json()
    ids = [row["conversationId"] for row in hit["conversations"]]
    assert a["conversationId"] in ids
    assert b["conversationId"] not in ids
    assert hit["total"] >= 1

    page1 = client.get("/api/agent/conversations?limit=1&offset=0", headers=HEADERS).json()
    assert len(page1["conversations"]) == 1
    assert page1["limit"] == 1
    assert page1["offset"] == 0
    assert page1["total"] >= 3
    assert page1["hasMore"] is True

    page2 = client.get("/api/agent/conversations?limit=1&offset=1", headers=HEADERS).json()
    assert len(page2["conversations"]) == 1
    assert page2["conversations"][0]["conversationId"] != page1["conversations"][0]["conversationId"]
