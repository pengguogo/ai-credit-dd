---
name: add-tool
description: 为 OCFT Agent 新增一个工具（数据查询、规则计算、文档检索等）。当需要让 Agent 访问新的数据表、执行新的业务规则或接入新数据源时使用。
---

# 新增 Agent 工具

按以下步骤执行，参考实现：`ocft-backend/app/tools/credit.py`。

## 1. 先确认

- 工具属于哪个场景？目标数据表/文档是什么？读出来的字段里有没有评测标签（如 `is_fraud`、`extracted_kpis`、`expected`、预存的 `decision`）？有就排除，并告诉用户。
- 已有工具能否满足？能就复用，不新增。

## 2. 实现

在 `ocft-backend/app/tools/<场景>.py` 中：

```python
from ..domain.types import EvidenceRecord, ToolResult
from .registry import register_tool

_FIELDS = ["id_col", "col_a", "col_b"]  # 输出字段白名单，显式列举

@register_tool(
    "get_xxx",                                  # snake_case，动词开头
    "一句话说清用途和何时调用。",                 # LLM 依赖它选工具，写准确
    {"type": "object",
     "properties": {"xxxId": {"type": "string", "description": "..."}},  # camelCase
     "required": ["xxxId"]},
)
def get_xxx(db, run_ctx: dict, xxxId: str):
    row = ...                                   # 参数化查询，只读
    if row is None:
        return ToolResult.failure("not_found", f"{xxxId} 不存在"), [], {"xxxId": xxxId}
    data = {...}                                # 只取 _FIELDS
    evidence = EvidenceRecord(
        source_type="db_query",                 # db_query | document | calculation
        source_ref={"table": "...", "keys": {"xxxId": xxxId}},
        snapshot=data, data_version=run_ctx["data_version"])
    return ToolResult.success(data), [evidence], {"xxxId": xxxId}
```

规则：
- 只读；禁止拼接 SQL 字符串，用 ORM 或绑定参数。
- 不写任何题目答案或固定结论；规则阈值是业务逻辑，要写进 `detail` 便于证据复核。
- 计算类结论把公式和输入写进证据（`source_type="calculation"`，`source_ref.calc`）。
- 异常用 `ToolError(code, message)`，不要吞掉。

## 3. 接线

1. 新文件需在 `ocft-backend/app/tools/__init__.py` 中 import（注册副作用）。
2. 把工具名加入 `app/agent/scenarios.py` 对应场景的 `allowed_tools`。
3. 必要时在场景 `system_prompt` 中说明何时调用该工具（只写调用策略，不写答案）。

## 4. 验证

- 在 `ocft-backend/tests/` 写 pytest：成功、not_found、参数非法三种情况；断言输出不含白名单外字段。
- 起后端，用 `POST /api/agent/runs` 提一个需要该工具的问题，`GET /api/agent/runs/{runId}` 确认 `toolTraces` 出现该工具且有 `evidenceIds`。
- 跑 `redline-scan` skill。
