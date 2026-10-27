"""金额专项：仅使用合成事实，不读取公开参考或评测标签。"""
from copy import deepcopy
import json

import pytest

from app.domain.errors import ToolError
from app.tools import dd_calc, registry
from app.tools.dd_config import load_config


def _inputs():
    application = {"application_id": "synthetic", "enterprise_id": "borrower",
                   "apply_amount": 1000, "loan_term_months": 12,
                   "apply_date": "2024-04-01", "guarantee_type": "抵押"}
    bundle = {"risk": {"existing_loan_balance": 5000,
                       "external_guarantee_amount": 3000, "overdue_count": 0}}
    finance = {"unit": "万元", "years": [{"year": 2023, "subjects": {
        "revenue": "10000", "ownersEquity": "5000", "operatingCashflow": "2000"}}]}
    rating = {"riskLevel": "低风险", "vetoes": []}
    cfg = load_config("credit_model.yaml")
    cfg.update(policy_version="incremental-v1", credit_scope="new_application_financing",
               cashflow={"non_positive_rating": "中风险"})
    return application, bundle, finance, rating, cfg


def _calculate(change=None):
    args = _inputs()
    if change:
        change(*args)
    return dd_calc.calc_credit_limit(*args)


def _range(credit):
    values = [int(x) for x in credit["suggestedCreditAmount"].split("-")]
    return values[0], values[-1]


def test_exposures_are_conditions_not_full_amount_deductions():
    """TC-1 存量与担保高于申请，不重复全额扣减。"""
    credit = _calculate()
    assert _range(credit) == (800, 1000)
    assert credit["exposures"] == {"existingLoanBalance": 5000,
                                   "externalGuaranteeAmount": 3000}
    assert credit["policyVersion"] == "incremental-v1"
    assert credit["creditScope"] == "new_application_financing"
    assert any("存量" in x for x in credit["conditions"])
    assert any("担保" in x for x in credit["conditions"])


def test_rating_adjusts_capacity_before_application_cap():
    """TC-2 财务容量先折减，不能把已封顶申请额再乘评级系数。"""
    def change(application, bundle, finance, rating, cfg):
        finance["years"][0]["subjects"].update(revenue=50000, ownersEquity=15000)
        rating["riskLevel"] = "中风险"
    assert _range(_calculate(change)) == (800, 1000)


@pytest.mark.parametrize("field,value", [
    ("revenue", 0), ("revenue", -10), ("ownersEquity", 0), ("ownersEquity", -10)])
def test_zero_financial_capacity_is_not_omitted(field, value):
    """TC-3 零/负财务容量不得被正数筛选跳过。"""
    args = _inputs()
    args[2]["years"][0]["subjects"][field] = value
    assert _range(dd_calc.calc_credit_limit(*args)) == (0, 0)


@pytest.mark.parametrize("cashflow", [0, -100])
def test_non_positive_cashflow_alone_is_a_condition_not_rejection(cashflow):
    """TC-4（incremental-v2）非正现金流只是一项重大异常：单项不折减、不归零，写入核查条件。"""
    args = _inputs()
    args[2]["years"][0]["subjects"]["operatingCashflow"] = cashflow
    credit = dd_calc.calc_credit_limit(*args)
    assert _range(credit) == (800, 1000)
    assert [a["code"] for a in credit["anomalies"]] == ["A1"]
    assert any("现金流" in x for x in credit["conditions"])
    step = next(x for x in credit["steps"] if x["step"] == "重大财务异常折减")
    assert step["value"] == ["A1"]


def test_multiple_major_anomalies_discount_prudently_without_veto():
    """TC-4b 命中 ≥2 项重大财务异常：不否决，区间按 [0.6, 0.8] 审慎压降，并写核查条件。"""
    args = _inputs()
    subjects = args[2]["years"][0]["subjects"]
    subjects.update(operatingCashflow=-100, netProfit=500, accountsReceivable=4500, totalAssets=20000)
    credit = dd_calc.calc_credit_limit(*args)
    assert [a["code"] for a in credit["anomalies"]] == ["A1", "A2"]
    assert _range(credit) == (600, 800)
    assert any("审慎测算" in x for x in credit["conditions"])


def test_large_amounts_round_to_coarser_step():
    """TC-7b 硬上限 ≥ large_amount.threshold 时按大步长取整，不突破硬上限。"""
    args = _inputs()
    args[0]["apply_amount"] = 2500
    args[2]["years"][0]["subjects"].update(revenue=50000, ownersEquity=15000)
    assert _range(dd_calc.calc_credit_limit(*args)) == (2000, 2500)   # 2125 → 2000
    args[0]["apply_amount"] = 1500
    assert _range(dd_calc.calc_credit_limit(*args)) == (1200, 1500)   # 小额仍按 100


