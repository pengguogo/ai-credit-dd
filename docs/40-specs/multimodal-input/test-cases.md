# 多模态输入 设计用例

状态：已确认

| 编号 | 追溯 | 类型 | 前置 | 操作 | 期望 | 验证 |
|------|------|------|------|------|------|------|
| TC-1 | 需求 1 | 红线 | sync/async 请求含一个 HTTPS 或 data URL 附件 | 调用 `POST /api/agent/runs` | 同步 422 `invalid_attachment`；不创建 AgentRun；不调用模型 | 单测 |
| TC-2 | 需求 1 | 边界 | 附件超过 4 张或单项超过 32MB | 调用创建 run | 同步 422 `invalid_attachment`；不调用模型 | 单测 |
| TC-3 | 需求 2 | 正常 | 省略附件或传空数组 | 发起纯文本 run | 文本链路照常执行，模型消息仍为文本 | 单测 |
| TC-4 | 需求 1 | 红线 | 直接调用 engine 并传非空附件 | 执行引擎 | 返回 `invalid_attachment`，不调用模型 | 单测 |
| TC-5 | 需求 3 | 正常 | 打开工作台输入区 | 尝试选择或粘贴图片 | 无图片选择、预览和附件提交入口 | 手工 |

## 现有自动化追溯
- `ocft-backend/tests/test_agent_runs.py`：TC-1～TC-3，含 run 数量和模型调用断言。
- `ocft-backend/tests/test_observability.py`：异步附件同步拒绝。
- `ocft-backend/tests/test_dd_multi_agent.py`：TC-4 的 engine 绕过保护。
