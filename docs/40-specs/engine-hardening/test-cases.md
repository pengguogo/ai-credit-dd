# 引擎补强 设计用例

状态：已确认

> 现状追溯版：本文件根据既有验收标准和当前自动化测试补录，不伪造历史顺序；本次只补文档，不新增或修改代码测试。

| 编号 | 追溯 | 类型 | 前置 | 操作 | 期望 | 验证 |
|------|------|------|------|------|------|------|
| TC-1 | 需求 1 | 异常 | 数据工具无目标证据 | 完成 run | 终态为 `insufficient_evidence`，且有说明文本 | 单测 |
| TC-2 | 需求 1 | 红线 | 模型给出结论但本次无证据 | 完成 run | 不得成功，终态为 `insufficient_evidence` | 单测 |
| TC-3 | 需求 1 | 正常 | 模型调用 `request_clarification` | 执行 run | 终态 `needs_clarification`，不再调用模型 | 单测 |
| TC-4 | 需求 1 | 正常 | 工具结果命中确认规则 | 执行 run | 终态 `needs_confirmation` 且 `answerVersion=1` | 单测 |
| TC-5 | 需求 2 | 边界 | run 剩余时限小于模型默认超时 | 发起模型调用 | 调用超时取较小值；时限截断时返回 `run_timeout` | 单测 |
| TC-6 | 需求 3 | 正常 | 同一会话已有工具摘要和实体 | 发起指代追问 | 历史含工具摘要与实体槽位，详情返回 `contextSnapshot` | 单测 |
| TC-7 | 需求 3 | 边界 | 历史超出 token 预算 | 构建历史 | 最旧消息被抽取式压缩，并记录消息范围 | 单测 |
| TC-8 | 需求 3 | 红线 | 前轮输入被合规拦截或工具结果含 PII | 构建下一轮模型历史 | 拦截内容不回放，工具摘要在发送前脱敏 | 单测 |

## 现有自动化追溯

- `ocft-backend/tests/test_engine_states.py`：终态、澄清、确认、run 时限、历史摘要/实体/压缩、拦截历史排除、工具脱敏与 LLM 审计。
- `ocft-backend/tests/test_token_budget.py`：token 截断、累计 token 与证据保留。
- `ocft-backend/tests/test_conversations.py`：会话归属、场景、搜索与分页。
- `pub-009`“第二轮不重复检索”未发现独立命名的专门 pytest；现有追问上下文测试验证摘要和实体传递，但不将其夸大为该样例的完整业务验收。
