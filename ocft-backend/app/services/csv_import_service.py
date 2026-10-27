"""CSV增量新增：先校验全部记录，已有事实不更新；事实与操作审计一起提交。"""
import csv
import hashlib
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from threading import Lock

from sqlalchemy import Float, Integer, String
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..api_errors import ApiError
from ..config import settings
from ..models import (CsvImportAudit, EnterpriseBasic, EnterpriseFinance,
                      EnterpriseGuarantee, EnterpriseLawsuit, EnterprisePublicOpinion,
                      EnterpriseRelated, EnterpriseRisk, EnterpriseShareholder,
                      LoanApplication)
from ..schemas import CsvImportIn

TABLES = {
    "enterprise_basic.csv": (EnterpriseBasic, ("enterprise_id",)),
    "enterprise_finance.csv": (EnterpriseFinance, ("enterprise_id", "year")),
    "enterprise_shareholder.csv": (EnterpriseShareholder, ("enterprise_id", "shareholder_name", "shareholder_type")),
    "enterprise_lawsuit.csv": (EnterpriseLawsuit, ("case_id",)),
    "enterprise_public_opinion.csv": (EnterprisePublicOpinion, ("event_id",)),
    "enterprise_related.csv": (EnterpriseRelated, ("enterprise_id", "related_enterprise_name", "relation_type")),
    "enterprise_guarantee.csv": (EnterpriseGuarantee, ("enterprise_id", "guaranteed_party", "guarantee_type", "guarantee_period")),
    "enterprise_risk.csv": (EnterpriseRisk, ("enterprise_id",)),
    "loan_application.csv": (LoanApplication, ("application_id",)),
}
# @why 源表 status 是占位字段（官方样例全为 pending），不是本系统的审核结果：
#       缺列、空值或 pending 一律按初始态「待处理」入库，避免没出尽调报告就显示待审核。
_SOURCE_STATUS = {
    "pending_dd": "pending", "pending": "pending",
    "pending_review": "pending_review",
    "approved": "approved", "rejected": "rejected",
}
# @why 人工审核留痕（review_reason / reviewed_by / reviewed_at）由审核流程写入，
#      不属于源 CSV 字段：表头校验不要求，入库保持 NULL，重复导入也不会拿 NULL 覆盖审核记录。
_OPTIONAL_COLUMNS = {
    "loan_application.csv": frozenset({"review_reason", "reviewed_by", "reviewed_at"}),
}
_OPTIONAL_DEFAULTS = {
    "loan_application.csv": {"status": "pending"},
}
_IMPORT_LOCK = Lock()


def _value(column, text):
    value = text.strip()
    if not value:
        if column.nullable:
            return None
        raise ValueError("必填字段为空")
    if isinstance(column.type, (Integer, Float)):
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise ValueError("需要有效数字") from None
        if not number.is_finite():
            raise ValueError("不允许NaN或无穷值")
        if isinstance(column.type, Integer):
            if number != number.to_integral_value() or not -(2**31) <= number < 2**31:
                raise ValueError("需要32位整数，不能截断小数")
            return int(number)
        result = float(number)
        if result == float("inf") or result == float("-inf"):
            raise ValueError("数字超出范围")
        return result
    if isinstance(column.type, String) and column.type.length and len(value) > column.type.length:
        raise ValueError("文本超出字段长度限制")
    if column.name.endswith("_date"):
        return _normalize_date(value)
    return value


# 年 + 分隔符（- / .）+ 月 + 同一分隔符 + 日；月日可不补零
_DATE_RE = re.compile(r"(\d{4})([-/.])(\d{1,2})\2(\d{1,2})")


def _normalize_date(value: str) -> str:
    """兼容 2008-05-12 / 2008/5/12 / 2008.5.12，统一存为 ISO 的 YYYY-MM-DD。

    @why 库里已有数据与工具查询都按 ISO 字符串比较日期；入库前规范化，
         避免同一天因写法不同被当成两条记录或比较出错。
    """
    match = _DATE_RE.fullmatch(value)
    if match:
        try:
            return date(int(match[1]), int(match[3]), int(match[4])).isoformat()
        except ValueError:
            pass
    raise ValueError("日期格式无效，支持 YYYY-MM-DD、YYYY/M/D、YYYY.M.D")


def import_csv_files(db: Session, payload: CsvImportIn, actor_id: str) -> tuple[dict, int]:
    # 与当前单进程部署一致，防止没有物理唯一约束的明细候选键并发重复。
    # 多worker或其他进程同时写库需要另行确认数据库级唯一键，不能靠此锁保证。
    with _IMPORT_LOCK:
        return _import_csv_files(db, payload, actor_id)


