"""工具包 — import 即完成注册（注册副作用集中声明于此）。"""
from . import registry
from . import credit  # noqa: F401  注册副作用（引擎/评测单测夹具；非 enterprise_dd 白名单）
from . import due_diligence  # noqa: F401  注册副作用
from . import sql_query  # noqa: F401  注册副作用
