"""运行时 Skill：加载校验、拼进角色模型调用、run 留痕、红线（不含题目数据）。"""
import re

import pytest

from app.agent import dd_roles
from app.agent.scenarios import DD_ROLE_SKILLS
from app.agent.skills import SKILL_DIR, SkillError, load_skills, parse_skill
from conftest import HEADERS, model_reply, tool_call

EXPECTED = {
    "business": ("business-verification", "工商核验"),
    "finance": ("financial-analysis", "财报解析"),
    "opinion": ("opinion-scan", "舆情扫描"),
    "fraud": ("fraud-detection", "反欺诈检测"),
    "rating": ("credit-limit", "风险评级与额度测算"),
    "report": ("dd-report", "尽调报告生成"),
}

ROLE_JSON = ('{"analysis": "合成解读", "keyFindings": [], "uncertainties": [], '
             '"needsReview": false}')


def test_every_role_has_one_skill_with_contract():
    assert set(DD_ROLE_SKILLS) == set(EXPECTED)
    for role, (name, title) in EXPECTED.items():
        skill = DD_ROLE_SKILLS[role]
        assert (skill.name, skill.title) == (name, title)
        assert re.fullmatch(r"\d+\.\d+\.\d+", skill.version)
        assert skill.inputs and skill.outputs
        for section in ("## 触发条件", "## 输入契约", "## 禁止"):
            assert section in skill.rules, f"{name} 缺少 {section}"


def test_report_skill_fixes_five_sections_and_layout():
    report = DD_ROLE_SKILLS["report"]
    headings = ["## 企业概况", "## 财务分析", "## 风险提示",
                "## 额度建议", "## 风控条件"]
    positions = [report.rules.index(h) for h in headings]
    assert positions == sorted(positions)
    assert "# 企业智能信贷尽调报告" in report.rules
    # 报告角色校验的五个章节名都在骨架里；免责条款写进骨架，避免事后补成引用块
    assert all(s in report.rules for s in dd_roles.REPORT_SECTIONS)
    assert "测算建议，非授信审批" in report.rules
    # 前端 Markdown 渲染器不支持的语法必须明确禁用
    assert "不嵌套列表" in report.rules and "引用块" in report.rules


def test_skills_contain_no_case_data_or_external_rating():
    for skill in DD_ROLE_SKILLS.values():
        text = skill.prompt()
        # 红线 3：不出现具体申请 / 企业编号；R5：运行时不使用外部汇总评级字段
        assert not re.search(r"\b(?:LA|E)\d{3}\b", text), skill.name
        assert "externalRiskLevel" not in text and "risk_level_summary" not in text
        assert "公开测试集答案" not in text and "expected" not in text


def test_parse_rejects_missing_fields():
    with pytest.raises(SkillError):
        parse_skill("---\nname: x\n---\n正文", "bad.md")
    with pytest.raises(SkillError):
        parse_skill("没有 front matter", "bad.md")


def _write(path, name, roles):
    path.write_text(f"---\nname: {name}\ntitle: t\nversion: 1.0.0\nrole: r\nroles: {roles}\n"
                    "inputs: i\noutputs: o\n---\n## 触发条件\nx\n", encoding="utf-8")


def test_duplicate_role_owner_rejected(tmp_path):
    _write(tmp_path / "a.md", "a", "[finance]")
    _write(tmp_path / "b.md", "b", "[finance]")
    with pytest.raises(SkillError):
        load_skills(str(tmp_path), dd_roles.ROLE_ORDER)


def test_unknown_role_rejected(tmp_path):
    _write(tmp_path / "a.md", "a", "[treasury]")
    with pytest.raises(SkillError):
        load_skills(str(tmp_path), dd_roles.ROLE_ORDER)


def test_real_skill_dir_loads():
    assert set(load_skills(str(SKILL_DIR), dd_roles.ROLE_ORDER)) == set(dd_roles.ROLE_ORDER)


def test_role_model_calls_carry_their_skill_and_run_records_it(client, fake_llm):
    fake_llm["replies"] = [
        model_reply(tool_calls=[tool_call("c1", "run_dd_agents",
                                          '{"applicationId": "LA001", "mode": "followup", '
                                          '"roles": ["finance"]}')]),
        model_reply(content=ROLE_JSON),
        model_reply(content="财务指标见角色结果。"),
    ]
    resp = client.post("/api/agent/runs", json={"question": "LA001 的财务情况"}, headers=HEADERS)
    assert resp.status_code == 200, resp.text

    role_call = fake_llm["calls"][1]["messages"]
    system = role_call[0]["content"]
    assert role_call[0]["role"] == "system"
    assert "Skill：财报解析（financial-analysis@" in system
    assert "## 数值换算" in system
    # 只用到本角色的 Skill，不带其他角色的规则
    assert "Skill：尽调报告生成" not in system

    run = resp.json()
    detail = client.get(f"/api/agent/runs/{run['runId']}", headers=HEADERS).json()
    assert detail["contextSnapshot"]["skillsApplied"] == [DD_ROLE_SKILLS["finance"].ref]