def _import_csv_files(db: Session, payload: CsvImportIn, actor_id: str) -> tuple[dict, int]:
    if len(actor_id) > 64:
        raise ApiError(400, "invalid_actor_id", "身份标识长度超过64")
    if sum(len(f.content.encode("utf-8")) for f in payload.files) > settings.csv_import_max_bytes:
        raise ApiError(413, "csv_import_too_large", "CSV内容超过导入大小限制")
    report = {"importId": "imp_" + uuid4().hex, "status": "imported", "added": 0,
              "skipped": 0, "files": [], "errors": []}
    parsed, seen_files, file_hashes = [], set(), []
    row_count = 0

    def error(name, row, field, code, message):
        # 不回显字段值、原始行、数据库错误或任意上传文件名。
        if len(report["errors"]) < 200:
            report["errors"].append({"fileName": name if name in TABLES else "",
                                     "row": row, "field": field,
                                     "errorCode": code, "message": message})

    for file in payload.files:
        name = file.file_name
        if name not in TABLES or name in seen_files:
            error(name, 1, "", "invalid_file", "文件不在业务CSV白名单中或重复上传")
            continue
        seen_files.add(name)
        model, keys = TABLES[name]
        columns = {c.name: c for c in model.__table__.columns if c.name != "id"}
        stats = {"fileName": name, "added": 0, "skipped": 0}
        report["files"].append(stats)
        file_hashes.append({"fileName": name, "sha256": hashlib.sha256(file.content.encode()).hexdigest()})
        reader = csv.reader(io.StringIO(file.content.lstrip("\ufeff"), newline=""), strict=True)
        try:
            header = next(reader, [])
            header_set = set(header)
            defaults = {
                field: value for field, value in _OPTIONAL_DEFAULTS.get(name, {}).items()
                if field not in header_set
            }
            required = set(columns) - set(defaults) - _OPTIONAL_COLUMNS.get(name, frozenset())
            if len(header) != len(header_set) or header_set != required:
                error(name, 1, "", "invalid_columns", "表头必须完整匹配该业务表，不能包含额外列")
                continue
            for index, cells in enumerate(reader, 2):
                if not cells:
                    continue
                row_count += 1
                if row_count > settings.csv_import_max_rows:
                    raise ApiError(413, "csv_import_too_many_rows", "CSV记录数超过限制")
                if len(cells) != len(header):
                    error(name, index, "", "invalid_row", "记录列数与表头不一致")
                    continue
                data, valid = dict(defaults), True
                for field, text in zip(header, cells):
                    try:
                        if field == "status" and name == "loan_application.csv" and not text.strip():
                            data[field] = "pending"
                            continue
                        data[field] = _value(columns[field], text)
                    except ValueError as exc:
                        valid = False
                        error(name, index, field, "invalid_value", str(exc))
                if valid and name == "loan_application.csv":
                    status = data.get("status", "pending")
                    if status not in _SOURCE_STATUS:
                        valid = False
                        error(name, index, "status", "invalid_value",
                              "status 只能是 pending / pending_review / approved / rejected（空值记为待处理）")
                    else:
                        data["status"] = _SOURCE_STATUS[status]
                if valid:
                    parsed.append((name, index, model, keys, data, stats))
        except csv.Error:
            error(name, None, "", "invalid_csv", "CSV引号或字段格式不正确")

    try:
        planned = {}
        new_entities = {data["enterprise_id"] for _, _, model, _, data, _ in parsed if model is EnterpriseBasic}
        parent_cache = {}
        with db.no_autoflush:
            for name, index, model, keys, data, stats in parsed:
                entity = data["enterprise_id"]
                if model is not EnterpriseBasic and entity not in new_entities:
                    if entity not in parent_cache:
                        parent_cache[entity] = db.query(EnterpriseBasic.id).filter_by(enterprise_id=entity).first() is not None
                    if not parent_cache[entity]:
                        error(name, index, "enterprise_id", "enterprise_not_found", "企业不存在，请同次上传基础表或先导入企业")
                        continue
                key = (model, tuple(data[k] for k in keys))
                if key in planned:
                    previous = planned[key]
                else:
                    found = db.query(model).filter_by(**{k: data[k] for k in keys}).all()
                    if len(found) > 1:
                        error(name, index, "", "ambiguous_key", "现有数据的候选业务键不唯一，需人工核对")
                        continue
                    previous = {k: getattr(found[0], k) for k in data} if found else None
                if previous is not None:
                    if previous == data:
                        stats["skipped"] += 1
                        report["skipped"] += 1
                    else:
                        error(name, index, "", "record_conflict", "同一业务键内容不同，增量导入不会覆盖")
                    continue
                planned[key] = data
                stats["added"] += 1

        if report["errors"]:
            report["status"] = "rejected"
            for stats in report["files"]:
                stats["added"] = 0
        else:
            # 基础记录先入队；当前业务关联没有数据库外键，未来加约束也保持正确顺序。
            for (model, _), data in sorted(planned.items(), key=lambda item: item[0][0] is not EnterpriseBasic):
                db.add(model(**data))
            report["added"] = sum(stats["added"] for stats in report["files"])
        db.add(CsvImportAudit(id=report["importId"], actor_id=actor_id,
                              status=report["status"], summary={**report, "sourceFiles": file_hashes}))
        db.commit()
        return report, 422 if report["errors"] else 200
    except IntegrityError:
        db.rollback()
        # 全局唯一键可防止并发重复插入；冲突时不自动覆盖或吞掉其他写入。
        db.add(CsvImportAudit(id=report["importId"], actor_id=actor_id, status="rejected",
                              summary={"errorCode": "csv_import_conflict", "sourceFiles": file_hashes}))
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise ApiError(500, "csv_import_audit_failed", "导入冲突已回滚，但审计写入失败") from None
        raise ApiError(409, "csv_import_conflict", "并发或唯一键冲突，未导入，请重试或核对记录") from None
    except SQLAlchemyError:
        db.rollback()
        raise ApiError(500, "csv_import_failed", "数据库导入失败，未提交本次数据") from None
