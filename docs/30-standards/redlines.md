# 红线清单

> 官方红线 → 工程约束 → 自查方法。违反任一条可能取消资格，合入 main 前必须自查。
> 来源：[比赛规则要求](../00-rules/比赛规则要求.md)。

| 编号 | 官方要求 | 工程约束 | 自查方法 |
|------|----------|----------|----------|
| R1 | 运行时模型只能是 `deepseek-v4.1-flash` | 模型调用只经 `app/llm.py`；配置写其他模型名启动即失败；禁止在任何地方 new 第二个 LLM 客户端 | 搜索 `OpenAI(`、`model=` 只出现在 `llm.py` |
| R2 | 必须代码实现 Agent，禁扣子等低代码 | 编排、工具、业务逻辑全部在仓库代码中；不调用 Coze/Dify 等平台的 Agent/工作流 API | 依赖清单与代码中无相关 SDK / 域名 |
| R3 | 答案证据可追溯至数据或查询结果 | 每个结论都有 `evidence` 行（`source_ref` 含表/主键/参数或文档 ID + 快照） | 任取一个 run，能从 `runId` 查到证据快照 |
| R4 | 禁止在 Prompt 或工具中 Mock 答案 | Prompt、工具、种子数据不写某题的结论；种子数据只放原始业务字段，结论由规则/计算在运行时产出；模型失败返回结构化错误，不返回模板化"假结论" | 运行 `redline-scan` skill；评审时双人复查 |
| R5 | 禁止使用测试集或答案密钥作答 | `expected` 只给评分器；评测标签字段（如 `is_fraud`、`extracted_kpis`）运行时不可见；禁止题目 ID → 答案的查找表；禁止按题 ID 特化 | 搜索评测标签字段名只出现在 models 注释、评分器、合规规则中 |
| R6 | 结论经业务确认后留痕 | 确认走 `POST /runs/{runId}/confirmations`，绑定身份、答案版本，审计追加写入 | 确认后 `GET /runs/{runId}/audit` 有对应事件 |
| R7 | 合规（敏感词、政治性等）为强制项 | 输入、输出双端检查；命中即拦截并写审计；不静默改写 | 跑合规样例题，拦截率与审计记录都正确 |
| R8 | 本地一键启动全栈 | 根目录 `start.ps1` / `start.bat` 使用仓库内离线包完成安装与静态页面启动，不联网下载依赖；“离线”仅指安装交付，执行模型型 Agent 仍需访问模型 API，当前交付配置还需访问云 MySQL，`ready=200` 另需云 Redis | 在无 Python / Node 且断开依赖下载源的干净环境完成安装启动；联网后再核验模型 API、云 MySQL / Redis 连通与 `/api/health/ready` |
| R9 | 密钥不入库（团队约束；比赛期间例外） | 敏感值用 `enc:` 密文存储（[密钥管理](../50-runbooks/密钥管理.md)）；代码、文档（`.env` 以外）、提交信息中不出现明文密码 / Key。**比赛期间例外**：`ocft-backend/.env` 与 `ocft-backend/master.key` 随私有仓库提交，克隆即可用；赛后删除这两个文件并轮换全部凭据（2026-10-22 团队决策） | 提交前 `git diff --cached` 搜 `password|api_key|sk-`，命中只允许出现在 `ocft-backend/.env` |

## 待处理事项

新发现的红线隐患记在这里，处理后移到"已处理"。

- 2026-10-24（R9，赛后）：`ocft-backend/.env` 的一行注释曾含 MySQL 明文连接串，已删除，但仍留在 git 历史里（远端私有仓库）。赛后轮换凭据时，这个 MySQL root 口令必须一起换掉。

### 已处理

- 2026-10-24（合规，自查第 9 条）：`dd_snapshot.Masker` 已覆盖企业、法人、实控人、股东、关联方等名称，模型请求、工具结果、工具参数和 `llm_calls` 预览均使用 run 内代号；`test_dd_multi_agent.py` 与 `test_agent_runs.py` 已覆盖名称不外送、参数还原和输出还原。

- 2026-10-24（R5）：`enterprise_risk.risk_level_summary` 与公开测评集评级 10/10 一致，此前经 `rate_risk.externalRiskLevel` 送入模型、参与复核判定，并在目录与 `sql_query` 中可见。已在运行时全部移除：工具、证据、目录、提示词不再出现；`sql_query` 显式引用拒绝、`SELECT *` 剔除；一致性对照只在 `eval/`。回归测试 `tests/test_dd_answer_isolation.py`（ADR-0008 决策 1）。

- 2026-10-24（R1）：分支 `feat/data-rag-base` 引入了本地嵌入模型 bge-small-zh-v1.5，嵌入模型算不算"运行时模型"一直没有确认。团队已确认赛题 04 不用 RAG，该分支不合入 `main`，此项风险消除。

- 2026-10-22：`db/models.py`、`db/seed.py` 移除 `rule_id`、`evidence`、`decision` 预存结论列，三张表只存业务事实，结论由运行时规则计算；之后 `sql_query` 才加固并注册进 Agent（待办 1-6 / 1-7）。
- 2026-10-22：前端改造，删除 `src/data/` 中带 `isFraud`、`extractedKpis`、`decisionReason` 的样例数据与五个静态场景面板；`src/data/scenario.ts` 只保留场景说明与提问模板；看板数据来自 `/api/agent/stats`。
- 2026-10-21：敏感配置改为密文存储（`app/secret_box.py`，`enc:` 前缀 + 本机主密钥），文档中的明文数据库连接信息已移除，见 [密钥管理](../50-runbooks/密钥管理.md)。
- 2026-10-21：`app/` 运行时数据去掉评测标签与预存结论（`is_fraud`、`fraud_type`、`decision`、`decision_reason`、`extracted_kpis`，信贷 `status` 统一为 `pending`）；原值迁到 `ocft-backend/eval/fixtures/sample_labels.json`，仅供离线评分。
- 2026-10-21：答题入口统一为 `/api/agent/runs`，移除 P0 阶段按场景直连的五个路由（`/api/credit|risk|claims|chat|docs`）及其模板化降级回复。由 `tests/test_redlines.py` 做回归保护。

- 2026-10-25（数据处理合规）：合成探针复现未知“合伙企业”与“由某某担任法定代表人”漏脱敏，已扩展名称/角色句式与结构化字段兜底；主控每轮重送前重新处理完整消息，解码嵌套 JSON 与 Unicode 转义；未知法人证件号按字段掩码，不依赖校验位。新增主控、历史、工具参数、六角色及假 SDK 边界回归。此修复不代表任意无标注自由文本实体均可识别，输入仍应优先采用申请编号和结构化资料。
