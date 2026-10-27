"""尽调计算 — 指标、规则、评分、额度全部由输入事实和 yaml 阈值算出。

外部汇总评级（risk_level_summary）运行时不读取、不输出（ADR-0008 决策 1），一致性对照只在 eval/ 里做。
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP

from ..domain.errors import ToolError


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _div(numerator, denominator) -> float | None:
    left, right = _num(numerator), _num(denominator)
    if left is None or right in (None, 0):
        return None
    return left / right


def _round(value, digits: int = 4):
    if value is None:
        return None
    return round(float(value), digits)


# @why 比率先按 4 位小数入档、再换算 1 位百分数会二次舍入（0.5385 → 53.9%，原始 53.846…% 应为 53.8%）。
#      送模型与落证据的比率保留 6 位，并附 display（1 位百分数），展示时直接引用。
_RATIO_DIGITS = 6
_RATIO_METRICS = frozenset({
    "asset_liability_ratio", "net_margin", "roe", "roa", "ocf_to_profit",
    "interest_bearing_ratio", "period_expense_ratio", "rd_ratio",
})


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _known_sum(rows: list[dict], key: str) -> float | None:
    """明细缺金额时合计未知；不能把缺数当作零敞口。"""
    values = [_num(row.get(key)) for row in rows]
    if any(value is None for value in values):
        return None
    return float(sum((Decimal(str(value)) for value in values), Decimal(0)))


def _camel_key(key: str) -> str:
    head, *rest = key.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _year_of(text: str | None) -> int | None:
    if not text:
        return None
    head = str(text)[:4]
    return int(head) if head.isdigit() else None


def _sorted_finance(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: int(row.get("year") or 0))


def _flag(value, spec: dict) -> str | None:
    if value is None:
        return None
    if "block_above" in spec and value > spec["block_above"]:
        return "block"
    if "block_below" in spec and value < spec["block_below"]:
        return "block"
    if "warn_above" in spec and value > spec["warn_above"]:
        return "warn"
    if "warn_below" in spec and value < spec["warn_below"]:
        return "warn"
    return None


def _metric_value(row: dict, key: str) -> float | None:
    assets = _num(row.get("total_assets"))
    revenue = _num(row.get("revenue"))
    if key == "asset_liability_ratio":
        return _div(row.get("total_liabilities"), assets)
    if key == "net_margin":
        return _div(row.get("net_profit"), revenue)
    if key == "roe":
        return _div(row.get("net_profit"), row.get("owners_equity"))
    if key == "roa":
        return _div(row.get("net_profit"), assets)
    if key == "ocf_to_profit":
        return _div(row.get("operating_cashflow"), row.get("net_profit"))
    if key == "receivable_days":
        turnover = _div(revenue, row.get("accounts_receivable"))
        return None if turnover in (None, 0) else 365 / turnover
    if key == "inventory_days":
        turnover = _div(revenue, row.get("inventory"))
        return None if turnover in (None, 0) else 365 / turnover
    if key == "interest_bearing_ratio":
        debt = (_num(row.get("short_term_loan")) or 0) + (_num(row.get("long_term_loan")) or 0)
        return _div(debt, assets)
    if key == "period_expense_ratio":
        expense = ((_num(row.get("sales_expense")) or 0)
                   + (_num(row.get("admin_expense")) or 0)
                   + (_num(row.get("finance_expense")) or 0))
        return _div(expense, revenue)
    if key == "rd_ratio":
        return _div(row.get("rd_expense"), revenue)
    return None


def _yoy(newer, older) -> float | None:
    left, right = _num(newer), _num(older)
    if left is None or right in (None, 0):
        return None
    return (left - right) / abs(right)


def _cagr(end, start, years: int) -> float | None:
    left, right = _num(end), _num(start)
    if left is None or right is None or right <= 0 or left < 0 or years <= 0:
        return None
    return (left / right) ** (1 / years) - 1


def _finance_before(rows: list[dict], as_of: str | None) -> list[dict]:
    try:
        cutoff = date.fromisoformat(as_of).year if as_of is not None else None
        years = [(int(row["year"]), row) for row in rows]
        if any(year <= 0 or year != row["year"] for year, row in years):
            raise ValueError("财报年度必须是正整数")
    except (TypeError, ValueError, KeyError) as exc:
        raise ToolError("invalid_args", f"财报年度或申请日期无效：{exc}") from exc
    return [row for year, row in sorted(years, key=lambda item: item[0])
            if cutoff is None or year < cutoff]


def analyze_financials(finances: list[dict], cfg: dict, as_of: str | None = None) -> dict:
    rows = _finance_before(finances, as_of)
    specs = cfg.get("metrics") or {}
    tolerance = _num(cfg.get("balance_tolerance")) or 1
    years = []
    for row in rows:
        assets = _num(row.get("total_assets"))
        liabilities = _num(row.get("total_liabilities"))
        equity = _num(row.get("owners_equity"))
        gap = None
        if None not in (assets, liabilities, equity):
            gap = assets - liabilities - equity
        metrics = {}
        for key, spec in specs.items():
            value = _metric_value(row, key)
            entry = {
                "name": spec.get("name") or key,
                "value": _round(value, _RATIO_DIGITS),
                "flag": _flag(value, spec),
            }
            if key in _RATIO_METRICS:
                # 报告与追问直接引用 display，不能把 0.538462 先写成 0.5385 再换算成 53.9%
                entry["display"] = _pct(value)
            metrics[_camel_key(key)] = entry
        receivable_turnover = _div(row.get("revenue"), row.get("accounts_receivable"))
        inventory_turnover = _div(row.get("revenue"), row.get("inventory"))
        metrics["receivableTurnover"] = {
            "name": "应收账款周转次数（营收口径）",
            "value": _round(receivable_turnover, _RATIO_DIGITS),
            "flag": None,
        }
        metrics["inventoryTurnover"] = {
            "name": "存货周转次数（营收口径）",
            "value": _round(inventory_turnover, _RATIO_DIGITS),
            "flag": None,
        }
        metrics["assetTurnover"] = {
            "name": "总资产周转次数",
            "value": _round(_div(row.get("revenue"), assets), _RATIO_DIGITS),
            "flag": None,
        }
        interest = (_num(row.get("short_term_loan")) or 0) + (_num(row.get("long_term_loan")) or 0)
        years.append({
            "year": row.get("year"),
            "subjects": {
                "revenue": row.get("revenue"),
                "netProfit": row.get("net_profit"),
                "totalAssets": row.get("total_assets"),
                "totalLiabilities": row.get("total_liabilities"),
                "ownersEquity": row.get("owners_equity"),
                "operatingCashflow": row.get("operating_cashflow"),
                "accountsReceivable": row.get("accounts_receivable"),
                "inventory": row.get("inventory"),
                "fixedAssets": row.get("fixed_assets"),
                "otherReceivable": row.get("other_receivable"),
                "shortTermLoan": row.get("short_term_loan"),
                "longTermLoan": row.get("long_term_loan"),
                "interestBearingDebt": interest,
                "rdExpense": row.get("rd_expense"),
                "salesExpense": row.get("sales_expense"),
                "adminExpense": row.get("admin_expense"),
                "financeExpense": row.get("finance_expense"),
                "auditOpinion": row.get("audit_opinion"),
            },
            "metrics": metrics,
            "balanceCheck": {
                "formula": "资产 = 负债 + 所有者权益",
                "gap": _round(gap, 2),
                "balanced": gap is not None and abs(gap) <= tolerance,
                "tolerance": tolerance,
            },
        })
    growth = {}
    if len(rows) >= 2:
        latest, prev = rows[-1], rows[-2]
        span = int(latest.get("year") or 0) - int(rows[0].get("year") or 0)
        growth = {
            "revenueYoy": _round(_yoy(latest.get("revenue"), prev.get("revenue")), _RATIO_DIGITS),
            "netProfitYoy": _round(_yoy(latest.get("net_profit"), prev.get("net_profit")), _RATIO_DIGITS),
            "inventoryYoy": _round(_yoy(latest.get("inventory"), prev.get("inventory")), _RATIO_DIGITS),
            "receivableYoy": _round(_yoy(latest.get("accounts_receivable"), prev.get("accounts_receivable")), _RATIO_DIGITS),
            "revenueCagr": _round(_cagr(latest.get("revenue"), rows[0].get("revenue"), span), _RATIO_DIGITS),
            "netProfitCagr": _round(_cagr(latest.get("net_profit"), rows[0].get("net_profit"), span), _RATIO_DIGITS),
        }
    return {
        "unit": cfg.get("unit") or "万元",
        "denominatorNote": cfg.get("turnover_denominator_note"),
        "configFile": cfg.get("_file"),
        "years": years,
        "growth": growth,
        "latestYear": years[-1]["year"] if years else None,
        "asOf": as_of,
    }


def verify_business(bundle: dict, cfg: dict) -> dict:
    basic = bundle["basic"]
    shareholders = bundle["shareholders"]
    related = bundle["related"]
    guarantees = bundle["guarantees"]
    paid = _div(basic.get("registered_capital_paid"), basic.get("register_capital"))
    top = max(shareholders, key=lambda row: _num(row.get("shareholding_ratio")) or -1, default=None)
    controller = (basic.get("actual_controller") or "").strip()
    top_name = (top or {}).get("shareholder_name") or ""
    related_count = len(related)
    declared = basic.get("related_enterprise_count")
    overdue = [row for row in guarantees if str(row.get("is_overdue")) == "是"]
    circles = [row for row in related if str(row.get("is_guarantee_circle")) == "是"]
    status = basic.get("business_status") or ""
    findings = []
    if status and status != cfg.get("normal_status", "在业"):
        findings.append({"code": "B01", "level": "block", "detail": f"经营状态为{status}"})
    if str(basic.get("legal_person_dishonest")) == "是":
        findings.append({"code": "B02", "level": "block", "detail": "法定代表人被列入失信"})
    if str(basic.get("legal_person_consumption_limit")) == "是":
        findings.append({"code": "B03", "level": "block", "detail": "法定代表人被限制高消费"})
    min_ratio = _num((cfg.get("penalties") or {}).get("paid_in_min_ratio")) or 0.8
    if paid is not None and paid < min_ratio:
        findings.append({"code": "B04", "level": "warn",
                         "detail": f"实缴比例 {_round(paid)} 低于 {min_ratio}"})
    if controller and top_name and controller != top_name:
        findings.append({"code": "B05", "level": "warn",
                         "detail": f"实控人{controller}与第一大股东{top_name}不一致"})
    if declared is not None and int(declared) != related_count:
        findings.append({"code": "B06", "level": "warn",
                         "detail": f"登记关联企业数 {declared} 与明细 {related_count} 条不一致"})
    if overdue:
        findings.append({"code": "B07", "level": "block",
                         "detail": f"对外担保逾期 {len(overdue)} 笔"})
    if circles:
        findings.append({"code": "B08", "level": "warn",
                         "detail": f"担保圈关联 {len(circles)} 家"})
    return {
        "enterpriseId": basic.get("enterprise_id"),
        "unit": "万元",
        "businessStatus": status,
        "paidInRatio": _round(paid),
        "actualController": controller,
        "topShareholder": top_name,
        "controllerMatchesTopShareholder": bool(controller and top_name and controller == top_name),
        "relatedEnterpriseCountDeclared": declared,
        "relatedEnterpriseCountActual": related_count,
        "guaranteeOverdueCount": len(overdue),
        "guaranteeCount": len(guarantees),
        "guaranteeAmount": _known_sum(guarantees, "guarantee_amount"),
        "guaranteeOverdueAmount": _known_sum(overdue, "guarantee_amount"),
        "guaranteeCircleCount": len(circles),
        "relatedByType": dict(Counter(row.get("relation_type") or "未注明" for row in related)),
        # @why 仅保留业务事实白名单，绝不把外部汇总评级带入报告。
        "riskFacts": {_camel_key(key): (bundle.get("risk") or {}).get(key) for key in (
            "existing_loan_balance", "overdue_count", "overdue_amount",
            "external_guarantee_amount", "public_opinion_score")},
        "findings": findings,
        "configFile": cfg.get("_file"),
    }


def _decay(event_date: str | None, as_of: str | None, per_year: float) -> float:
    start, end = _year_of(event_date), _year_of(as_of)
    if start is None or end is None:
        return 1.0
    return per_year ** max(end - start, 0)


def scan_public_opinion(bundle: dict, cfg: dict, as_of: str | None) -> dict:
    sentiment = cfg.get("sentiment") or {}
    impact = cfg.get("impact") or {}
    decay = _num(cfg.get("decay_per_year")) or 0.85
    closed = set(cfg.get("closed_statuses") or [])
    defendants = set(cfg.get("defendant_roles") or [])
    lawsuit_weights = cfg.get("lawsuit") or {}
    events = []
    score = _num(cfg.get("base_score")) or 0
    for row in bundle["opinions"]:
        delta = sentiment.get(row.get("sentiment"), 0) * impact.get(row.get("impact_level"), 1)
        weight = _decay(row.get("event_date"), as_of, decay)
        points = delta * weight
        score += points
        events.append({
            "eventId": row.get("event_id"),
            "eventDate": row.get("event_date"),
            "eventType": row.get("event_type"),
            "eventContent": row.get("event_content"),
            "eventSource": row.get("event_source"),
            "sentiment": row.get("sentiment"),
            "impactLevel": row.get("impact_level"),
            "points": _round(points, 2),
        })
    lawsuits = []
    open_defendant_amount = 0.0
    for row in bundle["lawsuits"]:
        is_closed = row.get("case_status") in closed
        is_defendant = row.get("litigation_role") in defendants
        if not is_closed and is_defendant:
            key = "open_defendant"
            amount = _num(row.get("amount")) or 0
            open_defendant_amount += amount
        elif not is_closed:
            key = "open_other"
        elif is_defendant:
            key = "closed_defendant"
        else:
            key = "closed_other"
        points = lawsuit_weights.get(key, 0)
        score += points
        lawsuits.append({
            "caseId": row.get("case_id"),
            "caseStatus": row.get("case_status"),
            "litigationRole": row.get("litigation_role"),
            "amount": row.get("amount"),
            "bucket": key,
            "points": points,
        })
    max_score = _num(cfg.get("max_score")) or 100
    score = _clamp(score, 0, max_score)
    labels = []
    for name, words in (cfg.get("labels") or {}).items():
        text = " ".join(str(row.get("event_type") or "") + str(row.get("event_content") or "")
                        for row in bundle["opinions"])
        if any(word and word in text for word in words):
            labels.append(name)
    if any(item["bucket"] == "open_defendant" for item in lawsuits):
        labels.append("未结被告/被执行")
    return {
        "enterpriseId": bundle["basic"].get("enterprise_id"),
        "unit": "万元",
        "asOf": as_of,
        "opinionRiskScore": _round(score, 2),
        "healthScore": _round(100 - score, 2),
        "labels": labels,
        "events": events,
        "lawsuits": lawsuits,
        "lawsuitCount": len(lawsuits),
        "lawsuitAmount": _known_sum(lawsuits, "amount"),
        "openDefendantAmount": _round(open_defendant_amount, 2),
        "configFile": cfg.get("_file"),
    }


def _confidence(value, threshold, higher_is_hit: bool, cfg: dict) -> str:
    margin = cfg.get("confidence") or {}
    high = _num(margin.get("high_margin")) or 0.5
    if threshold in (None, 0) or value is None:
        return margin.get("default") or "medium"
    gap = (value - threshold) / abs(threshold) if higher_is_hit else (threshold - value) / abs(threshold)
    if gap >= high:
        return "high"
    return margin.get("default") or "medium"


def detect_fraud(bundle: dict, finance: dict, cfg: dict) -> dict:
    rules_cfg = cfg.get("rules") or {}
    rows = _sorted_finance(bundle["finances"])
    latest = rows[-1] if rows else {}
    previous = rows[-2] if len(rows) >= 2 else None
    results = []

    def add(rule_id: str, hit: bool, value, threshold, detail: str, higher_is_hit: bool = True):
        spec = rules_cfg.get(rule_id) or {}
        results.append({
            "ruleId": rule_id,
            "name": spec.get("name") or rule_id,
            "hit": hit,
            "value": _round(value) if isinstance(value, float) else value,
            "threshold": threshold,
            "confidence": _confidence(value, threshold, higher_is_hit, cfg) if hit else None,
            "detail": detail,
        })

    revenue = _num(latest.get("revenue"))
    ocf = _num(latest.get("operating_cashflow"))
    ratio = _div(ocf, revenue)
    floor = _num((rules_cfg.get("F01") or {}).get("min_ocf_to_revenue"))
    add("F01", bool(revenue and revenue > 0 and ratio is not None and floor is not None and ratio < floor),
        ratio, floor, "最近一年经营现金流 / 营业收入", higher_is_hit=False)

    inv_gap = _num((rules_cfg.get("F02") or {}).get("gap_over_revenue_growth"))
    inv_min = _num((rules_cfg.get("F02") or {}).get("min_inventory_growth"))
    inv_yoy = _num((finance.get("growth") or {}).get("inventoryYoy"))
    rev_yoy = _num((finance.get("growth") or {}).get("revenueYoy"))
    inv_hit = (previous is not None and inv_yoy is not None and rev_yoy is not None
               and inv_min is not None and inv_gap is not None
               and inv_yoy >= inv_min and inv_yoy - rev_yoy >= inv_gap)
    add("F02", bool(inv_hit), None if inv_yoy is None or rev_yoy is None else inv_yoy - rev_yoy,
        inv_gap, "存货增速减营收增速")

    rec_gap = _num((rules_cfg.get("F03") or {}).get("gap"))
    rec_yoy = _num((finance.get("growth") or {}).get("receivableYoy"))
    rec_hit = (rec_yoy is not None and rev_yoy is not None and rec_gap is not None
               and rec_yoy > rev_yoy + rec_gap)
    add("F03", bool(rec_hit), None if rec_yoy is None or rev_yoy is None else rec_yoy - rev_yoy,
        rec_gap, "应收增速减营收增速")

    other_cap = _num((rules_cfg.get("F04") or {}).get("max_other_receivable_to_assets"))
    other_ratio = _div(latest.get("other_receivable"), latest.get("total_assets"))
    add("F04", bool(other_ratio is not None and other_cap is not None and other_ratio > other_cap),
        other_ratio, other_cap, "其他应收款 / 总资产")

    long_cfg = rules_cfg.get("F05") or {}
    weak_years = 0
    for row in rows:
        profit = _num(row.get("net_profit"))
        cash = _num(row.get("operating_cashflow"))
        if profit is not None and profit > 0 and cash is not None and cash < profit * (_num(long_cfg.get("max_ocf_to_profit")) or 0.3):
            weak_years += 1
    need_years = int(long_cfg.get("min_years") or 2)
    add("F05", weak_years >= need_years, weak_years, need_years, "净利为正且经营现金流明显偏弱的年数")

    rel_cfg = rules_cfg.get("F06") or {}
    related_n = len(bundle["related"])
    circle = any(str(row.get("is_guarantee_circle")) == "是" for row in bundle["related"])
    min_related = int(rel_cfg.get("min_related") or 4)
    add("F06", related_n >= min_related and circle, related_n, min_related,
        "关联企业数，且明细中存在担保圈")
    hits = [item for item in results if item["hit"]]
    return {
        "enterpriseId": bundle["basic"].get("enterprise_id"),
        "rules": results,
        "hitCount": len(hits),
        "hitRuleIds": [item["ruleId"] for item in hits],
        "configFile": cfg.get("_file"),
    }


def _latest_subjects(finance: dict) -> dict:
    years = finance.get("years") or []
    return (years[-1].get("subjects") or {}) if years else {}


def indicator_values(bundle: dict, finance: dict, opinion: dict | None = None) -> dict:
    """评分卡与额度共用的原始指标值（最近完整年度 + 风险事实）。缺数返回 None，不当成 0。"""
    latest = _latest_subjects(finance)
    revenue, net_profit = _num(latest.get("revenue")), _num(latest.get("netProfit"))
    assets, equity = _num(latest.get("totalAssets")), _num(latest.get("ownersEquity"))
    risk = bundle.get("risk") or {}
    basic = bundle.get("basic") or {}
    lawsuits = sum(_num(row.get("amount")) or 0 for row in bundle.get("lawsuits") or [])
    guarantees = sum(_num(row.get("guarantee_amount")) or 0 for row in bundle.get("guarantees") or [])
    positive_equity = equity if equity is not None and equity > 0 else None
    # @why 舆情评分优先用原始输入字段 public_opinion_score（事实特征，不是结论）；缺失时退回本系统舆情健康分
    opinion_score = _num(risk.get("public_opinion_score"))
    if opinion_score is None and opinion:
        opinion_score = _num(opinion.get("healthScore"))
    return {
        "asset_liability_ratio": _div(latest.get("totalLiabilities"), assets),
        "net_margin": _div(net_profit, revenue),
        "ocf_to_profit": _div(latest.get("operatingCashflow"), net_profit) if net_profit else None,
        "receivable_to_revenue": _div(latest.get("accountsReceivable"), revenue),
        "other_receivable_to_assets": _div(latest.get("otherReceivable"), assets),
        "overdue_count": _num(risk.get("overdue_count")),
        "lawsuit_to_equity": None if positive_equity is None else lawsuits / positive_equity,
        "guarantee_to_equity": None if positive_equity is None else guarantees / positive_equity,
        "public_opinion_score": opinion_score,
        "legal_person_credit": (str(basic.get("legal_person_dishonest")) == "是"
                                or str(basic.get("legal_person_consumption_limit")) == "是"),
        "overdue_guarantee": any(str(row.get("is_overdue")) == "是" for row in bundle.get("guarantees") or []),
        "guarantee_circle_count": sum(1 for row in bundle.get("related") or []
                                      if str(row.get("is_guarantee_circle")) == "是"),
        "operating_cashflow": _num(latest.get("operatingCashflow")),
        "net_profit": net_profit,
    }


def _indicator_points(value, spec: dict) -> int | None:
    """按阈值档给 0–N 点（越高越差）。flag 型指标为真时给固定点数。缺数返回 None。"""
    if "flag_points" in spec:
        return int(spec["flag_points"]) if value else 0
    if value is None:
        return None
    cuts = [float(c) for c in spec.get("cuts") or []]
    points = 0
    for index, cut in enumerate(cuts, 1):
        worse = value >= cut if spec.get("direction", "higher_worse") == "higher_worse" else value < cut
        if worse:
            points = index
    return points


def _vetoes(bundle: dict, fraud: dict, cfg: dict) -> list[str]:
    veto = cfg.get("veto") or {}
    reasons = []
    basic = bundle["basic"]
    if str(basic.get("legal_person_dishonest")) in set(map(str, veto.get("dishonest_values") or [])):
        reasons.append("法定代表人失信")
    if str(basic.get("legal_person_consumption_limit")) in set(map(str, veto.get("consumption_limit_values") or [])):
        reasons.append("法定代表人限高")
    risk = bundle.get("risk") or {}
    if veto.get("overdue_unresolved") and (risk.get("overdue_count") or 0) > 0:
        reasons.append("存在未结逾期")
    # @why 反欺诈命中是待核实线索，不作一票否决；由额度模型的「重大财务异常折减」与核查条件承接
    return reasons


def rate_risk(bundle: dict, finance: dict, business: dict, opinion: dict, fraud: dict, cfg: dict) -> dict:
    """点数制评分卡：每项指标按 scorecard.yaml 的阈值档给点（越高越差），合计点数映射风险档位。"""
    values = indicator_values(bundle, finance, opinion)
    dimensions = []
    total = 0
    missing = []
    for key, spec in (cfg.get("indicators") or {}).items():
        value = values.get(key)
        points = _indicator_points(value, spec)
        if points is None:
            missing.append(spec.get("name") or key)
            points = 0
        total += points
        shown = value if isinstance(value, bool) else _round(value, _RATIO_DIGITS)
        dimensions.append({"dimension": key, "name": spec.get("name") or key, "value": shown,
                           "points": points, "maxPoints": spec.get("flag_points") or len(spec.get("cuts") or []),
                           "cuts": spec.get("cuts"), "source": "calculated"})
    level = None
    for band in cfg.get("levels") or []:
        limit = band.get("max_points")
        if limit is None or total <= int(limit):
            level = band.get("name")
            break
    level = level or "高风险"
    vetoes = _vetoes(bundle, fraud, cfg)
    if vetoes:
        level = "高风险"
    return {
        "enterpriseId": bundle["basic"].get("enterprise_id"),
        "riskLevel": level,
        # 风险点数：越高越差，档位边界见 scorecard.yaml levels
        "score": total,
        "scoreDirection": "风险点数，越高越差",
        "dimensions": dimensions,
        "missingIndicators": missing,
        "vetoes": vetoes,
        # @why 复核条件只看本系统的事实缺口（没有财务行或关键指标缺数），
        #      不与外部汇总评级对照：那一列与公开答案一致，运行时不读（ADR-0008 决策 1）
        "needsManualReview": not finance.get("years") or bool(missing),
        "configFile": cfg.get("_file"),
    }


def major_anomalies(bundle: dict, finance: dict, cfg: dict) -> list[dict]:
    """额度模型的「重大财务异常」：命中项带指标值与阈值，供折减和核查条件引用。"""
    spec = cfg.get("anomaly_discount") or {}
    values = indicator_values(bundle, finance)
    hits = []
    ocf, profit = values["operating_cashflow"], values["net_profit"]
    ratio = _num(spec.get("min_ocf_to_profit"))
    if ocf is not None and (ocf <= 0 or (ratio is not None and profit and profit > 0 and ocf < profit * ratio)):
        hits.append({"code": "A1", "name": "营收与经营现金流背离", "value": ocf,
                     "threshold": f"经营现金流 ≤ 0 或 < 净利润 × {ratio}"})
    for code, key, name, limit in (
            ("A2", "receivable_to_revenue", "应收账款占营收过高", spec.get("max_receivable_to_revenue")),
            ("A3", "other_receivable_to_assets", "其他应收款占总资产过高", spec.get("max_other_receivable_to_assets"))):
        value, threshold = values[key], _num(limit)
        if value is not None and threshold is not None and value > threshold:
            hits.append({"code": code, "name": name, "value": _round(value), "threshold": threshold})
    circles, need = values["guarantee_circle_count"], int(spec.get("min_guarantee_circle") or 2)
    if circles >= need:
        hits.append({"code": "A4", "name": "关联担保圈", "value": circles, "threshold": need})
    return hits


def _pct(value) -> str:
    """比率 → 1 位小数百分数（从原始比率直接换算，避免二次舍入）。"""
    number = _num(value)
    if number is None:
        return "—"
    return f"{(Decimal(str(number)) * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"


def _amt(value) -> str:
    """金额 → 万元，整数带千分位（与报告版式一致）。"""
    number = _num(value)
    if number is None:
        return "—"
    return f"{number:,.0f}" if abs(number - round(number)) < 1e-9 else f"{number:,.2f}"


def key_risk_conclusions(bundle: dict, finance: dict, rating: dict, credit: dict | None,
                         fraud: dict, opinion: dict, business: dict) -> list[dict]:
    """把本户已命中的风险事实写成标准风险术语短句，供报告逐条引用。

    @why 评审 6.3 要求「风险结论与数据事实一致」，报告若只列数字不点名风险类型，
         审批人需要自行归纳；这里按阈值与规则命中生成固定名称 + 数值依据，
         模型只引用不重算，既保证口径一致，也避免按题目写答案。
    """
    items: list[dict] = []
    dimensions = {item.get("dimension"): item.get("value")
                  for item in rating.get("dimensions") or []}
    latest = _latest_subjects(finance)
    risk = bundle.get("risk") or {}
    basic = bundle.get("basic") or {}

    debt = dimensions.get("asset_liability_ratio")
    if debt is not None and debt >= 0.70:
        items.append({"code": "R1", "name": "资产负债率过高",
                      "detail": f"资产负债率 {_pct(debt)}，高于 70% 警戒线"})
    receivable = dimensions.get("receivable_to_revenue")
    if receivable is not None and receivable >= 0.40:
        items.append({"code": "R2", "name": "应收账款过高",
                      "detail": f"应收账款占营业收入 {_pct(receivable)}，高于 40% 关注线"})
    other_assets = _div(latest.get("otherReceivable"), latest.get("totalAssets"))
    if other_assets is not None and other_assets > 0.08:
        items.append({"code": "R3", "name": "其他应收款异常偏高",
                      "detail": f"其他应收款占总资产 {_pct(other_assets)}，高于 8% 关注线"})
    for rule in fraud.get("rules") or []:
        if rule.get("ruleId") == "F01" and rule.get("hit"):
            items.append({"code": "R4", "name": "营收现金流背离",
                          "detail": f"经营现金流/营业收入 {_pct(rule.get('value'))}，"
                                    f"低于 2.0% 阈值（F01）"})
    ocf, profit = _num(latest.get("operatingCashflow")), _num(latest.get("netProfit"))
    if (ocf is not None and profit is not None and profit > 0 and ocf < profit * 0.5):
        items.append({"code": "R5", "name": "现金流与利润背离",
                      "detail": f"经营现金流 {_amt(ocf)} 万元，不足净利润 {_amt(profit)} 万元的一半"})
    overdue_count = _num(risk.get("overdue_count")) or 0
    overdue_amount = _num(risk.get("overdue_amount")) or 0
    guarantee_overdue = int(business.get("guaranteeOverdueCount") or 0)
    if overdue_count > 0 and guarantee_overdue > 0:
        items.append({"code": "R6", "name": "逾期与逾期担保",
                      "detail": f"存量逾期 {int(overdue_count)} 次 / {_amt(overdue_amount)} 万元；"
                                f"对外担保逾期 {guarantee_overdue} 笔 / "
                                f"{_amt(business.get('guaranteeOverdueAmount'))} 万元"})
    elif overdue_count > 0:
        items.append({"code": "R6", "name": "存在未结逾期",
                      "detail": f"存量逾期 {int(overdue_count)} 次 / {_amt(overdue_amount)} 万元"})
    elif guarantee_overdue > 0:
        items.append({"code": "R6", "name": "对外担保逾期",
                      "detail": f"对外担保逾期 {guarantee_overdue} 笔 / "
                                f"{_amt(business.get('guaranteeOverdueAmount'))} 万元"})
    if str(basic.get("legal_person_consumption_limit")) == "是":
        items.append({"code": "R7", "name": "法人限高",
                      "detail": "法定代表人被限制高消费（B03）"})
    if str(basic.get("legal_person_dishonest")) == "是":
        items.append({"code": "R8", "name": "法定代表人失信",
                      "detail": "法定代表人被列入失信被执行人（B02）"})
    health = _num(opinion.get("healthScore"))
    labels = opinion.get("labels") or []
    if (health is not None and health < 50) or any("负面" in str(item) for item in labels):
        items.append({"code": "R9", "name": "舆情负面",
                      "detail": f"舆情健康分 {health:g} 分" if health is not None else "存在负面舆情"})
    executed = any("执行" in str(item.get("eventContent") or "") for item in opinion.get("events") or [])
    executed = executed or any("执行" in str(item) for item in labels)
    if executed and (opinion.get("lawsuitCount") or 0) > 0:
        items.append({"code": "R10", "name": "涉诉及被执行",
                      "detail": f"涉诉 {int(opinion.get('lawsuitCount') or 0)} 件 / "
                                f"{_amt(opinion.get('lawsuitAmount'))} 万元，含被执行记录"})
    circles = int(business.get("guaranteeCircleCount") or 0)
    if circles >= 2:
        items.append({"code": "R11", "name": "关联担保圈",
                      "detail": f"担保圈关联 {circles} 家，存在互保传导风险"})
    blocked = rating.get("riskLevel") == "高风险" or bool(rating.get("vetoes"))
    if credit and not blocked:
        apply_amount = _num(credit.get("applyAmount"))
        suggested = str(credit.get("suggestedCreditAmount") or "")
        top = _num(suggested.split("-")[-1]) if suggested else None
        if apply_amount and top is not None and top < apply_amount:
            items.append({"code": "R12", "name": "额度审慎",
                          "detail": f"建议额度 {suggested} 万元低于申请额 {_amt(apply_amount)} 万元"})
    if blocked:
        items.append({"code": "R13", "name": "拒贷建议",
                      "detail": f"风险评级{rating.get('riskLevel')}，建议拒贷（额度 0 万元），"
                                "需业务人员确认"})
    return items


def _credit_decimal(value, field: str, code: str = "execution_failed") -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ToolError(code, f"额度测算字段 {field} 缺失或非数值") from exc
    if not number.is_finite():
        raise ToolError(code, f"额度测算字段 {field} 必须是有限数值")
    return number


def _floor_step(value: Decimal, step: Decimal) -> int:
    return int((value / step).to_integral_value(rounding=ROUND_FLOOR) * step)


def _credit_inputs(application: dict, finance: dict) -> tuple[dict, Decimal | None, Decimal | None]:
    """取额度测算输入。

    有申请额：按本笔贷款封顶（loan 口径）。
    无申请额：企业主体能力测算（enterprise 口径），不做申请额封顶，期限可空。
    """
    raw_amount = application.get("apply_amount")
    capacity_only = raw_amount in (None, "")
    as_of = application.get("apply_date") or finance.get("asOf")
    if not as_of:
        as_of = date.today().isoformat()
    if capacity_only:
        amount = None
        months = None
    else:
        amount = _credit_decimal(raw_amount, "apply_amount", "invalid_args")
        months = _credit_decimal(application.get("loan_term_months"), "loan_term_months", "invalid_args")
        if amount <= 0 or months <= 0 or months != months.to_integral_value():
            raise ToolError("invalid_args", "申请金额须为正数，贷款期限须为正整数月")
        if not application.get("apply_date"):
            raise ToolError("invalid_args", "额度测算需要有效申请日期")
        as_of = application["apply_date"]
    rows = _finance_before(finance.get("years") or [], as_of)
    if not rows:
        raise ToolError("execution_failed",
                        ("申请时点之前没有可用完整年度财报，无法测算额度"
                         if not capacity_only else "没有可用完整年度财报，无法测算建议授信额度"))
    subjects = rows[-1].get("subjects") or {}
    inputs = {key: _credit_decimal(subjects.get(key), key)
              for key in ("revenue", "ownersEquity", "operatingCashflow")}
    inputs["year"] = rows[-1]["year"]
    inputs["asOf"] = as_of
    return inputs, amount, months


def _credit_policy(cfg: dict, level: str) -> dict:
    if cfg.get("credit_scope") != "new_application_financing" or not cfg.get("policy_version"):
        raise ToolError("execution_failed", "缺少本次融资模拟政策版本或口径")
    caps = cfg.get("caps") or {}
    ratings = cfg.get("rating_coef") or {}
    discount = cfg.get("anomaly_discount") or {}
    values = {"revenue": caps.get("revenue_coef"), "equity": caps.get("equity_coef"),
              "rating": ratings.get(level), "band": cfg.get("band"), "step": cfg.get("round_step"),
              "discountLow": discount.get("low_ratio", 1), "discountHigh": discount.get("high_ratio", 1)}
    policy = {key: _credit_decimal(value, f"config.{key}") for key, value in values.items()}
    if any(not 0 <= value <= 1 for key, value in policy.items() if key != "step"):
        raise ToolError("execution_failed", "额度系数、带宽与折减比例必须在 0 到 1 之间")
    if policy["discountLow"] > policy["discountHigh"]:
        raise ToolError("execution_failed", "异常折减下限不得高于上限")
    if policy["step"] <= 0 or policy["step"] != policy["step"].to_integral_value():
        raise ToolError("execution_failed", "额度取整步长必须是正整数万元")
    large = cfg.get("large_amount") or {}
    policy["largeThreshold"] = (_credit_decimal(large["threshold"], "config.large_amount.threshold")
                                if large.get("threshold") is not None else None)
    policy["largeStep"] = (_credit_decimal(large["step"], "config.large_amount.step")
                           if large.get("step") is not None else policy["step"])
    if policy["largeStep"] <= 0 or policy["largeStep"] != policy["largeStep"].to_integral_value():
        raise ToolError("execution_failed", "大额取整步长必须是正整数万元")
    policy["discountMinHits"] = int(discount.get("min_hits") or 2)
    return policy


def _credit_exposures(bundle: dict) -> dict:
    risk = bundle.get("risk") or {}
    exposures = {}
    for field, key in (("existing_loan_balance", "existingLoanBalance"),
                       ("external_guarantee_amount", "externalGuaranteeAmount")):
        value = risk.get(field)
        if value is None:
            exposures[key] = None
            continue
        number = _credit_decimal(value, field)
        if number < 0:
            raise ToolError("execution_failed", f"风险敞口 {field} 不得为负")
        exposures[key] = float(number)
    return exposures


def _credit_conditions(application: dict, bundle: dict, rating: dict, inputs: dict,
                       policy: dict, exposures: dict, anomalies: list[dict]) -> list[str]:
    conditions = []
    if application.get("guarantee_type"):
        conditions.append(f"担保方式按申请的{application.get('guarantee_type')}落实")
    for key, name in (("existingLoanBalance", "存量贷款"), ("externalGuaranteeAmount", "对外担保")):
        value = exposures[key]
        if value is None:
            conditions.append(f"缺少{name}敞口，需人工核验")
        elif value > 0:
            conditions.append(f"核验{name}{value:g}万元及履约安排，不作为本次额度全额扣减")
    if anomalies:
        names = "、".join(item["name"] for item in anomalies)
        if len(anomalies) >= policy["discountMinHits"]:
            conditions.append(f"命中重大财务异常（{names}），额度按 {policy['discountLow']}–"
                              f"{policy['discountHigh']} 审慎测算；投放前重点核查收入真实性及关联方资金往来")
        else:
            conditions.append(f"存在财务异常线索（{names}），投放前核查")
    if inputs["operatingCashflow"] <= 0:
        conditions.append("经营现金流非正：需核验还本付息来源及资金用途")
    if rating.get("vetoes"):
        conditions.append("一票否决项未解除前不新增授信：" + "、".join(rating["vetoes"]))
    if (bundle.get("risk") or {}).get("overdue_count"):
        conditions.append("存量逾期结清前不投放")
    if rating.get("riskLevel") == "高风险":
        conditions.append("高风险档建议额度为 0")
    return conditions


def _credit_steps(inputs: dict, policy: dict, amount: Decimal | None, level: str,
                  is_blocked: bool, anomalies: list[dict]) -> tuple[list[dict], str]:
    revenue = max(inputs["revenue"], Decimal(0)) * policy["revenue"]
    equity = max(inputs["ownersEquity"], Decimal(0)) * policy["equity"]
    capacity = min(revenue, equity)
    rated = capacity * policy["rating"]
    # 无申请额（企业主体）：以评级后能力为硬上限；有申请额：再与申请额取小
    if is_blocked:
        ceiling = Decimal(0)
    elif amount is None:
        ceiling = rated
    else:
        ceiling = min(amount, rated)
    # @why 多项重大财务异常（反欺诈线索）不一票否决，而是审慎压降：区间整体按折减比例测算
    discounted = len(anomalies) >= policy["discountMinHits"]
    low_ratio = policy["discountLow"] if discounted else 1 - policy["band"]
    high_ratio = policy["discountHigh"] if discounted else Decimal(1)
    # @why 取整档位按金额分段：大额按大步长报价（如 2000 万以上按 500 万），小额按基础步长
    large = policy["largeThreshold"] is not None and ceiling >= policy["largeThreshold"]
    step = policy["largeStep"] if large else policy["step"]
    low = _floor_step(ceiling * low_ratio, step)
    high = _floor_step(ceiling * high_ratio, step)
    if low > high:
        low = high
    suggested = str(low) if low == high else f"{low}-{high}"
    cap_step = (("能力上限", "评级后财务能力；高风险/否决为0", ceiling)
                if amount is None else
                ("申请额封顶", "min(申请额, 评级后能力)；高风险/否决为0", ceiling))
    values = [
        ("营收口径上限", f"营业收入 × {policy['revenue']}", revenue),
        ("净资产口径上限", f"max(所有者权益, 0) × {policy['equity']}", equity),
        ("财务能力取小", "min(营收口径, 净资产口径)，保留零值", capacity),
        ("评级调整", f"财务能力 × {level}系数{policy['rating']}", rated),
        cap_step,
    ]
    steps = [{"step": name, "formula": formula, "value": float(value)}
             for name, formula, value in values]
    steps.append({"step": "重大财务异常折减",
                  "formula": (f"命中 {len(anomalies)} 项（≥{policy['discountMinHits']} 项折减）："
                              f"区间 = 硬上限 × [{low_ratio}, {high_ratio}]"),
                  "value": [item["code"] for item in anomalies]})
    steps.append({"step": "输出区间", "formula": f"下界=硬上限×{low_ratio}，上界=硬上限×{high_ratio}；"
                  f"均向下取整至{step}万元", "value": suggested})
    return steps, suggested


def calc_credit_limit(application: dict, bundle: dict, finance: dict, rating: dict, cfg: dict) -> dict:
    inputs, amount, months = _credit_inputs(application, finance)
    if cfg.get("unit") != "万元" or finance.get("unit") != cfg["unit"]:
        raise ToolError("execution_failed", "额度与财报金额单位必须一致且为万元")
    level = rating.get("riskLevel") or "高风险"
    policy = _credit_policy(cfg, level)
    is_blocked = level == "高风险" or bool(rating.get("vetoes"))
    anomalies = major_anomalies(bundle, finance, cfg)
    steps, suggested = _credit_steps(inputs, policy, amount, level, is_blocked, anomalies)
    exposures = _credit_exposures(bundle)
    capacity_only = amount is None
    assumptions = [
        "团队模拟政策，非银行批准额度；营收和净资产约束本次融资",
        "存量与担保用于敞口及履约核验，不与净资产口径重复全额扣减",
        "无还本付息计划；经营现金流只作重大异常判定与核查条件，不是精确偿债覆盖率",
        "风险档位决定准入（高风险为 0）与利率方向；多项重大财务异常按比例审慎压降",
    ]
    if capacity_only:
        assumptions.append("企业主体测算：无申请额封顶，建议授信额度为财务能力测算结果")
    else:
        assumptions.append("按申请前完整年度取数；缺少披露日期，不能保证申请当日已经披露")
    return {
        "applicationId": application.get("application_id") or None,
        "enterpriseId": application.get("enterprise_id"),
        "riskLevel": level,
        "suggestedCreditAmount": suggested,
        # 企业主体测算无申请额：applyAmount 为 null，报告不得展示「申请贷款额度」
        "applyAmount": float(amount) if amount is not None else None,
        "unit": cfg["unit"],
        "termMonths": int(months) if months is not None else None,
        "rateDirection": (cfg.get("rate_direction") or {}).get(level) or "不适用",
        "guaranteeType": application.get("guarantee_type") or None,
        "conditions": _credit_conditions(application, bundle, rating, inputs, policy, exposures, anomalies),
        "steps": steps,
        "anomalies": anomalies,
        "configFile": cfg.get("_file"),
        "policyVersion": cfg["policy_version"],
        "creditScope": cfg["credit_scope"],
        "financialYear": inputs["year"],
        "asOf": inputs.get("asOf") or application.get("apply_date"),
        "exposures": exposures,
        "assumptions": assumptions,
    }


def _enterprise_conditions(bundle: dict, rating: dict, anomalies: list[dict]) -> list[str]:
    """企业口径的风控条件：只保留主体与风险类核查，不写额度、期限、担保放款条件。"""
    conditions = []
    risk = bundle.get("risk") or {}
    for field, name in (("existing_loan_balance", "存量贷款"),
                        ("external_guarantee_amount", "对外担保")):
        value = _num(risk.get(field))
        if value is None:
            conditions.append(f"缺少{name}敞口，需人工核验")
        elif value > 0:
            conditions.append(f"核验{name}{value:g}万元及履约安排")
    if anomalies:
        names = "、".join(item["name"] for item in anomalies)
        conditions.append(f"存在财务异常线索（{names}），需核查收入真实性及关联方资金往来")
    if rating.get("vetoes"):
        conditions.append("一票否决项未解除前不予准入：" + "、".join(rating["vetoes"]))
    if _num(risk.get("overdue_count")):
        conditions.append("存量逾期结清前不予新增授信")
    if rating.get("riskLevel") == "高风险":
        conditions.append("高风险档建议暂缓授信合作")
    return conditions


def _conclusion_word(level: str | None, vetoes: list | None) -> str:
    """贷款口径准入建议措辞与评级一一对应（与 dd-report Skill 的结论用语一致）。"""
    if level == "高风险" or vetoes:
        return "暂不准入"
    if level in ("低-中风险", "中风险"):
        return "审慎准入"
    if level == "低风险":
        return "建议准入"
    return "需人工复核"


def _cooperation_word(level: str | None, vetoes: list | None) -> str:
    """企业口径给出的是合作建议，不是贷款准入：两者结论用语必须区分。"""
    if level == "高风险" or vetoes:
        return "暂不合作"
    if level in ("低-中风险", "中风险"):
        return "审慎合作"
    if level == "低风险":
        return "建议合作"
    return "需人工复核"


def _loan_conclusion(rating: dict, credit: dict, fraud: dict) -> str:
    """贷款口径的尽调结论：先给结论（准入建议 + 建议额度 + 期限），再列支撑依据。

    @why 审批阅读顺序是先看结论再看理由；结构化结论同时用于报告预览与报告列表摘要，
         不能只罗列评级、额度数字而不下准入判断。
    """
    level = rating.get("riskLevel") or "未取得"
    vetoes = "、".join(rating.get("vetoes") or []) or "无"
    hits = "、".join(fraud.get("hitRuleIds") or []) or "无"
    word = _conclusion_word(level, rating.get("vetoes"))
    amount = credit.get("suggestedCreditAmount")
    term = credit.get("termMonths")
    if amount in (None, ""):
        head = f"{word}：额度无法测算，需补充材料后复核。"
    else:
        unit = credit.get("unit") or "万元"
        head = f"{word}：建议额度 {amount} {unit}"
        if term is not None:
            head += f"，期限 {term} 个月"
        head += "。"
    return (head + f"依据：风险评级{level}（评分{rating.get('score')}）；"
            f"一票否决：{vetoes}；反欺诈命中：{hits}。")


def _enterprise_conclusion(rating: dict, credit: dict, fraud: dict) -> str:
    """企业口径尽调结论：合作建议 + 建议授信额度，不含申请贷款额度与期限。"""
    level = rating.get("riskLevel") or "未取得"
    vetoes = "、".join(rating.get("vetoes") or []) or "无"
    hits = "、".join(fraud.get("hitRuleIds") or []) or "无"
    word = _cooperation_word(level, rating.get("vetoes"))
    amount = credit.get("suggestedCreditAmount")
    if amount in (None, ""):
        head = f"{word}：建议授信额度无法测算，需补充材料后复核。"
    else:
        unit = credit.get("unit") or "万元"
        head = f"{word}：建议授信额度 {amount} {unit}。"
    return (head + f"依据：风险评级{level}（评分{rating.get('score')}）；"
            f"一票否决：{vetoes}；反欺诈命中：{hits}。企业主体尽调，未绑定具体贷款申请。")


def build_report(application: dict, bundle: dict, finance: dict, business: dict,
                 opinion: dict, fraud: dict, rating: dict, credit: dict,
                 *, scope: str = "loan", anomalies: list[dict] | None = None) -> dict:
    """汇总结构化尽调报告。

    scope=loan：本笔贷款口径，五部分，额度建议并列申请贷款额度与建议授信额度；
    scope=enterprise：企业主体口径，五部分，额度建议只含建议授信额度，不出现申请贷款额度。
    """
    enterprise = scope == "enterprise"
    basic = bundle["basic"]
    credit = credit or {}
    sections = {
        "overview": {
            "title": "企业概况",
            "enterpriseId": basic.get("enterprise_id"),
            "industry": basic.get("industry"),
            "businessStatus": basic.get("business_status"),
            "establishDate": basic.get("establish_date"),
            "findings": business.get("findings"),
        },
        "financialAnalysis": {
            "title": "财务分析",
            "unit": finance.get("unit"),
            "denominatorNote": finance.get("denominatorNote"),
            "years": finance.get("years"),
            "growth": finance.get("growth"),
        },
        "riskAlerts": {
            "title": "风险提示",
            "riskLevel": rating.get("riskLevel"),
            "score": rating.get("score"),
            "vetoes": rating.get("vetoes"),
            "fraudHits": fraud.get("hitRuleIds"),
            "opinionLabels": opinion.get("labels"),
            "needsManualReview": bool(rating.get("needsManualReview")
                                      or credit.get("needsManualReview")),
        },
        "riskConditions": {
            "title": "风控条件",
            "conditions": (_enterprise_conditions(bundle, rating, anomalies or [])
                           if enterprise else credit.get("conditions")),
        },
    }
    credit_section = {
        "title": "额度建议",
        "suggestedCreditAmount": credit.get("suggestedCreditAmount"),
        "unit": credit.get("unit"),
        "termMonths": None if enterprise else credit.get("termMonths"),
        "rateDirection": credit.get("rateDirection"),
        "guaranteeType": None if enterprise else credit.get("guaranteeType"),
        "steps": credit.get("steps") or [],
        "policyVersion": credit.get("policyVersion"),
        "creditScope": credit.get("creditScope"),
        "financialYear": credit.get("financialYear"),
        "asOf": credit.get("asOf"),
        "exposures": credit.get("exposures"),
        "assumptions": credit.get("assumptions"),
    }
    # 仅贷款口径写入申请额；企业口径即使 credit 里有 applyAmount 也不落库、不进报告
    if not enterprise:
        credit_section["applyAmount"] = credit.get("applyAmount")
    sections["creditSuggestion"] = credit_section
    # 记录本笔实际事实与规则，供离线逐题核对；不宣称这些就是官方要点正确率。
    covered = [json.dumps(sections[key], ensure_ascii=False)
               for key in sections if key not in ("overview",)]
    conclusion = (_enterprise_conclusion(rating, credit, fraud) if enterprise
                  else _loan_conclusion(rating, credit, fraud))
    # 企业口径没有申请日期：不拿今天冒充数据基准日，缺失就如实留空（报告写「未提供」）
    as_of = (application.get("apply_date") or finance.get("asOf") or credit.get("asOf")
             if enterprise else application.get("apply_date") or date.today().isoformat())
    return {
        "scope": scope,
        "applicationId": None if enterprise else application.get("application_id"),
        "enterpriseId": application.get("enterprise_id") or basic.get("enterprise_id"),
        "riskLevel": rating.get("riskLevel"),
        "suggestedCreditAmount": credit.get("suggestedCreditAmount"),
        "dueDiligenceConclusion": conclusion,
        "scoringPoints": covered,
        "sections": sections,
        "asOf": as_of,
    }

