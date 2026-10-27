"""命令行：执行数据库迁移并幂等导入样例数据。

用法（cwd=ocft-backend）：
    python -m db.seed

@why 数据库层已统一到 app/db.py（待办 2-2）。本文件只保留原命令行入口，
     与后端启动时做的事情相同：执行尚未执行的迁移，业务表为空时导入样例数据。
     连接哪个库只由 DATABASE_URL（app.config.settings）决定。
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import engine, init_db, seed_business_data  # noqa: E402
from app.migrations import applied_versions  # noqa: E402


def main() -> None:
    migrated = init_db()
    imported = seed_business_data()
    print(f"数据库：{engine.url.render_as_string(hide_password=True)}")
    print(f"迁移：本次执行 {migrated or '无'}，已执行版本 {applied_versions(engine)}")
    print(f"样例数据：{'导入 ' + str(imported) + ' 行' if imported else '业务表已有数据，跳过'}")


if __name__ == "__main__":
    main()
