# 金融科技基座 Agent 架构分析

> 日期：2026-10-21。状态：设计稿，各项实现进度见 §3 与 [开发流程](../../10-strategy/开发流程.md)。
> 依据：《[比赛规则要求](../../00-rules/比赛规则要求.md)》《[工程规划与得分策略](../../10-strategy/工程规划与得分策略.md)》。

## 1. 结论与边界

基于 FastAPI + React/Vite 建设模块化单体：

**一个主 Agent、有界工具循环、可插拔场景包、MySQL 持久化、统一证据与确认日志。**

2026-10-22 起，循环的下一跳由 LangGraph 调度（[ADR-0004](../../20-architecture/adr/0004-用LangGraph封装有界工具循环.md)）。轮数、时限、token 与终态仍在 `engine.py` 判定。

底座不引入微服务、多 Agent 团队、向量数据库和复杂消息队列。先让一种真实数据场景贯穿问答、工具、证据、业务确认、评测导出，抽签后替换数据和场景规则。

基座负责工程能力；赛题规则、数据格式、输出格式属于场景包。不能提前保证未知赛题正确率，也不能用样本结论代替现场推理。

## 2. 官方要求与建议的区别

| 层级 | 能力 | 基座实现 |
|---|---|---|
| 完赛硬要求 | 本地一键启动前端、后端、存储与模型调用 | 启动脚本、依赖检查、数据库迁移、模型连通检查 |
| 完赛硬要求 | 运行时只用 `deepseek-v4.1-flash` | 配置校验和唯一模型适配器，禁止其他模型回退 |
| 完赛硬要求 | 代码实现 Agent | Python 状态机、工具注册表、参数验证、执行循环 |
| 通用红线 | 答案证据可追溯 | 数据版本、查询参数、结果快照、证据 ID |
| 通用红线 | 业务人员确认结论后留痕 | 有身份的确认接口、结论版本、追加式审计事件 |
| 通用红线 | 禁伪造答案、测试答案填充 | 禁预存答案降级、标签隔离、失败如实返回 |
| 客观评分项 | 上下文、编排、可观测性 | 会话持久化、状态快照、工具轨迹、耗时与用量 |
| 客观评分强制项 | 敏感内容等合规 | 输入输出检查、隐私保护、越权拦截及审计 |
| 提交要求 | 非公开题运行结果一并交付 | 同一执行入口批量跑题、导出和校验 |
| 可选增强 | 公开 Skill/MCP | 有业务需要才接入，使用时写清 README |
| 团队技术选择 | MySQL、SQL 工具、React、FastAPI | 团队选型，不是官方指定技术（见 [技术选型](../../20-architecture/技术选型-开发语言与前端.md)） |

注意：MCP/Skill 是允许使用，不是必须接入一个；SQL 工具也不是官方硬性指定。不能把工程规划中的技术建议当成资格门槛。

## 3. 能力建设清单

| 能力 | 设计要求 | 状态 |
|---|---|---|
| 模型锁定 | 只允许 `deepseek-v4.1-flash`，配错即拒绝启动；错误类型化、超时、用量记录 | ✅ `config.py`、`llm.py` |
| 持久化 | 启动只建表不清库；样本导入独立、幂等 | ✅ `db.py` |
| 执行存储 | 会话、执行、轨迹、证据、确认、审计表 | ✅ `models.py` |
| 唯一答题入口 | 所有答题经 `/api/agent/runs`，不设场景直连路由 | ✅ `routers/agent.py` |
| 标签隔离 | 评测标签与预存结论不进运行时数据，只存 `eval/fixtures/` | ✅ 回归测试 `tests/test_redlines.py` |
| 健康检查 | 存活与依赖就绪分开 | ✅ `/api/health/live`、`/api/health/ready` |
| 前端数据来源 | 对话、证据、操作状态全部来自真实 API | 🔄 对话已接 API；场景面板仍用静态样例 |
| 一键启动 | 根目录启动脚本（评测机为 Windows） | ✅ `start.ps1`（Windows，`-Offline` 离线模式） |
| 契约 | 统一在根目录 `/contracts` | ✅ `contracts/agent-api.md` |

规则引擎的阈值只是样例场景的业务逻辑，不是官方业务政策。

