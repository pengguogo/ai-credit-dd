"""赛题04离线逐项复核：只核对已经发布的正文，不调用模型、不改写答案。

prepare先保存同run完整脱敏证据，再读取参考文件；参考只出现在eval产物。
summarize验证复核记录的可定位性，不自动判断语义，不代替业务确认。
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


DECISIONS = {"满足", "部分满足", "不满足", "无法确认"}


def check_financial_tables(answer: str, evidence: list[dict]) -> dict:
    """只核对明确年度列的财务表；未识别的叙述不冒充已验证。"""
    from app.agent.dd_verify import _SUBJECTS

    aliases = {alias: key for key, names in _SUBJECTS.items() for alias in names}
    aliases.update({"资产总额": "totalassets", "负债总额": "totalliabilities",
                    "有息负债": "interestbearingdebt", "固定资产": "fixedassets"})
    facts: dict[tuple[int, str], set[Decimal]] = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            year = node.get("year")
            if isinstance(year, int) and isinstance(node.get("subjects"), dict):
                for key, value in node["subjects"].items():
                    if isinstance(value, (int, float)):
                        facts.setdefault((year, key.lower()), set()).add(Decimal(str(value)))
                for key, metric in (node.get("metrics") or {}).items():
                    if isinstance(metric.get("value"), (int, float)):
                        label = metric.get("name") or key
                        aliases[label] = key.lower()
                        facts.setdefault((year, key.lower()), set()).add(Decimal(str(metric["value"])))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(evidence)
    years, issues, checked = {}, [], 0
    for line in answer.splitlines():
        if not line.lstrip().startswith("|"):
            years = {}
            continue
        cells = [re.sub(r"\*|`", "", c).strip() for c in line.strip().strip("|").split("|")]
        header = {i: int(c.rstrip("年")) for i, c in enumerate(cells)
                  if re.fullmatch(r"20\d{2}年?", c)}
        if len(header) >= 2:
            years = header
            continue
        label = re.sub(r"[（(](?:万元|万|%|倍|次|天)[）)]", "", cells[0]).strip()
        key = aliases.get(label)
        if not years or not key:
            continue
        for column, year in years.items():
            cell = cells[column] if column < len(cells) else ""
            parsed = re.fullmatch(r"(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*(%|％|万元|万|倍|次|天)?", cell)
            actual, tolerance = None, Decimal(0)
            if parsed:
                actual = Decimal(parsed[1].replace(",", ""))
                tolerance = Decimal(5).scaleb(actual.as_tuple().exponent - 1)
                if parsed[2] in {"%", "％"}:
                    actual /= 100
                    tolerance /= 100
            expected = facts.get((year, key), set())
            checked += 1
            if len(expected) != 1 or actual is None or abs(actual - next(iter(expected))) > tolerance:
                issues.append({"year": year, "subject": label, "actual": cell,
                               "expected": [str(v) for v in sorted(expected)],
                               "detail": "表格值与同科目同年度证据不符或证据不唯一"})
    return {"checked": checked, "issues": issues}


def _unique(rows: list[dict], key: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        value = row.get(key)
        if not value or value in result:
            raise ValueError(f"{key}缺失或重复：{value}")
        result[value] = row
    return result


def _criteria(reference: dict, kind: str) -> list[dict]:
    fields = (("due_diligence_conclusion", "结论"), ("scoring_points", "要点")) if kind == "applications" else (
        ("reference_answer", "问询"),)
    criteria = []
    for field, label in fields:
        for index, text in enumerate(re.split(r"[;；]", reference.get(field) or ""), 1):
            if text.strip():
                criteria.append({"id": f"{field}:{index}", "category": label, "reference": text.strip(),
                                 "decision": "无法确认", "answerQuote": "", "evidenceIds": [],
                                 "reason": "尚未逐项复核"})
    if not criteria:
        raise ValueError("参考内容为空")
    return criteria


def build_dossier(results: list[dict], references: list[dict], kind: str,
                  evidence: dict[str, list[dict]]) -> dict:
    if kind not in {"applications", "questions"}:
        raise ValueError("未知参考类型")
    actual = _unique(results, "id")
    refs = _unique(references, "application_id" if kind == "applications" else "question_id")
    if actual.keys() != refs.keys():
        raise ValueError(f"结果与参考编号不一致：缺少{sorted(refs.keys() - actual.keys())}；"
                         f"多余{sorted(actual.keys() - refs.keys())}")
    items = []
    for key, result in actual.items():
        evs = evidence.get(key, [])
        ids = _unique(evs, "id")
        expected_ids = {e["id"] for e in result.get("evidence", [])}
        if set(ids) != expected_ids or any(e.get("runId") not in result.get("runIds", []) for e in evs):
            raise ValueError(f"{key}证据缺失或不属于同次run")
        answer = result.get("answer") or ""
        criteria = _criteria(refs[key], kind)
        items.append({"id": key, "status": result["status"], "runIds": result.get("runIds", []),
                      "answer": answer, "answerSha256": hashlib.sha256(answer.encode()).hexdigest(),
                      "evidence": evs, "criteria": criteria,
                      "financialTableChecks": check_financial_tables(answer, evs),
                      "criterionIds": [c["id"] for c in criteria], "findings": []})
    return {"kind": kind, "reviewerKind": "ai_assisted", "businessConfirmed": False,
            "itemIds": list(actual), "items": items,
            "scope": "离线逐项复核；摘录和证据可定位不等于业务正确。AI复核不代替业务签字或官方评分。"}


def summarize_reviews(dossier: dict) -> dict:
    items = _unique(dossier["items"], "id")
    if set(items) != set(dossier["itemIds"]):
        raise ValueError("复核记录漏题或增加题目")
    decisions, statuses = Counter(), Counter()
    unresolved, findings = [], []
    for key, row in items.items():
        if hashlib.sha256(row["answer"].encode()).hexdigest() != row["answerSha256"]:
            raise ValueError(f"{key}原始正文被修改")
        criteria = _unique(row["criteria"], "id")
        if set(criteria) != set(row["criterionIds"]):
            raise ValueError(f"{key}复核记录漏项或增加要点")
        evs = _unique(row["evidence"], "id")
        if any(e.get("runId") not in row["runIds"] for e in evs.values()):
            raise ValueError(f"{key}存在其他run的证据")
        statuses[row["status"]] += 1
        for criterion in criteria.values():
            decision = criterion["decision"]
            if decision not in DECISIONS or not criterion.get("reason", "").strip():
                raise ValueError(f"{key}判定非法或缺少理由")
            quote = criterion.get("answerQuote") or ""
            if quote and quote not in row["answer"]:
                raise ValueError(f"{key}正文摘录不存在")
            if not set(criterion.get("evidenceIds", [])) <= evs.keys():
                raise ValueError(f"{key}引用了不属于本题的证据")
            if decision in {"满足", "部分满足"} and (
                    not quote or not criterion.get("evidenceIds") or
                    row["status"] not in {"succeeded", "needs_confirmation"}):
                raise ValueError(f"{key}满足判定缺少实际正文或同run证据，或运行失败")
            decisions[decision] += 1
            if decision != "满足":
                unresolved.append({"id": key, **criterion})
        for finding in row.get("findings", []):
            if not finding.get("reason") or (finding.get("answerQuote") and finding["answerQuote"] not in row["answer"]):
                raise ValueError(f"{key}额外主张复核缺少理由或摘录不存在")
            if not set(finding.get("evidenceIds", [])) <= evs.keys():
                raise ValueError(f"{key}额外主张引用了其他run的证据")
            findings.append({"id": key, **finding})
    return {"kind": dossier["kind"], "total": len(items), "statuses": dict(statuses),
            "decisions": dict(decisions), "unresolved": unresolved, "findings": findings,
            "reviewerKind": dossier["reviewerKind"], "businessConfirmed": False,
            "scope": dossier["scope"]}


def collect_evidence(results: list[dict]) -> dict[str, list[dict]]:
    """导出完整脱敏证据，禁止用重算后的结果替代历史证据。"""
    from app.db import SessionLocal
    from app.models import Evidence
    from app.services.run_service import masked_snapshot, masked_source_ref

    output = {}
    with SessionLocal() as db:
        for result in results:
            ids = [e["id"] for e in result.get("evidence", [])]
            rows = db.query(Evidence).filter(Evidence.id.in_(ids)).order_by(Evidence.id).all()
            output[result["id"]] = [{"id": e.id, "runId": e.run_id, "contentHash": e.content_hash,
                                      "source": masked_source_ref(e), "snapshot": masked_snapshot(e)} for e in rows]
    return output


def _write(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--runs", type=Path, required=True)
    prepare.add_argument("--reference", type=Path, required=True)
    prepare.add_argument("--kind", choices=("applications", "questions"), required=True)
    prepare.add_argument("--output-dir", type=Path, required=True)
    summarize = commands.add_parser("summarize")
    summarize.add_argument("--review", type=Path, required=True)
    summarize.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            target = args.output_dir / "review.json"
            if target.exists():
                raise ValueError("复核文件已存在，请使用新目录，禁止覆盖既有判定")
            results = [json.loads(line) for line in args.runs.read_text(encoding="utf-8").splitlines() if line.strip()]
            _unique(results, "id")
            evidence = collect_evidence(results)
            args.output_dir.mkdir(parents=True, exist_ok=True)
            # 参考文件只在实际结果及同run证据独立保存后打开。
            _write(args.output_dir / "evidence.json", evidence)
            with args.reference.open(encoding="utf-8-sig", newline="") as stream:
                references = list(csv.DictReader(stream))
            dossier = build_dossier(results, references, args.kind, evidence)
            dossier["sourceHashes"] = {"runs": hashlib.sha256(args.runs.read_bytes()).hexdigest(),
                                       "reference": hashlib.sha256(args.reference.read_bytes()).hexdigest()}
            _write(target, dossier)
            print(json.dumps({"prepared": len(results), "review": str(target), "businessConfirmed": False}))
        else:
            dossier = json.loads(args.review.read_text(encoding="utf-8"))
            summary = summarize_reviews(dossier)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            _write(args.output, summary)
            csv_path = args.output.with_suffix(".csv")
            with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=("id", "criterionId", "category", "reference", "decision",
                                                            "answerQuote", "evidenceIds", "reason"))
                writer.writeheader()
                for row in dossier["items"]:
                    for criterion in row["criteria"]:
                        writer.writerow({"id": row["id"], "criterionId": criterion["id"],
                                         **{k: criterion[k] for k in writer.fieldnames[2:]}})
            print(json.dumps({"total": summary["total"], "decisions": summary["decisions"],
                              "businessConfirmed": False}, ensure_ascii=False))
    except (ValueError, KeyError) as exc:
        parser.exit(2, f"复核记录无效：{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
