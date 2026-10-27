"""Agent 有界工具循环引擎（设计 §5 / §8）。

调度由 graph.py 的 LangGraph 完成；本模块保留硬限制与终态判定。

@why 硬限制（轮数 / 时限 / token）在引擎集中强制：任何场景、任何调用方
     （HTTP / SSE / 批量评测）都不可绕过。引擎不写业务表：证据持久化经
     persist_evidence 回调注入，由服务层在同一事务内落库。
     终态判定（澄清 / 证据不足 / 需确认 / 成功）只依据本次 run 的真实工具结果。
"""
import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.orm import Session

from ..config import settings
from ..domain.types import (FAILED, INSUFFICIENT_EVIDENCE, NEEDS_CLARIFICATION,
                            NEEDS_CONFIRMATION, RUNNING, SUCCEEDED, EvidenceRecord,
                            ToolResult)
from ..tools import registry
from . import context
from .scenarios import Scenario

# 引擎内置工具：模型主动请求用户澄清，调用即结束本次 run
CLARIFY_TOOL = "request_clarification"
NO_EVIDENCE_MESSAGE = "本次未取得业务数据证据，无法形成结论，请提供或核对企业、申请编号后重试。"
_CLARIFY_DECL = {
    "type": "function",
    "function": {
        "name": CLARIFY_TOOL,
        "description": "信息不足以继续时向用户提问（如缺少申请编号、检索到多个候选、指代不明）。"
                       "调用后本次执行结束，等待用户补充。",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "向用户提出的澄清问题"},
                "missingInfo": {"type": "array", "items": {"type": "string"},
                                "description": "缺失的信息项，如 申请编号"},
            },
            "required": ["question"],
        },
    },
}


@dataclass
class ToolCallTrace:
    sequence: int
    tool_name: str
    args: dict
    status: str              # ok | error
    duration_ms: int
    error_code: str | None
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class RunOutcome:
    status: str
    # succeeded / needs_confirmation：结论；needs_clarification / insufficient_evidence：
    # 给用户的说明文本（服务层合规检查后移入 error_message）
    answer: str | None = None
    rounds: int = 0
    # key 为 camelCase：直接作为 AgentRun.usage JSON 持久化并直出契约
    usage: dict = field(default_factory=lambda: {
        "promptTokens": 0, "completionTokens": 0, "totalTokens": 0})
    traces: list[ToolCallTrace] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    # 上下文管理：本次工具结果摘要与提取的实体（服务层脱敏后写入 context_snapshot）
    tool_summaries: list[dict] = field(default_factory=list)
    entities: dict[str, list[str]] = field(default_factory=dict)
    confirmation_reasons: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    # 工具结果送模型前掩码的 PII 计数（类型 → 数量），服务层写 pii_redacted 审计
    tool_pii_counts: dict[str, int] = field(default_factory=dict)
    # 每次外部大模型调用的审计记录（llm_audit.build_record），服务层写 llm_calls 表
    llm_calls: list[dict] = field(default_factory=list)
    # 成功工具调用的原始数据，仅在内存中用于终态判定
    _tool_data: list[tuple[str, dict, object]] = field(default_factory=list, repr=False)
    # 工具结果送模型前的脱敏函数（engine.run 注入）
    _redact: Callable[[str], tuple[str, dict[str, int]]] = field(
        default=lambda text: (text, {}), repr=False)
    # 只还原名称；信用代码和证件号不在输出侧还原。
    _restore: Callable[[str], str] = field(default=lambda text: text, repr=False)
    # 本次 run 的累计 token 上限（场景覆盖或全局配置，engine.run 写入）
    token_limit: int | None = None
    # 本次 run 各角色模型调用所用的运行时 Skill（name@version，按调用顺序；dd_graph 经 run_ctx 写入）
    skills_applied: list[str] = field(default_factory=list)
    # 发布前校验已触发的重写次数（场景 answer_check）
    answer_rewrites: int = 0
    # 本次用户问题（已代号化），只用于能力外引导判定，不持久化
    _question: str = field(default="", repr=False)