## 4. 推荐执行状态机

```text
接收请求 → 建立 runId → 输入合规 → 加载会话与权限
                                         ↓
                       缺必要信息 → needs_clarification
                                         ↓
                          模型选择工具或提出答案草稿
                                         ↓
                 参数/权限校验 → 执行工具 → 保存结果与证据
                                         ↓
                    可继续调用工具，但受轮数/耗时/预算限制
                                         ↓
                  证据校验 → 生成结构化答案 → 输出合规检查
                                         ↓
              保存最终答案和审计 → succeeded / needs_confirmation

输入或输出违规 → blocked
证据不足 → insufficient_evidence
依赖故障或达到限制 → failed
```

确认是后续独立动作，不让长时间等待占用一次模型请求：

```text
业务人员 → 身份与权限检查 → 指定 runId 和结论版本
         → 事务内记录确认/驳回与审计 → 返回 confirmationId
```

确认结论与执行转账、放款、冻结是两件事。MVP 只提供结论确认；真实金融操作另需工具、授权、幂等与执行回执，不用话术模拟。

## 5. 模块边界

```text
contracts/                 请求、响应、工具 schema，版本化
ocft-backend/app/
  routers/                 HTTP 校验与响应，不直接访问 DB
  agent/                   graph.py 调度循环，engine.py 判定终态，另有场景与上下文策略
  services/                问答、确认、审计用例
  domain/                  状态与证据规则、存储接口
  repositories/            SQLAlchemy/MySQL 适配实现
  tools/                   公共查询、检索、确定性计算
  compliance/              输入输出与权限策略
  observability/           请求日志、工具轨迹、用量
  llm.py                   指定模型唯一调用入口
ocft-backend/scenarios/     每个场景的工具、规则与提示模板
ocft-backend/eval/          测试输入、评分与结果导出
ocft-starter/src/features/
  conversation/            对话与澄清
  evidence/                来源与执行轨迹
  confirmation/            人工确认
```

依赖方向：路由调用服务；服务/Agent 面向领域与接口；仓储和外部适配器实现接口；应用入口负责装配。领域层不导入 FastAPI、SQLAlchemy 或模型 SDK。

短期先拆最关键调用路径，不为了目录整齐一次重构所有场景。

## 6. 表结构到 API/类型映射

数据库是持久状态的单一事实源。DB 使用 snake_case，API/TS 使用 camelCase；时间统一 UTC，API 返回带时区的 ISO 8601。

| 表及核心字段 | API/TS 映射 | 用途 |
|---|---|---|
| `conversations(id, owner_id, context_version)` | `Conversation(id, ownerId, contextVersion)` | 会话归属、并发更新控制 |
| `messages(id, conversation_id, role, content, created_at)` | `Message(conversationId, createdAt, ...)` | 原始多轮历史 |
| `agent_runs(id, conversation_id, status, answer, answer_version, context_snapshot, model, usage, data_version)` | `AgentRun(answerVersion, contextSnapshot, dataVersion, ...)` | 一次执行、最终结论与上下文 |
| `tool_traces(id, run_id, sequence, tool_name, args, result_ref, duration_ms, error_code)` | `ToolTrace(runId, toolName, durationMs, ...)` | 实际工具输入、执行状态和耗时 |
| `evidence(id, run_id, source_type, source_ref, snapshot, content_hash, data_version)` | `Evidence(sourceType, sourceRef, contentHash, ...)` | 查询或原文快照，支持复核 |
| `audit_logs(id, run_id, event_type, actor_id, answer_version, payload, created_at)` | `AuditEvent(eventType, actorId, answerVersion, ...)` | 确认、驳回、拦截等追加式事件 |

`source_ref` 应包含表/主键、查询与绑定参数，或文档 ID/页码/片段位置。只有 SQL 文本或摘要不足以重现变化前的数据。

最终答案保存在 `agent_runs`，审计通过 ID 和版本引用，避免多张表各自维护一份可变结论。摘要是可重建派生上下文，注明覆盖消息范围，不覆盖原始历史。

## 7. 最小契约

先确认 `/contracts` 中的版本化契约，再实现代码和前端类型。

