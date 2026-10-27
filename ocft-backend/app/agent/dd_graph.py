"""赛题 04 多 Agent 编排：主控调度六个角色 Agent 的 LangGraph 子图（ADR-0008；spec dd-multi-agent）。

拓扑（静态，不在计划内的角色进入节点即返回 skipped）：

    START ─┬─ business ─┐
           ├─ finance  ─┼─ fraud ─ rating ─ report ─ verify ─ END
           └─ opinion  ─┘

- 工商 / 财报 / 舆情在同一个 superstep 并行执行，反欺诈等三路汇合后执行。
- 主控是场景的工具循环 Agent（engine + graph.py），通过控制工具 run_dd_agents 调度本子图：
  mode=full 时报告角色的五部分报告经事实校验后直接作为最终答案（终止工具）；
  mode=followup 时把角色结果交回主控成文，主控的答案同样经事实校验。

@why 角色节点不碰 Session：快照在工具入口（主线程）读出并冻结；证据由工具返回、
     engine 在主线程统一落库（与 run 同事务）。事件经本模块的锁串行写入记录器。
@why 只用 LangGraph 做调度；模型只经 app/llm.py，数字只来自 dd_calc 纯函数。
"""
from __future__ import annotations

import json
import threading
import time
from typing import Annotated

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session
from typing_extensions import TypedDict

from ..domain.errors import ToolError
from ..domain.types import ToolResult
from ..tools.registry import register_tool
from . import dd_roles, dd_verify
from .dd_roles import DEGRADED, FAILED, OK, ROLE_ORDER, SKIPPED, RoleContext, RoleResult
from .dd_snapshot import Masker, build_masker, load_snapshot

TOOL_NAME = "run_dd_agents"
_PARALLEL_GROUP = {"business": 1, "finance": 1, "opinion": 1, "fraud": 2, "rating": 3, "report": 4}


def _merge(left: dict, right: dict) -> dict:
    return {**(left or {}), **(right or {})}


class DDState(TypedDict):
    results: Annotated[dict, _merge]
    verify: dict


def _locked_emit(run_ctx: dict):
    emit = run_ctx.get("emit") or (lambda _t, _d: None)
    lock = threading.Lock()

    def safe(event_type: str, data: dict) -> None:
        # @why RunEventRecorder 按列表长度分配序号，并行角色需串行写入，保证序号唯一且连续
        with lock:
            emit(event_type, data)
    return safe


def _run_role(role: str, ctx: RoleContext, plan: list[str], results: dict, emit) -> RoleResult:
    """串行口径：算数字 → 写解读，一个角色一步。"""
    result, started = _prepare_role(role, ctx, plan, results, emit, _PARALLEL_GROUP[role])
    if result.status != SKIPPED:
        _interpret_role(role, ctx, result, results, started, emit)
    return result


def _prepare_role(role: str, ctx: RoleContext, plan: list[str], results: dict, emit,
                  group: int) -> tuple[RoleResult, float]:
    """只算数字和证据（纯函数，毫秒级），不调模型。"""
    spec = ctx.config.roles[role]
    result = RoleResult(role=role, name=spec.name, status=OK)
    started = time.monotonic()
    if role not in plan:
        result.status = SKIPPED
        return result, started
    blocked = [d for d in dd_roles._all_deps(role, results) if results[d].status in (FAILED, SKIPPED)]
    missing = [d for d in spec.depends_on if d not in results]
    emit("role_started", {"role": role, "name": spec.name, "parallelGroup": group})
    if blocked or missing:
        result.status = FAILED
        result.error_code = "upstream_failed"
        result.error_message = f"上游角色未完成：{'、'.join(blocked + missing)}"
    else:
        try:
            result.data = dd_roles.compute(role, ctx.snapshot, results)
        except ToolError as exc:
            result.status, result.error_code, result.error_message = FAILED, exc.code, exc.message
        except Exception as exc:  # noqa: BLE001 计算意外异常也要落到角色状态里，不抛出图外
            result.status = FAILED
            result.error_code = "execution_failed"
            result.error_message = f"{type(exc).__name__}: {exc}"
        if result.status == OK:
            result.evidence = dd_roles.evidence_for(role, result.data, ctx.snapshot, ctx.run_ctx)
    return result, started


