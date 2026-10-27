"""风险结论命名：按事实与阈值生成标准风险术语，报告逐条引用（不是按题目写答案）。"""
from app.tools import dd_calc


def _names(bundle, finance, rating, credit, fraud, opinion, business) -> list[str]:
    return [item["name"] for item in dd_calc.key_risk_conclusions(
        bundle, finance, rating, credit, fraud, opinion, business)]


def test_high_risk_conclusions_are_explicit():
    bundle = {"risk": {"overdue_count": 1, "overdue_amount": 320},
              "basic": {"legal_person_consumption_limit": "是"}}
    finance = {"years": [{"subjects": {"otherReceivable": 1200, "totalAssets": 88000,
                                      "operatingCashflow": 350, "netProfit": 980}}]}
    rating = {"riskLevel": "高风险", "vetoes": ["法定代表人限高"],
              "dimensions": [{"dimension": "asset_liability_ratio", "value": 0.75},
                             {"dimension": "receivable_to_revenue", "value": 0.223}]}
    fraud = {"rules": [{"ruleId": "F01", "hit": True, "value": 0.008}]}
    opinion = {"healthScore": 0, "labels": ["负面"], "lawsuitCount": 4, "lawsuitAmount": 2270,
               "events": [{"eventContent": "子公司被强制执行 320 万元"}]}
    business = {"guaranteeOverdueCount": 1, "guaranteeOverdueAmount": 4000,
                "guaranteeCircleCount": 2}
    names = _names(bundle, finance, rating, {"applyAmount": 3000, "suggestedCreditAmount": "0"},
                   fraud, opinion, business)
    for expected in ("资产负债率过高", "逾期与逾期担保", "法人限高", "舆情负面",
                     "涉诉及被执行", "关联担保圈", "拒贷建议"):
        assert expected in names, names
    assert "现金流与利润背离" in names


def test_prudent_amount_is_named_for_mid_risk():
    bundle = {"risk": {"overdue_count": 0}, "basic": {}}
    finance = {"years": [{"subjects": {"otherReceivable": 800, "totalAssets": 18500,
                                      "operatingCashflow": -800, "netProfit": 1850}}]}
    rating = {"riskLevel": "中风险", "vetoes": [],
              "dimensions": [{"dimension": "asset_liability_ratio", "value": 0.62},
                             {"dimension": "receivable_to_revenue", "value": 0.445455}]}
    names = _names(bundle, finance, rating, {"applyAmount": 3000, "suggestedCreditAmount": "1500-2000"},
                   {"rules": [{"ruleId": "F01", "hit": True, "value": 0.0364}]},
                   {"healthScore": 65, "labels": []}, {"guaranteeCircleCount": 2})
    assert "额度审慎" in names
    assert "拒贷建议" not in names
    assert "应收账款过高" in names  # 9800/22000=44.5%，越 40% 关注线
    assert "营收现金流背离" in names


def test_clean_company_has_no_false_positive_conclusion():
    bundle = {"risk": {"overdue_count": 0}, "basic": {"legal_person_consumption_limit": "否"}}
    finance = {"years": [{"subjects": {"otherReceivable": 100, "totalAssets": 20000,
                                      "operatingCashflow": 900, "netProfit": 500}}]}
    rating = {"riskLevel": "低风险", "vetoes": [],
              "dimensions": [{"dimension": "asset_liability_ratio", "value": 0.30},
                             {"dimension": "receivable_to_revenue", "value": 0.12}]}
    names = _names(bundle, finance, rating, {"applyAmount": 500, "suggestedCreditAmount": "400-500"},
                   {"rules": []}, {"healthScore": 88, "labels": []}, {"guaranteeCircleCount": 0})
    assert names == []
