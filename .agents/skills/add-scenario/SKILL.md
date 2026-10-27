---
name: add-scenario
description: 为 OCFT Agent 新增或装配一个业务场景包（信贷、反欺诈、理赔、客服、文档或赛题新场景）。抽签公布赛题后装配场景、或需要新的 scenarioId 时使用。
---

# 新增场景包

场景 = system prompt + 工具白名单 + 原始业务数据。引擎、存储、审计、评测接口不改。

## 1. 先确认

- 赛题要求的输入、输出格式、判定规则来自哪里（官方题面/数据说明）？把出处记下来，写进 spec。
- 跨模块时先用 `write-spec`（内部按 `code-write-requirements` → `code-write-design` → `code-split-tasks`）生成 `docs/40-specs/<场景>/`。格式只以 `docs/40-specs/README.md` 为准。

## 2. 数据

- 表结构加到 `ocft-backend/app/models.py`，只放原始业务字段。
- 官方给出的答案、标签、结论列不得进入运行时可读的表；如需离线评分，单独存放并在模型注释中标明"评测标签，运行时禁读"。
- 样本导入保持幂等（参考 `app/db.py::seed_business_data`），不清表。

## 3. 工具

用 `add-tool` skill 逐个实现。规则引擎类工具：结论由代码根据数据实时计算，不读取预存结论。

## 4. 注册场景

在 `ocft-backend/app/agent/scenarios.py`：

```python
XXX_SYSTEM = """你是 <角色>。工作方式：
1. 回答前必须调用工具获取真实数据；禁止凭记忆或猜测作答。
2. 结论必须引用数据来源（记录编号、规则编号）。
3. 数据不足时说明缺失项，请用户补充，禁止虚构。
4. 输出格式：<按官方要求>。
5. 与本场景无关的问题，说明职责范围。"""

SCENARIOS["xxx"] = Scenario(scenario_id="xxx", system_prompt=XXX_SYSTEM,
                            allowed_tools=["tool_a", "tool_b"])
```

Prompt 里只写工作方式与格式，不写任何样例题的答案或"如果问 X 就答 Y"。

## 5. 样例题与验证

- 在评测目录补 5～10 条该场景样例题（查数、多步、证据不足、违规请求、多轮），`expected` 只给评分器。
- 跑 `run-eval` skill；用 `POST /api/agent/runs`（`scenarioId: "xxx"`）手测一次，检查轨迹和证据。
- 在 `docs/INDEX.md` 登记 spec，在 README 场景说明处补一行。