def _interpret_role(role: str, ctx: RoleContext, result: RoleResult, results: dict, started: float,
                    emit, upstream_analysis: bool = True) -> None:
    """写模型解读（或报告）并发出 role_finished。upstream_analysis=False 时只给上游数字。"""
    spec = ctx.config.roles[role]
    if result.status == OK and spec.llm:
        try:
            if role == "report":
                dd_roles.write_report(spec, ctx, result, results)
            else:
                dd_roles.analyze(spec, ctx, result, results, upstream_analysis=upstream_analysis)
        except Exception as exc:  # noqa: BLE001 解读失败只降级，数字照常可用
            result.status = DEGRADED
            result.error_code = "analysis_unavailable"
            result.error_message = f"{type(exc).__name__}: {exc}"
    result.duration_ms = int((time.monotonic() - started) * 1000)
    emit("role_finished", {
        "role": role, "name": spec.name, "status": result.status, "durationMs": result.duration_ms,
        "llm": bool(spec.llm and result.llm_calls), "evidenceCount": len(result.evidence),
        "errorCode": result.error_code,
        # 要点经代号化 + 掩码后推送（事件会落库并给前端展示），最多 3 条
        "keyFindings": [ctx.redact(str(item))[0]
                        for item in ((result.analysis or {}).get("keyFindings") or [])[:3]]})


# 报告事实校验只允许引用申请期限；本次申请额度不进报告正文，故不纳入事实源
_LOAN_FACT_FIELDS = ("loan_term_months",)


def _verify_report(ctx: RoleContext, results: dict, emit) -> dict:
    report = results.get("report")
    if report is None or report.status != OK or not report.report_text:
        return {"status": "skipped"}
    # @why 事实来源只取角色计算结果和申请期限。不放整份快照：原始行里数字太多，校验会形同虚设。
    #      申请额不进报告，也不作事实源，避免正文写出「本次申请额度」。
    loan = ctx.snapshot.loan or {}
    sources = [r.data for r in results.values() if r.data] + [
        {k: loan.get(k) for k in _LOAN_FACT_FIELDS}]
    level = ((results.get("rating").data or {}).get("rating") or {}).get("riskLevel") \
        if results.get("rating") else None
    issues = (dd_verify.check(report.report_text, sources, expected_level=level)
              + dd_verify.check_scope(report.report_text, ctx.snapshot.scope))
    attempt = 1
    while issues and attempt <= ctx.config.max_rewrites:
        emit("verify_finished", {"status": "retry", "attempt": attempt,
                                 "issues": [i["detail"] for i in issues[:12]]})
        previous = report.report_text
        report.report_text = None
        dd_roles.write_report(ctx.config.roles["report"], ctx, report, results,
                              fix=dd_verify.render_issues(issues), previous=previous)
        if not report.report_text:
            break
        issues = (dd_verify.check(report.report_text, sources, expected_level=level)
                  + dd_verify.check_scope(report.report_text, ctx.snapshot.scope))
        attempt += 1
    status = "ok" if (report.report_text and not issues) else "failed"
    emit("verify_finished", {"status": status, "attempt": attempt,
                             "issues": [i["detail"] for i in issues[:12]]})
    return {"status": status, "attempts": attempt, "issues": issues}


def run_graph(ctx: RoleContext, plan: list[str], run_ctx: dict) -> tuple[dict, dict]:
    if ctx.config.parallel_analysis:
        return _run_graph_parallel(ctx, plan, run_ctx)
    emit = _locked_emit(run_ctx)

    def node(role: str):
        def fn(state: DDState) -> dict:
            return {"results": {role: _run_role(role, ctx, plan, state.get("results") or {}, emit)}}
        return fn

    def verify(state: DDState) -> dict:
        return {"verify": _verify_report(ctx, state.get("results") or {}, emit)}

    graph = StateGraph(DDState)
    for role in ROLE_ORDER:
        graph.add_node(role, node(role))
    graph.add_node("verify", verify)
    for role in ("business", "finance", "opinion"):
        graph.add_edge(START, role)
    graph.add_edge(["business", "finance", "opinion"], "fraud")
    graph.add_edge("fraud", "rating")
    graph.add_edge("rating", "report")
    graph.add_edge("report", "verify")
    graph.add_edge("verify", END)
    final = graph.compile().invoke({"results": {}, "verify": {}})
    return final.get("results") or {}, final.get("verify") or {}


_ANALYSTS = ("business", "finance", "opinion", "fraud", "rating")