@pytest.mark.parametrize("level,vetoes", [("高风险", []), ("低风险", ["合成否决"])])
def test_veto_cannot_be_overridden_by_cashflow_fallback(level, vetoes):
    """TC-5 高风险或任何否决仍输出零。"""
    args = _inputs()
    args[3].update(riskLevel=level, vetoes=vetoes)
    assert _range(dd_calc.calc_credit_limit(*args)) == (0, 0)


@pytest.mark.parametrize("field,value", [
    ("revenue", None), ("revenue", ""), ("revenue", "NaN"),
    ("ownersEquity", "Infinity"), ("operatingCashflow", None),
    ("operatingCashflow", "-Infinity"), ("revenue", True)])
def test_invalid_financial_subjects_fail_honestly(field, value):
    """TC-6 非有限/缺失字段不能当零或用申请额代替容量。"""
    args = _inputs()
    args[2]["years"][0]["subjects"][field] = value
    with pytest.raises(ToolError):
        dd_calc.calc_credit_limit(*args)


@pytest.mark.parametrize("field,value", [
    ("apply_amount", 0), ("apply_amount", -1), ("apply_amount", "NaN"),
    ("loan_term_months", 0), ("loan_term_months", 1.5),
    ("apply_date", ""), ("apply_date", "2024-02-31")])
def test_invalid_application_fails(field, value):
    """TC-6 不静默替换非法期限或日期。"""
    args = _inputs()
    args[0][field] = value
    with pytest.raises(ToolError):
        dd_calc.calc_credit_limit(*args)


@pytest.mark.parametrize("field,value", [
    ("round_step", 0), ("round_step", -10), ("band", -0.1), ("band", 1.1)])
def test_invalid_policy_fails(field, value):
    """TC-6 非法配置不能静默回退默认参数。"""
    args = _inputs()
    args[4][field] = value
    with pytest.raises(ToolError):
        dd_calc.calc_credit_limit(*args)


def test_absent_financials_and_unit_conflicts_fail():
    """TC-6 无财报或单位冲突不生成金额建议。"""
    for finance in ({"years": [], "unit": "万元"},
                    {"years": _inputs()[2]["years"], "unit": "元"}):
        args = list(_inputs())
        args[2] = finance
        with pytest.raises(ToolError):
            dd_calc.calc_credit_limit(*args)


def test_decimal_band_and_hard_ceiling():
    """TC-7 十进制区间边界不损失一个步长，不上浮突破容量。"""
    args = _inputs()
    args[4]["large_amount"] = {}   # 只验证十进制精度，关闭大额分档取整
    args[0]["apply_amount"] = 2000
    args[2]["years"][0]["subjects"].update(revenue=50000, ownersEquity=15000)
    args[4]["band"] = "0.8"
    assert _range(dd_calc.calc_credit_limit(*args)) == (400, 2000)
    args[2]["years"][0]["subjects"]["revenue"] = "24583.333333333333333333333"
    args[0]["apply_amount"] = 5000
    args[4]["band"] = 0
    assert _range(dd_calc.calc_credit_limit(*args)) == (2900, 2900)


def test_less_than_round_step_is_not_rounded_up():
    """TC-7 容量不足一个步长不能上抬为可投放额度。"""
    args = _inputs()
    args[0]["apply_amount"] = "99.99"
    assert _range(dd_calc.calc_credit_limit(*args)) == (0, 0)


def test_financial_analysis_filters_future_years_without_mutation():
    """TC-8 申请年度及以后全年报排除，原始数据不被改写。"""
    rows = [{"year": year, "revenue": year} for year in (2025, 2023, 2024, 2022)]
    original = deepcopy(rows)
    data = dd_calc.analyze_financials(rows, load_config("metrics.yaml"), "2024-04-01")
    assert [x["year"] for x in data["years"]] == [2022, 2023]
    assert rows == original
    assert data["asOf"] == "2024-04-01"


def test_credit_independently_selects_latest_eligible_financial_year():
    """TC-8 额度函数自身也不得盲取末行或未来年度。"""
    args = _inputs()
    latest = args[2]["years"][0]
    future = {"year": 2024, "subjects": {"revenue": 0, "ownersEquity": 0,
                                        "operatingCashflow": -1}}
    args[2]["years"] = [future, latest]
    credit = dd_calc.calc_credit_limit(*args)
    assert _range(credit) == (800, 1000)
    assert credit["financialYear"] == 2023
    args[2]["years"] = [future]
    with pytest.raises(ToolError):
        dd_calc.calc_credit_limit(*args)


