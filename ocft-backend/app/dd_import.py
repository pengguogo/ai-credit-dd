"""赛题 04 事实表导入。只装载业务 csv，跳过问询参考答案和测评答案文件。

用法（cwd=ocft-backend）：
    python -m app.dd_import [目录]
目录里与样例同名的 csv 会按主键覆盖更新，其他企业的行保留。
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from .models import (EnterpriseBasic, EnterpriseFinance, EnterpriseGuarantee,
                     EnterpriseLawsuit, EnterprisePublicOpinion, EnterpriseRelated,
                     EnterpriseRisk, EnterpriseShareholder, LoanApplication,
                     SchemaRelationship)

DATA_DIR = Path(__file__).resolve().parents[1] / "scenarios" / "dd04" / "data"

# 这些文件含评测标签或参考答案，运行时导入必须跳过
_SKIP_NAMES = {"question_public.csv", "公开测试集答案.csv"}

# 源表只认已决策值；pending、空值与未知值一律从初始态「待处理」起步
_SOURCE_DECISIONS = {"approved": "approved", "rejected": "rejected"}

_INT = {"year", "loan_term_months", "employee_count", "related_enterprise_count", "overdue_count"}
_FLOAT = {
    "apply_amount", "register_capital", "registered_capital_paid", "shareholding_ratio",
    "contribution_amount", "contribution_ratio", "revenue", "net_profit", "total_assets",
    "total_liabilities", "operating_cashflow", "accounts_receivable", "inventory",
    "fixed_assets", "short_term_loan", "long_term_loan", "accounts_payable",
    "other_receivable", "prepayment", "owners_equity", "rd_expense", "sales_expense",
    "admin_expense", "finance_expense", "amount", "guarantee_amount",
    "existing_loan_balance", "overdue_amount", "external_guarantee_amount",
    "public_opinion_score",
}


def _convert(key: str, value: str):
    text = (value or "").strip()
    if key in _INT:
        return int(float(text))
    if key in _FLOAT:
        return float(text)
    return text


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [{key: _convert(key, value) for key, value in row.items()}
                for row in csv.DictReader(handle)]


def _upsert(session: Session, model, key: str, row: dict) -> None:
    found = session.query(model).filter(getattr(model, key) == row[key]).one_or_none()
    if found is None:
        session.add(model(**row))
        return
    for name, value in row.items():
        setattr(found, name, value)


def _replace_children(session: Session, model, enterprise_ids: set[str], rows: list[dict]) -> None:
    if enterprise_ids:
        session.query(model).filter(model.enterprise_id.in_(enterprise_ids)).delete(synchronize_session=False)
    for row in rows:
        session.add(model(**row))


def import_directory(session: Session, directory: Path | None = None) -> int:
    """按文件覆盖更新尽调事实。返回写入行数。答案文件即使放进目录也不会读。"""
    directory = directory or DATA_DIR
    count = 0
    loans = _rows(directory / "loan_application.csv")
    for row in loans:
        # @why 源表 status 是源系统占位（官方样例全为 pending），不是本系统的审核结果：
        #      新行从初始态 pending（待处理）起步；重复导入不覆盖已推进的业务状态。
        explicit = (row.get("status") or "").strip()
        row.pop("status", None)
        found = session.query(LoanApplication).filter(
            LoanApplication.application_id == row["application_id"]).one_or_none()
        if found is None:
            row["status"] = _SOURCE_DECISIONS.get(explicit, "pending")
        _upsert(session, LoanApplication, "application_id", row)
    count += len(loans)
    basics = _rows(directory / "enterprise_basic.csv")
    for row in basics:
        _upsert(session, EnterpriseBasic, "enterprise_id", row)
    count += len(basics)
    enterprise_ids = {row["enterprise_id"] for row in basics}
    children = [
        (EnterpriseShareholder, "enterprise_shareholder.csv"),
        (EnterpriseFinance, "enterprise_finance.csv"),
        (EnterpriseLawsuit, "enterprise_lawsuit.csv"),
        (EnterprisePublicOpinion, "enterprise_public_opinion.csv"),
        (EnterpriseRelated, "enterprise_related.csv"),
        (EnterpriseGuarantee, "enterprise_guarantee.csv"),
    ]
    for model, filename in children:
        rows = _rows(directory / filename)
        ids = {row["enterprise_id"] for row in rows} | enterprise_ids
        _replace_children(session, model, ids, rows)
        count += len(rows)
    risks = _rows(directory / "enterprise_risk.csv")
    for row in risks:
        _upsert(session, EnterpriseRisk, "enterprise_id", row)
    count += len(risks)
    relations = directory / "schema_relationships.csv"
    if relations.is_file():
        session.query(SchemaRelationship).delete(synchronize_session=False)
        with relations.open(encoding="utf-8-sig", newline="") as handle:
            for raw in csv.DictReader(handle):
                session.add(SchemaRelationship(
                    main_table=raw["主表"].strip(),
                    primary_key=raw["主键"].strip(),
                    child_table=raw["从表"].strip(),
                    foreign_key=raw["外键/关联键"].strip(),
                    note=raw["说明"].strip(),
                ))
                count += 1
    return count


def import_if_empty(session: Session) -> int:
    if session.query(LoanApplication).count() > 0:
        return 0
    return import_directory(session, DATA_DIR)


def main() -> None:
    from .db import SessionLocal, init_db
    init_db()
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR
    skipped = sorted(path.name for path in directory.glob("*.csv") if path.name in _SKIP_NAMES or "答案" in path.name)
    with SessionLocal() as session:
        imported = import_directory(session, directory)
        session.commit()
    print(f"尽调事实：写入 {imported} 行，目录 {directory}")
    if skipped:
        print(f"已跳过评测文件：{', '.join(skipped)}")


if __name__ == "__main__":
    main()