def _run_graph_parallel(ctx: RoleContext, plan: list[str], run_ctx: dict) -> tuple[dict, dict]:
    """并行解读口径（agents.yaml parallel_analysis: true）：

        START ─ compute ─┬─ business ─┐
                         ├─ finance  ─┤
                         ├─ opinion  ─┼─ report ─ verify ─ END
                         ├─ fraud    ─┤
                         └─ rating   ─┘

    @why 数字全部来自 dd_calc 纯函数，按依赖顺序算完只要毫秒；串行链路的耗时都在模型解读上。
         反欺诈、评级的解读改为只看上游数字（不等上游解读），五个解读同时调用，
         关键路径从「三路最慢 + 反欺诈 + 评级 + 报告」缩短为「解读最慢 + 报告」。
         报告仍在全部解读完成后写，能用到每个角色的判断。
    """
    emit = _locked_emit(run_ctx)
    started: dict[str, float] = {}

    def compute(_state: DDState) -> dict:
        results: dict = {}
        for role in _ANALYSTS:
            results[role], started[role] = _prepare_role(role, ctx, plan, results, emit, 1)
        return {"results": results}

    def analyst(role: str):
        def fn(state: DDState) -> dict:
            results = state.get("results") or {}
            result = results[role]
            if result.status != SKIPPED:
                _interpret_role(role, ctx, result, results, started[role], emit,
                                upstream_analysis=False)
            return {"results": {role: result}}
        return fn

    def report(state: DDState) -> dict:
        # @why 报告在解读全部完成后才开始（role_started 也在此时发出），前端泳道与耗时如实反映
        results = state.get("results") or {}
        result, begun = _prepare_role("report", ctx, plan, results, emit, 2)
        if result.status != SKIPPED:
            _interpret_role("report", ctx, result, results, begun, emit)
        return {"results": {"report": result}}

    def verify(state: DDState) -> dict:
        return {"verify": _verify_report(ctx, state.get("results") or {}, emit)}

    graph = StateGraph(DDState)
    graph.add_node("compute", compute)
    for role in _ANALYSTS:
        graph.add_node(role, analyst(role))
    graph.add_node("report", report)
    graph.add_node("verify", verify)
    graph.add_edge(START, "compute")
    for role in _ANALYSTS:
        graph.add_edge("compute", role)
    graph.add_edge(list(_ANALYSTS), "report")
    graph.add_edge("report", "verify")
    graph.add_edge("verify", END)
    final = graph.compile().invoke({"results": {}, "verify": {}})
    return final.get("results") or {}, final.get("verify") or {}


def _failure_explanation(results: dict, evidence_count: int, issue_count: int,
                         scope: str = "loan") -> str:
    """报告被事实校验拦下时，保留可核验的中间结果，避免整笔只剩一个错误码。

    @why 只披露规则工具算出的确定性结果与证据条数，不发布未通过校验的正文；
         评审可据此判断是「模型幻觉」还是「校验口径」问题。
    @why 企业口径没有额度测算，失败说明里不列建议额度与期限，避免把贷款口径带进无额度报告。
    """
    rating_data = (results.get("rating").data or {}) if results.get("rating") else {}
    rating = rating_data.get("rating") or {}
    credit = rating_data.get("credit") or {}
    fraud = (results.get("fraud").data or {}) if results.get("fraud") else {}
    opinion = (results.get("opinion").data or {}) if results.get("opinion") else {}
    level = rating.get("riskLevel") or "未取得"
    points = rating.get("score")
    vetoes = "、".join(rating.get("vetoes") or []) or "无"
    rules = "、".join(fraud.get("hitRuleIds") or []) or "无"
    labels = "、".join(opinion.get("labels") or []) or "无"
    lines = [
        "",
        "以下是规则工具算出的可核验中间结果（未经事实校验，不作为结论发布）：",
        f"- 尽调口径：{'企业主体（含建议授信额度，不含申请贷款额度）' if scope == 'enterprise' else '本笔贷款申请'}",
        f"- 风险评级：{level}（风险点数 {points if points is not None else '未取得'}）；一票否决：{vetoes}",
    ]
    amount = credit.get("suggestedCreditAmount") or "未测算"
    if scope == "enterprise":
        lines.append(f"- 建议授信额度：{amount}")
    else:
        term = credit.get("termMonths")
        lines.append(f"- 建议额度：{amount}；期限：{term if term is not None else '未取得'} 个月")
    lines += [
        f"- 反欺诈命中：{rules}；舆情标签：{labels}",
        f"- 已落库证据 {evidence_count} 条，可在 run 详情与 evidence 接口逐条追溯",
        f"- 失败原因：正文有 {issue_count} 处数字、评级或规则编号与本次工具结果对不上；"
        "完整报告已撤下，避免发布未核实数字，修正校验问题后可重跑同一申请",
    ]
    return "\n".join(lines)