def token_limit(outcome: RunOutcome) -> int:
    return outcome.token_limit if outcome.token_limit is not None else settings.run_max_total_tokens


Emit = Callable[[str, dict], None]
# 文本 → (掩码后文本, {PII 类型: 数量})
Redact = Callable[[str], tuple[str, dict[str, int]]]


def _noop_emit(_event_type: str, _data: dict) -> None:
    return None


def _no_redact(text: str) -> tuple[str, dict[str, int]]:
    return text, {}


def run(db: Session, *, scenario: Scenario, question: str, history: list[dict],
        run_ctx: dict,
        persist_evidence: Callable[[EvidenceRecord], str],
        emit: Emit = _noop_emit,
        attachments: list[str] | None = None,
        redact: Redact = _no_redact) -> RunOutcome:
    """执行一次有界 run，返回终态与轨迹；持久化交由调用方。

    emit：阶段事件回调（llm_call_finished / tool_started / tool_finished），
    由服务层推送 SSE 并持久化；引擎不关心事件去向。
    redact：工具结果作为 tool 消息送模型前的脱敏函数，由服务层注入（分层：agent 不依赖 compliance）。
    """
    if attachments:
        return _failed(RunOutcome(status=RUNNING), "invalid_attachment",
                       "图片内容暂无法安全脱敏，请改用脱敏后的文本资料")
    tools_decl = registry.get_openai_tools(scenario.allowed_tools) + [_CLARIFY_DECL]
    if scenario.sql_tables:
        # @why sql_query 按场景收窄：执行时只能查本场景的表，描述也只列这些表（待办 1-10）
        from ..tools.sql_query import describe_for
        run_ctx = {**run_ctx, "sql_tables": tuple(scenario.sql_tables)}
        for decl in tools_decl:
            if decl["function"]["name"] == "sql_query":
                decl["function"]["description"] = describe_for(scenario.sql_tables)
    outcome = RunOutcome(status=RUNNING)
    outcome.token_limit = scenario.max_total_tokens or settings.run_max_total_tokens
    masker = scenario.build_masker(db) if scenario.build_masker else None
    if masker is not None:
        outcome._restore = masker.restore_names
        # @why 外送模型的全部内容先代号化（企业名、人名、信用代码等，ADR-0008 决策 5），
        #      再做号码类 PII 掩码；历史、问题、工具结果、审计预览都走这一个函数
        pii_redact = redact

        def redact(text: str) -> tuple[str, dict[str, int]]:  # noqa: F811
            return pii_redact(masker.mask(text))

        question = masker.mask(question)
        history = [{**m, "content": masker.mask(m["content"])}
                   if isinstance(m.get("content"), str) else m for m in history]
    outcome._redact = redact
    outcome._question = question
    # 工具可读的 run 级上下文：事件、脱敏、调用审计与用量（多 Agent 调度工具用来记录角色的模型调用）
    run_ctx = {**run_ctx, "emit": emit, "redact": redact, "masker": masker,
               "llm_calls": outcome.llm_calls, "usage": outcome.usage,
               "token_limit": outcome.token_limit, "skills_applied": outcome.skills_applied}
    messages: list[dict] = ([{"role": "system", "content": scenario.system_prompt}]
                            + list(history)
                            + [{"role": "user", "content": question}])
    if masker is not None:
        messages = masker.mask_obj(messages)
    started = time.monotonic()
    # 调度交给 LangGraph；硬限制与终态判定仍在本模块
    from .graph import invoke_bounded_loop
    invoke_bounded_loop(
        db=db, scenario=scenario, outcome=outcome, run_ctx=run_ctx,
        persist_evidence=persist_evidence, emit=emit, tools_decl=tools_decl,
        messages=messages, started=started)
    return outcome


