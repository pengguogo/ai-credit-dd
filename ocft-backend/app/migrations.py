"""版本化数据库迁移 — 启动时按版本号顺序执行尚未执行的迁移（待办 2-3）。

@why 不引入 Alembic：只需"按顺序补表、补列"，自写约 80 行即可，不加依赖，
     离线提交包也不必多带 wheel。create_all 只会补缺失的表，不会给已有表加列，
     表结构变化必须写成一条迁移。
@why 只做增量变更：迁移里只允许建表、加列、加索引；删表、删列、改类型会丢数据，
     必须先在开发日志记录决策并人工执行，不写进自动迁移。
@why 已执行的版本记在 schema_migrations 表；sql_query 白名单不含该表。
     MySQL 的 DDL 会隐式提交，所以每条迁移都要写成可重复执行（先检查再变更）。

新增迁移：在 MIGRATIONS 末尾追加 Migration(版本号 + 1, "说明", 函数)，函数接收一个 Connection。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import (Column, DateTime, Integer, MetaData, String, Table, inspect,
                        select, text)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from .models import Base

_meta = MetaData()
schema_migrations = Table(
    "schema_migrations", _meta,
    Column("version", Integer, primary_key=True, autoincrement=False),
    Column("name", String(200), nullable=False),
    Column("applied_at", DateTime, nullable=False),
)


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[Connection], None]


def add_column_if_missing(conn: Connection, table: str, column: str, ddl_type: str) -> bool:
    """给已有表加一列（不存在才加）。ddl_type 如 "VARCHAR(32) NULL"。返回是否真的加了。

    @why 表名、列名只允许字母数字下划线：迁移由开发者编写，这里再兜一道，防止拼接注入。
    """
    for name in (table, column):
        if not name.replace("_", "").isalnum():
            raise ValueError(f"非法标识符: {name!r}")
    existing = {c["name"] for c in inspect(conn).get_columns(table)}
    if column in existing:
        return False
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
    return True


def _baseline(conn: Connection) -> None:
    """按当前 ORM 建全部表（已存在的表跳过）。"""
    Base.metadata.create_all(conn)


def _conversation_scenario(conn: Connection) -> None:
    """会话补场景列，并用该会话最早一次 run 回填。"""
    add_column_if_missing(conn, "conversations", "scenario_id", "VARCHAR(32)")
    pending = conn.execute(text(
        "SELECT id FROM conversations WHERE scenario_id IS NULL OR scenario_id = ''")).all()
    for (conversation_id,) in pending:
        scenario_id = conn.execute(text(
            "SELECT scenario_id FROM agent_runs WHERE conversation_id = :id "
            "ORDER BY started_at ASC LIMIT 1"), {"id": conversation_id}).scalar()
        if scenario_id:
            conn.execute(text(
                "UPDATE conversations SET scenario_id = :scenario WHERE id = :id"),
                {"scenario": scenario_id, "id": conversation_id})


def _llm_calls(conn: Connection) -> None:
    """新增 llm_calls：外部大模型调用审计（待办 0-5）。"""
    Base.metadata.tables["llm_calls"].create(conn, checkfirst=True)


def _memory(conn: Connection) -> None:
    """新增会话记忆与记忆变更审计（待办 0-6）。"""
    Base.metadata.tables["conversation_memories"].create(conn, checkfirst=True)
    Base.metadata.tables["memory_events"].create(conn, checkfirst=True)


def _due_diligence_tables(conn: Connection) -> None:
    """赛题 04 尽调事实表。已存在则跳过，不改演示场景的旧表。"""
    names = (
        "loan_application", "enterprise_basic", "enterprise_shareholder", "enterprise_finance",
        "enterprise_lawsuit", "enterprise_public_opinion", "enterprise_related",
        "enterprise_guarantee", "enterprise_risk", "schema_relationships",
    )
    for name in names:
        Base.metadata.tables[name].create(conn, checkfirst=True)


def _csv_import_audits(conn: Connection) -> None:
    Base.metadata.tables["csv_import_audits"].create(conn, checkfirst=True)


def _sys_auth_tables(conn: Connection) -> None:
    """系统管理：角色、用户、登录会话。"""
    for name in ("sys_roles", "sys_users", "sys_sessions"):
        Base.metadata.tables[name].create(conn, checkfirst=True)


def _loan_application_status(conn: Connection) -> None:
    """审批表增加业务审批状态；存量默认待审批。"""
    added = add_column_if_missing(
        conn, "loan_application", "status", "VARCHAR(16) NOT NULL DEFAULT 'pending'")
    if added:
        conn.execute(text(
            "UPDATE loan_application SET status = 'pending' "
            "WHERE status IS NULL OR status = ''"))


def _workspace_assets(conn: Connection) -> None:
    """新增任务与资产档案：产出物建档、状态流转、归档检索（评审维度②）。"""
    for name in ("workspace_assets", "workspace_asset_events"):
        Base.metadata.tables[name].create(conn, checkfirst=True)


def _loan_application_initial_status(conn: Connection) -> None:
    """审批状态增加初始态「待尽调」：没有尽调报告的存量待审批行回到初始状态。

    @why 迁移 11 把存量行一律写成 pending（待审批）。新口径下 pending 表示
          「已生成尽调报告、等待人工审批」，因此只保留已有报告归档的行，
          其余回到 pending_dd（待尽调），避免没有报告却显示待审批。
    @why 用相关 NOT EXISTS 而不是 NOT IN：两种方言都不受子查询 NULL 影响，
          也避免 MySQL 的 UPDATE 目标表限制。
    """
    has_assets = inspect(conn).has_table("workspace_assets")
    if has_assets:
        conn.execute(text(
            "UPDATE loan_application SET status = 'pending_dd' "
            "WHERE status = 'pending' AND NOT EXISTS ("
            "SELECT 1 FROM workspace_assets a "
            "WHERE a.application_id = loan_application.application_id)"))
    else:
        conn.execute(text(
            "UPDATE loan_application SET status = 'pending_dd' WHERE status = 'pending'"))
    conn.execute(text(
        "UPDATE loan_application SET status = 'pending_dd' WHERE status IS NULL OR status = ''"))


def _loan_application_status_rename(conn: Connection) -> None:
    """贷款申请状态改为四态：待处理 / 待审核 / 审核通过 / 审核不通过。

    @why 旧口径的 pending_dd（待尽调）与 pending（待审批）在界面与接口里含义不一致，
          统一为 pending（待处理，尚未生成尽调报告）与 pending_review（待审核，已生成报告）。
          先改 pending -> pending_review，再把 pending_dd -> pending，避免两批数据互相覆盖。
    """
    conn.execute(text(
        "UPDATE loan_application SET status = 'pending_review' WHERE status = 'pending'"))
    conn.execute(text(
        "UPDATE loan_application SET status = 'pending' WHERE status = 'pending_dd'"))
    conn.execute(text(
        "UPDATE loan_application SET status = 'pending' WHERE status IS NULL OR status = ''"))


def _loan_application_review(conn: Connection) -> None:
    """审批表记录人工审核理由：原因、审核人、审核时间。

    @why 贷款申请列表的审核弹窗要求填写原因；状态与原因写在同一事务，留痕可追溯。
    """
    add_column_if_missing(conn, "loan_application", "review_reason", "TEXT NULL")
    add_column_if_missing(conn, "loan_application", "reviewed_by", "VARCHAR(64) NULL")
    add_column_if_missing(conn, "loan_application", "reviewed_at", "VARCHAR(30) NULL")


# 版本号只增不改；已发布的迁移不再修改内容，需要变更就追加新版本
MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "baseline：按 ORM 建业务事实表与 Agent 执行表（已存在的表跳过）", _baseline),
    Migration(2, "conversations 增加 scenario_id，并用最早的 run 回填", _conversation_scenario),
    # @why 版本 3、4 已被未合入的分支占用并登记在共享的阿里云 MySQL 上
    #      （feat/supplier-recommendation 的 3、feat/data-rag-base 的 3 / 4），这里跳号用 5，避免被当成已执行而跳过。
    #      版本号允许有空缺；分支合入时补上 3 / 4 即可，run_migrations 会补跑未执行的低版本。
    Migration(5, "新增 llm_calls：外部大模型调用审计", _llm_calls),
    Migration(6, "新增 conversation_memories / memory_events：会话记忆查看、纠正、清除", _memory),
    Migration(8, "新增赛题 04 尽调事实表（贷款申请、企业工商财务舆情与关系说明）", _due_diligence_tables),
    Migration(9, "新增CSV增量导入操作审计", _csv_import_audits),
    Migration(10, "新增 sys_roles / sys_users / sys_sessions：登录与系统管理", _sys_auth_tables),
    Migration(11, "loan_application 增加 status：业务审批状态", _loan_application_status),
    Migration(12, "新增 workspace_assets / workspace_asset_events：任务产出物建档与归档", _workspace_assets),
    Migration(13, "loan_application.status 增加初始态 pending_dd（待尽调）并回填未生成报告的申请",
              _loan_application_initial_status),
    Migration(14, "loan_application.status 统一为四态：待处理 pending / 待审核 pending_review / 审核通过 / 审核不通过",
              _loan_application_status_rename),
    Migration(15, "loan_application 增加人工审核留痕：review_reason / reviewed_by / reviewed_at",
              _loan_application_review),
)


def applied_versions(engine: Engine) -> list[int]:
    with engine.begin() as conn:
        schema_migrations.create(conn, checkfirst=True)
        return sorted(row[0] for row in conn.execute(select(schema_migrations.c.version)))


def run_migrations(engine: Engine, migrations: tuple[Migration, ...] = MIGRATIONS) -> list[int]:
    """执行尚未执行的迁移，返回本次执行的版本号。重复调用安全。"""
    versions = [m.version for m in migrations]
    if versions != sorted(set(versions)):
        raise ValueError(f"迁移版本号必须唯一且递增: {versions}")
    done = set(applied_versions(engine))
    applied: list[int] = []
    for migration in migrations:
        if migration.version in done:
            continue
        with engine.begin() as conn:
            migration.apply(conn)
            try:
                conn.execute(schema_migrations.insert().values(
                    version=migration.version, name=migration.name,
                    applied_at=datetime.now(timezone.utc).replace(tzinfo=None)))
            except IntegrityError:
                # 另一个进程（如同时启动的后端与评测）已执行并登记了同一版本：迁移本身可重复执行，跳过即可
                continue
        applied.append(migration.version)
    return applied
