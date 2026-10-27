"""赛题 04 多 Agent：六个角色的定义与执行模板（ADR-0008；spec dd-multi-agent 需求 2、4）。

每个角色按同一模板执行：
1. 计算：只调 app/tools/dd_calc.py 的纯函数，输入是冻结快照与上游角色的计算结果（确定性）；
2. 分析：配置 llm=true 时调一次模型写结构化解读（JSON，Pydantic 校验，失败按 retries 重试，
   用尽记为 degraded：数字保留、解读为空、需人工复核）；报告角色输出五部分 Markdown；
3. 产出 RoleResult：计算结果、解读、待落库证据、模型调用审计、用量。

@why 角色函数不接收 Session：并行线程里不碰数据库（决策 3）。模型只经 app/llm.py（R1）。
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field, ValidationError

from .. import llm
from ..config import settings
from ..domain.errors import LLMError, ToolError
from ..domain.types import EvidenceRecord
from ..tools import dd_calc
from ..tools.dd_config import CONFIG_DIR, load_config
from . import llm_audit
from .dd_snapshot import Snapshot
from .skills import SKILL_DIR, Skill, SkillError, load_skills

ROLE_ORDER = ("business", "finance", "opinion", "fraud", "rating", "report")
OK, DEGRADED, SKIPPED, FAILED = "ok", "degraded", "skipped", "failed"
# 两种口径都是五部分；差异只在额度建议是否展示「申请贷款额度」
REPORT_SECTIONS = ("企业概况", "财务分析", "风险提示", "额度建议", "风控条件")
ENTERPRISE_REPORT_SECTIONS = REPORT_SECTIONS


def report_sections(scope: str | None) -> tuple[str, ...]:
    return ENTERPRISE_REPORT_SECTIONS if scope == "enterprise" else REPORT_SECTIONS


# @why 只给问题清单时，模型常把同一个被拦的数字原样再写一遍（实测同一写法连续两次被拦）。
#      写明改法：照抄输入原值，输入里没有的数字改成定性描述，不要换算法再算一次
REWRITE_GUIDE = ("改法：每个被指出的数字，改为照抄输入里的原值（比率换算为百分数并保留 1 位小数，"
                 "负值保留负号，如 -0.2222 写作 -22.2%；金额照抄万元原值）；输入里没有的数字"
                 "（差值、合计、平均、自己推算的结果）删掉数字，改为定性描述，不要换一种算法重新计算。")

Redact = Callable[[str], tuple[str, dict[str, int]]]
Emit = Callable[[str, dict], None]


@dataclass(frozen=True)
class RoleSpec:
    role: str
    name: str
    depends_on: tuple[str, ...]
    llm: bool
    max_tokens: int
    retries: int
    prompt: str
    # 单次模型调用时限（秒）；None 用全局 llm_timeout_seconds
    timeout_seconds: float | None = None
    # 模型推理模式：None 沿用接口默认（开启），False 关闭（agents.yaml 的 thinking）
    thinking: bool | None = None


@dataclass(frozen=True)
class AgentsConfig:
    roles: dict[str, RoleSpec]
    controller_prompt: str
    common_prompt: str
    max_rewrites: int
    disclaimer: str
    # 企业口径报告的收尾条款：不涉及额度，避免把「测算建议」写进无额度的报告
    enterprise_disclaimer: str
    config_file: str
    max_total_tokens: int | None = None
    max_tokens_cap: int = 8192
    # True：先按依赖顺序算完全部数字，再让非报告角色并行写解读（解读只看上游数字，不看上游解读）
    parallel_analysis: bool = False
    # 主控工具循环的推理开关（controller.thinking）；None 沿用接口默认
    controller_thinking: bool | None = None


def load_agents_config() -> AgentsConfig:
    """读 scenarios/dd04/agents.yaml 与 prompts/；每次调用重新读取（改配置不改代码）。"""
    cfg = load_config("agents.yaml")
    prompts = CONFIG_DIR / "prompts"
    roles: dict[str, RoleSpec] = {}
    for role in ROLE_ORDER:
        item = (cfg.get("roles") or {}).get(role)
        if not isinstance(item, dict):
            raise ToolError("execution_failed", f"agents.yaml 缺少角色 {role}")
        deps = tuple(item.get("depends_on") or ())
        unknown = [d for d in deps if d not in ROLE_ORDER or ROLE_ORDER.index(d) >= ROLE_ORDER.index(role)]
        if unknown:
            raise ToolError("execution_failed", f"角色 {role} 的依赖非法: {unknown}")
        roles[role] = RoleSpec(
            role=role, name=str(item.get("name") or role), depends_on=deps,
            llm=bool(item.get("llm", True)), max_tokens=int(item.get("max_tokens") or 700),
            retries=max(int(item.get("retries", 1)), 0),
            prompt=_read_prompt(prompts, item.get("prompt") or f"{role}.md"),
            timeout_seconds=float(item["timeout_seconds"]) if item.get("timeout_seconds") else None,
            thinking=bool(item["thinking"]) if item.get("thinking") is not None else None)
    verify = cfg.get("verify") or {}
    controller = cfg.get("controller") or {}
    return AgentsConfig(
        roles=roles,
        controller_prompt=_read_prompt(prompts, controller.get("prompt") or "controller.md"),
        common_prompt=_read_prompt(prompts, "_role_common.md"),
        max_rewrites=max(int(verify.get("max_rewrites", 1)), 0),
        disclaimer=str(verify.get("disclaimer") or "测算建议，非授信审批"),
        enterprise_disclaimer=str(verify.get("enterprise_disclaimer") or "尽调分析建议，非授信审批"),
        config_file=cfg["_file"],
        max_total_tokens=int(controller["max_total_tokens"]) if controller.get("max_total_tokens") else None,
        max_tokens_cap=int(cfg.get("max_tokens_cap") or 8192),
        parallel_analysis=bool(cfg.get("parallel_analysis", False)),
        controller_thinking=(bool(controller["thinking"])
                             if controller.get("thinking") is not None else None))


def _read_prompt(folder: Path, name: str) -> str:
    path = folder / name
    if not path.is_file():
        raise ToolError("execution_failed", f"缺少角色提示词: scenarios/dd04/prompts/{name}")
    return path.read_text(encoding="utf-8").strip()


def plan_roles(requested: list[str], config: AgentsConfig, mode: str) -> list[str]:
    """依赖闭包：mode=full 跑全部；followup 按 depends_on 递归补齐，保持 ROLE_ORDER 顺序。"""
    if mode == "full":
        return list(ROLE_ORDER)
    unknown = [r for r in requested if r not in config.roles]
    if unknown:
        raise ToolError("invalid_args", f"未知角色: {unknown}，可选 {list(ROLE_ORDER)}")
    if not requested:
        raise ToolError("invalid_args", "followup 模式需要至少一个角色")
    wanted: set[str] = set()
    stack = list(requested)
    while stack:
        role = stack.pop()
        if role not in wanted:
            wanted.add(role)
            stack.extend(config.roles[role].depends_on)
    return [role for role in ROLE_ORDER if role in wanted]


class RoleAnalysis(BaseModel):
    analysis: str = Field(min_length=1, max_length=1200)
    keyFindings: list[str] = Field(default_factory=list, max_length=8)
    uncertainties: list[str] = Field(default_factory=list, max_length=8)
    needsReview: bool = False


def disclaimer_line(disclaimer: str) -> str:
    """补齐免责条款的固定写法。
    @why 用普通段落，不用 Markdown 引用块（`> `）：前端渲染器与导出都不支持引用块，会原样显示 ">"。"""
    return f"说明：{disclaimer}。"


def role_skills() -> dict[str, Skill]:
    """角色键 → 运行时 Skill（scenarios/dd04/skills/）。六个角色必须各有一个。"""
    skills = load_skills(str(SKILL_DIR), ROLE_ORDER)
    missing = [role for role in ROLE_ORDER if role not in skills]
    if missing:
        raise SkillError(f"以下角色缺少 Skill：{missing}")
    return skills


def _with_skill(system: str, result: "RoleResult") -> str:
    """角色 system 消息末尾拼上本角色 Skill，并记下所用版本。"""
    skill = role_skills()[result.role]
    result.skill = skill.ref
    return f"{system}\n\n{skill.prompt()}"


@dataclass
class RoleResult:
    role: str
    name: str
    status: str
    # 本角色模型调用使用的运行时 Skill（name@version）；未调用模型时为 None
    skill: str | None = None
    data: dict = field(default_factory=dict)
    analysis: dict | None = None
    report_text: str | None = None
    evidence: list[EvidenceRecord] = field(default_factory=list)
    llm_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int = 0


@dataclass
class RoleContext:
    """一次调度共享的只读输入与线程安全的计量。"""
    snapshot: Snapshot
    config: AgentsConfig
    run_ctx: dict
    redact: Redact
    token_limit: int
    focus: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    used_tokens: int = 0     # 本次调度开始时 run 已用 + 本次调度各角色累计

    def reserve(self, tokens: int) -> bool:
        """并行调用前按 max_tokens 预占；超出 run 的 token 上限则不再调用模型。"""
        with self.lock:
            if self.used_tokens + tokens > self.token_limit:
                return False
            self.used_tokens += tokens
            return True

    def settle(self, reserved: int, actual: int) -> None:
        with self.lock:
            self.used_tokens += actual - reserved


# ---- 计算：每个角色只调纯函数 ----

def _cfg(name: str) -> dict:
    return load_config(name)


def compute(role: str, snapshot: Snapshot, upstream: dict[str, RoleResult]) -> dict:
    bundle = snapshot.copy_bundle()
    loan = dict(snapshot.loan)
    as_of = loan.get("apply_date") or None
    if role == "business":
        return dd_calc.verify_business(bundle, _cfg("scorecard.yaml"))
    if role == "finance":
        return dd_calc.analyze_financials(bundle["finances"], _cfg("metrics.yaml"), as_of)
    if role == "opinion":
        return dd_calc.scan_public_opinion(bundle, _cfg("opinion.yaml"), as_of)
    finance = upstream["finance"].data
    if role == "fraud":
        return dd_calc.detect_fraud(bundle, finance, _cfg("fraud_rules.yaml"))
    business, opinion, fraud = (upstream[k].data for k in ("business", "opinion", "fraud"))
    if role == "rating":
        rating = dd_calc.rate_risk(bundle, finance, business, opinion, fraud, _cfg("scorecard.yaml"))
        if snapshot.application_id:
            rating["applicationId"] = snapshot.application_id
        credit_cfg = _cfg("credit_model.yaml")
        anomalies = dd_calc.major_anomalies(bundle, finance, credit_cfg)
        try:
            # 企业口径 loan 无申请额：calc_credit_limit 走能力上限，产出建议授信额度但不带申请额
            credit = dd_calc.calc_credit_limit(loan, bundle, finance, rating, credit_cfg)
            credit_error = None
        except ToolError as exc:
            # 额度无法测算（如无完整年度财报）：评级照常给出，额度如实标缺，不编造
            credit, credit_error = None, {"code": exc.code, "message": exc.message}
        return {"rating": rating, "credit": credit, "creditError": credit_error,
                "anomalies": anomalies}
    if role == "report":
        rating_data = upstream["rating"].data
        credit = rating_data.get("credit") or {}
        return dd_calc.build_report(loan, bundle, finance, business, opinion, fraud,
                                    rating_data["rating"], credit,
                                    scope=snapshot.scope,
                                    anomalies=rating_data.get("anomalies") or [])
    raise ToolError("invalid_args", f"未知角色 {role}")


def evidence_for(role: str, data: dict, snapshot: Snapshot, run_ctx: dict) -> list[EvidenceRecord]:
    """与单工具版本相同的证据口径（source_ref.calc 沿用工具名，评测按它取证），并标注角色。"""
    eid, aid = snapshot.enterprise_id, snapshot.application_id
    version = run_ctx.get("data_version", 1)

    def record(table: str, keys: dict, snap, calc: str) -> EvidenceRecord:
        return EvidenceRecord(source_type="calculation",
                              source_ref={"table": table, "keys": keys, "calc": calc, "role": role},
                              snapshot=snap, data_version=version)

    if role == "business":
        return [record("enterprise_basic", {"enterpriseId": eid}, data, "verify_business_info")]
    if role == "finance":
        return [record("enterprise_finance", {"enterpriseId": eid}, data, "analyze_financials")]
    if role == "opinion":
        return [record("enterprise_public_opinion", {"enterpriseId": eid}, data, "scan_public_opinion")]
    if role == "fraud":
        return [record("enterprise_finance", {"enterpriseId": eid}, data, "detect_fraud_signals")]
    if role == "rating":
        out = [record("enterprise_risk", {"enterpriseId": eid}, data["rating"], "rate_risk")]
        if data.get("credit"):
            if aid:
                out.append(record("loan_application", {"applicationId": aid}, data["credit"],
                                  "calc_credit_limit"))
            else:
                # 企业主体测算：额度证据挂在企业上，快照不含申请额
                out.append(record("enterprise_basic", {"enterpriseId": eid}, data["credit"],
                                  "calc_credit_limit"))
        return out
    # 企业口径报告没有申请行，证据键落在企业主体上；贷款口径仍指向本次申请
    if snapshot.scope == "enterprise":
        return [record("enterprise_basic", {"enterpriseId": eid}, data, "build_dd_report")]
    return [record("loan_application", {"applicationId": aid}, data, "build_dd_report")]


# ---- 送模型的精简输入 ----

def brief(role: str, data: dict) -> dict:
    """角色计算结果的精简视图：只留解读需要的字段，控制 token。"""
    if role == "finance":
        years = []
        for year in data.get("years") or []:
            subjects = year.get("subjects") or {}
            years.append({
                "year": year.get("year"),
                "subjects": {k: subjects.get(k) for k in (
                    "revenue", "netProfit", "totalAssets", "totalLiabilities", "ownersEquity",
                    "operatingCashflow", "accountsReceivable", "inventory", "fixedAssets", "otherReceivable",
                    "interestBearingDebt", "auditOpinion")},
                "metrics": {k: {"name": m.get("name"), "value": m.get("value"), "flag": m.get("flag")}
                            for k, m in (year.get("metrics") or {}).items()},
                "balanced": (year.get("balanceCheck") or {}).get("balanced"),
            })
        return {"unit": data.get("unit"), "note": data.get("denominatorNote"),
                "asOf": data.get("asOf"), "years": years, "growth": data.get("growth")}
    if role == "opinion":
        return {k: data.get(k) for k in ("asOf", "unit", "opinionRiskScore", "healthScore", "labels",
                                         "events", "lawsuits", "lawsuitCount", "lawsuitAmount",
                                         "openDefendantAmount")}
    if role == "fraud":
        return {"rules": data.get("rules"), "hitCount": data.get("hitCount"),
                "hitRuleIds": data.get("hitRuleIds")}
    if role == "rating":
        rating = data.get("rating") or {}
        credit = data.get("credit") or {}
        # 贷款口径：申请额与建议额度并列；企业口径：只传建议额度，去掉申请额。
        credit_brief = None
        if credit:
            keys = ["suggestedCreditAmount", "unit", "termMonths", "rateDirection", "guaranteeType",
                    "conditions", "financialYear", "assumptions", "anomalies"]
            if credit.get("applyAmount") is not None:
                keys = ["applyAmount", *keys]
            credit_brief = {k: credit.get(k) for k in keys}
            credit_brief["steps"] = credit.get("steps") or []
        elif data.get("anomalies") is not None:
            credit_brief = {"anomalies": data.get("anomalies") or []}
        return {"rating": {k: rating.get(k) for k in ("riskLevel", "score", "dimensions", "vetoes",
                                                       "missingIndicators", "needsManualReview")},
                "credit": credit_brief,
                "creditError": data.get("creditError")}
    if role == "report":
        sections = data.get("sections") or {}
        overview = sections.get("overview") or {}
        return {"scope": data.get("scope"), "overview": {k: overview.get(k) for k in (
                    "enterpriseId", "industry", "businessStatus", "establishDate")},
                "riskLevel": data.get("riskLevel"), "asOf": data.get("asOf"),
                "suggestedCreditAmount": data.get("suggestedCreditAmount"),
                "conclusion": data.get("dueDiligenceConclusion")}
    return {k: v for k, v in data.items() if k != "configFile"}


def upstream_view(spec: RoleSpec, upstream: dict[str, RoleResult],
                  with_analysis: bool = True) -> dict:
    """下游角色看到的上游：计算精简 + 解读（不含原始快照）。

    with_analysis=False：并行解读时只给上游数字。上游解读此时可能正在另一线程写入，
    不读它，保证同一输入每次送模型的内容一致。
    """
    view = {}
    for dep in _all_deps(spec.role, upstream):
        result = upstream[dep]
        item = {"name": result.name, "status": result.status,
                "brief": brief(dep, result.data) if result.data else None}
        if with_analysis:
            item["analysis"] = result.analysis
        view[dep] = item
    return view


def _all_deps(role: str, upstream: dict[str, RoleResult]) -> list[str]:
    if role == "report":
        return [r for r in ROLE_ORDER[:-1] if r in upstream]
    if role == "rating":
        return [r for r in ("fraud", "business", "finance", "opinion") if r in upstream]
    if role == "fraud":
        return [r for r in ("business", "finance", "opinion") if r in upstream]
    return []


# ---- 模型调用 ----

def _parse_json(text: str) -> dict:
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("```")[1].removeprefix("json").strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("没有 JSON 对象")
    return json.loads(body[start:end + 1])


def call_model(ctx: RoleContext, result: RoleResult, messages: list[dict], max_tokens: int,
               attempt: int, timeout: float | None = None,
               thinking: bool | None = None) -> dict | None:
    """一次角色模型调用；记录审计与用量。返回模型响应，预算不足返回 None。失败抛 LLMError。

    timeout：角色在 agents.yaml 配置的单次时限；未配置用全局 llm_timeout_seconds。
    @why 报告角色一次输出约 3000 token（含多张表），实测 9–15s，偶发超过全局 30s。
    """
    if not ctx.reserve(max_tokens):
        return None
    masked = [{**m, "content": ctx.redact(m["content"])[0]} for m in messages]
    sha256 = llm_audit.request_sha256(masked, [])
    started_at = llm_audit.utcnow()
    started = time.monotonic()
    resp, error_code = None, None
    try:
        resp = llm.complete_with_tools(masked, [], temperature=0.0,
                                       timeout=timeout or settings.llm_timeout_seconds,
                                       max_tokens=max_tokens, thinking=thinking)
    except LLMError as exc:
        error_code = exc.code
        ctx.settle(max_tokens, 0)
        raise
    finally:
        result.llm_calls.append(llm_audit.build_record(
            round_no=attempt, purpose=f"role:{result.role}", model=settings.llm_model,
            messages=masked, tools=[], sha256=sha256, started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000), resp=resp,
            error_code=error_code, redact=ctx.redact))
    usage = resp.get("usage") or {}
    for key in result.usage:
        result.usage[key] += usage.get(key, 0) or 0
    ctx.settle(max_tokens, usage.get("total_tokens", 0) or 0)
    return resp


def analyze(spec: RoleSpec, ctx: RoleContext, result: RoleResult,
            upstream: dict[str, RoleResult], upstream_analysis: bool = True) -> None:
    """非报告角色：结构化 JSON 解读，校验失败重试，用尽降级。"""
    payload = {"role": spec.name, "applicationId": ctx.snapshot.application_id or None,
               "enterpriseId": ctx.snapshot.enterprise_id, "scope": ctx.snapshot.scope,
               "focus": ctx.focus,
               "result": brief(spec.role, result.data),
               "upstream": upstream_view(spec, upstream, with_analysis=upstream_analysis)}
    messages = [
        {"role": "system", "content": _with_skill(f"{ctx.config.common_prompt}\n\n{spec.prompt}", result)},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]
    last_error = ""
    budget = spec.max_tokens
    for attempt in range(1, spec.retries + 2):
        try:
            resp = call_model(ctx, result, messages, budget, attempt, spec.timeout_seconds,
                              spec.thinking)
        except LLMError as exc:
            last_error = f"模型调用失败[{exc.code}]"
            continue
        if resp is None:
            last_error = "run token 上限不足，未调用模型"
            break
        if resp.get("finish_reason") == "length":
            # @why 推理 token 也计入上限：截断时同样的上限重试大概率再截断，翻倍后重试
            last_error = "模型输出达到长度上限"
            budget = min(budget * 2, ctx.config.max_tokens_cap)
        else:
            try:
                result.analysis = RoleAnalysis.model_validate(
                    _parse_json(resp.get("content") or "")).model_dump()
                return
            except (ValueError, ValidationError) as exc:
                last_error = f"输出不符合结构：{str(exc)[:200]}"
        messages = messages + [
            {"role": "assistant", "content": resp.get("content") or ""},
            {"role": "user", "content": f"上一次输出无效（{last_error}）。只输出要求的 JSON 对象。"}]
    result.status = DEGRADED
    result.error_code = "analysis_unavailable"
    result.error_message = last_error


def write_report(spec: RoleSpec, ctx: RoleContext, result: RoleResult,
                 upstream: dict[str, RoleResult], fix: str | None = None,
                 previous: str | None = None) -> None:
    """报告角色：按口径输出 Markdown（贷款口径五部分 / 企业口径四部分）。fix 为事实校验的问题清单。"""
    scope = ctx.snapshot.scope
    sections = report_sections(scope)
    payload = {"applicationId": ctx.snapshot.application_id or None,
               "enterpriseId": ctx.snapshot.enterprise_id,
               "scope": scope,
               "report": brief("report", result.data), "roles": upstream_view(spec, upstream)}
    messages = [
        {"role": "system", "content": _with_skill(spec.prompt, result)},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
    ]
    if fix and previous:
        messages += [{"role": "assistant", "content": previous},
                     {"role": "user", "content": f"事实校验未通过，请只修正下列问题，其余保持不变，"
                                                 f"仍输出完整报告（{len(sections)} 个章节）：\n{fix}\n{REWRITE_GUIDE}"}]
    attempts = spec.retries + 1
    last_error = ""
    budget = spec.max_tokens
    for attempt in range(1, attempts + 1):
        try:
            resp = call_model(ctx, result, messages, budget, attempt, spec.timeout_seconds,
                              spec.thinking)
        except LLMError as exc:
            last_error = f"模型调用失败[{exc.code}]"
            continue
        if resp is None:
            last_error = "run token 上限不足，未调用模型"
            break
        text = (resp.get("content") or "").strip()
        missing = [s for s in sections if s not in text]
        if resp.get("finish_reason") == "length":
            last_error = "模型输出达到长度上限"
            budget = min(budget * 2, ctx.config.max_tokens_cap)
        elif missing:
            last_error = f"缺少章节：{'、'.join(missing)}"
        else:
            disclaimer = (ctx.config.enterprise_disclaimer if scope == "enterprise"
                          else ctx.config.disclaimer)
            if disclaimer not in text:
                # 固定条款按结构确定性补齐（不是结论），见 design「事实校验」
                text += "\n\n" + disclaimer_line(disclaimer)
            result.report_text = text
            return
        messages = messages + [{"role": "assistant", "content": text},
                               {"role": "user", "content": f"上一次输出无效（{last_error}），请重写完整报告（{len(sections)} 个章节）。"}]
    result.status = DEGRADED
    result.error_code = "report_unavailable"
    result.error_message = last_error