| 入口 | 最小输入/输出 |
|---|---|
| `POST /api/agent/runs` | 输入 `question, conversationId?, scenarioId?`；输出 `runId, conversationId, status, answer?, evidenceIds[], error?` |
| `GET /api/agent/runs/{runId}` | 返回持久化执行状态、答案版本和证据引用 |
| `GET /api/agent/runs/{runId}/events` | SSE 返回阶段、工具状态、证据与最终结果，带可恢复事件序号 |
| `GET /api/conversations/{id}/messages` | 返回有权限访问的会话历史 |
| `POST /api/agent/runs/{runId}/confirmations` | 输入 `answerVersion, action, comment?, idempotencyKey`；身份取自服务端认证 |
| `GET /api/agent/runs/{runId}/audit` | 返回有权限访问的追加式事件 |
| `GET /api/health/live`、`GET /api/health/ready` | 分别检查进程存活、配置/数据库/近期模型连通状态 |

统一内部工具返回：

```text
ToolResult {
  isSuccess, data, evidenceIds[],
  error?: { code, message, isRetryable }
}
```

HTTP、SSE、批量评测全部调用同一个 `run()` 服务。不另外制造演示专用回答路径。

SSE 可以先推送真实阶段和工具事件；最终答案通过输出检查后再显示，避免违规文本先流出后拦截。

## 8. 各项能力怎么实现

### 模型与工具编排

运行时固定 `deepseek-v4.1-flash`，环境变量只提供 API 地址和凭据；其他模型名称配置直接报错。摘要、规划、生成等运行时模型调用均遵守限制。

接入阶段用实际赛事接口验证工具调用、结构化输出、流式及 usage 支持。模型名称写进配置不代表已连通，不能假设普通公开 DeepSeek 接口可提供该模型。

优先原生 tool calling；若赛事接口不支持，使用经 Pydantic 校验的结构化 action 协议，允许有限格式修复，失败退出。禁止 `eval` 模型文本。

建议初始限制：最多 6 轮工具循环、每次执行 60 秒、每个模型请求明确 token 上限；数值是起点，按真实评测调整。记录 usage 和按实际价格估算费用，执行前检查余量，不能承诺估算绝不超支。

### 工具与证据

先提供 3 类公共能力：只读数据查询、原文检索、确定性计算，再加入选定场景规则工具。

查询优先参数化业务工具；确需开放 SQL 时，同时使用只读数据库账号、表/视图白名单、SQL 语法树校验、单条只读查询、结果行数与执行时间限制。不能只检查字符串是否以 SELECT 开头。

排除答案标签列和存放 expected 的数据源；只读权限本身无法防止答案泄漏。

计算工具使用 Decimal 或受控运算，记录输入数据证据及公式。金融结论来自规则和实际数据；LLM 负责理解、规划、抽取与表达。文档抽取可由 LLM 完成，但必须引用原文并校验单位和数值。

### 上下文管理

保存会话原文、最近若干轮、必要实体与约束；超预算时压缩旧内容，保存摘要覆盖范围和原文引用。大工具结果只将有关行/片段传给模型，完整证据仍持久化。

摘要中的身份、授权、确认不能成为权限依据；授权由服务端状态决定。不同用户的会话按归属隔离，并发提交通过版本控制避免覆盖。

### 合规与安全

输入检查、工具权限、输出检查共同执行；敏感词表只是基础，不能保证完整合规评分。加入诱导泄漏、提示注入、隐私查询、违规金融承诺等测试。

检索内容按不可信数据处理，不能替换系统规则或赋予工具权限。日志不得保存 API Key 或连接密码；敏感业务数据按权限显示与脱敏，受限原始证据和可见日志分开。

模型不可用返回结构化错误；规则已完成时可明确展示已有事实，但标记执行降级，不能宣称真模型 Agent 完整成功。

### 留痕与可观测

记录 runId、节点状态、真实工具入出参引用、耗时、模型标识、usage、错误码、证据 ID、合规命中及结论版本。

展示可验证的计划摘要和实际执行过程，不要求展示模型内部思维链。

确认必须绑定服务端身份、runId 与答案版本；重复提交幂等，确认与审计在事务中写入。过时版本拒绝确认。按应用权限限制审计修改，并备份数据库。

### 一键启动与持久化

