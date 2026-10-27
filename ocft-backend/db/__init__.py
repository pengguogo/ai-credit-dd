"""db/ — 仅保留命令行入口 `python -m db.seed`（执行迁移 + 幂等导入样例数据）。

数据库层已统一到 app/db.py、app/models.py、app/migrations.py（待办 2-2）。
原 db/ 的三张副本表（credit_decisions、fraud_decisions、claim_decisions）
只含 app 业务表的部分行，已不再使用，也不在 sql_query 白名单内。
"""
