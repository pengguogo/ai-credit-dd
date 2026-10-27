"""离线金额诊断，不是 Agent 专用答题路径，也不生成正式提交结果。

先重算并写出无标签事实结果，再可选读取指定参考文件评分。
真实 Agent 验证另走 eval.run，本模块只读取其已持久化证据，不重算补缺。
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re


def _interval(text: str) -> tuple[Decimal, Decimal] | None:
    if not re.fullmatch(r"\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?", str(text)):
        return None
    values = [Decimal(x) for x in str(text).split("-")]
    interval = values[0], values[-1]
    return interval if interval[0] <= interval[1] else None


def _unique(rows: list[dict], field: str) -> dict:
    mapping = {row[field]: row for row in rows}
    if len(mapping) != len(rows) or "" in mapping:
        raise ValueError(f"{field} 为空或重复")
    return mapping


def compare_amounts(actual: list[dict], reference: list[dict]) -> tuple[list[dict], dict]:
    computed = _unique(actual, "applicationId")
    refs = _unique(reference, "application_id")
    rows = []
    for key in sorted(computed.keys() | refs.keys()):
        row = computed.get(key) or {"applicationId": key, "status": "missing"}
        ref = refs.get(key) or {}
        left = _interval(row.get("systemCredit", ""))
        right = _interval(ref.get("suggested_credit_amount", ""))
        is_numeric = left is not None and right is not None
        # needs_confirmation：结论已出、待业务确认（R6），金额照常计入有效比对
        is_eligible = row["status"] in {"calculated", "succeeded", "needs_confirmation"}
        exact = is_numeric and left == right
        overlap = is_numeric and max(left[0], right[0]) <= min(left[1], right[1])
        within = is_numeric and right[0] <= left[0] <= left[1] <= right[1]
        rows.append({**row, "referenceRisk": ref.get("risk_level"),
                     "referenceCredit": ref.get("suggested_credit_amount"),
                     "referenceNumeric": right is not None,
                     "candidateRiskExact": row.get("systemRisk") == ref.get("risk_level") and bool(ref),
                     "candidateExact": exact, "eligibleExact": exact and is_eligible,
                     "eligibleOverlap": overlap and is_eligible,
                     "eligibleWithin": within and is_eligible})
    total = len(rows)
    summary = {
        "total": total, "statuses": dict(Counter(row["status"] for row in rows)),
        "numericReferenceCount": sum(row["referenceNumeric"] for row in rows),
        "referenceNonNumericCount": sum(not row["referenceNumeric"] for row in rows),
        "eligibleExactCount": sum(row["eligibleExact"] for row in rows),
        "eligibleOverlapCount": sum(row["eligibleOverlap"] for row in rows),
        "eligibleWithinCount": sum(row["eligibleWithin"] for row in rows),
        "candidateRiskExactCount": sum(row["candidateRiskExact"] for row in rows),
        "failedCount": sum(row["status"] in {"failed", "runner_error", "missing"} for row in rows),
        "exactRateAllRows": sum(row["eligibleExact"] for row in rows) / total if total else 0,
        "scope": "单字段离线比对；非数值参考不补阈值，不等于全文正确率或正式提交完成率",
    }
    return rows, summary


def calculate_facts() -> list[dict]:
    from app.db import SessionLocal
    from app.models import LoanApplication
    from app.tools.due_diligence import _pipeline
    from app.domain.errors import ToolError

    rows = []
    with SessionLocal() as db:
        for loan in db.query(LoanApplication).order_by(LoanApplication.application_id).all():
            row = {"applicationId": loan.application_id, "enterpriseId": loan.enterprise_id,
                   "applyAmount": loan.apply_amount, "status": "calculated"}
            try:
                packed = _pipeline(db, loan)
                credit = packed["credit"]
                row.update(systemRisk=credit["riskLevel"], systemCredit=credit["suggestedCreditAmount"],
                           financialYear=credit["financialYear"], asOf=credit["asOf"],
                           policyVersion=credit["policyVersion"], steps=credit["steps"],
                           exposures=credit["exposures"], conditions=credit["conditions"],
                           vetoes=packed["rating"].get("vetoes"), assumptions=credit["assumptions"])
            except ToolError as exc:
                row.update(status="failed", errorCode=exc.code, errorMessage=exc.message)
            rows.append(row)
        db.rollback()
    return rows


def _text_amounts(text: str) -> list[tuple[Decimal, Decimal]]:
    number = r"\d+(?:,\d{3})*(?:\.\d+)?"
    prefix = (r"(?:(?:建议(?:授信(?:额度|区间)?|额度|贷款额度)|授信额度)"
              r"[^\d\n]{0,24}|建议\s*\*{0,2}\s*)")
    pattern = (prefix + rf"({number}(?:\s*[-–—~至]\s*{number})?)"
               r"\s*(?:\*{0,2}\s*)(万元|万|亿元|亿)")
    amounts = []
    for value, unit in re.findall(pattern, text):
        normalized = re.sub(r"[–—~至]", "-", value)
        interval = _interval(re.sub(r"[\s,]", "", normalized))
        if interval:
            multiplier = Decimal(10000) if unit.startswith("亿") else Decimal(1)
            amounts.append((interval[0] * multiplier, interval[1] * multiplier))
    return amounts


def collect_runs(path: Path) -> list[dict]:
    from app.db import SessionLocal
    from app.models import Evidence
    from app.services.run_service import get_run, masked_snapshot

    attempts = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    _unique(attempts, "id")
    rows = []
    with SessionLocal() as db:
        for attempt in attempts:
            reports, credits = [], []
            for run_id in attempt["runIds"]:
                _, _, evidence_ids = get_run(db, run_id, "eval_runner")
                for ev in db.query(Evidence).filter(Evidence.id.in_(evidence_ids)).order_by(Evidence.id):
                    calc = (ev.source_ref or {}).get("calc")
                    if calc in {"build_dd_report", "calc_credit_limit"}:
                        (reports if calc == "build_dd_report" else credits).append((ev.id, masked_snapshot(ev)))
            found = (reports or credits)
            evidence_id, credit = found[-1] if found else (None, {})
            section = (credit.get("sections") or {}).get("creditSuggestion") or credit
            parsed = _text_amounts(attempt.get("answer") or "")
            amount = _interval(credit.get("suggestedCreditAmount", ""))
            text_match = len(set(parsed)) == 1 and parsed[0] == amount if parsed else None
            rows.append({"applicationId": attempt["id"], "status": attempt["status"],
                         "errorCode": attempt.get("errorCode"), "runIds": attempt["runIds"],
                         "evidenceId": evidence_id, "systemRisk": credit.get("riskLevel"),
                         "systemCredit": credit.get("suggestedCreditAmount"),
                         "policyVersion": section.get("policyVersion"),
                         "financialYear": section.get("financialYear"),
                         "finalTextCreditMatch": text_match,
                         "finalAmountParse": "detected" if parsed else "not_detected",
                         "answer": attempt.get("answer"), "creditEvidence": credit})
    return rows


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = ("applicationId", "status", "systemRisk", "referenceRisk", "systemCredit",
              "referenceCredit", "financialYear", "policyVersion", "candidateExact",
              "eligibleExact", "eligibleOverlap", "eligibleWithin", "finalTextCreditMatch",
              "errorCode", "runIds", "evidenceId")
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--runs", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    facts = calculate_facts()
    _write_json(args.output_dir / "facts.json", facts)
    scenario = Path(__file__).resolve().parents[1] / "scenarios" / "dd04"
    hashes = {str(path.relative_to(scenario)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in [*sorted((scenario / "data").glob("*.csv")), scenario / "credit_model.yaml",
                           scenario / "scorecard.yaml"]}
    backend = scenario.parents[1]
    runtime_hashes = {name: hashlib.sha256((backend / name).read_bytes()).hexdigest()
                      for name in ("app/tools/dd_calc.py", "app/tools/due_diligence.py")}
    summary = {"scope": "只读金额诊断，不是正式提交结果",
               "sourceHashes": hashes, "runtimeHashes": runtime_hashes}
    runs = collect_runs(args.runs) if args.runs else None
    if runs is not None:
        _write_json(args.output_dir / "agent-evidence.json", runs)
    # @why 标签只在事实及已持久化 Agent 结果独立写出后打开，不可能参与上述计算。
    if args.reference:
        with args.reference.open(encoding="utf-8-sig", newline="") as stream:
            reference = list(csv.DictReader(stream))
        rows, summary["facts"] = compare_amounts(facts, reference)
        _write_csv(args.output_dir / "facts-comparison.csv", rows)
        if runs is not None:
            rows, summary["agent"] = compare_amounts(runs, reference)
            _write_csv(args.output_dir / "agent-comparison.csv", rows)
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
