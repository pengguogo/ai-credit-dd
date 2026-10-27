"""赛题 04 原始业务数据离线体检，不读取问询参考答案和标准答案，不修改输入。"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from eval.dd04 import read_table

# 原始包表头快照；只含字段名，不含样本、标签或结论。
SCHEMAS = {
    "enterprise_basic": (
        "enterprise_id enterprise_name credit_code legal_person legal_person_id "
        "register_capital registered_capital_paid establish_date enterprise_type industry "
        "register_address business_scope employee_count related_enterprise_count "
        "business_status legal_person_dishonest legal_person_consumption_limit "
        "actual_controller"
    ).split(),
    "enterprise_finance": (
        "enterprise_id year revenue net_profit total_assets total_liabilities "
        "operating_cashflow accounts_receivable inventory fixed_assets short_term_loan "
        "long_term_loan accounts_payable other_receivable prepayment owners_equity rd_expense "
        "sales_expense admin_expense finance_expense audit_opinion"
    ).split(),
    "enterprise_guarantee": (
        "enterprise_id guaranteed_party guarantee_amount guarantee_type guarantee_period "
        "is_overdue"
    ).split(),
    "enterprise_lawsuit": (
        "enterprise_id case_id case_number case_type cause filing_date case_status "
        "litigation_role amount"
    ).split(),
    "enterprise_public_opinion": (
        "enterprise_id event_id event_date event_type event_source event_content sentiment "
        "impact_level"
    ).split(),
    "enterprise_related": (
        "enterprise_id related_enterprise_name relation_type shareholding_ratio "
        "is_guarantee_circle"
    ).split(),
    "enterprise_risk": (
        "enterprise_id existing_loan_balance overdue_count overdue_amount "
        "external_guarantee_amount public_opinion_score risk_level_summary abnormal_operation"
    ).split(),
    "enterprise_shareholder": (
        "enterprise_id shareholder_name shareholder_type shareholding_ratio contribution_amount "
        "contribution_ratio"
    ).split(),
    "loan_application": (
        "application_id enterprise_id apply_amount loan_purpose loan_term_months apply_date "
        "guarantee_type"
    ).split(),
}

KEYS = {
    "enterprise_basic": ("enterprise_id",),
    "loan_application": ("application_id",),
    "enterprise_finance": ("enterprise_id", "year"),
    "enterprise_risk": ("enterprise_id",),
    "enterprise_lawsuit": ("case_id",),
    "enterprise_public_opinion": ("event_id",),
    "enterprise_shareholder": ("enterprise_id", "shareholder_name"),
    "enterprise_related": ("enterprise_id", "related_enterprise_name", "relation_type"),
    "enterprise_guarantee": ("enterprise_id", "guaranteed_party", "guarantee_period"),
}
NUMERIC = {
    "enterprise_basic": "register_capital registered_capital_paid employee_count related_enterprise_count",
    "enterprise_finance": "year revenue net_profit total_assets total_liabilities operating_cashflow accounts_receivable inventory fixed_assets short_term_loan long_term_loan accounts_payable other_receivable prepayment owners_equity rd_expense sales_expense admin_expense finance_expense",
    "enterprise_shareholder": "shareholding_ratio contribution_amount contribution_ratio",
    "enterprise_related": "shareholding_ratio",
    "enterprise_guarantee": "guarantee_amount",
    "enterprise_lawsuit": "amount",
    "enterprise_risk": "existing_loan_balance overdue_count overdue_amount external_guarantee_amount public_opinion_score",
    "loan_application": "apply_amount loan_term_months",
}
INTEGER = {"year", "employee_count", "related_enterprise_count", "overdue_count", "loan_term_months"}


def audit_data(folder: Path) -> dict:
    tables = {}
    issues = []

    def issue(level, code, table, row=None, field=None, message=""):
        # 报告只记录定位信息，不复制企业姓名、证件号或财务原值。
        issues.append({"level": level, "code": code, "table": table,
                       "row": row, "field": field, "message": message})

    for table, schema in SCHEMAS.items():
        try:
            rows = read_table(folder / f"{table}.csv", tuple(schema))
        except (OSError, UnicodeError, ValueError, csv.Error) as exc:
            issue("error", "table_invalid", table, message=type(exc).__name__)
            continue
        tables[table] = rows
        with (folder / f"{table}.csv").open(encoding="utf-8-sig", newline="") as stream:
            extra = set(next(csv.reader(stream))) - set(schema)
        if extra:
            issue("warning", "extra_columns", table, message="额外列未纳入体检，请人工确认")
        counts = Counter(tuple(row[k] for k in KEYS[table]) for row in rows)
        for line, row in enumerate(rows, 2):
            count = counts[tuple(row[k] for k in KEYS[table])]
            if count > 1:
                inferred_key = table in ("enterprise_shareholder", "enterprise_related", "enterprise_guarantee")
                issue("warning" if inferred_key else "error", "duplicate_key", table,
                      row=line, field=",".join(KEYS[table]),
                      message=f"候选键重复 {count} 次；无官方主键的明细表需人工确认")
            for field in schema:
                value = row[field]
                if not value:
                    issue("error" if field in KEYS[table] or field == "enterprise_id" else "warning",
                          "empty_value", table, line, field)
                    continue
                if field in NUMERIC.get(table, "").split():
                    try:
                        number = Decimal(value)
                        if not number.is_finite() or (field in INTEGER and number != number.to_integral_value()):
                            raise InvalidOperation
                        if field == "year" and not 1 <= number <= 9999:
                            raise InvalidOperation
                    except InvalidOperation:
                        issue("error", "invalid_number", table, line, field)
                if field.endswith("_date"):
                    try:
                        date.fromisoformat(value)
                    except ValueError:
                        issue("error", "invalid_date", table, line, field)

    enterprises = {r["enterprise_id"] for r in tables.get("enterprise_basic", [])}
    for table, rows in tables.items():
        if table != "enterprise_basic" and "enterprise_basic" in tables:
            for line, row in enumerate(rows, 2):
                if row["enterprise_id"] not in enterprises:
                    issue("error", "orphan_enterprise", table, line, "enterprise_id")
    for table in ("enterprise_finance", "enterprise_risk"):
        present = {r["enterprise_id"] for r in tables.get(table, [])}
        missing = enterprises - present
        if missing:
            issue("warning", "missing_enterprise_records", table,
                  message=f"有 {len(missing)} 家企业缺记录")

    finances = tables.get("enterprise_finance", [])
    for line, row in enumerate(finances, 2):
        try:
            values = [Decimal(row[c]) for c in ("total_assets", "total_liabilities", "owners_equity")]
            if all(v.is_finite() for v in values) and abs(values[0] - values[1] - values[2]) > Decimal("0.01"):
                issue("warning", "balance_mismatch", "enterprise_finance", line,
                      message="资产与负债加权益差额超过 0.01 原始金额单位；仅作数据勾稽检查")
        except InvalidOperation:
            pass  # 上面的字段类型检查已记录
    for enterprise in enterprises:
        years = set()
        for row in finances:
            if row["enterprise_id"] == enterprise:
                try:
                    years.add(int(row["year"]))
                except ValueError:
                    pass
        if len(years) != 3 or (years and max(years) - min(years) != 2):
            issue("warning", "three_years_incomplete", "enterprise_finance",
                  message="一家企业不满足连续三年记录；具体年份窗口仍需业务口径确认")
    # 只检查关系说明的结构。最后一行是时点关联，不能当作 year=apply_date 的等值外键。
    try:
        relations = read_table(folder / "schema_relationships.csv", ("主表", "主键", "从表", "外键/关联键", "说明"))
        for line, relation in enumerate(relations, 2):
            for table_col, key_col in (("主表", "主键"), ("从表", "外键/关联键")):
                schema = SCHEMAS.get(relation[table_col], [])
                if not schema or not set(k.strip() for k in relation[key_col].split("+")) <= set(schema):
                    issue("error", "invalid_relationship", "schema_relationships", line, key_col)
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        issue("error", "table_invalid", "schema_relationships", message=type(exc).__name__)
    return {"passed": not any(i["level"] == "error" for i in issues),
            "rowCounts": {name: len(rows) for name, rows in tables.items()},
            "issues": issues,
            "notes": ["实物为 9 张业务表；提交说明称 10 张，待负责人确认，未虚构额外业务表。",
                      "明细表采用候选业务键检查重复，最终数据库主键由数据负责人确定。",
                      "不读取 question_public.csv、公开测试集答案.csv；不导入数据库、不修改原文件。",
                      "金额单位、比率口径、财务时点和缺失科目须业务确认；体检通过不代表可授信。",
                      "现有科目缺流动资产、流动负债、营业成本；不推算流动/速动比率或毛利率。"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.resolve().is_relative_to(args.data_dir.resolve()):
        parser.error("报告输出目录必须在原始数据目录之外")
    report = audit_data(args.data_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "data-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 赛题 04 数据体检", "", f"结构检查通过：{report['passed']}（warning 仍需人工复核）", "",
             "| 表 | 数据行数 |", "|---|---:|"]
    lines += [f"| {table} | {count} |" for table, count in report["rowCounts"].items()]
    lines += ["", "## 定位清单", "", "| 级别 | 代码 | 表 | CSV 行 | 字段 | 说明 |", "|---|---|---|---|---|---|"]
    lines += ["| " + " | ".join(str(i[k] or "—") for k in ("level", "code", "table", "row", "field", "message")) + " |" for i in report["issues"]]
    lines += ["", "## 范围与待确认", ""] + ["- " + note for note in report["notes"]]
    (args.output_dir / "data-audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "issueCount": len(report["issues"]), "output": str(args.output_dir)}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
