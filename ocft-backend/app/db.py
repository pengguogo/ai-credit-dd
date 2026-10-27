"""数据库引擎 — 全项目唯一的数据库层：版本化迁移 + 显式幂等种子导入。

@why 唯一数据库层（待办 2-2）：业务事实表与 Agent 执行表都在 app/models.py，
     引擎只在这里创建；sql_query、评测、db.seed 命令行全部复用本模块。
     部署与评测用 MySQL（DATABASE_URL，enc: 密文见 .env）；未配置时退回本地 SQLite，
     自动化测试用临时 SQLite。
@why 比赛红线要求结论可追溯、重启数据不丢：启动只执行增量迁移（app/migrations.py），
     绝不 drop。样本导入是显式独立函数 seed_business_data()，仅在业务表为空时灌入。
"""
import re

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from .config import settings
from .dd_import import import_if_empty
from .models import ClaimCase, CreditApplication, FinDoc, RiskTransaction
from . import seed


def _engine_options(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    # @why 云 MySQL 会断开空闲连接：取连接前先探活，并定期回收，避免演示中途报 "MySQL server has gone away"；
    #      同时给握手与读写设上限，网络中断时尽快报错重试，不能无限挂起。
    return {"pool_pre_ping": True, "pool_recycle": 1800,
            "connect_args": {"connect_timeout": 10, "read_timeout": 60, "write_timeout": 60}}


engine = create_engine(settings.database_url, **_engine_options(settings.database_url))
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

_SNAKE = re.compile(r"(?<!^)(?=[A-Z])")


def _to_snake(row: dict) -> dict:
    return {_SNAKE.sub("_", key).lower(): value for key, value in row.items()}


def init_db() -> list[int]:
    """执行尚未执行的迁移（首个迁移按 ORM 补建缺失的表），不动已有数据。返回本次执行的版本号。"""
    from .migrations import run_migrations
    return run_migrations(engine)


def seed_business_data() -> int:
    """显式幂等样本导入：仅当各业务表为空时灌入种子。返回导入行数。

    @why 与 init_db 分离：重启绝不重灌；换数据集时由脚本显式调用。
    """
    imported = 0
    inspector = inspect(engine)
    with SessionLocal() as session:
        plan = [
            (CreditApplication, seed.CREDIT_APPLICATIONS),
            (RiskTransaction, seed.TRANSACTIONS),
            (ClaimCase, seed.CLAIMS),
            (FinDoc, seed.FIN_DOCS),
        ]
        for model, rows in plan:
            if not inspector.has_table(model.__tablename__):
                continue
            if session.query(model).count() > 0:
                continue
            for row in rows:
                session.add(model(**_to_snake(row)))
                imported += 1
        if inspector.has_table("loan_application"):
            imported += import_if_empty(session)
        session.commit()
        # 演示登录账号（幂等）
        if inspector.has_table("sys_users"):
            from .services.auth_service import ensure_seed_users
            ensure_seed_users(session)
    return imported


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
