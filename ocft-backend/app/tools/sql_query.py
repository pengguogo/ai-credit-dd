"""sql_query — 只读 SQL 查询工具（数据层模块，可独立调用）。

用法：
    CLI:  python app/tools/sql_query.py "SELECT * FROM loan_application LIMIT 5"
    库内: from app.tools.sql_query import sql_query（独立函数）/
          execute_sql_query（Agent 注册工具，经 app.tools 包导入生效）

@why 只返回库里的真实行：答案只存在于数据库，本文件不含任何
     业务数据，杜绝把标准答案硬编码进工具。
@why 加固（待办 1-7）：sqlglot 语法树校验只读语义 + 表白名单
     （Agent 执行表与评测数据不可查）+ 行数 / 执行时间上限 + 产出
     EvidenceRecord。原前缀 / 写关键字正则降级为 load_file 等危险
     函数兜底：写语句已由语句类型白名单拒绝，且不再误伤 REPLACE()。
@why 输出字段随查询列动态，不逐列白名单；唯一例外是 _FORBIDDEN_COLUMNS
     里的预存结论列（赛题 04 enterprise_risk.risk_level_summary）：显式引用拒绝，
     SELECT * 结果剔除（ADR-0008 决策 1）。
@why 执行时间上限为"事后检测 + 丢弃结果"的诚实失败。
@why 数据库层只有 app/db.py 一套（待办 2-2）：原 db/ 三张副本表
     （credit_decisions 等，只含 app 业务表的一半行）已移出白名单，
     免得模型在副本表上反复核对（真实模型评测中出现过）。
@why 按场景收窄（待办 1-10）：Agent 调用时只能查本场景声明的表
     （run_ctx["sql_tables"]），工具描述也只列这些表。
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
from sqlalchemy import text

# 表白名单：业务事实四表；Agent 执行表（evidence / agent_runs / tool_traces 等）、
# 迁移记录表与评测数据一律不可查
_ALLOWED_TABLES = frozenset({
    "credit_applications", "risk_transactions", "claim_cases", "fin_docs",
    "loan_application", "enterprise_basic", "enterprise_shareholder", "enterprise_finance",
    "enterprise_lawsuit", "enterprise_public_opinion", "enterprise_related",
    "enterprise_guarantee", "enterprise_risk", "schema_relationships",
})
# 语句类型白名单：只读查询节点；SHOW / EXPLAIN 在 sqlglot 里是 Command
# 节点（无法提取表名做白名单校验），不放行
_ALLOWED_STATEMENT_TYPES = (exp.Select, exp.Union, exp.Describe)
# 正则兜底：语法树层不可见的危险函数（文件读写 / 拖库 / DoS）
_FORBIDDEN_FUNCTIONS = re.compile(
    r"\b(load_file|outfile|dumpfile|sleep|benchmark|get_lock)\b", re.IGNORECASE)
_MAX_ROWS = 500
_MAX_SECONDS = 10.0
# 列级黑名单：白名单表里与评测答案一致的预存结论列（ADR-0008 决策 1）。
# 显式引用（SELECT / WHERE / ORDER BY 等任意位置）直接拒绝；SELECT * 的结果里剔除该列。
_FORBIDDEN_COLUMNS = frozenset({"risk_level_summary"})
# 含禁止列的表 → 允许外露的列。执行前把表替换成只含这些列的子查询（R02）：
# @why 列名黑名单只能看到别名，`WITH t(..., x) AS (SELECT * FROM enterprise_risk)`
#      这类位置重命名会绕过；改写后禁止列根本不在查询可见范围内，与别名写法无关
_MASKED_TABLES = {
    "enterprise_risk": ("id", "enterprise_id", "existing_loan_balance", "overdue_count",
                        "overdue_amount", "external_guarantee_amount",
                        "public_opinion_score", "abnormal_operation"),
}


def _is_cte_ref(table: exp.Table, cte_names: set[str]) -> bool:
    """表节点是否指向 CTE 而不是真实表。

    @why 不能只按名字判断：`WITH enterprise_risk(...) AS (SELECT * FROM main.enterprise_risk)`
         用同名 CTE 遮蔽真表，按名字会把 CTE 内的真表一起当成 CTE，跳过白名单与列遮蔽。
         带库名 / catalog 前缀的一定是真表；在同名 CTE 自己的定义体内引用的也是真表（非递归语义）。
    """
    name = table.name.lower()
    if name not in cte_names or table.args.get("db") or table.args.get("catalog"):
        return False
    owner = table.find_ancestor(exp.CTE)
    while owner is not None:
        if owner.alias_or_name.lower() == name:
            return False
        owner = owner.find_ancestor(exp.CTE)
    return True


def _referenced_tables(stmt: exp.Expression) -> set[str]:
    """提取语句引用的真实表名（小写；指向 CTE 的引用不是表，剔除）。"""
    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    return {t.name.lower() for t in stmt.find_all(exp.Table)
            if not _is_cte_ref(t, cte_names)}


def _validate_read_only(sql: str, allowed: frozenset[str] = _ALLOWED_TABLES) -> set[str]:
    """Guard（语法树级）：单条只读语句 + 涉及表全在白名单。

    allowed：本次可查的表（场景子集，必须是全局白名单的子集）。
    返回涉及的表名集合；违规抛 ValueError（plain 函数契约）。
    """
    allowed = allowed & _ALLOWED_TABLES
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise ValueError("SQL 为空")
    if ";" in stripped:
        raise ValueError("不允许多语句")
    matched = _FORBIDDEN_FUNCTIONS.search(stripped)
    if matched:
        raise ValueError(f"检测到危险函数 {matched.group()!r}，sql_query 只允许只读查询")
    try:
        statements = [s for s in sqlglot.parse(stripped) if s is not None]
    except ParseError as exc:
        raise ValueError(f"SQL 语法无法解析: {exc}") from exc
    if len(statements) != 1:
        raise ValueError("不允许多语句")
    stmt = statements[0]
    if not isinstance(stmt, _ALLOWED_STATEMENT_TYPES):
        raise ValueError(f"仅支持只读查询（SELECT/WITH/UNION/DESCRIBE），"
                         f"当前语句类型为 {type(stmt).__name__}")
    tables = _referenced_tables(stmt)
    illegal = sorted(tables - allowed)
    if illegal:
        raise ValueError(f"表不在白名单内: {', '.join(illegal)}；"
                         f"当前可查 {', '.join(sorted(allowed))}")
    # @why 也覆盖 WHERE / GROUP BY 里的引用：按该列过滤同样能把答案带出来
    blocked = sorted({c.name.lower() for c in stmt.find_all(exp.Column)} & _FORBIDDEN_COLUMNS)
    if blocked:
        raise ValueError(f"列不可查询: {', '.join(blocked)}")
    return tables


def _shield_columns(sql: str, dialect: str | None = None) -> str:
    """把含禁止列的表替换为只含允许列的子查询，保留原别名（R02）；不涉及时原样返回。"""
    stmt = sqlglot.parse_one(sql.strip().rstrip(";"))
    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}

    def shield(node: exp.Expression) -> exp.Expression:
        if (isinstance(node, exp.Table) and node.name.lower() in _MASKED_TABLES
                and not _is_cte_ref(node, cte_names)):
            columns = _MASKED_TABLES[node.name.lower()]
            return (sqlglot.select(*columns).from_(exp.to_table(node.name))
                    .subquery(node.alias_or_name))
        return node

    if not any(isinstance(n, exp.Table) and n.name.lower() in _MASKED_TABLES
               for n in stmt.find_all(exp.Table)):
        return sql
    return stmt.transform(shield).sql(dialect=dialect)


def scenario_tables(run_ctx: dict) -> frozenset[str]:
    """本次 run 可查的表：场景声明的子集；未声明时用全局白名单。"""
    declared = run_ctx.get("sql_tables")
    return frozenset(declared) & _ALLOWED_TABLES if declared else _ALLOWED_TABLES


def describe_for(tables) -> str:
    """按场景生成工具描述：只列本场景可查的表，减少模型在无关表上漫游。"""
    listed = "、".join(sorted(frozenset(tables) & _ALLOWED_TABLES)) or "（无）"
    return ("对本场景的业务事实表执行只读 SQL 查询（SELECT / WITH / UNION / DESCRIBE），"
            f"可查表：{listed}。只用于其他工具覆盖不到的跨行核对与聚合统计；"
            "规则工具已给出结论时不要再用本工具复核或浏览表结构。"
            "返回真实行（camelCase 键），大结果集会截断，查询请带 LIMIT。")


def _to_camel(key: str) -> str:
    """snake_case 列名 → camelCase 输出键（契约约定）。"""
    head, *rest = key.split("_")
    return head + "".join(part.title() for part in rest)


def _jsonable(value):
    """驱动返回值 → 可 JSON 序列化的值（结果要写进证据快照的 JSON 列）。

    @why MySQL（PyMySQL）对 DECIMAL 列与 SUM/AVG 聚合返回 Decimal，日期列返回 date/datetime；
         SQLite 返回 float / str，所以只在 MySQL 上出现 "Decimal is not JSON serializable"。
    """
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date, dt_time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return value


def _execute(sql: str, engine) -> tuple[list[dict], bool]:
    """在 engine 上执行只读 SQL：fetchmany 到上限即停（控内存）。

    返回 (行, 是否截断)；超时抛 ValueError（结果丢弃，诚实失败）。
    """
    sql = _shield_columns(sql, engine.dialect.name)
    started = time.monotonic()
    with engine.connect() as conn:
        rows = [{_to_camel(column): _jsonable(value) for column, value in row.items()
                 if str(column).lower() not in _FORBIDDEN_COLUMNS}
                for row in conn.execute(text(sql)).mappings().fetchmany(_MAX_ROWS + 1)]
    elapsed = time.monotonic() - started
    if elapsed > _MAX_SECONDS:
        raise ValueError(f"查询耗时 {elapsed:.1f}s 超过 {_MAX_SECONDS:.0f}s 上限，结果已丢弃")
    truncated = len(rows) > _MAX_ROWS
    return (rows[:_MAX_ROWS] if truncated else rows), truncated


def sql_query(sql: str, engine=None) -> dict:
    """执行只读 SQL，返回契约格式 {tool, input, output, evidence}。

    engine 缺省时用 app.db 的唯一引擎（config.yaml database 段 > DATABASE_URL，见 app.config.settings）。
    校验失败（写语句 / 越权表 / 多语句 / 危险函数 / 超时）抛 ValueError。
    """
    _validate_read_only(sql)
    if engine is None:
        from app.db import engine
    rows, truncated = _execute(sql, engine)
    evidence = f"sql_query 在数据库执行只读查询，返回 {len(rows)} 行真实记录"
    if truncated:
        evidence = f"sql_query 返回 {len(rows)} 行（超 {_MAX_ROWS} 行截断）"
    return {"tool": "sql_query", "input": {"sql": sql}, "output": rows, "evidence": evidence}


# --- Agent 工具入口（仅包内导入时注册；独立加载模式见模块 docstring） ---
if __package__ == "app.tools":
    from sqlalchemy.orm import Session

    from app.domain.types import EvidenceRecord, ToolResult
    from app.tools.registry import register_tool

    @register_tool(
        "sql_query",
        describe_for(_ALLOWED_TABLES),   # 引擎按场景替换为 describe_for(场景表)
        {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "只读 SQL，如 SELECT * FROM credit_applications "
                                   "WHERE application_id = 'APP-2026-1100' LIMIT 10",
                },
            },
            "required": ["sql"],
        },
    )
    def execute_sql_query(db: Session, run_ctx: dict,
                          sql: str) -> tuple[ToolResult, list[EvidenceRecord], dict]:
        """Agent 工具入口（待办 1-7）：语法树校验 → 只读执行 → 产出证据。"""
        try:
            tables = _validate_read_only(sql, scenario_tables(run_ctx))
        except ValueError as exc:
            return (ToolResult.failure("not_allowed", f"sql_query 拒绝执行: {exc}"),
                    [], {"sql": sql})
        try:
            rows, truncated = _execute(sql, db.get_bind())
        except ValueError as exc:  # 执行时间上限
            return (ToolResult.failure("execution_failed", str(exc), is_retryable=True),
                    [], {"sql": sql})
        data = {"rowCount": len(rows), "truncated": truncated,
                "tables": sorted(tables), "rows": rows}
        evidence = [EvidenceRecord(
            source_type="db_query",
            source_ref={"table": ", ".join(sorted(tables)) or "(无表)",
                        "filters": {"sql": sql}},
            snapshot=rows, data_version=run_ctx["data_version"])]
        return (ToolResult.success(data), evidence, {"sql": sql})


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python app/tools/sql_query.py \"SELECT ...\"", file=sys.stderr)
        raise SystemExit(2)
    result = sql_query(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
