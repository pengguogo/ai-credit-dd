# Git 协作规范

## 分支

- `main` 永远可启动：一键启动成功 + 样例评测可跑。
- 功能分支：`feat/<模块>-<简述>`，修复：`fix/<模块>-<简述>`，文档：`docs/<简述>`。
- 分支寿命不超过一天；每天至少合入 main 两次，减少冲突。
- 禁止 force push 到 `main`。

## 提交信息（Conventional Commits）

```text
<type>(<scope>): <中文简述>

type:  feat | fix | refactor | docs | test | chore
scope: agent | llm | tools | compliance | eval | db | web | docs | infra
```

示例：`feat(tools): 新增理赔材料核验工具`、`fix(agent): 单次 LLM 调用超时计入 run 时限`。

## 合并

1. 本地跑通：后端可启动、相关测试通过、`npm run lint`（若改前端）。
2. 按 [评审清单](review-checklist.md) 自查，涉及红线的改动找第二个人看。
3. 契约变更先合 `/contracts` 再合实现，并在群里通知。
4. 冲突时优先保证 main 可启动，其次再保功能。

## 禁止入库与比赛期间例外

通常禁止入库：`.env`、`master.key`、数据库文件、`node_modules/`、`.venv/`、评测 `expected` 之外的官方非公开题答案、任何密码与 API Key。

比赛期间私有仓库例外以根目录 [AGENTS.md](../../AGENTS.md)「红线」第 6 条为准：仅 `ocft-backend/.env` 与 `ocft-backend/master.key` 可随私有仓库提交，以保证克隆即可用；其他路径和提交信息仍不得出现敏感值。比赛结束后删除这两个文件并轮换全部凭据。