def _is_out_of_scope(outcome: RunOutcome, scenario: Scenario) -> bool:
    """能力外问题：场景配了引导文本，本次没调用任何数据工具，且用户问题不含业务信号。"""
    if not (scenario.require_evidence and scenario.guide_message
            and scenario.business_intent_pattern):
        return False
    if any(t.tool_name != CLARIFY_TOOL for t in outcome.traces):
        return False
    return not re.search(scenario.business_intent_pattern, outcome._question)


def _finish_with_answer(outcome: RunOutcome, scenario: Scenario,
                        content: str | None) -> RunOutcome:
    text = outcome._restore((content or "").strip())
    if not text:
        return _failed(outcome, "llm_unavailable", "模型返回空内容")
    outcome.answer = text
    _finalize_context(outcome, scenario)
    data_calls = [t for t in outcome.traces if t.tool_name != CLARIFY_TOOL]
    if data_calls and not outcome.evidence_ids:
        # 调用过工具却没拿到任何证据（如查无此申请）：不能算成功结论
        return _insufficient(outcome, "调用的工具均未取得数据证据")
    missing = _unresolved_not_found(outcome)
    if missing:
        # @why 用户要找的对象不存在时，即使模型又做了别的检索（拿到了无关证据），
        #      也不能把"查无此项"算作成功结论；只看工具返回，不看模型措辞（待办 1-9）
        return _insufficient(outcome, "未找到：" + "、".join(missing))
    if not outcome.evidence_ids and scenario.require_evidence and _is_out_of_scope(outcome, scenario):
        # @why 问候 / 闲聊 / 能力外问题：给固定引导而不是“证据不足”。走到这里时本次没有数据工具调用，
        #      模型原文同样不发布，只给场景配置的固定文本，不含任何业务断言
        outcome.answer = scenario.guide_message
        outcome.status = NEEDS_CLARIFICATION
        outcome.error_code = "clarification_required"
        return outcome
    if not outcome.evidence_ids and scenario.require_evidence:
        # @why R01：业务断言的措辞无法穷举（“无担保”“可以放款”…），场景要求证据时
        #      本次没有取得任何证据就一律不发布；原文不进 errorMessage / 历史，只给固定说明
        outcome.answer = NO_EVIDENCE_MESSAGE
        return _insufficient(outcome, "本次执行没有取得任何工具证据")
    if (not outcome.evidence_ids and scenario.conclusion_pattern
            and re.search(scenario.conclusion_pattern, text)):
        return _insufficient(outcome, "答案含结论但本次执行没有任何工具证据")
    reasons = _confirmation_reasons(outcome, scenario)
    if reasons:
        outcome.status = NEEDS_CONFIRMATION
        outcome.confirmation_reasons = reasons
        return outcome
    outcome.status = SUCCEEDED
    return outcome


def _unresolved_not_found(outcome: RunOutcome) -> list[str]:
    """按标识查找返回 not_found、且本次 run 中没有任何工具用同一取值成功取到证据的标识。

    标识取自工具参数里的字符串值（如 applicationId / txnId / claimId / docId）。
    @why "成功"必须带证据：用同一编号做关键词检索返回 0 条也是 ok，但什么都没找到，
         不能算已解决；用同一取值重查并拿到证据（如模型纠正格式后重查）才算。
    """
    missing: list[str] = []
    resolved: set[str] = set()
    for trace in outcome.traces:
        values = [v.strip() for v in (trace.args or {}).values() if isinstance(v, str) and v.strip()]
        if trace.status == "ok" and trace.evidence_ids:
            resolved.update(values)
        elif trace.error_code == "not_found":
            missing += [v for v in values if v not in missing]
    return [value for value in missing if value not in resolved]


def _insufficient(outcome: RunOutcome, reason: str) -> RunOutcome:
    outcome.status = INSUFFICIENT_EVIDENCE
    outcome.error_code = "evidence_missing"
    outcome.missing_info = [reason]
    return outcome


