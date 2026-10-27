"""点数制评分卡（score-points-v2）：只用合成事实，不读取公开参考或评测标签。"""
import pytest

from app.tools import dd_calc
from app.tools.dd_config import load_config


def _facts(**overrides):
    subjects = {"revenue": 10000, "netProfit": 1200, "totalAssets": 10000,
                "totalLiabilities": 3000, "ownersEquity": 7000, "operatingCashflow": 1500,
                "accountsReceivable": 1000, "otherReceivable": 100}
    subjects.update(overrides.pop("subjects", {}))
    bundle = {"basic": {"enterprise_id": "synthetic", "legal_person_dishonest": "否",
                        "legal_person_consumption_limit": "否"},
              "risk": {"overdue_count": 0, "public_opinion_score": 90},
              "lawsuits": [], "guarantees": [], "related": []}
    for key, value in overrides.items():
        if key in ("risk", "basic"):
            bundle[key].update(value)
        else:
            bundle[key] = value
    finance = {"unit": "万元", "years": [{"year": 2023, "subjects": subjects}]}
    return bundle, finance


def _rate(bundle, finance):
    return dd_calc.rate_risk(bundle, finance, {}, {}, {"rules": []}, load_config("scorecard.yaml"))


def test_clean_facts_score_zero_points_low_risk():
    rating = _rate(*_facts())
    assert rating["score"] == 0 and rating["riskLevel"] == "低风险"
    assert all(d["source"] == "calculated" for d in rating["dimensions"])
    assert rating["vetoes"] == [] and rating["needsManualReview"] is False


@pytest.mark.parametrize("debt,points", [(0.4499, 0), (0.45, 1), (0.60, 2), (0.70, 3)])
def test_threshold_edges_are_inclusive_for_higher_worse(debt, points):
    bundle, finance = _facts(subjects={"totalLiabilities": debt * 10000})
    dim = next(d for d in _rate(bundle, finance)["dimensions"] if d["dimension"] == "asset_liability_ratio")
    assert dim["points"] == points


@pytest.mark.parametrize("total,level", [(1, "低风险"), (2, "低-中风险"), (4, "低-中风险"),
                                         (5, "中风险"), (19, "中风险"), (20, "高风险")])
def test_level_bands(total, level):
    cfg = load_config("scorecard.yaml")
    band = next(b["name"] for b in cfg["levels"] if b.get("max_points") is None or total <= b["max_points"])
    assert band == level


def test_moderate_weaknesses_accumulate_to_medium_risk():
    """负债率 60–70%、净利率 <3%、现金流/净利 <1、舆情 <80 叠加 → 中风险（单项都未到警戒线）。"""
    bundle, finance = _facts(subjects={"totalLiabilities": 6500, "netProfit": 200, "operatingCashflow": 180},
                             risk={"public_opinion_score": 70})
    rating = _rate(bundle, finance)
    assert rating["score"] == 2 + 3 + 1 + 1
    assert rating["riskLevel"] == "中风险"


def test_fraud_hits_do_not_veto_but_credit_flags_do():
    bundle, finance = _facts()
    many_hits = {"rules": [{"ruleId": f"F0{i}", "hit": True, "confidence": "high"} for i in range(1, 5)]}
    cfg = load_config("scorecard.yaml")
    assert dd_calc.rate_risk(bundle, finance, {}, {}, many_hits, cfg)["vetoes"] == []
    bundle["basic"]["legal_person_consumption_limit"] = "是"
    rating = dd_calc.rate_risk(bundle, finance, {}, {}, many_hits, cfg)
    assert rating["riskLevel"] == "高风险" and "法定代表人限高" in rating["vetoes"]


def test_missing_indicator_is_not_scored_as_zero_silently():
    bundle, finance = _facts(subjects={"ownersEquity": 0})
    rating = _rate(bundle, finance)
    assert "涉诉金额/净资产" in rating["missingIndicators"]
    assert rating["needsManualReview"] is True


def test_identity_does_not_change_rating():
    bundle, finance = _facts(subjects={"totalLiabilities": 6500})
    first = _rate(bundle, finance)
    bundle["basic"]["enterprise_id"] = "another-borrower"
    second = _rate(bundle, finance)
    assert (first["score"], first["riskLevel"]) == (second["score"], second["riskLevel"])
