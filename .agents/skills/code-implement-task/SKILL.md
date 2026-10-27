---
name: code-implement-task
description: 按 tasks.md 中未完成的任务改代码，只做该条范围，完成标准满足后才勾选。当用户说按任务开发、实现某个 task、照 spec 写代码时使用。范围不够时先走 code-update-spec，不在代码里临场改需求。
---

# 按任务开发

先读 `docs/40-specs/README.md` 的门禁，再读该功能的 `requirements.md`、`design.md`、`tasks.md`。编码细则以 `docs/30-standards/coding.md` 和 `AGENTS.md` 为准。

## 门禁

需求或设计不是「已确认」，或 `tasks.md` 不是「已确认」时，停下来，不要写实现。

用户要求的行为在 spec 里没有，或和验收标准冲突：停下来走 `code-update-spec`。不要先改代码再补文档。

## 步骤

1. 列出未勾选任务。用户指定了编号就只做那一条；没指定就做序号最小的一条。做完再继续下一条。
2. 只改这条任务点名的模块。公共层（`app/agent/`、`app/llm.py`、合规、可观测）的改动在回复里说明。
3. 按设计落地：
   - 契约以 `/contracts` 为准；设计写了变更但契约还没有时，先改契约。
   - 表结构在 `app/models.py` 之外，必须在 `app/migrations.py` 追加一条新迁移。
   - 新工具改用 `add-tool`，新场景改用 `add-scenario`，不要在本 skill 里另写注册方式。
   - 模型调用只经 `ocft-backend/app/llm.py`。
4. 对照该条「完成标准」自测。没满足就不勾选。
5. 勾选后在任务下补一行实际验证命令和结果。验证任务等单测和审查都完成后才勾。
6. 改了后端就跑相关 pytest；改了前端就跑 `npm run lint` 和 `npm run build`。答题链路改动再按 `run-eval` 跑一次公开样例。涉及红线时按 `redline-scan` 扫一遍。

## 禁止

- 写死题目答案、结论或话术；运行时读取评测标签或 `expected`。
- 失败时返回模板化假结论。用 `ToolError` / `LLMError` 或既有 `errorCode`。
- 顺手做任务列表之外的重构。
