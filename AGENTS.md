# AGENTS.md — AI 开发规范（唯一来源）

> Cursor、Codex、Kiro 等所有 AI 工具都以本文件为准。各工具目录（`.cursor/rules/`、`.kiro/steering/`）只放指向本文件的薄层，不重复写规则。
> 改规范只改这里；细则见 `docs/30-standards/`。

## 项目是什么

金融科技 Agent 黑客松作品：FastAPI 后端（`ocft-backend/`）+ React/Vite 前端（`ocft-starter/`）。
核心链路：`POST /api/agent/runs → run_service → 输入合规 → graph.py（LangGraph 调度）→ engine 判定终态 → 证据落库 → 输出合规 → 审计`。
底座与具体赛题无关，换题只替换场景包。

## 赛题 04 评测基准

- 评测集以官方[题目说明（固定版本 `88cf4b4`）](https://github.com/pengguogo/ocft-ai-marathon/blob/88cf4b456519d80216530d92fc2648f261f6d2dc/docs/00-rules/赛题/赛题04_企业智能信贷尽调/题目说明.md)第四章及第 6.2 节为准；本地参照[题目说明](docs/00-rules/赛题/赛题04_企业智能信贷尽调/题目说明.md)。
- 官方公开测评集为 [公开测试集答案.csv](docs/00-rules/赛题/赛题04_企业智能信贷尽调/data/公开测试集答案.csv) 的 **10 笔贷款申请**；逐笔对照风险评级、建议额度、尽调结论与评分要点覆盖，不能以 Agent 运行成功率代替业务正确率。
- [question_public.csv](docs/00-rules/赛题/赛题04_企业智能信贷尽调/data/question_public.csv) 是自然语言尽调问询自测集，单独验证结论与依据；底座样例、团队衍生集仅作补充回归，不替代官方公开测评集。
- 标准结果与参考答案仅供 `eval/` 离线对照；运行时只接收业务输入，禁止读取答案、`expected` 或建立题号到答案的映射，禁止预录或回填结论。公开集亦须能现场即时处理、实时重算并逐项比对。
- 官方非公开测评集赛前不下发，现场由评委提供另一批未参与公开集的企业样本，**只有输入、没有结果**；验证泛化能力与新增样本适配成本，优先改配置，不将团队衍生集称为官方非公开集。
- 交付须包含公开测评集及现场非公开测评集的系统输出结果文件；失败与待确认状态如实披露。详细评分标准与分值未公开，不把内部评分口径写成官方标准。

## 红线（违反即可能取消资格，不得以任何理由绕过）

1. 运行时模型只能是 `deepseek-v4.1-flash`，只经 `ocft-backend/app/llm.py` 调用。
2. Agent 必须是代码实现，不得接入扣子（Coze）等低代码平台编排。
3. 禁止在 Prompt、工具、种子数据、前端里写死任何题目的答案或结论。
4. 运行时禁止读取评测标签与 `expected`（如 `is_fraud`、`extracted_kpis`）；禁止题号→答案映射。
5. 每个结论必须有证据（`evidence` 表行）；失败如实返回结构化错误，不生成模板化假结论。
6. 密码、API Key、真实连接串不得写入代码、文档或提交信息，只放 `ocft-backend/.env`。比赛期间例外：`ocft-backend/.env` 与 `ocft-backend/master.key` 随私有仓库提交，保证克隆即可用，赛后删除并轮换全部凭据（2026-10-22 团队决策）。

详见 [docs/30-standards/redlines.md](docs/30-standards/redlines.md)。

## 目录归属

| 目录 | 负责 | 说明 |
|------|------|------|
| `ocft-backend/app/agent/`、`app/llm.py` | Agent 核心 | 编排、模型入口（公共层，改前先沟通） |
| `ocft-backend/db/`、`app/tools/sql_query.py` | 数据层 | 数据与查询工具 |
| `ocft-backend/eval/`、`ocft-backend/scripts/` | 评测 | 评测与批量导出 |
| `ocft-backend/app/compliance/`、`app/observability/` | 合规与可观测 | 合规与可观测（公共层） |
| `ocft-starter/` | 前端 | 前端 |
| `ocft-backend/scenarios/`、`docs/` | 场景与文档 | 场景包与文档 |
| `contracts/` | Agent 核心统筹 | 接口契约，变更先改这里并通知全员 |

修改他人目录前先确认；AI 生成的改动同样遵守。

## 后端约定

- 分层只能向下依赖：`routers → services → agent / tools / compliance → domain`。router 不直接访问 ORM 或 LLM。
- 配置只从 `app.config.settings` 读取。
- 数据库层只有一套：模型在 `app/models.py`，引擎在 `app/db.py`。表结构变化写成 `app/migrations.py` 里的一条新迁移（只增不删），不要只改模型。
- 新增工具：用 `@register_tool` 声明 → handler 返回 `(ToolResult, [EvidenceRecord], args)` → 输出字段白名单 → 加入场景 `allowed_tools` → 写单测。参考 `app/tools/credit.py`。
- 新增场景：在 `app/agent/scenarios.py` 注册 `Scenario(system_prompt, allowed_tools)`，引擎与存储不改。
- 写操作与审计在同一事务；审计只追加。
- 错误类型化（`ToolError` / `LLMError`），禁止吞异常。
- 依赖固定版本。

## 前端约定

- 业务数据只来自后端 API；`src/data/` 仅放场景说明类静态内容。
- 加载、失败、拦截、证据不足都要有诚实的 UI。
- 提交前 `npm run lint`。

## 命名

DB/Python 用 snake_case；API JSON、JS、工具参数用 camelCase；时间 API 输出 ISO 8601 带 `Z`。

## 常用命令

```bash
start.bat                                    # 评委 / 干净克隆：双击即离线启动（不联网装依赖，页面在 :8000）
powershell -ExecutionPolicy Bypass -File .\start.ps1   # 一键启动（Windows PowerShell；无 node_modules 时自动离线，-Dev 强制开发模式）
powershell -ExecutionPolicy Bypass -File .\pack-offline.ps1   # 改了依赖或前端后重建离线包，vendor/ 与 ocft-starter/dist/ 一起提交
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Reinstall   # 依赖有更新时重装后再启动
cd ocft-backend && uvicorn app.main:app --reload --port 8000
cd ocft-backend && python -m db.seed         # 执行数据库迁移 + 幂等导入样例数据（后端启动时也会做）
cd ocft-starter && npm run dev               # 前端 5173，/api 代理到 8000
cd ocft-starter && npm run lint
cd ocft-backend && python -m pytest tests -q   # 后端测试：假模型 + 临时 SQLite，不联网
python .agents/skills/redline-scan/scripts/scan.py  # 红线扫描
cd ocft-backend && python -m eval.run --input eval/datasets/public_sample.jsonl   # 评测，见 eval/README.md
```

## 工作方式

- 跨模块功能先写 spec：`docs/40-specs/<功能名>/`，模板见 [docs/40-specs/README.md](docs/40-specs/README.md)。小改动直接做。
- 接口变更先改 `/contracts`。
- 新文档登记到 [docs/INDEX.md](docs/INDEX.md)；完成开发流程中的一步时，同步更新 [开发流程](docs/10-strategy/开发流程.md) 的时序图与状态表。
- 过程留痕：每次合入 main 或做出决策，在 [开发日志](docs/10-strategy/开发日志.md) 追加一条；重要技术决策写 ADR（`docs/20-architecture/adr/`）。
- 自研边界：不接入扣子等低代码平台。编排调度可用 LangGraph，但模型只经 `llm.py`，工具只经注册表，不使用框架自带 ChatModel。新增任何依赖都登记到 [自研边界与依赖清单](docs/20-architecture/自研边界与依赖清单.md)。
- 可复用操作优先用 `.agents/skills/` 中的 Skill。规格八步以 `docs/40-specs/README.md` 为唯一格式：`code-write-requirements`、`code-write-design`、`code-split-tasks`、`code-implement-task`、`code-write-test-cases`、`code-review-code`、`code-write-unit-tests`、`code-update-spec`（`write-spec` 只串起前三步）。其余：`add-tool`、`add-scenario`、`run-eval`、`redline-scan`、`pre-submit`。
- 合入前按 [评审清单](docs/30-standards/review-checklist.md) 自查；提交信息遵循 [Git 规范](docs/30-standards/git-workflow.md)。
- 不确定的事先读代码再下结论；没验证过的不要声称已完成。
- 每次改完代码：跑通测试 / lint / build 后，把前后端运行起来（后端 `uvicorn app.main:app --port 8000 --reload`，前端 `npm run dev`，已在运行则确认已加载新代码），并告诉用户访问地址 http://localhost:5173 。
