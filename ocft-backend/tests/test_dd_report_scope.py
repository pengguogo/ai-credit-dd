"""尽调口径区分（spec dd-report-scope）：企业口径含建议授信额度、不出现申请贷款额度。

真实引擎 / 子图 / 计算 / 落库，只替换模型：带工具声明的是主控（按脚本回放），
不带工具的是角色 Agent（按系统提示词识别角色，报告角色按 scope 写五部分）。
"""
import json
import threading

import pytest

from app import llm
from app.agent import dd_roles, dd_verify
from app.agent.dd_snapshot import load_snapshot
from app.db import SessionLocal
from app.models import Evidence, WorkspaceAsset
from app.tools import dd_calc
from app.tools.dd_config import load_config
from conftest import HEADERS, model_reply, tool_call

_ROLE_MARKERS = {"工商核验 Agent": "business", "财报解析 Agent": "finance",
                 "舆情扫描 Agent": "opinion", "反欺诈 Agent": "fraud",
                 "评级授信 Agent": "rating", "报告 Agent": "report"}


def _role_of(messages) -> str:
    system = messages[0]["content"]
    for marker, role in _ROLE_MARKERS.items():
        if marker in system:
            return role
    raise AssertionError("无法识别角色")


def _loan_report(payload: dict) -> str:
    report = payload["report"]
    return (f"## 企业概况\n{payload['enterpriseId']} 经营正常。\n"
            f"## 财务分析\n见财报解析角色结果。\n"
            f"## 风险提示\n风险评级：{report['riskLevel']}。\n"
            f"## 额度建议\n建议额度 {report['suggestedCreditAmount']}，测算建议，非授信审批。\n"
            f"## 风控条件\n按评级授信角色列出的条件落实。")


def _enterprise_report(payload: dict) -> str:
    assert payload["scope"] == "enterprise"
    assert payload["applicationId"] in (None, "")
    report = payload["report"]
    suggested = report.get("suggestedCreditAmount") or "未测算"
    return (f"## 企业概况\n{payload['enterpriseId']} 经营正常。\n"
            f"## 财务分析\n见财报解析角色结果。\n"
            f"## 风险提示\n风险评级：{report['riskLevel']}。\n"
            f"## 额度建议\n建议授信额度 {suggested}，测算建议，非授信审批。\n"
            f"## 风控条件\n按评级授信角色列出的核查事项落实。")


class Router:
    def __init__(self, controller, *, enterprise_report=False, report_writer=None):
        self.controller = list(controller)
        self.calls: list[dict] = []
        self.lock = threading.Lock()
        self.enterprise_report = enterprise_report
        self.report_writer = report_writer
        self.report_attempts = 0

    def __call__(self, messages, tools, temperature=0.2, timeout=None, max_tokens=None,
                 thinking=None):
        if tools:
            with self.lock:
                self.calls.append({"who": "controller", "messages": list(messages)})
            if not self.controller:
                raise AssertionError("主控脚本已用完")
            reply = self.controller.pop(0)
            return reply(messages) if callable(reply) else reply
        role = _role_of(messages)
        with self.lock:
            self.calls.append({"who": role, "messages": list(messages)})
        if role == "report":
            payload = json.loads(messages[1]["content"])
            with self.lock:
                self.report_attempts += 1
                attempt = self.report_attempts
            if self.report_writer is not None:
                return model_reply(content=self.report_writer(payload, attempt), tokens=20)
            writer = _enterprise_report if self.enterprise_report else _loan_report
            return model_reply(content=writer(payload), tokens=20)
        return model_reply(content=json.dumps({
            "analysis": f"{role} 角色分析完成", "keyFindings": [f"{role} 要点"],
            "uncertainties": [], "needsReview": False}, ensure_ascii=False), tokens=10)


@pytest.fixture
def router(monkeypatch):
    def install(controller, **kwargs):
        instance = Router(controller, **kwargs)
        monkeypatch.setattr(llm, "complete_with_tools", instance)
        return instance
    return install


