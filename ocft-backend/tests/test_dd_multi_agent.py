"""赛题 04 多 Agent 编排（ADR-0008，spec dd-multi-agent）：真实引擎 / 子图 / 计算 / 落库，只替换模型。

假模型按请求路由：带工具声明的是主控（按脚本回放），不带工具的是角色 Agent（按系统提示词识别角色）。
工商 / 财报 / 舆情三个角色在假模型里用 Barrier(3) 互相等待：只有真正并行执行时才能通过。
"""
import json
import threading

import pytest

from app import llm
from app.agent import dd_roles, dd_verify
from app.agent.dd_snapshot import build_masker, load_snapshot
from app.db import SessionLocal
from app.models import EnterpriseBasic, Evidence, LlmCall
from conftest import HEADERS, model_reply, tool_call

_ROLE_MARKERS = {"工商核验 Agent": "business", "财报解析 Agent": "finance",
                 "舆情扫描 Agent": "opinion", "反欺诈 Agent": "fraud",
                 "评级授信 Agent": "rating", "报告 Agent": "report"}
_PARALLEL = {"business", "finance", "opinion"}


def _role_of(messages) -> str:
    system = messages[0]["content"]
    for marker, role in _ROLE_MARKERS.items():
        if marker in system:
            return role
    raise AssertionError("无法识别角色")


def _good_report(payload: dict) -> str:
    report = payload["report"]
    return (f"## 企业概况\n{payload['enterpriseId']} 经营正常。\n"
            f"## 财务分析\n见财报解析角色结果。\n"
            f"## 风险提示\n风险评级：{report['riskLevel']}。\n"
            f"## 额度建议\n建议额度 {report['suggestedCreditAmount']}，测算建议，非授信审批。\n"
            f"## 风控条件\n按评级授信角色列出的条件落实。")


class Router:
    def __init__(self, controller: list, *, parallel=True, role_override=None, report_writer=None):
        self.controller = list(controller)
        self.calls: list[dict] = []
        self.lock = threading.Lock()
        self.barrier = threading.Barrier(3, timeout=5) if parallel else None
        self.role_override = role_override or {}
        self.report_writer = report_writer or (lambda payload, attempt: _good_report(payload))
        self.report_attempts = 0

    def __call__(self, messages, tools, temperature=0.2, timeout=None, max_tokens=None,
                 thinking=None):
        if tools:
            with self.lock:
                self.calls.append({"who": "controller", "messages": list(messages), "tools": tools,
                                   "thinking": thinking})
            if not self.controller:
                raise AssertionError("主控脚本已用完")
            reply = self.controller.pop(0)
            return reply(messages) if callable(reply) else reply
        role = _role_of(messages)
        with self.lock:
            self.calls.append({"who": role, "messages": list(messages), "max_tokens": max_tokens,
                               "timeout": timeout, "thinking": thinking})
        if role in _PARALLEL and self.barrier is not None and not any(
                m["role"] == "assistant" for m in messages):
            self.barrier.wait()   # 三路未并行时这里超时，测试失败
        if role in self.role_override:
            override = self.role_override[role]
            if isinstance(override, list):   # 按调用顺序回放；用完后走默认回复
                if override:
                    with self.lock:
                        return override.pop(0)
            else:
                return model_reply(content=override)
        if role == "report":
            with self.lock:
                self.report_attempts += 1
                attempt = self.report_attempts
            payload = json.loads(messages[1]["content"])
            return model_reply(content=self.report_writer(payload, attempt), tokens=50)
        return model_reply(content=json.dumps({
            "analysis": f"{role} 角色分析完成", "keyFindings": [f"{role} 要点"],
            "uncertainties": [], "needsReview": False}, ensure_ascii=False), tokens=20)


@pytest.fixture
def router(monkeypatch):
    holder = {}

    def install(controller, **kwargs):
        holder["router"] = Router(controller, **kwargs)
        monkeypatch.setattr(llm, "complete_with_tools", holder["router"])
        return holder["router"]
    return install