def _confirmation_reasons(outcome: RunOutcome, scenario: Scenario) -> list[str]:
    reasons: list[str] = []
    for rule in scenario.confirmation_rules:
        for name, args, data in outcome._tool_data:
            value = data.get(rule.field) if isinstance(data, dict) else None
            if name == rule.tool_name and value in rule.values:
                target = json.dumps(args, ensure_ascii=False, default=str)
                reasons.append(f"{rule.reason}（{name} {target} → {rule.field}={value}）")
    return reasons


def _try_clarify(outcome: RunOutcome, messages: list[dict], tc: dict, emit: Emit) -> bool:
    """解析澄清请求；参数非法时把错误回给模型继续循环（返回 False）。"""
    seq = len(outcome.traces) + 1
    emit("tool_started", {"sequence": seq, "toolName": CLARIFY_TOOL})
    try:
        args = json.loads(outcome._restore(tc["function"].get("arguments") or "{}"))
    except json.JSONDecodeError:
        args = None
    question = args.get("question") if isinstance(args, dict) else None
    missing = args.get("missingInfo", []) if isinstance(args, dict) else []
    valid = (isinstance(question, str) and question.strip()
             and isinstance(missing, list) and all(isinstance(m, str) for m in missing))
    outcome.traces.append(ToolCallTrace(
        sequence=seq, tool_name=CLARIFY_TOOL, args=args if isinstance(args, dict) else {},
        status="ok" if valid else "error", duration_ms=0,
        error_code=None if valid else "invalid_args"))
    emit("tool_finished", {"sequence": seq, "toolName": CLARIFY_TOOL,
                           "status": "ok" if valid else "error", "durationMs": 0,
                           "errorCode": None if valid else "invalid_args", "evidenceIds": []})
    if not valid:
        messages.append({"role": "tool", "tool_call_id": tc["id"],
                         "content": _render_result(ToolResult.failure(
                             "invalid_args", "question 必填且为字符串，missingInfo 为字符串数组"))})
        return False
    outcome.status = NEEDS_CLARIFICATION
    outcome.answer = question.strip()
    outcome.error_code = "clarification_required"
    outcome.missing_info = list(missing)
    return True


def _finalize_context(outcome: RunOutcome, scenario: Scenario) -> None:
    sources: list[object] = []
    for name, args, data in outcome._tool_data:
        sources += [args, data]
    outcome.entities = context.extract_entities(scenario.entity_keys, sources)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _timed_out(outcome: RunOutcome) -> RunOutcome:
    limit = settings.run_timeout_seconds
    return _failed(outcome, "run_timeout",
                   f"run 超出 {limit:g}s 时限" if limit is not None else "run 超出时限")


def _failed(outcome: RunOutcome, error_code: str, message: str) -> RunOutcome:
    outcome.status = FAILED
    outcome.answer = None
    outcome.error_code = error_code
    outcome.error_message = message
    return outcome


def _accumulate(usage: dict, resp_usage: dict) -> None:
    usage["promptTokens"] += resp_usage.get("prompt_tokens", 0) or 0
    usage["completionTokens"] += resp_usage.get("completion_tokens", 0) or 0
    usage["totalTokens"] += resp_usage.get("total_tokens", 0) or 0


def _validate_response(outcome: RunOutcome, resp: dict, started: float) -> bool:
    # @why 最后一次响应也要验收，否则不再调用工具的答案能绕过硬限制。
    #      总时限未配置（None，默认不限）时跳过时限验收，token 与截断验收照常
    if (settings.run_timeout_seconds is not None
            and time.monotonic() - started >= settings.run_timeout_seconds):
        _timed_out(outcome)
        return False
    if outcome.usage["totalTokens"] > token_limit(outcome):
        _failed(outcome, "token_limit_exceeded",
                f"run 累计 token 超出上限 {token_limit(outcome)}")
        return False
    if resp.get("finish_reason") == "length":
        _failed(outcome, "llm_output_incomplete", "模型响应达到长度上限，未生成完整内容")
        return False
    return True