def test_identity_independence_and_capacity_monotonicity():
    """TC-9 编号不参与计算；申请/敞口/风险变化满足硬边界。"""
    args = _inputs()
    original = deepcopy(args)
    credit = dd_calc.calc_credit_limit(*args)
    assert args == original
    args[0].update(application_id="unseen", enterprise_id="new-borrower")
    args[1]["risk"].update(existing_loan_balance=900000,
                           external_guarantee_amount=900000)
    assert _range(dd_calc.calc_credit_limit(*args)) == _range(credit)
    args[0]["apply_amount"] = 100000
    assert _range(dd_calc.calc_credit_limit(*args))[1] == 1200
    args[3]["riskLevel"] = "中风险"
    assert _range(dd_calc.calc_credit_limit(*args))[1] <= 1200


def test_report_and_registered_tools_share_as_of_and_credit(client):
    """TC-10 临时库注入合成未来财报；工具和报告使用相同事实时点。"""
    from app.db import SessionLocal
    from app.models import EnterpriseFinance
    db = SessionLocal()
    try:
        db.add(EnterpriseFinance(
            enterprise_id="E001", year=2024, revenue=1, net_profit=0,
            total_assets=1, total_liabilities=0, operating_cashflow=-1,
            accounts_receivable=0, inventory=0, fixed_assets=0,
            short_term_loan=0, long_term_loan=0, accounts_payable=0,
            other_receivable=0, prepayment=0, owners_equity=1, rd_expense=0,
            sales_expense=0, admin_expense=0, finance_expense=0,
            audit_opinion="标准无保留意见"))
        db.flush()
        ctx = {"run_id": "synthetic", "data_version": 1, "sql_tables": ()}
        outputs = {}
        for name in ("analyze_financials", "calc_credit_limit", "build_dd_report"):
            result, records, _ = registry.execute_tool(
                db, ctx, name, json.dumps({"applicationId": "LA001"}))
            assert result.is_success and records
            outputs[name] = result.data
        credit = outputs["calc_credit_limit"]
        report = outputs["build_dd_report"]
        assert outputs["analyze_financials"]["latestYear"] == 2023
        assert credit["financialYear"] == 2023
        assert report["suggestedCreditAmount"] == credit["suggestedCreditAmount"]
        assert report["sections"]["creditSuggestion"]["policyVersion"] == credit["policyVersion"]
        assert report["sections"]["financialAnalysis"]["years"][-1]["year"] == 2023
        assert "expected" not in json.dumps(outputs)
    finally:
        db.rollback()
        db.close()


def test_offline_amount_scoring_keeps_failures_and_semantic_cases():
    """TC-11 离线评分不把重叠当精确，不给失败/语义结果补分。"""
    from eval.dd04_credit import compare_amounts
    reference = [
        {"application_id": "a", "risk_level": "低风险", "suggested_credit_amount": "100-200"},
        {"application_id": "b", "risk_level": "低风险", "suggested_credit_amount": "100-200"},
        {"application_id": "c", "risk_level": "高风险", "suggested_credit_amount": "拒贷/极小额度"},
        {"application_id": "d", "risk_level": "低风险", "suggested_credit_amount": "100-200"}]
    actual = [
        {"applicationId": "a", "status": "calculated", "systemRisk": "低风险", "systemCredit": "100-200"},
        {"applicationId": "b", "status": "calculated", "systemRisk": "低风险", "systemCredit": "150-200"},
        {"applicationId": "c", "status": "calculated", "systemRisk": "高风险", "systemCredit": "0"},
        {"applicationId": "d", "status": "failed", "systemRisk": "低风险", "systemCredit": "100-200"}]
    rows, summary = compare_amounts(actual, reference)
    assert summary["total"] == 4
    assert summary["numericReferenceCount"] == 3
    assert summary["referenceNonNumericCount"] == 1
    assert summary["eligibleExactCount"] == 1
    assert summary["eligibleOverlapCount"] == 2
    assert summary["eligibleWithinCount"] == 2
    assert summary["failedCount"] == 1
    assert rows[3]["candidateExact"] is True
    assert rows[3]["eligibleExact"] is False


@pytest.mark.parametrize("text,bounds", [
    ("建议额度 **1,234–1,567 万元**", ("1234", "1567")),
    ("建议授信区间 1234—1567万元", ("1234", "1567")),
    ("建议 **1234—1567万元**", ("1234", "1567")),
    ("建议授信额度 1.2亿元", ("12000", "12000")),
])
def test_final_amount_parser_handles_generic_financial_formats(text, bounds):
    """TC-13 离线核对支持千分位/区间分隔符/单位，不改写 Agent 答案。"""
    from decimal import Decimal
    from eval.dd04_credit import _text_amounts
    assert _text_amounts(text) == [tuple(Decimal(x) for x in bounds)]


def test_apply_amount_is_echoed_for_report_display():
    """申请额原值随额度结果输出，供报告对照；建议额度仍不超过申请额。"""
    credit = _calculate()
    assert credit["applyAmount"] == 1000
    assert isinstance(credit["applyAmount"], float)
    assert _range(credit)[1] <= credit["applyAmount"]
    json.dumps(credit)                     # 可序列化后落库为证据快照