def _create(client, question):
    resp = client.post("/api/agent/runs", json={"question": question}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _events(client, run_id):
    text = client.get(f"/api/agent/runs/{run_id}/events", headers=HEADERS).text
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


def _dispatch(args: dict, call_id="d1"):
    return model_reply(tool_calls=[tool_call(call_id, "run_dd_agents",
                                             json.dumps(args, ensure_ascii=False))])


def test_full_due_diligence_runs_six_roles_in_parallel_and_publishes_report(client, router):
    r = router([_dispatch({"applicationId": "LA001", "mode": "full"})])
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    assert run["answer"].startswith("## 企业概况") and "测算建议，非授信审批" in run["answer"]

    roles_called = [c["who"] for c in r.calls if c["who"] != "controller"]
    assert sorted(roles_called) == sorted(dd_roles.ROLE_ORDER)
    assert len([c for c in r.calls if c["who"] == "controller"]) == 1  # 报告是终止结果，主控不再成文

    events = _events(client, run["runId"])
    names = [e[0] for e in events]
    assert names.count("role_started") == 6 and names.count("role_finished") == 6
    assert "plan_ready" in names and "verify_finished" in names
    assert [e[1]["eventIndex"] for e in events] == list(range(1, len(events) + 1))
    started = {e[1]["role"]: i for i, e in enumerate(events) if e[0] == "role_started"}
    finished = {e[1]["role"]: i for i, e in enumerate(events) if e[0] == "role_finished"}
    # 并行解读口径（agents.yaml parallel_analysis: true）：五个解读同时开始，全部完成后才写报告
    analysts = _PARALLEL | {"fraud", "rating"}
    assert max(started[x] for x in analysts) < min(finished[x] for x in analysts)
    assert max(finished[x] for x in analysts) < started["report"] < finished["report"]
    plan = next(e[1]["plan"] for e in events if e[0] == "plan_ready")
    assert plan["roles"] == list(dd_roles.ROLE_ORDER) and plan["mode"] == "full"

    with SessionLocal() as db:
        evidence = db.query(Evidence).filter(Evidence.run_id == run["runId"]).all()
        assert {ev.source_ref.get("role") for ev in evidence} == set(dd_roles.ROLE_ORDER)
        assert {ev.source_ref.get("calc") for ev in evidence} >= {"calc_credit_limit", "build_dd_report"}
        purposes = [c.purpose for c in db.query(LlmCall).filter(LlmCall.run_id == run["runId"])]
    assert sorted(p for p in purposes if p.startswith("role:")) == sorted(
        f"role:{x}" for x in dd_roles.ROLE_ORDER)
    assert purposes.count("tool_loop") == 1

    detail = client.get(f"/api/agent/runs/{run['runId']}", headers=HEADERS).json()
    assert [t["toolName"] for t in detail["toolTraces"]] == ["run_dd_agents"]


def test_models_never_see_enterprise_or_person_names(client, router):
    r = router([_dispatch({"applicationId": "LA003", "mode": "full"})])
    with SessionLocal() as db:
        basic = db.query(EnterpriseBasic).filter(EnterpriseBasic.enterprise_id == "E003").one()
        secrets = [basic.enterprise_name, basic.legal_person, basic.credit_code,
                   basic.legal_person_id, basic.actual_controller]
    run = _create(client, f"对 {basic.enterprise_name} 的申请 LA003 做完整尽调")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    sent = json.dumps([c["messages"] for c in r.calls], ensure_ascii=False)
    for secret in secrets:
        assert secret and secret not in sent, secret
    assert "企业E003" in sent
    with SessionLocal() as db:
        previews = json.dumps([c.request_preview for c in db.query(LlmCall)
                               .filter(LlmCall.run_id == run["runId"])], ensure_ascii=False)
    assert basic.enterprise_name not in previews


def test_followup_runs_only_requested_role(client, router):
    r = router([_dispatch({"enterpriseId": "E001", "mode": "followup", "roles": ["finance"]}),
                model_reply(content="企业E001 的资产负债率见财报解析 Agent 的结果。")], parallel=False)
    run = _create(client, "E001 的资产负债率是多少")
    assert run["status"] == "succeeded", run
    assert [c["who"] for c in r.calls] == ["controller", "finance", "controller"]
    events = _events(client, run["runId"])
    assert [e[1]["role"] for e in events if e[0] == "role_started"] == ["finance"]
    plan = next(e[1]["plan"] for e in events if e[0] == "plan_ready")
    assert plan["roles"] == ["finance"] and plan["mode"] == "followup"


def test_followup_dependencies_are_closed_by_code(client, router):
    r = router([_dispatch({"applicationId": "LA001", "mode": "followup", "roles": ["rating"]}),
                model_reply(content="评级授信 Agent 已给出额度测算结果。")])
    run = _create(client, "LA001 的额度为什么是这个数")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    events = _events(client, run["runId"])
    plan = next(e[1]["plan"] for e in events if e[0] == "plan_ready")
    assert plan["roles"] == ["business", "finance", "opinion", "fraud", "rating"]
    assert "report" not in {c["who"] for c in r.calls}
    # 涉及额度的追问补齐固定免责条款
    assert "测算建议，非授信审批" in run["answer"]


def test_followup_answer_with_fabricated_number_is_rewritten_then_fails(client, router):
    bad = model_reply(content="企业E001 资产负债率为 99.9%。")
    router([_dispatch({"enterpriseId": "E001", "mode": "followup", "roles": ["finance"]}),
            bad, bad, bad], parallel=False)
    run = _create(client, "E001 的资产负债率")
    assert run["status"] == "failed" and run["errorCode"] == "narrative_check_failed"
    assert run["answer"] is None and run["evidenceIds"]
    statuses = [e[1]["status"] for e in _events(client, run["runId"]) if e[0] == "verify_finished"]
    assert statuses == ["retry", "retry", "failed"]


def test_followup_rewrite_can_fix_the_answer(client, router):
    router([_dispatch({"enterpriseId": "E001", "mode": "followup", "roles": ["finance"]}),
            model_reply(content="企业E001 资产负债率为 99.9%。"),
            model_reply(content="企业E001 的资产负债率请见财报解析结果。")], parallel=False)
    run = _create(client, "E001 的资产负债率")
    assert run["status"] == "succeeded", run
    statuses = [e[1]["status"] for e in _events(client, run["runId"]) if e[0] == "verify_finished"]
    assert statuses == ["retry", "ok"]


def test_full_report_failing_fact_check_twice_is_not_published(client, router):
    def fabricated(payload, attempt):
        return _good_report(payload).replace("见财报解析角色结果。", "营业收入 123456 万元。")
    router([_dispatch({"applicationId": "LA001", "mode": "full"})], report_writer=fabricated)
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["status"] == "failed" and run["errorCode"] == "narrative_check_failed"
    assert run["answer"] is None and run["evidenceIds"]   # 结构化报告仍作为证据落库


def test_full_report_fixed_on_rewrite(client, router):
    def first_wrong(payload, attempt):
        text = _good_report(payload)
        return text.replace("见财报解析角色结果。", "营业收入 123456 万元。") if attempt == 1 else text
    r = router([_dispatch({"applicationId": "LA001", "mode": "full"})], report_writer=first_wrong)
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    assert "123456" not in run["answer"] and r.report_attempts == 2


def test_role_with_invalid_output_degrades_and_requires_review(client, router):
    router([_dispatch({"applicationId": "LA001", "mode": "full"})],
           role_override={"finance": "这不是 JSON"})
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["status"] == "needs_confirmation", run
    events = _events(client, run["runId"])
    finance = next(e[1] for e in events if e[0] == "role_finished" and e[1]["role"] == "finance")
    assert finance["status"] == "degraded" and finance["evidenceCount"] == 1
    detail = client.get(f"/api/agent/runs/{run['runId']}", headers=HEADERS).json()
    assert any("人工复核" in reason for reason in detail["contextSnapshot"]["confirmationReasons"])


def test_truncated_role_output_retries_with_doubled_budget(client, router):
    # 推理 token 计入上限：首轮被截断（内容为空），重试时上限翻倍后正常输出，不降级
    truncated = {**model_reply(content=""), "finish_reason": "length"}
    r = router([_dispatch({"applicationId": "LA001", "mode": "full"})],
               role_override={"finance": [truncated]})
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    budgets = [c["max_tokens"] for c in r.calls if c["who"] == "finance"]
    configured = dd_roles.load_agents_config().roles["finance"].max_tokens
    assert budgets == [configured, configured * 2]
    events = _events(client, run["runId"])
    finance = next(e[1] for e in events if e[0] == "role_finished" and e[1]["role"] == "finance")
    assert finance["status"] == "ok"


def test_role_timeout_comes_from_agents_yaml(client, router):
    # 报告输出长、单次耗时可能超过全局 30s：按 agents.yaml 的 timeout_seconds 放宽；
    # 未配置的角色仍用全局 llm_timeout_seconds
    from app.config import settings
    r = router([_dispatch({"applicationId": "LA001", "mode": "full"})])
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    roles = dd_roles.load_agents_config().roles
    for call in r.calls:
        if call["who"] == "controller":
            continue
        expected = roles[call["who"]].timeout_seconds or settings.llm_timeout_seconds
        assert call["timeout"] == expected, call["who"]
    assert roles["report"].timeout_seconds and roles["report"].timeout_seconds > settings.llm_timeout_seconds


def test_role_thinking_switch_comes_from_agents_yaml(client, router):
    # 推理开关按 agents.yaml 透传到模型入口（耗时优化：关闭推理）：角色按 roles.*.thinking，
    # 主控工具循环按 controller.thinking
    r = router([_dispatch({"applicationId": "LA001", "mode": "full"})])
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    config = dd_roles.load_agents_config()
    role_calls = [c for c in r.calls if c["who"] != "controller"]
    assert role_calls
    for call in role_calls:
        assert call["thinking"] == config.roles[call["who"]].thinking, call["who"]
    assert all(spec.thinking is False for spec in config.roles.values())
    controller_calls = [c for c in r.calls if c["who"] == "controller"]
    assert controller_calls and all(c["thinking"] is False for c in controller_calls)
    assert config.controller_thinking is False


def test_serial_analysis_still_available_when_parallel_disabled(client, router, monkeypatch):
    # parallel_analysis: false 时回到逐级等待解读：反欺诈在三路之后，评级在反欺诈之后
    from dataclasses import replace
    original = dd_roles.load_agents_config
    monkeypatch.setattr(dd_roles, "load_agents_config",
                        lambda: replace(original(), parallel_analysis=False))
    router([_dispatch({"applicationId": "LA001", "mode": "full"})])
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    events = _events(client, run["runId"])
    started = {e[1]["role"]: i for i, e in enumerate(events) if e[0] == "role_started"}
    finished = {e[1]["role"]: i for i, e in enumerate(events) if e[0] == "role_finished"}
    assert max(finished[x] for x in _PARALLEL) < started["fraud"]
    assert finished["fraud"] < started["rating"] < finished["rating"] < started["report"]


def test_unknown_application_is_not_dispatched(client, router):
    r = router([_dispatch({"applicationId": "LA999", "mode": "full"}),
                model_reply(tool_calls=[tool_call("c", "request_clarification",
                                                  '{"question": "请确认申请编号"}')])])
    run = _create(client, "对 LA999 做尽调")
    assert run["status"] == "needs_clarification"
    assert [c["who"] for c in r.calls] == ["controller", "controller"]
    assert not [e for e in _events(client, run["runId"]) if e[0] == "role_started"]


def test_code_names_from_model_are_resolved_locally(client, router):
    router([model_reply(tool_calls=[tool_call("f", "find_enterprise", '{"name": "企业E002"}')]),
            model_reply(content="已定位企业E002。")], parallel=False)
    run = _create(client, "找一下企业E002")
    assert run["status"] == "succeeded", run
    detail = client.get(f"/api/agent/runs/{run['runId']}", headers=HEADERS).json()
    trace = detail["toolTraces"][0]
    assert trace["status"] == "ok" and trace["args"]["name"] == "企业E002"


# ---- 纯函数单测 ----

def test_plan_closure_and_unknown_role():
    config = dd_roles.load_agents_config()
    assert dd_roles.plan_roles(["fraud"], config, "followup") == ["business", "finance", "opinion", "fraud"]
    assert dd_roles.plan_roles([], config, "full") == list(dd_roles.ROLE_ORDER)
    with pytest.raises(Exception):
        dd_roles.plan_roles(["nope"], config, "followup")


def test_verify_numbers_levels_rules_and_evidence():
    facts = [{"riskLevel": "中风险", "ratio": 0.4, "revenue": 28600.0,
              "rules": [{"ruleId": "F01"}], "findings": [{"code": "B03"}]}]
    assert dd_verify.check("资产负债率 40%，营收 2.86 亿元，即 28600 万元；风险评级：中风险；命中 F01、B03。",
                           facts) == []
    issues = dd_verify.check("资产负债率 45%；风险评级：低风险；命中 F09；见 ev_deadbeef01。",
                             facts, evidence_ids=["ev_abc123456"])
    assert {i["type"] for i in issues} == {"number", "risk_level", "rule_id", "evidence_id"}
    # 精度容差：文本写到一位小数时允许半个末位
    assert dd_verify.check("营收 2.9 亿元", facts) == []
    assert dd_verify.check("营收 2.8 亿元", facts) != []


def test_masker_round_trip_and_snapshot_has_no_answer_column(client):
    with SessionLocal() as db:
        masker = build_masker(db)
        basic = db.query(EnterpriseBasic).filter(EnterpriseBasic.enterprise_id == "E001").one()
        text = f"{basic.enterprise_name} 法人 {basic.legal_person} 代码 {basic.credit_code}"
        masked = masker.mask(text)
        assert basic.enterprise_name not in masked and basic.legal_person not in masked
        assert basic.credit_code not in masked and "企业E001" in masked
        assert masker.unmask("企业E001") == basic.enterprise_name
        snapshot = load_snapshot(db, "LA001")
    assert "risk_level_summary" not in json.dumps(snapshot.bundle, ensure_ascii=False)
    assert snapshot.enterprise_id == "E001" and snapshot.loan["application_id"] == "LA001"


# ---- 2026-10-24 修复：事实来源收窄、免责条款写法、确认只看确定性信号 ----

def test_verify_ignores_numbers_inside_dates():
    # 日期拆出来的 15、3 不能让「15 万元」「3 倍」这种编造数字通过；额度区间仍可引用
    facts = [{"asOf": "2024-03-15", "suggestedCreditAmount": "2500-3000"}]
    issues = dd_verify.check("新增贷款 15 万元，覆盖 3 倍。", facts)
    assert {i["snippet"] for i in issues} == {"15 万元", "3 倍"}
    assert dd_verify.check("建议额度 2500-3000 万元，下界 2500 万元。", facts) == []


def test_report_fact_check_does_not_accept_raw_snapshot_numbers(client, router):
    # 原始快照里的数字（如某笔诉讼金额以外的任意字段）不再算事实：编造的金额两次都过不了校验
    def fabricated(payload, attempt):
        # 员工人数 420 只在原始工商行里，不是任何角色的计算结果
        return _good_report(payload).replace("见财报解析角色结果。", "营业收入 420 万元。")
    router([_dispatch({"applicationId": "LA001", "mode": "full"})], report_writer=fabricated)
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["status"] == "failed" and run["errorCode"] == "narrative_check_failed"


def test_disclaimer_is_appended_as_plain_paragraph(client, router):
    def without_disclaimer(payload, attempt):
        return _good_report(payload).replace("，测算建议，非授信审批", "")
    router([_dispatch({"applicationId": "LA001", "mode": "full"})], report_writer=without_disclaimer)
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["answer"].rstrip().endswith("说明：测算建议，非授信审批。")
    assert "\n> " not in run["answer"]


def test_model_self_review_flag_does_not_force_confirmation(client, router):
    # 模型自评 needsReview=true 只作参考（reviewSuggestedBy），低风险申请不因此进入待确认
    flagged = json.dumps({"analysis": "财务分析完成", "keyFindings": ["要点"],
                          "uncertainties": ["缺少银行流水"], "needsReview": True}, ensure_ascii=False)
    router([_dispatch({"applicationId": "LA001", "mode": "full"})], role_override={"finance": flagged})
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["status"] == "succeeded", run
    detail = client.get(f"/api/agent/runs/{run['runId']}", headers=HEADERS).json()
    assert detail["contextSnapshot"]["confirmationReasons"] == []


def test_confirmation_rules_target_registered_tools():
    # 规则只能挂在已注册工具上；单环节工具的高风险规则作兜底保留（模型直接点名时仍会执行）
    from app.agent.scenarios import SCENARIOS
    from app.tools import registry
    scenario = SCENARIOS["enterprise_dd"]
    names = {r.tool_name for r in scenario.confirmation_rules}
    assert "run_dd_agents" in names
    assert names <= set(registry.list_tool_names())

def test_masker_restores_only_names_and_does_not_match_unknown_code_prefixes():
    from app.agent.dd_snapshot import Masker

    masker = Masker()
    masker.add_org("测试示例科技有限公司", "企业E001")
    masker.add("张三", "人员E001-1", restore_on_output=True)
    masker.add("91310000MA1FL3K72A", "信用代码E001")
    masker.add("310101199001011234", "证件号E001")
    text = "企业E001、人员E001-1、信用代码E001、证件号E001；企业E0010、人员E001-10"
    restored = masker.restore_names(text)
    assert restored == ("测试示例科技有限公司、张三、信用代码E001、证件号E001；"
                        "企业E0010、人员E001-10")
    assert masker.unmask("企业E0010、人员E001-10") == "企业E0010、人员E001-10"


def test_terminal_report_restores_names_but_all_role_payloads_and_audits_stay_masked(
        client, router):
    with SessionLocal() as db:
        basic = db.query(EnterpriseBasic).filter_by(enterprise_id="E001").one()
        name, person, credit_code = basic.enterprise_name, basic.legal_person, basic.credit_code

    def report_writer(payload, _attempt):
        return _good_report(payload) + "\n企业E001，人员E001-1，信用代码E001。"

    r = router([_dispatch({"applicationId": "LA001", "mode": "full"})],
               report_writer=report_writer)
    run = _create(client, f"对{name}申请 LA001 做完整尽调")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    assert name in run["answer"] and person not in run["answer"]
    # 人员代号发布为保留姓的脱敏姓名（张三 → 张*），不出现全名也不出现内部代号
    assert f"{person[0]}*" in run["answer"] and "人员E001-1" not in run["answer"]
    assert credit_code not in run["answer"]
    audit = client.get(f"/api/agent/runs/{run['runId']}/llm-calls", headers=HEADERS).json()
    for value in (name, person, credit_code):
        assert value not in json.dumps(r.calls, ensure_ascii=False)
        assert value not in json.dumps(audit, ensure_ascii=False)


@pytest.mark.parametrize("text", [
    "营收同比下降 22.2%", "营收同比下降22.2%", "营业收入同比减少 22.2%", "营收降幅 22.2%",
    "营收同比 -22.2%", "净利润同比下滑 67.9%",
])
def test_verify_accepts_decline_wording_for_negative_ratio(text):
    # LA003 回归：工具给出 revenueYoy=-0.2222，报告写「下降 22.2%」是照抄而不是自算
    facts = [{"growth": {"revenueYoy": -0.2222, "netProfitYoy": -0.6786}}]
    assert dd_verify.check(text, facts) == [], text


@pytest.mark.parametrize("text", [
    "营收同比增长 22.2%",        # 方向写反
    "营收同比下降 25.0%",        # 数值不对
    "营业收入减少 1.6 亿元",     # 自算差值：金额不放开方向词
    "资产负债率下降至 22.2%",    # 「下降至」是水平值，不按变化量放行
])
def test_verify_still_rejects_wrong_direction_value_or_self_computed_gap(text):
    facts = [{"growth": {"revenueYoy": -0.2222},
              "years": [{"year": 2022, "subjects": {"revenue": 72000}},
                        {"year": 2023, "subjects": {"revenue": 56000}}]}]
    assert dd_verify.check(text, facts), text


def test_verify_amount_after_formula_is_checked_against_all_results():
    # dd-006 回归：「净资产 × 0.4 得 5,880 万元」是额度测算步骤的结果，不能只拿所有者权益原值比
    facts = [{"years": [{"year": 2023, "subjects": {"ownersEquity": 14700, "revenue": 28600}}]},
             {"steps": [{"step": "营收口径上限", "value": 3432.0},
                        {"step": "净资产口径上限", "value": 5880.0}]}]
    assert dd_verify.check("按净资产 × 0.4 得 5,880 万元", facts) == []
    assert dd_verify.check("营业收入 × 0.12 = 3,432 万元", facts) == []
    assert dd_verify.check("营收口径上限 3,432 万元", facts) == []
    # 没有运算措辞时仍按科目绑定：拿测算值冒充科目原值要拦
    assert dd_verify.check("2023年净资产 5,880 万元", facts)
    # 测算口径下编造的数字照样拦
    assert dd_verify.check("按净资产 × 0.4 得 6,000 万元", facts)


@pytest.mark.parametrize("text", ["经营现金流800万元", "经营现金流3500万元"])
def test_verify_rejects_sign_and_account_mismatch(text):
    facts = [{"operatingCashflow": -800, "otherReceivables": 3500}]
    assert dd_verify.check(text, facts)
    assert dd_verify.check("经营现金流-800万元，其他应收款3500万元", facts) == []


def test_verify_binds_explicit_financial_year_and_preserves_rounding():
    facts = [{"years": [
        {"year": 2022, "subjects": {"revenue": 12000}},
        {"year": 2023, "subjects": {"revenue": 28600}},
    ]}]
    assert dd_verify.check("2023年营收1.2亿元", facts)
    assert dd_verify.check("2023年营收2.9亿元", facts) == []
    assert dd_verify.check("2022年营收1.2亿元", facts) == []


@pytest.mark.parametrize("text,values,valid", [
    ("经营现金流由负转正。", [-200, -100], False),
    ("经营现金流由负转正。", [-200, 100], True),
    ("经营现金流由正转负。", [200, -100], True),
    ("经营现金流由正转负。", [-200, 100], False),
    ("经营现金流由负转正。", [100], False),
    ("需核实经营现金流是否由负转正。", [-200, -100], True),
])
def test_verify_cashflow_sign_transition_requires_dated_facts(text, values, valid):
    facts = [{"year": 2020 + i, "operatingCashflow": value}
             for i, value in enumerate(values)]
    assert (not dd_verify.check(text, facts)) == valid


def test_masker_hides_unknown_labeled_entities_without_hiding_known_codes():
    from app.agent.dd_snapshot import Masker

    masker = Masker()
    masker.add_org("已入库测试有限公司", "企业E999")
    masker.add("已知测试人甲", "人员E999-1")
    raw = "核对法人：未入库测试人乙，企业名称：虚构测试甲有限公司；申请金额100万元。"
    masked = masker.mask(raw)
    assert "未入库测试人乙" not in masked
    assert "虚构测试甲有限公司" not in masked
    assert "申请金额100万元" in masked
    assert masker.mask(masked) == masked
    known = masker.mask("法人：已知测试人甲，企业名称：已入库测试有限公司")
    assert "人员E999-1" in known and "企业E999" in known
    assert "已入库测试有限公司" in masker.restore_names(known)
    assert masker.mask("企业名称：已入库测试有限公司 申请100万元贷款。") == "企业名称：企业E999 申请100万元贷款。"
    assert masker.mask("企业编号：E999。请分析现金流是否正常。") == "企业编号：E999。请分析现金流是否正常。"


@pytest.mark.parametrize("text,value,valid", [
    ("营收同比下降22.2%。", -0.2222, True),
    ("营收同比下降22.2%。", 0.2222, False),
    ("营收同比增长22.2%。", -0.2222, False),
    ("净利率降至22.2%。", 0.2222, True),
    ("营收同比下降约22.2%。", -0.2222, True),
    ("营收同比下降了约22.2%。", -0.2222, True),
])
def test_verify_decline_percentage_preserves_direction(text, value, valid):
    assert (not dd_verify.check(text, [{"value": value}])) == valid


def test_unknown_labeled_entities_are_hidden_in_model_and_run(client, router):
    r = router([model_reply(content="请先导入该企业业务资料。")], parallel=False)
    run = _create(client, "核对法人：未入库测试人乙，企业名称：虚构测试甲有限公司。")
    messages = json.dumps(r.calls[0]["messages"], ensure_ascii=False)
    saved = json.dumps(run, ensure_ascii=False)
    events = json.dumps(_events(client, run["runId"]), ensure_ascii=False)
    for raw in ("未入库测试人乙", "虚构测试甲有限公司"):
        assert raw not in messages and raw not in saved and raw not in events


@pytest.mark.parametrize("raw", ["张 三", "欧阳 晓明", "张三 李四"])
def test_masker_hides_entire_labeled_name_with_spaces(raw):
    from app.agent.dd_snapshot import Masker
    masker = Masker()
    masked = masker.mask(f"法人：{raw} 企业名称：虚构测试有限公司；金额100万元。")
    assert not any(part in masked for part in raw.split())
    assert "虚构测试有限公司" not in masked
    assert "金额100万元" in masked


@pytest.mark.parametrize("text", ["2023年经营现金流由负转正。",
                                "经营现金流由负转正而净利润由正转负。"])
def test_verify_checks_each_transition_and_requires_named_year(text):
    facts = [{"year": 2021, "operatingCashflow": -200},
             {"year": 2022, "operatingCashflow": 100}]
    assert dd_verify.check(text, facts)
@pytest.mark.parametrize("text", [
    "2021—2023 年营业收入分别为 10,500.0 万元、11,800.0 万元和 12,500.0 万元",
    "2021-2023年营收分别为10,500万元、11,800万元、12,500万元",
    "营业收入由 2021 年的 10,500 万元增至 2023 年的 12,500 万元",
    "2021 年至 2023 年营业收入从 10,500 万元增长到 12,500 万元",
])
def test_verify_multi_year_wording_binds_subject_not_last_year(text):
    # 公开集回归：子句里有多个年度时不能取最后一个年度去比第一个数字
    facts = [{"years": [{"year": 2021, "subjects": {"revenue": 10500, "netProfit": 550}},
                        {"year": 2022, "subjects": {"revenue": 11800, "netProfit": 620}},
                        {"year": 2023, "subjects": {"revenue": 12500, "netProfit": 680}}]}]
    assert dd_verify.check(text, facts) == [], text
    # 仍按科目绑定：多年度措辞下拿别的科目的值冒充营收要拦
    assert dd_verify.check("2021—2023 年营业收入分别为 550 万元、620 万元", facts)


def test_person_names_stay_masked_in_answers_and_evidence(client):
    from app.services.run_service import masked_snapshot
    from app.models import Evidence
    with SessionLocal() as db:
        masker = build_masker(db)
        basic = db.query(EnterpriseBasic).filter_by(enterprise_id="E001").one()
        raw = basic.legal_person
        code = masker.mask(raw)
        assert raw not in masker.restore_names(code)
        assert masker.unmask(code) == raw  # 本地工具查询仍可用原名
        value = masked_snapshot(Evidence(snapshot={"legalPerson": raw, "actual_controller": raw}))
        assert raw not in json.dumps(value, ensure_ascii=False)


def test_engine_cannot_bypass_image_rejection(client):
    from app.agent import engine
    from app.agent.scenarios import SCENARIOS
    outcome = engine.run(None, scenario=SCENARIOS["enterprise_dd"], question="看图", history=[],
                         run_ctx={}, persist_evidence=lambda _: "unused",
                         attachments=["data:image/png;base64,QUJD"])
    assert outcome.status == "failed" and outcome.error_code == "invalid_attachment"


def test_known_person_question_is_masked_before_persistence(client):
    from app.services.run_service import _public_question
    from app.agent.scenarios import SCENARIOS
    with SessionLocal() as db:
        basic = db.query(EnterpriseBasic).filter_by(enterprise_id="E001").one()
        text = _public_question(db, SCENARIOS["enterprise_dd"], f"核查{basic.legal_person}与{basic.enterprise_name}")
        assert basic.legal_person not in text
        assert basic.enterprise_name in text


def test_name_fields_and_finding_text_are_masked_together():
    from app.compliance.pii import redact_obj
    value = {"actualController": "测试自然人甲", "topShareholder": "测试自然人乙",
             "findings": [{"detail": "实控人测试自然人甲与第一大股东测试自然人乙不一致"}]}
    masked = json.dumps(redact_obj(value), ensure_ascii=False)
    assert "测试自然人甲" not in masked and "测试自然人乙" not in masked
    assert "不一致" in masked


def test_person_display_keeps_surname_and_repairs_legacy_codes():
    """自然人对外只显示姓 + *；旧版误遮罩的 ****01-1 按编号修复成同一脱敏姓名。"""
    from app.agent.dd_snapshot import Masker
    from app.compliance.pii import mask_person_name, redact_obj

    assert mask_person_name("张三") == "张*" and mask_person_name("欧阳修远") == "欧*"
    masker = Masker()
    masker.add_person("张三", "人员E001-1")
    masker.add_person("李四", "人员E001-2")
    masker.add_org("测试示例科技有限公司", "企业E001")
    out = masker.restore_names("企业E001 实控人 人员E001-1 ｜ 人员E001-2（一致）；人员E001-10")
    assert out == "测试示例科技有限公司 实控人 张* ｜ 李*（一致）；人员E001-10"
    assert masker.unmask("人员E001-1") == "张三"          # 本地工具入参仍可还原原名
    legacy = "| 实控人 / 第一大股东 | ****01-1 ｜ ****01-2（一致） |"
    assert masker.repair_legacy_person_codes(legacy) == "| 实控人 / 第一大股东 | 张* ｜ 李*（一致） |"
    assert masker.repair_legacy_person_codes("编号****99-9") == "编号****99-9"   # 未知编号不猜
    assert masker.display_persons("实控人与第一大股东均为张三") == "实控人与第一大股东均为张*"   # 早期全名
    masker.add_person("王五", "人员E101-1")
    assert masker.repair_legacy_person_codes("****01-1", ["E001"]) == "张*"           # 尾号歧义按企业限定
    assert masker.repair_legacy_person_codes("****01-1") == "****01-1"               # 不能唯一定位则不猜
    shown = redact_obj({"actualController": "张三", "detail": "实控人张三与第一大股东一致"})
    assert shown == {"actualController": "张*", "detail": "实控人张*与第一大股东一致"}


def test_unknown_entity_focus_is_masked_in_all_six_role_calls(client, router):
    raw = '云端演练合伙企业，由欧阳演练担任法定代表人。'
    r = router([_dispatch({'applicationId': 'LA001', 'mode': 'full', 'focus': raw})], parallel=False)
    run = _create(client, '请对 LA001 生成完整尽调报告。')
    assert run['status'] in {'succeeded', 'needs_confirmation'}, run
    roles = {call['who'] for call in r.calls if call['who'] != 'controller'}
    assert roles == {'business', 'finance', 'opinion', 'fraud', 'rating', 'report'}
    sent = json.dumps(r.calls, ensure_ascii=False)
    assert '云端演练合伙企业' not in sent and '欧阳演练' not in sent
