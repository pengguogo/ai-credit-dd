"""引擎终态、单次调用时限、多轮上下文（待办 1-1 / 1-4 / 1-2）。"""
import time
import uuid

from app.agent import context
from app.agent.scenarios import SCENARIOS
from app.config import settings
from app.domain.errors import LLMError
from conftest import HEADERS, model_reply, tool_call


def _create(client, question, **extra):
    resp = client.post("/api/agent/runs", json={"question": question, **extra}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _detail(client, run_id):
    return client.get(f"/api/agent/runs/{run_id}", headers=HEADERS).json()


def _messages(client, conversation_id):
    return client.get(f"/api/agent/conversations/{conversation_id}/messages",
                      headers=HEADERS).json()["messages"]


def _rules(app_id, call_id="c1"):
    return model_reply(tool_calls=[tool_call(call_id, "run_credit_rules",
                                             f'{{"applicationId": "{app_id}"}}')])


# ---- 1-1 状态机 ----

def test_not_found_application_is_insufficient_evidence(client, fake_llm):
    fake_llm["replies"] = [_rules("APP-2099-0001"),
                           model_reply(content="未找到申请 APP-2099-0001，请核对编号。")]
    run = _create(client, "评估申请 APP-2099-0001 的审批结论")
    assert run["status"] == "insufficient_evidence"
    assert run["errorCode"] == "evidence_missing"
    assert run["answer"] is None and run["answerVersion"] is None
    assert "未找到" in run["errorMessage"]
    # 说明文本作为 assistant 消息进入历史，下一轮可接着补充
    assert _messages(client, run["conversationId"])[-1]["content"] == run["errorMessage"]
    confirm = client.post(f"/api/agent/runs/{run['runId']}/confirmations", headers=HEADERS,
                          json={"answerVersion": 1, "action": "confirm",
                                "idempotencyKey": uuid.uuid4().hex})
    assert confirm.status_code == 409 and confirm.json()["errorCode"] == "run_not_confirmable"


def _call(name, args, call_id):
    import json as _json
    return tool_call(call_id, name, _json.dumps(args, ensure_ascii=False))


def test_not_found_target_stays_insufficient_despite_unrelated_evidence(client, fake_llm):
    """目标申请不存在时，即使又列出其他企业拿到证据，仍判证据不足。"""
    fake_llm["replies"] = [
        model_reply(tool_calls=[_call("get_loan_application", {"applicationId": "LA999"}, "c1")]),
        model_reply(tool_calls=[_call("find_enterprise", {"name": "LA999"}, "c2")]),
        model_reply(tool_calls=[_call("find_enterprise", {"name": "有限公司"}, "c3")]),
        model_reply(content="未找到申请 LA999。"),
    ]
    run = _create(client, "评估贷款申请 LA999 的尽调结论")
    assert run["status"] == "insufficient_evidence" and run["errorCode"] == "evidence_missing"
    assert run["evidenceIds"]
    assert _detail(client, run["runId"])["contextSnapshot"]["missingInfo"] == ["未找到：LA999"]


def test_not_found_then_same_id_found_is_resolved(client, fake_llm):
    """同一取值后来成功取到证据（如模型纠正格式重查）就算已解决，不误判。"""
    fake_llm["replies"] = [
        model_reply(tool_calls=[_call("get_credit_application", {"applicationId": "APP-2026-1004 "}, "c1")]),
        _rules("APP-2026-1004", "c2"),
        model_reply(content="结论：通过。"),
    ]
    run = _create(client, "评估 APP-2026-1004")
    assert run["status"] == "succeeded"


def test_comparison_with_one_missing_entity_is_insufficient(client, fake_llm):
    """比较两笔、其中一笔不存在：无法完整回答，判证据不足并指明缺哪一笔。"""
    fake_llm["replies"] = [
        model_reply(tool_calls=[_call("run_credit_rules", {"applicationId": "APP-2026-1004"}, "c1"),
                                _call("run_credit_rules", {"applicationId": "APP-2099-0002"}, "c2")]),
        model_reply(content="APP-2026-1004 通过；APP-2099-0002 未找到。"),
    ]
    run = _create(client, "比较 APP-2026-1004 和 APP-2099-0002")
    assert run["status"] == "insufficient_evidence"
    assert _detail(client, run["runId"])["contextSnapshot"]["missingInfo"] == ["未找到：APP-2099-0002"]


def test_conclusion_without_any_evidence_is_insufficient(client, fake_llm):
    fake_llm["replies"] = [model_reply(content="风险评级为低风险。各项指标良好。")]
    run = _create(client, "LA001 的风险评级是什么")
    assert run["status"] == "insufficient_evidence"
    assert _detail(client, run["runId"])["contextSnapshot"]["missingInfo"]


def test_answer_without_any_evidence_is_not_published_even_without_keywords(client, fake_llm):
    """R01：无证据回答不靠关键词放行；能力外问题改给场景固定引导，模型原文同样不发布。"""
    fake_llm["replies"] = [model_reply(content="我负责信贷审批相关问题，请提供申请编号。")]
    run = _create(client, "今天天气怎么样？")
    assert run["status"] == "needs_clarification" and run["answer"] is None
    assert run["errorMessage"] == SCENARIOS["enterprise_dd"].guide_message


def test_approved_decision_succeeds_without_confirmation(client, fake_llm):
    fake_llm["replies"] = [_rules("APP-2026-1004"), model_reply(content="结论：通过。")]
    run = _create(client, "评估 APP-2026-1004")
    assert run["status"] == "succeeded" and run["answerVersion"] == 1
    assert _detail(client, run["runId"])["contextSnapshot"]["confirmationReasons"] == []


def test_request_clarification_ends_run(client, fake_llm):
    fake_llm["replies"] = [model_reply(tool_calls=[tool_call(
        "c1", "request_clarification",
        '{"question": "请问是哪一笔申请？请提供申请编号。", "missingInfo": ["申请编号"]}')])]
    run = _create(client, "帮我看看那笔贷款")
    assert run["status"] == "needs_clarification"
    assert run["errorCode"] == "clarification_required"
    assert run["errorMessage"] == "请问是哪一笔申请？请提供申请编号。"
    assert run["answer"] is None and len(fake_llm["calls"]) == 1
    detail = _detail(client, run["runId"])
    assert detail["contextSnapshot"]["missingInfo"] == ["申请编号"]
    assert [t["toolName"] for t in detail["toolTraces"]] == ["request_clarification"]
    assert _messages(client, run["conversationId"])[-1]["content"] == run["errorMessage"]


def test_invalid_clarification_args_returned_to_model(client, fake_llm):
    fake_llm["replies"] = [
        model_reply(tool_calls=[tool_call("c1", "request_clarification", '{"missingInfo": 1}')]),
        model_reply(content="请提供申请编号。")]
    run = _create(client, "帮我看看")
    # 无证据不发布模型原文（R01）；问题不含业务信号，给固定引导
    assert run["status"] == "needs_clarification"
    assert run["errorMessage"] == SCENARIOS["enterprise_dd"].guide_message
    tool_msg = fake_llm["calls"][1]["messages"][-1]
    assert tool_msg["role"] == "tool" and "invalid_args" in tool_msg["content"]


def test_clarification_text_goes_through_output_compliance(client, fake_llm):
    fake_llm["replies"] = [model_reply(tool_calls=[tool_call(
        "c1", "request_clarification", '{"question": "这笔贷款稳赚不赔，要办吗？"}')])]
    run = _create(client, "看看贷款")
    assert run["status"] == "blocked" and run["errorCode"] == "compliance_output_blocked"


# ---- 1-4 单次调用时限 ----

def test_call_timeout_bounded_by_remaining_run_time(client, fake_llm, monkeypatch):
    monkeypatch.setattr(settings, "run_timeout_seconds", 10.0)
    fake_llm["replies"] = [model_reply(content="好的。")]
    _create(client, "你好")
    timeout = fake_llm["calls"][0]["timeout"]
    assert timeout is not None and timeout <= 10.0


def test_slow_model_ends_with_run_timeout_within_limit(client, fake_llm, monkeypatch):
    monkeypatch.setattr(settings, "run_timeout_seconds", 1.5)
    monkeypatch.setattr(settings, "run_min_llm_budget_seconds", 1.0)

    def slow():
        time.sleep(0.7)
        return model_reply(tool_calls=[tool_call("c1", "get_credit_application",
                                                 '{"applicationId": "APP-2026-1004"}')])

    fake_llm["replies"] = [slow, model_reply(content="不应被调用")]
    started = time.monotonic()
    run = _create(client, "查 APP-2026-1004")
    assert run["status"] == "failed" and run["errorCode"] == "run_timeout"
    assert time.monotonic() - started < 1.5
    assert len(fake_llm["calls"]) == 1


def test_deadline_bound_llm_timeout_reported_as_run_timeout(client, fake_llm, monkeypatch):
    monkeypatch.setattr(settings, "run_timeout_seconds", 5.0)
    fake_llm["replies"] = [LLMError("timeout", "模型请求超时（5s）", is_retryable=True)]
    run = _create(client, "查 APP-2026-1004")
    assert run["status"] == "failed" and run["errorCode"] == "run_timeout"


# ---- 1-2 上下文管理 ----

def test_follow_up_turn_gets_tool_summary_and_entities(client, fake_llm):
    fake_llm["replies"] = [
        model_reply(tool_calls=[tool_call("c1", "search_credit_applications",
                                          '{"keyword": "赵美琳"}')]),
        model_reply(content="已找到赵美琳的申请。")]
    first = _create(client, "帮我看看赵美琳的申请")
    entities = _detail(client, first["runId"])["contextSnapshot"]["entities"]
    assert entities["customerName"] == ["赵美琳"]
    app_id = entities["applicationId"][0]

    fake_llm["replies"] = [_rules(app_id), model_reply(content="结论：通过。")]
    second = _create(client, "她能通过审批吗？", conversationId=first["conversationId"])
    sent = fake_llm["calls"][2]["messages"]
    system_notes = [m["content"] for m in sent if m["role"] == "system"][1:]
    assert any("会话已知实体" in n and app_id in n for n in system_notes)
    assert any("search_credit_applications" in n and first["runId"] in n for n in system_notes)

    snapshot = _detail(client, second["runId"])["contextSnapshot"]
    assert snapshot["toolSummaryRuns"] == [first["runId"]]
    assert snapshot["entities"]["applicationId"][0] == app_id
    assert snapshot["entities"]["customerName"] == ["赵美琳"]


def test_history_compressed_when_over_budget():
    rows = [context.HistoryMessage(message_id=i, role="user" if i % 2 else "assistant",
                                   content="很长的内容" * 40) for i in range(1, 11)]
    messages, meta = context.build_history(rows, entities={}, max_recent=6, token_budget=300)
    assert meta["compressedRange"]["fromMessageId"] == 1
    assert meta["compressedRange"]["toMessageId"] == 10 - meta["historyMessages"]
    assert messages[0]["role"] == "system" and "早期对话摘要（消息 #1–" in messages[0]["content"]
    assert meta["historyMessages"] >= 1


def test_history_within_budget_not_compressed():
    rows = [context.HistoryMessage(message_id=1, role="user", content="你好"),
            context.HistoryMessage(message_id=2, role="assistant", content="您好")]
    messages, meta = context.build_history(rows, entities={}, max_recent=12, token_budget=4000)
    assert meta["compressedRange"] is None
    assert [m["content"] for m in messages] == ["你好", "您好"]


def test_entities_extracted_newest_first():
    found = context.extract_entities(("applicationId",), [
        {"applicationId": "A"}, {"applications": [{"applicationId": "B"}]}, {"applicationId": "A"}])
    assert found == {"applicationId": ["A", "B"]}


def test_blocked_question_excluded_from_later_history(client, fake_llm):
    blocked = _create(client, "怎么洗钱不被发现")
    assert blocked["status"] == "blocked"
    fake_llm["replies"] = [model_reply(content="请提供申请编号。")]
    _create(client, "帮我看看贷款", conversationId=blocked["conversationId"])
    contents = [m["content"] for m in fake_llm["calls"][0]["messages"]]
    assert "怎么洗钱不被发现" not in contents
    # 会话记录仍完整保留（审计可查），user 消息关联到产生它的 run
    msgs = _messages(client, blocked["conversationId"])
    assert msgs[0]["content"] == "怎么洗钱不被发现" and msgs[0]["runId"] == blocked["runId"]


def test_sql_query_limited_to_scenario_tables(client, fake_llm):
    """尽调场景的 sql_query 只能查尽调事实表，描述里不列其他场景的表。"""
    fake_llm["replies"] = [
        model_reply(tool_calls=[_call("sql_query", {"sql": "SELECT * FROM fin_docs"}, "c1")]),
        model_reply(tool_calls=[_call("sql_query", {"sql": "SELECT COUNT(*) AS n FROM loan_application"}, "c2")]),
        model_reply(content="已统计贷款申请笔数。"),
    ]
    run = _create(client, "一共有多少笔贷款申请？")
    assert run["status"] == "succeeded"
    traces = _detail(client, run["runId"])["toolTraces"]
    assert [(t["toolName"], t["status"], t.get("errorCode")) for t in traces] == [
        ("sql_query", "error", "not_allowed"), ("sql_query", "ok", None)]
    decl = next(t for t in fake_llm["calls"][0]["tools"] if t["function"]["name"] == "sql_query")
    assert "loan_application" in decl["function"]["description"]
    assert "fin_docs" not in decl["function"]["description"]
    assert "credit_applications" not in decl["function"]["description"]


# ---- 工具结果送模型前脱敏（通用纪律第 2 条、自查第 9 条） ----

RAW_MOBILE = "13812345678"
RAW_ID_CARD = "11010519491231002X"   # 校验位合法的虚构号码


def test_tool_result_is_redacted_before_sent_to_model(client, fake_llm, monkeypatch):
    from app.db import SessionLocal
    from app.domain.types import EvidenceRecord, ToolResult
    from app.models import AuditLog, Evidence
    from app.tools import registry

    row = {"applicationId": "APP-2026-1004", "mobile": RAW_MOBILE, "idCard": RAW_ID_CARD}

    def fake_execute(_db, run_ctx, name, _raw_args):
        record = EvidenceRecord(source_type="db_query", source_ref={"table": "t", "keys": {}},
                                snapshot=row, data_version=run_ctx["data_version"])
        return ToolResult.success({"decision": "approved", "applicant": row}), [record], \
            {"applicationId": "APP-2026-1004"}

    monkeypatch.setattr(registry, "execute_tool", fake_execute)
    fake_llm["replies"] = [_rules("APP-2026-1004"), model_reply(content="结论：通过。")]
    run = _create(client, "评估申请 APP-2026-1004")

    tool_messages = [m for m in fake_llm["calls"][1]["messages"] if m["role"] == "tool"]
    sent = tool_messages[0]["content"]
    assert RAW_MOBILE not in sent and RAW_ID_CARD not in sent
    assert "138****5678" in sent and "110105********002X" in sent
    with SessionLocal() as db:
        audits = db.query(AuditLog).filter(AuditLog.run_id == run["runId"],
                                           AuditLog.event_type == "pii_redacted").all()
        assert {"stage": "tool_result", "counts": {"idCard": 1, "mobile": 1}} in [a.payload for a in audits]
        # 证据只落本地库，保留原始快照用于复核
        snapshot = db.query(Evidence).filter(Evidence.run_id == run["runId"]).one().snapshot
        assert snapshot["mobile"] == RAW_MOBILE
    detail = _detail(client, run["runId"])
    assert RAW_MOBILE not in str(detail["contextSnapshot"])   # 工具摘要与实体槽位同样掩码

    # 待办 0-7：证据 API 输出掩码，库内原值不变，哈希仍对应原始快照
    evidence = client.get(f"/api/agent/runs/{run['runId']}/evidence", headers=HEADERS).json()["evidence"]
    shown = evidence[0]["snapshot"]
    assert shown["mobile"] == "138****5678" and shown["idCard"] == "110105********002X"
    assert shown["applicationId"] == "APP-2026-1004"
    with SessionLocal() as db:
        stored = db.query(Evidence).filter(Evidence.run_id == run["runId"]).one()
        assert stored.snapshot["mobile"] == RAW_MOBILE
        assert evidence[0]["contentHash"] == stored.content_hash


# ---- 待办 0-5：外部大模型调用审计 ----

def test_llm_calls_are_audited_with_hash_and_masked_preview(client, fake_llm, monkeypatch):
    import json as _json

    from app.agent import llm_audit
    from app.domain.types import EvidenceRecord, ToolResult
    from app.tools import registry

    def fake_execute(_db, run_ctx, _name, _raw_args):
        record = EvidenceRecord(source_type="db_query", source_ref={"table": "t", "keys": {}},
                                snapshot={"mobile": RAW_MOBILE}, data_version=run_ctx["data_version"])
        return ToolResult.success({"decision": "approved", "mobile": RAW_MOBILE}), [record], {}

    monkeypatch.setattr(registry, "execute_tool", fake_execute)
    fake_llm["replies"] = [_rules("APP-2026-1004"), model_reply(content="结论：通过。", tokens=7)]
    run = _create(client, f"评估申请 APP-2026-1004，联系电话 {RAW_MOBILE}")

    resp = client.get(f"/api/agent/runs/{run['runId']}/llm-calls", headers=HEADERS)
    assert resp.status_code == 200
    calls = resp.json()["calls"]
    assert [c["round"] for c in calls] == [1, 2] and {c["purpose"] for c in calls} == {"tool_loop"}
    assert all(c["status"] == "ok" and c["model"] == "deepseek-v4.1-flash" for c in calls)
    # 主控只声明定位 / 调度工具：六个专业环节由 run_dd_agents 调度的角色 Agent 完成（ADR-0008）
    assert calls[0]["startedAt"].endswith("Z") and "run_dd_agents" in calls[0]["toolNames"]
    assert calls[0]["responsePreview"]["toolCalls"][0]["name"] == "run_credit_rules"
    assert calls[1]["responsePreview"]["content"] == "结论：通过。" and calls[1]["usage"]["total_tokens"] == 7
    # 第 2 次调用带上了工具结果，消息条数更多
    assert calls[1]["messageCount"] > calls[0]["messageCount"]
    # hash 对应的正是模型那一次真实收到的请求
    sent = fake_llm["calls"][1]
    assert calls[1]["requestSha256"] == llm_audit.request_sha256(sent["messages"], sent["tools"])
    # 审计内容不含原始号码（用户输入与工具结果都已脱敏）
    assert RAW_MOBILE not in _json.dumps(calls, ensure_ascii=False)
    assert any(p["role"] == "tool" for p in calls[1]["requestPreview"])

    other = client.get(f"/api/agent/runs/{run['runId']}/llm-calls", headers={"X-Actor-Id": "someone-else"})
    assert other.status_code == 403


def test_failed_llm_call_is_audited(client, fake_llm):
    fake_llm["replies"] = [LLMError("unavailable", "上游 503")]
    run = _create(client, "评估申请 APP-2026-1004")
    assert run["status"] == "failed"
    calls = client.get(f"/api/agent/runs/{run['runId']}/llm-calls", headers=HEADERS).json()["calls"]
    assert len(calls) == 1 and calls[0]["status"] == "error" and calls[0]["errorCode"] == "unavailable"
    assert calls[0]["responsePreview"] == {} and calls[0]["requestSha256"]


def test_llm_audit_preview_truncates_and_hides_images():
    from app.agent import llm_audit
    rows = llm_audit.request_preview(
        [{"role": "user", "content": [{"type": "text", "text": "看图"},
                                      {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]},
         {"role": "system", "content": "长" * 500}],
        lambda t: (t, {}))
    assert rows[0]["preview"] == "看图 [图片]" and "base64" not in str(rows)
    assert rows[1]["chars"] == 500 and len(rows[1]["preview"]) == llm_audit.PREVIEW_CHARS + 1