def _dispatch(args: dict, call_id: str = "d1"):
    return model_reply(tool_calls=[tool_call(call_id, "run_dd_agents",
                                             json.dumps(args, ensure_ascii=False))])


def _create(client, question):
    resp = client.post("/api/agent/runs", json={"question": question}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---- 企业口径完整链路 ----

def test_enterprise_scope_report_has_suggested_credit_without_apply_amount(client, router):
    router([_dispatch({"enterpriseId": "E001", "mode": "full", "scope": "enterprise"})],
           enterprise_report=True)
    run = _create(client, "企业 E001：请对该企业进行尽调并生成尽调报告")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    answer = run["answer"]
    assert "## 额度建议" in answer and "## 风控条件" in answer
    assert "建议授信额度" in answer or "建议额度" in answer
    # 企业口径不得出现「申请贷款额度」字段式表述（可有建议授信额度）
    assert "申请贷款额度" not in answer

    detail = client.get(f"/api/agent/runs/{run['runId']}", headers=HEADERS).json()
    trace = detail["toolTraces"][0]
    assert trace["toolName"] == "run_dd_agents"
    assert trace["status"] == "ok"
    plan = next(e["data"]["plan"] for e in _events(client, run["runId"])
                if e["event"] == "plan_ready")
    assert plan["scope"] == "enterprise"
    assert plan["target"]["applicationId"] is None

    with SessionLocal() as db:
        evidence = db.query(Evidence).filter(Evidence.run_id == run["runId"]).all()
        calcs = {row.source_ref.get("calc") for row in evidence}
        assert "build_dd_report" in calcs and "calc_credit_limit" in calcs
        report = next(row for row in evidence if row.source_ref.get("calc") == "build_dd_report")
        credit = (report.snapshot.get("sections") or {}).get("creditSuggestion") or {}
        assert report.snapshot["scope"] == "enterprise"
        assert report.snapshot["applicationId"] is None
        assert report.snapshot.get("suggestedCreditAmount")
        assert "applyAmount" not in credit

        asset = db.query(WorkspaceAsset).filter(WorkspaceAsset.run_id == run["runId"]).one()
        assert asset.application_id is None and asset.enterprise_id == "E001"


def test_enterprise_asset_is_not_attached_to_located_loan(client, router):
    """主控定位阶段 find_enterprise 会带回该企业唯一申请；企业口径报告不能因此挂到那笔贷款上。"""
    router([model_reply(tool_calls=[tool_call("f", "find_enterprise", '{"enterpriseId": "E001"}')]),
            _dispatch({"enterpriseId": "E001", "mode": "full", "scope": "enterprise"})],
           enterprise_report=True)
    run = _create(client, "企业 E001：请对该企业进行尽调并生成尽调报告")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    with SessionLocal() as db:
        asset = db.query(WorkspaceAsset).filter(WorkspaceAsset.run_id == run["runId"]).one()
    assert asset.application_id is None
    assert asset.enterprise_id == "E001"
    assert asset.title == "E001 企业主体尽调报告"


def test_enterprise_report_with_loan_wording_is_rewritten(client, router):
    """企业口径正文如果写出申请额度或放款表述，按事实校验拦下并重写。"""
    def writer(payload, attempt):
        text = _enterprise_report(payload)
        if attempt == 1:
            return text.replace("按评级授信角色列出的核查事项落实。",
                                "申请贷款额度 3,000 万元，放款前落实担保。")
        return text
    router([_dispatch({"enterpriseId": "E001", "mode": "full", "scope": "enterprise"})],
           report_writer=writer)
    run = _create(client, "企业 E001：请对该企业进行尽调并生成尽调报告")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    assert "申请贷款额度" not in run["answer"] and "放款前" not in run["answer"]
    statuses = [e["data"]["status"] for e in _events(client, run["runId"])
                if e["event"] == "verify_finished"]
    assert statuses[0] == "retry" and statuses[-1] == "ok"


def test_scope_check_blocks_loan_wording_in_enterprise_text():
    text = "本报告为企业主体尽调。申请贷款额度 3,000 万元，投放前落实担保，贷款期限 12 个月。"
    issues = dd_verify.check_scope(text, "enterprise")
    snippets = {item["snippet"] for item in issues}
    assert {"申请贷款额度", "投放前", "贷款期限"} <= snippets
    # 建议授信额度允许出现；贷款口径不适用该检查
    assert dd_verify.check_scope("建议授信额度 800-1000 万元，测算建议。", "enterprise") == []
    assert dd_verify.check_scope(text, "loan") == []


# ---- 贷款口径保持原样 ----

def test_loan_scope_keeps_five_sections_and_credit_evidence(client, router):
    router([_dispatch({"applicationId": "LA001", "mode": "full"})])
    run = _create(client, "对申请 LA001 做完整尽调")
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    assert "## 额度建议" in run["answer"]
    plan = next(e["data"]["plan"] for e in _events(client, run["runId"])
                if e["event"] == "plan_ready")
    assert plan["scope"] == "loan" and plan["target"]["applicationId"] == "LA001"
    with SessionLocal() as db:
        calcs = {row.source_ref.get("calc") for row in
                 db.query(Evidence).filter(Evidence.run_id == run["runId"]).all()}
    assert "calc_credit_limit" in calcs and "build_dd_report" in calcs


def test_invalid_scope_is_rejected_without_roles(client, router):
    router([_dispatch({"enterpriseId": "E001", "mode": "full", "scope": "group"}),
            model_reply(content="口径参数不合法，请指定企业尽调或本笔贷款尽调。")])
    run = _create(client, "企业 E001 尽调")
    assert run["status"] == "insufficient_evidence", run
    assert run["errorCode"] == "evidence_missing"
    events = _events(client, run["runId"])
    assert not [e for e in events if e["event"] == "role_started"]


# ---- 纯函数：企业口径报告结构 ----

def test_build_report_enterprise_has_suggested_credit_without_apply_amount():
    application = {"application_id": "", "enterprise_id": "E001", "apply_date": None}
    bundle = {"basic": {"enterprise_id": "E001", "industry": "制造业",
                        "business_status": "存续", "establish_date": "2015-01-01"},
              "risk": {"existing_loan_balance": 100, "external_guarantee_amount": 0,
                       "overdue_count": 0}}
    rating = {"riskLevel": "中风险", "score": 5, "vetoes": [], "needsManualReview": False}
    credit = {"suggestedCreditAmount": "800-1000", "unit": "万元", "applyAmount": 1200.0,
              "termMonths": 12, "rateDirection": "上浮", "steps": [], "conditions": []}
    report = dd_calc.build_report(application, bundle, {"unit": "万元", "years": []}, {},
                                  {}, {"hitRuleIds": []}, rating, credit,
                                  scope="enterprise", anomalies=[])
    assert report["scope"] == "enterprise"
    assert report["applicationId"] is None
    assert report["suggestedCreditAmount"] == "800-1000"
    assert set(report["sections"]) == {
        "overview", "financialAnalysis", "riskAlerts", "creditSuggestion", "riskConditions"}
    credit_section = report["sections"]["creditSuggestion"]
    assert credit_section["suggestedCreditAmount"] == "800-1000"
    assert "applyAmount" not in credit_section
    assert credit_section.get("termMonths") is None
    assert report["dueDiligenceConclusion"].startswith("审慎合作：")
    assert "建议授信额度 800-1000" in report["dueDiligenceConclusion"]
    assert "依据：" in report["dueDiligenceConclusion"]
    assert "applyAmount" not in json.dumps(credit_section, ensure_ascii=False)
    assert any("存量贷款" in item for item in report["sections"]["riskConditions"]["conditions"])


def test_build_report_loan_default_still_has_credit_section():
    application = {"application_id": "LA001", "enterprise_id": "E001", "apply_date": "2025-01-01"}
    bundle = {"basic": {"enterprise_id": "E001"}, "risk": {}}
    rating = {"riskLevel": "低风险", "score": 1, "vetoes": []}
    credit = {"suggestedCreditAmount": "800-1000", "unit": "万元", "applyAmount": 1200.0,
              "termMonths": 12, "rateDirection": "下浮", "guaranteeType": "抵押",
              "conditions": ["落实抵押"], "steps": []}
    report = dd_calc.build_report(application, bundle, {"unit": "万元", "years": []}, {},
                                  {}, {}, rating, credit)
    assert report["scope"] == "loan"
    assert report["sections"]["creditSuggestion"]["applyAmount"] == 1200.0
    assert report["dueDiligenceConclusion"].startswith("建议准入：")
    assert "建议额度 800-1000 万元" in report["dueDiligenceConclusion"]
    assert "期限 12 个月" in report["dueDiligenceConclusion"]
    assert "依据：" in report["dueDiligenceConclusion"]


def test_loan_conclusion_states_decision_before_reasons():
    application = {"application_id": "LA001", "enterprise_id": "E001", "apply_date": "2025-01-01"}
    bundle = {"basic": {"enterprise_id": "E001"}, "risk": {}}
    high = {"riskLevel": "高风险", "score": 18, "vetoes": ["法人限高"]}
    credit = {"suggestedCreditAmount": "0", "unit": "万元", "termMonths": 12}
    text = dd_calc.build_report(application, bundle, {"unit": "万元", "years": []}, {},
                                {}, {"hitRuleIds": ["F01"]}, high, credit)["dueDiligenceConclusion"]
    assert text.startswith("暂不准入：")
    assert text.index("依据：") > text.index("暂不准入")
    assert "一票否决：法人限高" in text and "反欺诈命中：F01" in text

    medium = {"riskLevel": "中风险", "score": 9, "vetoes": []}
    no_credit = dd_calc.build_report(application, bundle, {"unit": "万元", "years": []}, {},
                                     {}, {}, medium, {})["dueDiligenceConclusion"]
    assert no_credit.startswith("审慎准入：额度无法测算")
    assert "依据：" in no_credit


def test_enterprise_snapshot_ignores_loan_row(client):
    with SessionLocal() as db:
        snapshot = load_snapshot(db, application_id="LA001", scope="enterprise")
    assert snapshot.scope == "enterprise"
    assert snapshot.application_id == ""
    assert snapshot.loan["application_id"] == ""
    with SessionLocal() as db:
        loan_snapshot = load_snapshot(db, application_id="LA001")
    assert loan_snapshot.scope == "loan" and loan_snapshot.application_id == "LA001"


# ---- 配置：口径判断写进提示词与 Skill ----

def test_scope_instructions_exist_in_prompts_and_skill():
    config = dd_roles.load_agents_config()
    controller = config.controller_prompt
    assert "scope=enterprise" in controller and "scope=loan" in controller
    assert "申请贷款额度" in controller
    report_prompt = config.roles["report"].prompt
    assert "scope=enterprise" in report_prompt and "建议授信额度" in report_prompt
    # 贷款口径的尽调结论：先结论、后依据
    assert "先明确结论再给理由" in report_prompt
    assert "scope=enterprise" in config.roles["rating"].prompt
    skill = dd_roles.role_skills()["report"]
    assert "企业口径骨架（scope=enterprise" in skill.rules
    assert "申请贷款额度" in skill.rules
    assert "建议授信额度" in skill.rules
    assert "先给结论" in skill.rules and "依据：" in skill.rules


def _events(client, run_id):
    text = client.get(f"/api/agent/runs/{run_id}/events", headers=HEADERS).text
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            out.append({"event": lines["event"], "data": json.loads(lines["data"])})
    return out