提供 `start.ps1`（评测机为 Windows，不维护 bash 脚本与 Docker 方案），统一检查依赖、加载本机 `.env`、执行非破坏性迁移、起前后端并打印地址；退出时清理子进程。

数据库统一用 MySQL（2026-10-24 决策），连接在 `config.yaml` 的 database 段配置；SQLite 只用于自动化测试。启动脚本不清表，样本导入为显式、幂等操作。

“本地启动”不等于模型离线运行；真实模型仍需网络和凭据，README 必须写清前置条件。

### 评测与 MCP

评测输入保留题 ID 和问题，expected 只交给评分器，不进入 Agent 请求、Prompt、工具或会话。JSONL 逐题落盘，记录失败，支持中断续跑与产物校验。

公开题用于发现通用推理/工具缺陷，不建立题目到标准答案的查找表。非公开集不猜答案、不按题 ID 特化。最终提交格式等官方公布后增加导出适配器。

MCP 可以按赛题选择文件读取或检索组件，所有调用仍经相同权限、证据和审计管道；README 说明来源、版本、配置、权限、失败策略。不是为了数量强接无用组件。

## 9. 建设顺序与验收

| 顺序 | 交付 | 验收条件 |
|---|---|---|
| P0-1 | 模型锁定、异常可见、停用清库 | 错模型拒启动；真实模型请求成功；重启数据不丢 |
| P0-2 | 最小契约、迁移、run/证据/审计存储 | 一次执行可通过 ID 追溯到实际查询快照 |
| P0-3 | 一个真实场景的工具循环 | 新输入实际触发工具，不是命中固定答案 |
| P0-4 | 合规与结论确认 | 越权被拦；确认人、结论版本与时间可查 |
| P0-5 | 一键启动与真 API 前端 | 干净环境按 README 起全栈并显示真实结果 |
| P1-1 | 上下文、轨迹、限制与恢复 | 多轮保留约束；工具错误有轨迹；循环会终止 |
| P1-2 | 批量评测与导出 | 同一 pipeline 跑公开/非公开输入，错误题不丢失 |
| P2 | 其余场景包、可选 MCP、路演 | 替换场景无需改公共执行/审计/评测接口 |

建议六人按模块并行：A 编排与模型；B 数据与工具；C 评测提交；D 合规审计确认；E 前端；F 场景文档与集成。公共契约由 A 统筹，数据库由 B、审计由 D 维护，跨模块改动先协商。

最小验收题覆盖：单表查询、多工具计算、文档引用、多轮澄清、证据不足、违规请求、越权查询、模型超时、工具失败、重启保留、重复确认、标签隔离。

## 10. 待确认事项

1. 主办方提供的真实模型 endpoint、鉴权、限流及工具调用能力。
2. 赛题数据形态、可访问范围与最终提交格式。
3. 官方“48 小时”与“周六上午到周日中午”的时间表不一致，按实际截止时间规划并向主办方确认。
4. 团队是否采用本方案的模块化单体、MySQL 启动方式和最小契约。

工程规划的时间占比已于 2026-10-22 修正为合计 100%，并按赛时约 26 小时排期（待办 3-3）。

## 11. 主要取舍记录

| 决策 | 原因 | 代价与重访条件 |
|---|---|---|
| 自研有界状态机优先，不立即引入 LangGraph | 现有 Python 资产可直接复用，执行路径容易验证 | 2026-10-22 已由 [ADR-0004](../../20-architecture/adr/0004-用LangGraph封装有界工具循环.md) 取代：LangGraph 只调度下一跳，终态、工具与证据事务仍自研；未启用 checkpointer |
| 单主 Agent，不先做多 Agent | 降低调用费用、协调与排错成本 | 无专门多角色辩论；单 Agent 经评测证明受限后再拆 |
| MySQL 统一持久状态，不先加 Redis/向量库 | 本地交付简单，减少重复状态 | 检索与并发能力有限；真实数据规模需要时再加专用组件 |
| 最终答案合规检查后发布 | 防止未检查内容通过流式泄漏 | 首字延迟增加；先用真实阶段事件反馈进度 |
| 先查数闭环，再扩展五场景 | 最快验证模型、工具、证据、确认和提交全链路 | 不宣称覆盖未知赛题；抽签后优先完善目标场景 |
