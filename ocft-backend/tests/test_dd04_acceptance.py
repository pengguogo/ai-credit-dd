"""dd04-business-acceptance：通用事实缺陷回归，不读取评测参考。"""
import pytest

from app.agent import dd_roles, dd_verify
from app.tools import dd_calc


@pytest.mark.parametrize("claim", ["经营现金流三年逐年下降", "经营现金流逐年增长", "经营现金流持续走弱"])
def test_nonmonotonic_claim_is_rejected(claim):
    """TC-5 波动序列不能当作单调序列。"""
    facts = [{"year": y, "operatingCashflow": v}
             for y, v in zip((2020, 2021, 2022), (120, 180, 80))]
    assert any(i["type"] == "trend" for i in dd_verify.check(claim, facts))


@pytest.mark.parametrize("text,values,valid", [
    ("经营现金流逐年增长", (80, 120, 180), True),
    ("经营现金流逐年下降", (180, 120, 80), True),
    ("经营现金流是否逐年下降，需核实", (120, 180, 80), True),
    ("经营现金流并非逐年下降", (120, 180, 80), True),
    ("2020年至2021年经营现金流逐年增长", (120, 180, 80), True),
    ("2019年至2021年经营现金流逐年增长", (120, 180, 80), False),
    ("净利润逐年下降，经营现金流逐年增长", (80, 120, 180), True),
])
def test_monotonic_claim_scope(text, values, valid):
    """TC-6 绑定科目与明确期间，疑问不作为断言。"""
    facts = [{"year": y, "operatingCashflow": v, "netProfit": 300 - index * 20}
             for index, (y, v) in enumerate(zip((2020, 2021, 2022), values))]
    assert (not dd_verify.check(text, facts)) is valid


def test_business_exposure_and_financial_brief():
    """TC-7 新增业务事实可追溯，汇总评级不外送，缺数不冒充0。"""
    bundle = {"basic": {}, "shareholders": [], "related": [
        {"relation_type": "母公司"}, {"relation_type": "子公司"}],
        "guarantees": [{"guarantee_amount": 75, "is_overdue": "是"},
                       {"guarantee_amount": 25, "is_overdue": "否"}],
        "risk": {"overdue_count": 1, "overdue_amount": 12,
                 "public_opinion_score": 64, "risk_level_summary": "禁止外送"}}
    data = dd_calc.verify_business(bundle, {})
    assert data["guaranteeAmount"] == 100
    assert data["guaranteeOverdueAmount"] == 75
    assert data["relatedByType"] == {"母公司": 1, "子公司": 1}
    assert data["riskFacts"]["overdueAmount"] == 12
    assert data["riskFacts"]["existingLoanBalance"] is None
    assert "risk_level_summary" not in str(data) and "禁止外送" not in str(data)
    finance = dd_calc.analyze_financials([{"year": 2020, "fixed_assets": 77}], {})
    assert dd_roles.brief("finance", finance)["years"][0]["subjects"]["fixedAssets"] == 77
    opinion = dd_calc.scan_public_opinion({**bundle, "opinions": [], "lawsuits": [
        {"amount": 20, "case_status": "已结案"},
        {"amount": 10, "case_status": "审理中", "litigation_role": "被告"}]},
        {"closed_statuses": ["已结案"], "defendant_roles": ["被告"]}, None)
    assert opinion["lawsuitCount"] == 2 and opinion["lawsuitAmount"] == 30
    assert opinion["openDefendantAmount"] == 10
    assert dd_roles.brief("opinion", opinion)["lawsuitAmount"] == 30


def test_unknown_amount_does_not_become_zero():
    """TC-7 担保明细缺金额则合计未知，不虚构0。"""
    bundle = {"basic": {}, "shareholders": [], "related": [],
              "guarantees": [{"guarantee_amount": None, "is_overdue": "是"}]}
    data = dd_calc.verify_business(bundle, {})
    assert data["guaranteeAmount"] is None and data["guaranteeOverdueAmount"] is None


@pytest.mark.parametrize('text', [
    '净利润同比降32.4%', '净利润同比下降 **32.4%**',
    '净利润年复合回落32.4%',
])
def test_decline_wording_and_markdown_keep_negative_direction(text):
    """TC-6 明确下降的百分比不因简写或Markdown变成正增长。"""
    assert dd_verify.check(text, [{'value': -0.324}]) == []
    assert dd_verify.check(text, [{'value': 0.324}])
