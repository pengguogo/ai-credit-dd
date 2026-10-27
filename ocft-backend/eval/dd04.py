"""赛题 04 离线准备与提交格式校验；不调用模型，不读取标准答案。

cwd=ocft-backend: python -m eval.dd04 --help
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from eval.dataset import DatasetError

RESULT_COLUMNS = (
    "application_id", "enterprise_id", "risk_level", "suggested_credit_amount",
    "due_diligence_conclusion", "scoring_points",
)


def read_table(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        header = reader.fieldnames or []
        if len(set(header)) != len(header) or not set(required) <= set(header):
            raise DatasetError(f"{path.name}: 表头重复或缺少必需列 {required}")
        rows = []
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise DatasetError(f"{path.name}:{line}: 列数与表头不一致")
            if not any(value.strip() for value in row.values()):
                continue
            rows.append({key: value.strip() for key, value in row.items()})
        if not rows:
            raise DatasetError(f"{path.name}: 数据为空")
        return rows


def prepare_inputs(path: Path, kind: str, scenario_id: str) -> list[dict]:
    """从字段白名单构造 runner 输入；任何额外列（含答案列）都被丢弃。"""
    if not scenario_id.strip():
        raise DatasetError("必须显式指定已实现的场景 ID")
    key = "application_id" if kind == "applications" else "question_id"
    required = (key, "enterprise_id") + (() if kind == "applications" else ("question",))
    rows = read_table(path, required)
    seen = set()
    items = []
    for line, row in enumerate(rows, 2):
        if any(not row[field] for field in required) or row[key] in seen:
            raise DatasetError(f"{path.name}:{line}: 必需字段为空或编号重复")
        seen.add(row[key])
        context = f"企业编号：{row['enterprise_id']}。"
        question = (f"请对贷款申请 {row[key]} 完成企业信贷尽调，并提供结论与证据。"
                    if kind == "applications" else row["question"])
        items.append({"id": row[key], "question": context + question, "scenarioId": scenario_id})
    return items


def validate_results(applications: Path, results: Path) -> dict:
    """只检查结构与完整性；不评价评级、额度或结论的业务正确性。"""
    inputs = read_table(applications, ("application_id", "enterprise_id"))
    mapping = {}
    for row in inputs:
        key = row["application_id"]
        if not key or not row["enterprise_id"] or key in mapping:
            raise DatasetError("申请输入存在空编号、空企业编号或重复申请编号")
        mapping[key] = row["enterprise_id"]
    rows = read_table(results, RESULT_COLUMNS)
    errors = []
    if not results.read_bytes().startswith(b"\xef\xbb\xbf"):
        errors.append({"code": "encoding", "message": "结果 CSV 必须使用 utf-8-sig"})
    with results.open(encoding="utf-8-sig", newline="") as stream:
        if tuple(next(csv.reader(stream))) != RESULT_COLUMNS:
            errors.append({"code": "columns", "message": "列名与顺序必须严格匹配官方六列"})
    counts = Counter(row["application_id"] for row in rows)
    for key, count in counts.items():
        if count > 1:
            errors.append({"code": "duplicate", "applicationId": key})
    for key in sorted(mapping.keys() - counts.keys()):
        errors.append({"code": "missing", "applicationId": key})
    for line, row in enumerate(rows, 2):
        key = row["application_id"]
        if key not in mapping:
            errors.append({"code": "unknown_application", "row": line, "applicationId": key})
        elif row["enterprise_id"] != mapping[key]:
            errors.append({"code": "enterprise_mismatch", "row": line, "applicationId": key})
        for column in RESULT_COLUMNS:
            if not row[column]:
                errors.append({"code": "empty_field", "row": line, "column": column})
    return {"passed": not errors, "expectedCount": len(mapping), "actualCount": len(rows),
            "errors": errors, "scope": "仅格式与完整性，不代表业务正确或正式答题成功"}


# @why 已给出结论的终态：needs_confirmation 是「结论已出、待业务确认后生效」（红线 R6 留痕流程），
#      结论本身完整，应进入结果文件；另在状态清单里标明待确认，不混同为已确认。
CONCLUDED_STATUSES = frozenset({"succeeded", "needs_confirmation"})
STATUS_COLUMNS = ("application_id", "status", "pending_confirmation", "error_code", "run_id")


def _snapshot(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value or {}


def load_run_evidence(run_ids: list[str]) -> list[dict]:
    """读取同次 run 已落库的证据（完整快照，PII 掩码后）。不重算、不补缺。"""
    from app.db import SessionLocal
    from app.models import Evidence
    from app.services.run_service import masked_snapshot

    with SessionLocal() as db:
        rows = (db.query(Evidence).filter(Evidence.run_id.in_(run_ids))
                .order_by(Evidence.created_at, Evidence.id).all())
        return [{"sourceRef": row.source_ref or {}, "snapshot": masked_snapshot(row)} for row in rows]


def _structured_result(evidence: list[dict]) -> dict:
    """从证据里取工具算出的结构化结论：报告优先，缺报告时用评级与额度证据。"""
    found: dict[str, dict] = {}
    for item in evidence:
        calc = (item.get("sourceRef") or {}).get("calc")
        if calc in {"rate_risk", "calc_credit_limit", "build_dd_report"}:
            found[calc] = _snapshot(item.get("snapshot"))   # 同类取最后一条
    report = found.get("build_dd_report") or {}
    rating = found.get("rate_risk") or {}
    credit = found.get("calc_credit_limit") or {}
    points = report.get("scoringPoints")
    return {
        "risk_level": report.get("riskLevel") or rating.get("riskLevel") or credit.get("riskLevel"),
        "suggested_credit_amount": report.get("suggestedCreditAmount") or credit.get("suggestedCreditAmount"),
        "due_diligence_conclusion": report.get("dueDiligenceConclusion"),
        "scoring_points": ";".join(points) if isinstance(points, list) else points,
    }


def export_results(applications: Path, runs: Path, output: Path,
                   evidence_loader=load_run_evidence) -> dict:
    """eval.run 结果 → 官方六列 CSV（utf-8-sig）+ 同目录状态清单。不读取任何参考答案。"""
    inputs = read_table(applications, ("application_id", "enterprise_id"))
    attempts = {}
    for line in runs.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            attempts[item["id"]] = item
    rows, status_rows, summary = [], [], Counter()
    for app in inputs:
        key = app["application_id"]
        attempt = attempts.get(key)
        status = attempt["status"] if attempt else "missing"
        run_ids = (attempt or {}).get("runIds") or []
        result = _structured_result(evidence_loader(run_ids)) if run_ids and status in CONCLUDED_STATUSES else {}
        if result and (attempt or {}).get("answer"):
            # 六列交付保留实际发布的完整报告，不能用工具的短摘要替代正文。
            result["due_diligence_conclusion"] = attempt["answer"]
        concluded = status in CONCLUDED_STATUSES and all(result.get(c) for c in RESULT_COLUMNS[2:])
        if not concluded:
            # 没有结论时如实写明原因，不用模板结论填空
            reason = f"未生成结论（{status}{'/' + attempt['errorCode'] if attempt and attempt.get('errorCode') else ''}）"
            result = {column: reason for column in RESULT_COLUMNS[2:]}
        rows.append({"application_id": key, "enterprise_id": app["enterprise_id"], **result})
        status_rows.append({"application_id": key, "status": status,
                            "pending_confirmation": "是" if status == "needs_confirmation" and concluded else "否",
                            "error_code": (attempt or {}).get("errorCode") or "",
                            "run_id": run_ids[-1] if run_ids else ""})
        summary["concluded" if concluded else "notConcluded"] += 1
        summary[status] += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    status_path = output.with_name(output.stem + "-status.csv")
    with status_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=STATUS_COLUMNS)
        writer.writeheader()
        writer.writerows(status_rows)
    return {"output": str(output), "statusFile": str(status_path), "total": len(rows),
            "concluded": summary["concluded"], "notConcluded": summary["notConcluded"],
            "pendingConfirmation": [r["application_id"] for r in status_rows if r["pending_confirmation"] == "是"],
            "statuses": {k: v for k, v in summary.items() if k not in {"concluded", "notConcluded"}},
            "scope": "结论取自同次 run 已落库的工具证据；needs_confirmation 为结论已出、待业务确认"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="仅生成不含标签的 JSONL，不运行 Agent")
    prepare.add_argument("--input", type=Path, required=True)
    prepare.add_argument("--kind", choices=("applications", "questions"), required=True)
    prepare.add_argument("--scenario-id", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", help="校验官方六列结果 CSV")
    validate.add_argument("--applications", type=Path, required=True)
    validate.add_argument("--results", type=Path, required=True)
    export = commands.add_parser("export", help="eval.run 结果导出官方六列 CSV（含待业务确认的结论）")
    export.add_argument("--applications", type=Path, required=True)
    export.add_argument("--runs", type=Path, required=True, help="eval.run 输出的 results.jsonl")
    export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "export":
            summary = export_results(args.applications, args.runs, args.output)
            summary["validation"] = validate_results(args.applications, args.output)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0 if summary["validation"]["passed"] else 1
        if args.command == "prepare":
            items = prepare_inputs(args.input, args.kind, args.scenario_id)
            if args.output.resolve() == args.input.resolve():
                raise DatasetError("输出不能覆盖输入文件")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items),
                                   encoding="utf-8")
            print(json.dumps({"prepared": len(items), "output": str(args.output),
                              "executed": False}, ensure_ascii=False))
            return 0
        report = validate_results(args.applications, args.results)
    except (OSError, UnicodeError, csv.Error, DatasetError) as exc:
        report = {"passed": False, "errors": [{"code": "invalid_input", "message": str(exc)}]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