def _role_view(result: RoleResult) -> dict:
    return {"name": result.name, "status": result.status, "errorCode": result.error_code,
            "errorMessage": result.error_message, "durationMs": result.duration_ms,
            "skill": result.skill,
            "analysis": result.analysis, "brief": dd_roles.brief(result.role, result.data)
            if result.data else None}


@register_tool(
    TOOL_NAME,
    "调度尽调专业角色 Agent：工商核验 business、财报解析 finance、舆情扫描 opinion、反欺诈 fraud、"
    "评级授信 rating、报告 report。工商 / 财报 / 舆情并行，依赖自动补齐。mode=full 执行全部角色并直接"
    "给出经事实校验的尽调报告：scope=loan 为本笔贷款尽调（五部分，额度建议并列申请贷款额度与建议授信额度），"
    "scope=enterprise 为企业主体尽调（五部分，额度建议只含建议授信额度，不得出现申请贷款额度）。"
    "mode=followup 只执行 roles 及其依赖，返回各角色结果供你回答追问。数字由规则工具计算，照抄即可。",
    {"type": "object", "properties": {
        "applicationId": {"type": "string", "description": "贷款申请编号（scope=loan 时使用）"},
        "enterpriseId": {"type": "string", "description": "企业编号；scope=loan 且只给企业时取其最近一笔申请"},
        "scope": {"type": "string",
                  "description": "尽调口径：loan=针对某笔贷款申请（含申请贷款额度）；"
                                 "enterprise=针对企业主体（含建议授信额度，不含申请贷款额度）。"
                                 "按用户问题判断；不传时有 applicationId 按 loan，只给 enterpriseId 按 enterprise"},
        "mode": {"type": "string", "description": "full：完整尽调报告；followup：单项追问"},
        "roles": {"type": "array", "items": {"type": "string"},
                  "description": "followup 时需要的角色，如 [\"finance\"]、[\"rating\"]"},
        "focus": {"type": "string", "description": "追问焦点，如 资产负债率、额度为什么下调"},
    }, "required": ["mode"]},
)
def run_dd_agents(db: Session, run_ctx: dict, mode: str, applicationId: str | None = None,
                  enterpriseId: str | None = None, roles: list | None = None,
                  focus: str | None = None, scope: str | None = None):
    args = {"applicationId": applicationId, "enterpriseId": enterpriseId, "mode": mode,
            "scope": scope, "roles": roles or [], "focus": focus}
    if mode not in ("full", "followup"):
        return ToolResult.failure("invalid_args", "mode 只能是 full 或 followup"), [], args
    if roles is not None and not all(isinstance(r, str) for r in roles):
        return ToolResult.failure("invalid_args", "roles 必须是字符串数组"), [], args
    try:
        config = dd_roles.load_agents_config()
        plan = dd_roles.plan_roles(list(roles or []), config, mode)
        snapshot = load_snapshot(db, applicationId, enterpriseId, scope=scope)
    except ToolError as exc:
        return ToolResult.failure(exc.code, exc.message), [], args
    scope_used = snapshot.scope
    masker: Masker = run_ctx.get("masker") or build_masker(db)
    redact = run_ctx.get("redact") or (lambda text: (masker.mask(text), {}))
    usage = run_ctx.get("usage") or {}
    ctx = RoleContext(snapshot=snapshot, config=config, run_ctx=run_ctx, redact=redact,
                      token_limit=int(run_ctx.get("token_limit") or 10**9), focus=focus,
                      used_tokens=int(usage.get("totalTokens", 0) or 0))
    emit = _locked_emit(run_ctx)
    emit("plan_ready", {"plan": {"mode": mode, "scope": scope_used, "roles": plan,
                                 "target": {"applicationId": snapshot.application_id or None,
                                            "enterpriseId": snapshot.enterprise_id},
                                 "focus": redact(focus or "")[0] or None,
                                 "configFile": config.config_file}})
    results, verify = run_graph(ctx, plan, run_ctx)

    # 主线程汇总：证据按角色固定顺序返回（engine 统一落库），模型调用审计与用量并入 run
    evidence, calls = [], run_ctx.setdefault("llm_calls", [])
    skills_applied = run_ctx.setdefault("skills_applied", [])
    for role in ROLE_ORDER:
        result = results.get(role)
        if result is None:
            continue
        evidence.extend(result.evidence)
        calls.extend(result.llm_calls)
        if result.skill and result.skill not in skills_applied:
            skills_applied.append(result.skill)
        if usage is not None and "totalTokens" in usage:
            usage["promptTokens"] += result.usage["prompt_tokens"]
            usage["completionTokens"] += result.usage["completion_tokens"]
            usage["totalTokens"] += result.usage["total_tokens"]

    executed = [r for r in (results.get(role) for role in plan) if r is not None]
    failed = [r for r in executed if r.status == FAILED]
    rating = (results.get("rating").data or {}) if results.get("rating") else {}
    credit = rating.get("credit") or {}
    data = {
        "mode": mode, "scope": scope_used,
        "applicationId": snapshot.application_id or None,
        "enterpriseId": snapshot.enterprise_id, "plan": plan,
        "riskLevel": (rating.get("rating") or {}).get("riskLevel"),
        "suggestedCreditAmount": credit.get("suggestedCreditAmount"),
        # @why 是否需人工复核（会让终态变为 needs_confirmation）只看确定性信号：角色降级 / 失败、
        #      评分卡要求复核、额度无法测算。模型自评的 needsReview 每次可能不同，放进 reviewSuggestedBy
        #      供补件与复核参考，不决定终态（spec dd-multi-agent 任务 13）
        #      企业口径不测算额度，creditError 恒为空，不参与复核判定。
        "needsManualReview": any(r.status != OK for r in executed) or bool(
            (rating.get("rating") or {}).get("needsManualReview")) or bool(rating.get("creditError")),
        "reviewSuggestedBy": [r.role for r in executed if (r.analysis or {}).get("needsReview")],
        "roles": {r.role: _role_view(r) for r in executed},
        "verify": {k: v for k, v in verify.items() if k != "issues"},
    }
    if failed and all(r.error_code == "not_found" for r in failed):
        return ToolResult.failure("not_found", failed[0].error_message or "对象不存在"), evidence, args
    if mode == "full":
        report = results.get("report")
        if verify.get("status") == "ok" and report is not None and report.report_text:
            data["finalAnswer"] = report.report_text
        elif verify.get("status") == "failed":
            issues = verify.get("issues") or []
            data["terminalError"] = {
                "code": "narrative_check_failed",
                "message": ("报告未通过事实校验：" + dd_verify.render_issues(issues, 5)
                            + _failure_explanation(results, len(evidence), len(issues), scope_used))}
        # 报告角色降级（未产出正文）时不设终止：交回主控，按角色结果如实说明
    # 返回给模型与写入上下文的数据先代号化（决策 5）；证据快照保留原值，只在本地库
    return ToolResult.success(masker.mask_obj(data)), evidence, masker.mask_obj(args)


# ---- 主控答案的发布前校验（followup 与普通问答） ----

def check_answer(text: str, tool_data: list, evidence_ids: list[str],
                 disclaimer: str | None = None) -> tuple[str, list[dict]]:
    """主控答案的事实校验；本次 run 没有任何工具结果时不校验（如职责说明）。

    额度相关回答缺免责声明时按固定条款补齐（不是结论）。
    """
    if not tool_data:
        return text, []
    sources = [data for _name, _args, data in tool_data]
    levels = {d.get("riskLevel") for d in sources if isinstance(d, dict) and d.get("riskLevel")}
    issues = dd_verify.check(text, sources, evidence_ids=evidence_ids,
                             expected_level=next(iter(levels)) if len(levels) == 1 else None)
    if disclaimer is None:
        try:
            disclaimer = dd_roles.load_agents_config().disclaimer
        except ToolError:
            disclaimer = "测算建议，非授信审批"
    if ("额度" in text) and disclaimer not in text:
        text = f"{text}\n\n{dd_roles.disclaimer_line(disclaimer)}"
    return text, issues
