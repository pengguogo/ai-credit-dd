"""LangGraph 薄封装 — 只调度 model / tools 两个节点。

@why 图只决定下一跳。模型调用、工具校验、轮数 / 时限 / token 上限、
     终态判定仍走 engine 里的原函数，不使用框架自带的 ChatModel 或 ToolNode。
     不启用 checkpointer：证据与审计由 run_service 在同一事务落库。
"""
import time
from typing import Callable, Literal

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session
from typing_extensions import TypedDict

from .. import llm
from ..config import settings
from ..domain.errors import LLMError
from ..domain.types import EvidenceRecord
from . import llm_audit
from .scenarios import Scenario

Route = Literal["model", "tools", "end"]

# 不限轮数时 LangGraph 的 recursion_limit 兜底（图步数，约等于 2 × 轮数），只防图自身死循环
_UNBOUNDED_RECURSION_LIMIT = 10_000


class LoopState(TypedDict):
    messages: list
    route: Route


def invoke_bounded_loop(*, db: Session, scenario: Scenario, outcome, run_ctx: dict,
                        persist_evidence: Callable[[EvidenceRecord], str],
                        emit: Callable[[str, dict], None], tools_decl: list,
                        messages: list, started: float) -> None:
    """跑完一张图。终态写在 outcome 上；图的返回值不使用。"""
    # 延迟导入：graph 在 engine.run 内调用，此时 engine 已加载完成
    from . import engine

    def model_node(state: LoopState) -> dict:
        msgs = state["messages"]
        next_round = outcome.rounds + 1
        max_rounds = settings.run_max_tool_rounds
        if max_rounds is not None and next_round > max_rounds:
            engine._failed(outcome, "round_limit_exceeded",
                           f"工具循环超出 {max_rounds} 轮未产出结论")
            return {"messages": msgs, "route": "end"}
        outcome.rounds = next_round
        # @why 配了总时限时，按剩余时间约束每次模型调用，而不是只在轮次之间检查；
        #      未配置（None，默认）时不限总时长，单次调用仍受 llm_timeout_seconds 约束
        call_timeout = settings.llm_timeout_seconds
        if settings.run_timeout_seconds is not None:
            remaining = settings.run_timeout_seconds - (time.monotonic() - started)
            if remaining < settings.run_min_llm_budget_seconds:
                engine._timed_out(outcome)
                return {"messages": msgs, "route": "end"}
            call_timeout = min(call_timeout, remaining)
        limit = engine.token_limit(outcome)
        if outcome.usage["totalTokens"] >= limit:
            engine._failed(outcome, "token_limit_exceeded", f"run 累计 token 超出上限 {limit}")
            return {"messages": msgs, "route": "end"}
        # 每轮重送前重新处理完整消息：包括历史、模型返回的工具参数及嵌套 JSON。
        # 工具执行仍使用本地参数；仅发送给模型的副本脱敏，审计 hash 与外送体保持一致。
        masker = run_ctx.get("masker")
        if masker is not None:
            msgs = masker.mask_obj(msgs)

        def redact_values(value):
            if isinstance(value, str):
                return outcome._redact(value)[0]
            if isinstance(value, dict):
                return {key: redact_values(item) for key, item in value.items()}
            if isinstance(value, list):
                return [redact_values(item) for item in value]
            return value

        msgs = redact_values(msgs)
        # 审计：请求体 hash 必须在调用前算（调用后 msgs 会被追加）
        sha256 = llm_audit.request_sha256(msgs, tools_decl)
        audit_started_at = llm_audit.utcnow()
        call_started = time.monotonic()

        def record(resp: dict | None, error_code: str | None) -> None:
            outcome.llm_calls.append(llm_audit.build_record(
                round_no=outcome.rounds, purpose=llm_audit.PURPOSE_TOOL_LOOP,
                model=settings.llm_model, messages=msgs, tools=tools_decl, sha256=sha256,
                started_at=audit_started_at, duration_ms=engine._elapsed_ms(call_started),
                resp=resp, error_code=error_code, redact=outcome._redact))

        try:
            # thinking 为 None（多数场景）时不下发推理参数，请求与原来一致
            resp = (llm.complete_with_tools(msgs, tools_decl, timeout=call_timeout,
                                            thinking=scenario.thinking)
                    if scenario.thinking is not None
                    else llm.complete_with_tools(msgs, tools_decl, timeout=call_timeout))
        except LLMError as exc:
            record(None, exc.code)
            emit("llm_call_finished", {"round": outcome.rounds, "status": "error",
                                       "errorCode": exc.code,
                                       "durationMs": engine._elapsed_ms(call_started)})
            if exc.code == "timeout" and call_timeout < settings.llm_timeout_seconds:
                engine._timed_out(outcome)
            else:
                engine._failed(outcome, "llm_unavailable",
                               f"模型调用失败[{exc.code}]: {exc.message}")
            return {"messages": msgs, "route": "end"}
        engine._accumulate(outcome.usage, resp["usage"])
        is_valid = engine._validate_response(outcome, resp, started)
        error_code = None if is_valid else outcome.error_code
        record(resp, error_code)
        tool_calls = resp["tool_calls"] or []
        emit("llm_call_finished", {
            "round": outcome.rounds, "status": "ok" if is_valid else "error",
            "errorCode": error_code,
            "durationMs": engine._elapsed_ms(call_started),
            "totalTokens": resp["usage"].get("total_tokens", 0) or 0,
            "toolCalls": [tc["function"]["name"] for tc in tool_calls]})
        if not is_valid:
            return {"messages": msgs, "route": "end"}
        if not tool_calls:
            # @why 发布前事实校验（场景 answer_check）：答案里的数字、评级、规则编号必须能在
            #      本次工具结果里找到；不通过时带问题清单让模型重写，用尽仍不通过如实失败
            content, issues = engine.check_answer(outcome, scenario, resp["content"])
            if issues:
                details = [item["detail"] for item in issues[:12]]
                if outcome.answer_rewrites < scenario.max_answer_rewrites:
                    outcome.answer_rewrites += 1
                    emit("verify_finished", {"status": "retry", "attempt": outcome.answer_rewrites,
                                             "issues": details})
                    msgs.append({"role": "assistant", "content": resp["content"]})
                    msgs.append({"role": "user", "content": (
                        "上面的回答未通过事实校验，请只依据工具结果修正下列问题后重新回答：\n"
                        + "\n".join(f"- {d}" for d in details)
                        # @why 只给问题清单时模型常原样重写同一个自算数字，写明改法
                        + "\n改法：被指出的数字改为照抄工具结果里的原值（负值保留负号）；"
                          "工具结果里没有的数字（差值、合计、自行推算的比例）删掉数字改为定性描述，"
                          "不要换一种算法重新计算。")})
                    return {"messages": msgs, "route": "model"}
                emit("verify_finished", {"status": "failed",
                                         "attempt": outcome.answer_rewrites + 1, "issues": details})
                engine._finalize_context(outcome, scenario)
                engine._failed(outcome, "narrative_check_failed",
                               "回答未通过事实校验：" + "；".join(details[:5]))
                return {"messages": msgs, "route": "end"}
            if scenario.answer_check is not None and outcome._tool_data:
                emit("verify_finished", {"status": "ok", "attempt": outcome.answer_rewrites + 1,
                                         "issues": []})
            engine._finish_with_answer(outcome, scenario, content)
            return {"messages": msgs, "route": "end"}
        msgs.append({"role": "assistant", "content": resp["content"],
                     "tool_calls": tool_calls})
        return {"messages": msgs, "route": "tools"}

    def tools_node(state: LoopState) -> dict:
        msgs = state["messages"]
        tool_calls = msgs[-1].get("tool_calls") or []
        clarify_calls = [tc for tc in tool_calls
                         if tc["function"]["name"] == engine.CLARIFY_TOOL]
        for tc in tool_calls:
            if tc["function"]["name"] != engine.CLARIFY_TOOL:
                engine._execute_tool_call(db, outcome, msgs, run_ctx, persist_evidence, tc, emit)
        if clarify_calls and engine._try_clarify(outcome, msgs, clarify_calls[0], emit):
            engine._finalize_context(outcome, scenario)
            return {"messages": msgs, "route": "end"}
        # 终止工具（多 Agent 完整尽调）：报告已由报告 Agent 写好并通过事实校验，直接收尾
        if engine._terminal_outcome(outcome, scenario, tool_calls):
            return {"messages": msgs, "route": "end"}
        return {"messages": msgs, "route": "model"}

    graph = StateGraph(LoopState)
    graph.add_node("model", model_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "model")
    # model → model：发布前校验不通过时带问题清单重写一次
    graph.add_conditional_edges("model", lambda state: state["route"],
                                {"tools": "tools", "model": "model", "end": END})
    graph.add_conditional_edges("tools", lambda state: state["route"],
                                {"model": "model", "end": END})
    compiled = graph.compile()
    # 业务轮数（如配置）已在 model 节点强制；recursion_limit 只防止图自身死循环。
    # @why LangGraph 必须给一个整数：不限轮数时用一个足够大的框架兜底值，实际由 token 上限先截停
    max_rounds = settings.run_max_tool_rounds
    limit = (max_rounds * 2 + 4) if max_rounds is not None else _UNBOUNDED_RECURSION_LIMIT
    try:
        compiled.invoke({"messages": messages, "route": "model"},
                        {"recursion_limit": limit})
    except GraphRecursionError:
        engine._failed(outcome, "round_limit_exceeded",
                       f"工具循环超出 {max_rounds or limit // 2} 轮未产出结论")
