"""Run budget enforcement: token cap, truncation and deadline regressions."""
import pytest

from app.agent import engine, llm_audit
from app.agent.scenarios import Scenario
from app.config import settings
from conftest import model_reply, tool_call


def _run():
    return engine.run(
        None, scenario=Scenario("synthetic", "Explain tool facts.", []),
        question="Describe the available facts.", history=[],
        run_ctx={"run_id": "synthetic-run", "data_version": 1},
        persist_evidence=lambda record: "synthetic-evidence")


@pytest.mark.parametrize("has_tools", [False, True])
def test_length_truncation_is_failed_before_answer_or_tool_execution(fake_llm, has_tools):
    calls = [tool_call("incomplete", "request_clarification", '{"question":"partial"}')]
    fake_llm["replies"] = [
        {**model_reply(content="Incomplete output", tool_calls=calls if has_tools else []),
         "finish_reason": "length"},
    ]
    result = _run()
    assert result.status == "failed"
    assert result.error_code == "llm_output_incomplete"
    assert result.answer is None and result.traces == []
    assert result.usage["totalTokens"] == 10
    assert result.llm_calls[0]["response_preview"]["finishReason"] == "length"


@pytest.mark.parametrize("tokens", [9, 10, 11, 37])
def test_final_answer_cannot_bypass_token_cap(fake_llm, monkeypatch, tokens):
    monkeypatch.setattr(settings, "run_max_total_tokens", 10)
    fake_llm["replies"] = [model_reply(content="Scope explanation.", tokens=tokens)]
    result = _run()
    assert result.usage["totalTokens"] == tokens
    assert result.status == ("failed" if tokens > 10 else "succeeded")
    assert result.error_code == ("token_limit_exceeded" if tokens > 10 else None)
    if tokens > 10:
        assert result.answer is None
        assert result.llm_calls[0]["error_code"] == "token_limit_exceeded"


def test_final_answer_after_deadline_is_not_success(fake_llm, monkeypatch):
    from app.agent import graph

    clock = {"now": 0.0}
    monkeypatch.setattr(graph.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(settings, "run_timeout_seconds", 5)

    def late_response():
        clock["now"] = 6.0
        return model_reply(content="Late answer.")

    fake_llm["replies"] = [late_response]
    result = _run()
    assert result.status == "failed" and result.error_code == "run_timeout"
    assert result.answer is None and len(fake_llm["calls"]) == 1


def test_finish_reason_is_present_in_audit_preview():
    result = llm_audit.response_preview(
        {**model_reply(content="Partial."), "finish_reason": "length"},
        lambda text: (text, {}))
    assert result["finishReason"] == "length"


def test_cumulative_budget_failure_preserves_existing_evidence(client, fake_llm, monkeypatch):
    # 尽调场景有场景级 token 上限（agents.yaml controller.max_total_tokens），优先于全局配置
    import dataclasses

    from app.agent.scenarios import SCENARIOS
    monkeypatch.setitem(SCENARIOS, "enterprise_dd",
                        dataclasses.replace(SCENARIOS["enterprise_dd"], max_total_tokens=15))
    fake_llm["replies"] = [
        model_reply(tool_calls=[tool_call(
            "lookup", "get_loan_application", '{"applicationId":"LA001"}')], tokens=8),
        model_reply(content="A complete explanation.", tokens=8),
    ]
    run = client.post("/api/agent/runs", headers={"X-Actor-Id": "tester"},
                      json={"question": "查看贷款申请"}).json()
    assert run["status"] == "failed" and run["errorCode"] == "token_limit_exceeded"
    assert run["answer"] is None and run["answerVersion"] is None
    assert run["usage"]["totalTokens"] == 16 and run["evidenceIds"]


def test_truncation_with_evidence_is_not_publishable(client, fake_llm):
    fake_llm["replies"] = [
        model_reply(tool_calls=[tool_call(
            "lookup", "get_loan_application", '{"applicationId":"LA001"}')]),
        {**model_reply(content="风险评级"), "finish_reason": "length"},
    ]
    run = client.post("/api/agent/runs", headers={"X-Actor-Id": "tester"},
                      json={"question": "查看贷款申请"}).json()
    assert run["status"] == "failed" and run["errorCode"] == "llm_output_incomplete"
    assert run["answer"] is None and run["evidenceIds"]
