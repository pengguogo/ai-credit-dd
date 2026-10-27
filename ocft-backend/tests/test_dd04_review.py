"""dd04-business-acceptance 离线复核记录，不读取官方参考夹具。"""
import copy

import pytest

from eval.dd04_review import build_dossier, summarize_reviews, check_financial_tables


def sample():
    result = {"id": "case-a", "status": "succeeded", "answer": "营业收入80万元，建议审慎。",
              "runIds": ["run_a"], "evidence": [{"id": "ev_a"}]}
    evidence = [{"id": "ev_a", "runId": "run_a", "snapshot": {"revenue": 80}}]
    reference = {"application_id": "case-a", "due_diligence_conclusion": "营业收入80万元",
                 "scoring_points": "财务分析;审慎建议"}
    return result, evidence, reference


def test_dossier_preserves_full_evidence_and_unreviewed_status():
    """TC-1 未复核不能自动通过；原文、参考和完整证据分开。"""
    result, evidence, reference = sample()
    dossier = build_dossier([result], [reference], "applications", {"case-a": evidence})
    row = dossier["items"][0]
    assert row["answer"] == result["answer"] and row["evidence"] == evidence
    assert len(row["criteria"]) == 3
    assert all(c["decision"] == "无法确认" for c in row["criteria"])
    summary = summarize_reviews(dossier)
    assert summary["decisions"] == {"无法确认": 3}
    assert summary["businessConfirmed"] is False


@pytest.mark.parametrize("fault", ["duplicate", "missing", "other_run"])
def test_dossier_rejects_invalid_result_sets(fault):
    """TC-2、TC-3 拒绝重复、遗漏或串run证据。"""
    result, evidence, reference = sample()
    results = [result, result] if fault == "duplicate" else ([] if fault == "missing" else [result])
    if fault == "other_run":
        evidence[0]["runId"] = "run_b"
    with pytest.raises(ValueError):
        build_dossier(results, [reference], "applications", {"case-a": evidence})


@pytest.mark.parametrize("fault", ["quote", "evidence", "no_evidence", "missing_criterion"])
def test_review_requires_real_quote_and_same_run_evidence(fault):
    """TC-3 不存在的摘录、串题证据或漏项不能出通过汇总。"""
    result, evidence, reference = sample()
    dossier = build_dossier([result], [reference], "applications", {"case-a": evidence})
    row = dossier["items"][0]
    criterion = row["criteria"][0]
    criterion.update(decision="满足", answerQuote="营业收入80万元", evidenceIds=["ev_a"],
                     reason="对应同次证据的营业收入科目和金额。")
    if fault == "quote":
        criterion["answerQuote"] = "净利润80万元"
    elif fault == "evidence":
        criterion["evidenceIds"] = ["ev_b"]
    elif fault == "no_evidence":
        criterion["evidenceIds"] = []
    else:
        row["criteria"].pop()
    with pytest.raises(ValueError):
        summarize_reviews(dossier)


def test_review_counts_partial_failure_without_business_signoff():
    """TC-4 AI复核不是业务签字，部分满足和不满足单列。"""
    result, evidence, reference = sample()
    dossier = build_dossier([result], [reference], "applications", {"case-a": evidence})
    for criterion, decision in zip(dossier["items"][0]["criteria"], ("满足", "部分满足", "不满足")):
        criterion.update(decision=decision, answerQuote="营业收入80万元", evidenceIds=["ev_a"],
                         reason="AI逐项复核记录，仍需业务人员确认。")
    summary = summarize_reviews(dossier)
    assert summary["decisions"] == {"满足": 1, "部分满足": 1, "不满足": 1}
    assert summary["businessConfirmed"] is False
    broken = copy.deepcopy(dossier)
    broken["items"][0]["status"] = "failed"
    with pytest.raises(ValueError):
        summarize_reviews(broken)


def test_financial_tables_bind_subject_year_sign_and_units():
    """TC-1、TC-3 表格核验不得跨科目或年度匹配同值。"""
    evidence = [{"snapshot": {"years": [
        {"year": 2020, "subjects": {"revenue": 100, "operatingCashflow": -10},
         "metrics": {"assetLiabilityRatio": {"name": "资产负债率", "value": 0.4}}},
        {"year": 2021, "subjects": {"revenue": 200, "operatingCashflow": 10},
         "metrics": {"assetLiabilityRatio": {"name": "资产负债率", "value": 0.5}}}]}}]
    text = "|科目|2020|2021|\n|---|---|---|\n|营业收入（万元）|100|200|\n|经营现金流|-10|10|\n|资产负债率|40%|50%|"
    assert check_financial_tables(text, evidence) == {"checked": 6, "issues": []}
    issues = check_financial_tables(text.replace("|-10|10|", "|10|-10|"), evidence)["issues"]
    assert len(issues) == 2 and {i["year"] for i in issues} == {2020, 2021}
    assert check_financial_tables(text.replace("|100|200|", "|200|100|"), evidence)["issues"]
