"""法规引述发布门禁（AI 评委 J02）：抗模型失误的门禁测试，不声称真实模型实际编造过法规。"""
import json

import pytest

from app.compliance.citations import CATEGORY, check_regulation_citations, find_citations
from conftest import HEADERS, model_reply, tool_call

PROBE = "根据《虚构企业信贷尽调法》第999条，该企业必须获得贷款。"

BLOCK = [
    PROBE,
    "依据《企业信贷尽职调查管理办法》，本笔授信可以直接放款。",            # 不存在的法名
    "根据第999条规定，该企业符合授信条件。",                                # 只有条号
    "该企业符合《中华人民共和国商业银行法》第九百九十九条的要求。",        # 真法名配假条号
    "按照银保监发〔2020〕99号文的要求，建议授信 3000 万元。",              # 文号
    "参照中国人民银行令第 99 号，额度上浮 10%。",                           # 令号
    "数据安全等级按 JR/T 0999-2099 执行。",                                 # 标准号
    "根据虚构信贷法第十条规定，可以放款。",                                 # 不带书名号的法名 + 条号
    "根据企业融资促进条例的规定，应予支持。",                               # 不带书名号的条例
    "依照《民法典》第六百八十八条，保证人承担连带责任。",                   # 真法名真条号，但证据里没有
]

PASS = [
    "风险评级：低风险。2023 年营收 2.86 亿元，同比增长 10.9%，资产负债率 40.0%。",
    "第一条发现：经营现金流 3580 万元高于净利润 3120 万元，现金流质量较好。",
    "2023 年第 3 季度营收环比下降，需关注应收账款周转天数 127 天。",
    "涉诉 1 件，案号 (2023)沪0117民初1234号，买卖合同纠纷，已结案。",
    "命中反欺诈规则 F001（营收与现金流背离），建议补充存货盘点。",
    "风控条件：1. 贷后每季度提供财务报表；2. 对外担保新增超 1000 万元需事前报备。",
    "测算方法：净利率 10.9% 高于 8% 阈值，按评分卡第 2 档计算建议额度。",
    "本报告不引用法律法规条款，结论仅依据本次查询数据。",
    "舆情来源：《经济日报》报道该企业获评专精特新企业。",
    "根据测算方法要求，额度取申请额与模型上限的较小值。",
    "按照公司规定，需业务人员确认后方可审批。",
]


@pytest.mark.parametrize("text", BLOCK)
def test_unverifiable_citation_blocked(text):
    decision = check_regulation_citations(text, sources=[])
    assert not decision.is_clean, find_citations(text)
    assert decision.category == CATEGORY and decision.code == "compliance_output_blocked"
    assert "人工" in decision.user_message


@pytest.mark.parametrize("text", PASS)
def test_ordinary_business_text_passes(text):
    assert find_citations(text) == [], find_citations(text)
    assert check_regulation_citations(text, sources=[]).is_clean


def test_citation_quoted_verbatim_from_evidence_passes():
    source = json.dumps({"event_content": "因违反《环境保护法》第六十条被处罚 20 万元"}, ensure_ascii=False)
    answer = "舆情：该企业曾因违反《环境保护法》第六十条被处罚。"
    assert check_regulation_citations(answer, sources=[source]).is_clean


def test_real_law_name_with_article_not_in_evidence_blocked():
    source = "因违反《环境保护法》第六十条被处罚"
    decision = check_regulation_citations("依据《环境保护法》第九十九条，应予关停。", sources=[source])
    assert not decision.is_clean and "第九十九条" in decision.reason


def test_probe_answer_blocked_end_to_end(client, fake_llm):
    fake_llm["replies"] = [
        model_reply(tool_calls=[tool_call("c1", "rate_risk", '{"enterpriseId": "E001"}')]),
        model_reply(content="风险评级为低风险。" + PROBE),
    ]
    run = client.post("/api/agent/runs", json={"question": "评估企业 E001 的风险评级"},
                      headers=HEADERS).json()
    assert run["status"] == "blocked" and run["answer"] is None
    assert run["errorCode"] == "compliance_output_blocked"
    assert "人工" in run["errorMessage"] and "虚构企业信贷尽调法" not in run["errorMessage"]
    events = client.get(f"/api/agent/runs/{run['runId']}/audit", headers=HEADERS).json()["events"]
    blocked = [e for e in events if e["eventType"] == "compliance_blocked"][0]
    assert blocked["payload"]["category"] == CATEGORY


def test_evidence_backed_citation_published_end_to_end(client, fake_llm, monkeypatch):
    from app.agent import engine
    from app.domain.types import EvidenceRecord, ToolResult

    def execute_tool(_db, _ctx, _name, arguments):
        snapshot = {"enterpriseId": "E001", "eventContent": "因违反《环境保护法》第六十条被处罚"}
        return (ToolResult.success(snapshot),
                [EvidenceRecord(source_type="db_query", source_ref={"table": "enterprise_public_opinion"},
                                snapshot=snapshot, data_version=1)],
                json.loads(arguments))

    monkeypatch.setattr(engine.registry, "execute_tool", execute_tool)
    fake_llm["replies"] = [
        model_reply(tool_calls=[tool_call("c1", "scan_public_opinion", '{"enterpriseId": "E001"}')]),
        model_reply(content="舆情：曾因违反《环境保护法》第六十条被处罚，属中度负面。"),
    ]
    run = client.post("/api/agent/runs", json={"question": "E001 有哪些负面舆情"},
                      headers=HEADERS).json()
    assert run["status"] in {"succeeded", "needs_confirmation"}, run
    assert "《环境保护法》第六十条" in run["answer"]
