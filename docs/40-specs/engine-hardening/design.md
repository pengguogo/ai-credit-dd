# 引擎补强 设计

状态：已确认    对应需求：已实现

## 方案概述
- 终态判定在 `app/agent/engine.py` 的 `_finish_with_answer`，优先级：澄清 > 证据不足 > 需确认 > 成功。判定只用本次 run 的工具结果（内存中的 `_tool_data`），不读评测数据。
- 澄清用引擎内置工具 `request_clarification`（不进注册表、不产证据），调用即结束；参数非法时把 `invalid_args` 回给模型继续循环。
- 场景新增三个可选字段（`app/agent/scenarios.py`）：`entity_keys`、`confirmation_rules`、`conclusion_pattern`。信贷场景：`rejected` / `manual_review` 需确认。
- 超时：`llm.complete_with_tools(..., timeout=)`，传入时用 `with_options(timeout, max_retries=0)`，避免 SDK 重试让耗时翻倍。
- 上下文：新增纯函数模块 `app/agent/context.py`（工具摘要、实体提取与合并、历史组装与压缩）。`run_service._build_history` 读取前序 run 的 `context_snapshot.toolSummaries` 与 `entities`，组装为 system 消息插入历史。

## 涉及模块与负责人
Agent 核心（engine、scenarios、llm、context、run_service）；评测（样例题 status 期望值更新、新增 pub-016–018）。

## 接口 / 契约变更
[contracts/agent-api.md](../../../contracts/agent-api.md)：终态判定表、`evidence_missing` / `clarification_required` 错误码、`GET /runs/{runId}` 增加 `contextSnapshot`。

## 数据变更
无表结构变更；`agent_runs.context_snapshot`（JSON）新增键：`compressedRange`、`toolSummaryRuns`、`estimatedHistoryTokens`、`historyTokenBudget`、`entities`、`toolSummaries`、`missingInfo`、`confirmationReasons`。

## 红线影响
- 红线 3/4：确认规则与结论正则只匹配运行时工具结果与模型文本，不含任何题目答案；`eval/` 标签不被读取。
- 红线 5：无证据的结论不再显示为 `succeeded`。
- 合规：澄清问题与证据不足说明同样经过输出合规与 PII 掩码；工具摘要入库前掩码。

## 取舍
- 信贷场景 `approved` 不强制确认，便于演示两种终态；赛题若要求所有结论都确认，只改场景配置。
- 前序工具摘要只用于理解指代，系统提示要求给结论前重新调用规则工具，保证每个 run 的结论都有自己的证据。
- token 估算按 1.5 字/token 粗略计算，够用于预算判断；若出现预算误判再接入 tokenizer。