def _execute_tool_call(db: Session, outcome: RunOutcome, messages: list[dict],
                       run_ctx: dict, persist_evidence: Callable[[EvidenceRecord], str],
                       tc: dict, emit: Emit = _noop_emit) -> None:
    name = tc["function"]["name"]
    seq = len(outcome.traces) + 1
    emit("tool_started", {"sequence": seq, "toolName": name})
    started = time.monotonic()
    arguments = tc["function"].get("arguments", "")
    masker = run_ctx.get("masker")
    if masker is not None:
        # 模型看到的是代号：入参在本地还原成原文再查库（代号不落库、不外送原文）
        arguments = masker.unmask(arguments)
    result, records, args = registry.execute_tool(db, run_ctx, name, arguments)
    if masker is not None:
        # 轨迹参数会落库并经 run 详情返回，记录代号形式
        args = masker.mask_obj(args)
    duration_ms = int((time.monotonic() - started) * 1000)
    ev_ids = [persist_evidence(record) for record in records]
    result.evidence_ids = ev_ids
    outcome.evidence_ids.extend(ev_ids)
    error_code = result.error.code if result.error else None
    outcome.traces.append(ToolCallTrace(
        sequence=seq, tool_name=name, args=args,
        status="ok" if result.is_success else "error",
        duration_ms=duration_ms, error_code=error_code, evidence_ids=ev_ids))
    emit("tool_finished", {"sequence": seq, "toolName": name,
                           "status": "ok" if result.is_success else "error",
                           "durationMs": duration_ms, "errorCode": error_code,
                           "evidenceIds": ev_ids})
    if result.is_success:
        outcome._tool_data.append((name, args, result.data))
    outcome.tool_summaries.append(context.summarize_tool_call(
        name, args, result.is_success, result.data, error_code, ev_ids,
        settings.context_tool_summary_chars))
    # @why 工具返回的是数据库原始行（手机号、身份证、卡号等），作为 tool 消息会原样外送给模型；
    #      送出前掩码（通用纪律第 2 条、自查第 9 条）。终态判定与证据仍用未掩码的 result.data，
    #      证据只落本地库，不外送
    content, counts = outcome._redact(_render_result(result))
    for kind, n in counts.items():
        outcome.tool_pii_counts[kind] = outcome.tool_pii_counts.get(kind, 0) + n
    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": content})


def _terminal_outcome(outcome: RunOutcome, scenario: Scenario,
                      tool_calls: list[dict]) -> bool:
    """场景终止工具：本轮成功结果带 finalAnswer 时直接收尾，带 terminalError 时失败收尾。"""
    names = {tc["function"]["name"] for tc in tool_calls} & set(scenario.terminal_tools)
    if not names:
        return False
    for name, _args, data in reversed(outcome._tool_data):
        if name not in names or not isinstance(data, dict):
            continue
        if data.get("terminalError"):
            error = data["terminalError"]
            _finalize_context(outcome, scenario)
            _failed(outcome, error.get("code") or "execution_failed", error.get("message") or "")
            return True
        if data.get("finalAnswer"):
            _finish_with_answer(outcome, scenario, data["finalAnswer"])
            return True
        return False
    return False


def check_answer(outcome: RunOutcome, scenario: Scenario,
                 text: str | None) -> tuple[str | None, list[dict]]:
    """场景发布前校验；没有配置时原样通过。"""
    if scenario.answer_check is None or not (text or "").strip():
        return text, []
    if not outcome.evidence_ids and _is_out_of_scope(outcome, scenario):
        # 能力外问题的模型原文不会发布（改用固定引导），不必校验也不必重写
        return text, []
    return scenario.answer_check(text, outcome._tool_data, outcome.evidence_ids)


def _render_result(result: ToolResult) -> str:
    """ToolResult 序列化为给 LLM 的工具消息（契约 §内部 ToolResult 的 camelCase 形态）。"""
    payload: dict = {"isSuccess": result.is_success, "data": result.data,
                     "evidenceIds": result.evidence_ids}
    if result.error:
        payload["error"] = {"code": result.error.code,
                            "message": result.error.message,
                            "isRetryable": result.error.is_retryable}
    return json.dumps(payload, ensure_ascii=False, default=str)
