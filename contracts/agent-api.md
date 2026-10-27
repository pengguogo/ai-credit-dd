# Agent 基座 API 契约 v1

> 依据根目录 [README](../README.md)、[ADR-0004](../docs/20-architecture/adr/0004-用LangGraph封装有界工具循环.md) 与 [ADR-0008](../docs/20-architecture/adr/0008-赛题04采用主控加六角色多Agent编排.md)。DB 使用 snake_case，API/TS 使用 camelCase，时间统一 UTC（ISO 8601 带 `Z`）。
> 本契约是 Agent 执行基座的唯一对外形态；HTTP、SSE、批量评测共用同一个 `run()` 服务，无演示专用路径。

## 通用约定

- 所有响应 camelCase。错误结构：`{ errorCode, message }`（HTTP 状态码 4xx/5xx）。
- Agent 接口身份优先取自有效的 `Authorization: Bearer <token>`（由 `POST /api/auth/login` 签发）；未解析到有效 Bearer 会话时兼容读取 `X-Actor-Id`（评测 / 旧调用）。两者同时有效时以 Bearer 登录用户的 `username` 作为 actorId；两者都不可用时返回 400 `actor_id_required`。`/api/auth/me`、logout 与管理接口只接受 Bearer，不走兼容回退。
- run 状态机（终态六种）：
  `running → succeeded | needs_confirmation | needs_clarification | blocked | insufficient_evidence | failed`
- 运行限制：**默认不限工具循环轮数、不限单次 run 总时长**（2026-10-24 起取消原 6 轮 / 60 秒，[ADR-0008](../docs/20-architecture/adr/0008-赛题04采用主控加六角色多Agent编排.md) 决策 4）；保留单次模型调用超时 `llm_timeout_seconds`、单请求 max_tokens、run 累计 token 上限。轮数与总时限仍可经 `RUN_MAX_TOOL_ROUNDS` / `RUN_TIMEOUT_SECONDS` 配置启用，启用后行为同下文。

## 端点

### POST /api/agent/runs

执行一次 Agent run（默认不限总时长；单次模型调用受 `llm_timeout_seconds` 约束）。

请求：

```json
{
  "question": "评估贷款申请 LA001 的尽调结论",
  "conversationId": "可选，缺省新建会话",
  "scenarioId": "可选，缺省 enterprise_dd",
  "mode": "可选，sync（默认）| async",
  "attachments": [
    { "type": "image_url", "imageUrl": "https://… 或 data:image/jpeg;base64,…" }
  ]
}
```

- `question` 是唯一必填字段；`conversationId`、`scenarioId`、`mode`、`attachments` 均有缺省值或可省略。
- `sync`：执行完成后返回终态（评测与批量导出用）。
- `async`：校验场景、附件与会话归属后立即返回 **202**，`status = "running"`，带完整 `AgentRunOut` 字段；随后用 `GET /runs/{runId}/events` 实时接收过程，`run_finished` 后用 `GET /runs/{runId}` 取结果。参数或权限错误仍同步返回 4xx。执行中的实时推送只在执行所在进程可见（单进程部署）。

所有响应带 `X-Request-Id` 头（请求传入的合法值原样回显，否则服务端生成），并记录在 run 的 `contextSnapshot.requestId` 与审计中。

#### 多模态输入约定（attachments）

- `attachments` 保留兼容字段；省略或空数组继续执行文本链路。
- **2026-10-24 合规修复**：当前没有本地图片内容脱敏能力，任何非空图片附件均同步返回 HTTP 422、`errorCode = "invalid_attachment"`，提示改用脱敏文本；sync / async 一致，不创建 run、不调用模型。原图片直传行为停用，前端选择与粘贴图片入口关闭。
- 企业名称可在本地业务答案中还原；法人、实控人等自然人名称保持代号，证据API及导出中的法人/实控人字段掩码。号码和地址继续不还原。

响应 200（sync 模式，终态即返回；`answer` 仅在 succeeded / needs_confirmation 出现）：

```json
{
  "runId": "run_ab12cd34",
  "conversationId": "uuid",
  "scenarioId": "enterprise_dd",
  "question": "评估贷款申请 LA001 的尽调结论",
  "status": "needs_confirmation",
  "answer": "…结论文本…",
  "answerVersion": 1,
  "model": "deepseek-v4.1-flash",
  "usage": { "promptTokens": 1234, "completionTokens": 567, "totalTokens": 1801 },
  "dataVersion": 1,
  "errorCode": null,
  "errorMessage": null,
  "evidenceIds": ["ev_1a2b3c4d"],
  "createdAt": "2026-10-21T08:00:00Z"
}
```

`model` 取本次 run 持久化的产品模型名；`dataVersion` 取当前配置（代码默认 `1`）。async 的 202 响应字段相同，但 `status="running"`、`answer/answerVersion` 为空、usage 为 0、`evidenceIds` 为空。

终态判定（只依据本次 run 的真实工具结果）：

| status | 触发条件 | answer / answerVersion | errorCode | errorMessage |
|--------|----------|------------------------|-----------|--------------|
| `needs_clarification` | 模型调用内置工具 `request_clarification`（指代不明、多个候选、缺必要信息）；或场景 `require_evidence` 下的能力外问题：本次未调用任何数据工具，且用户问题不含业务信号（场景 `business_intent_pattern`，如问候、闲聊） | null | `clarification_required` | 澄清问题；能力外问题为场景固定引导文本（`guide_message`，说明能力范围与提问示例），不含模型原文 |
| `insufficient_evidence` | 调用过数据工具但没有任何证据；或答案含结论（场景 `conclusion_pattern`）而本次无证据；或场景 `require_evidence`（企业尽调）且本次无任何证据（能力外问题除外，见上一行） | null | `evidence_missing` | 模型给用户的说明（如"未找到该申请"）；`require_evidence` 无证据时为固定说明，不含模型原文 |
| `needs_confirmation` | 有证据，且工具结果命中场景 `confirmation_rules`（信贷：规则引擎结论为 rejected / manual_review） | 结论 / 1 | null | null |
| `succeeded` | 有证据且未命中确认规则；或未调用工具的非结论回复（如职责说明，仅限未开启 `require_evidence` 的场景） | 结论 / 1 | null | null |

`needs_clarification` / `insufficient_evidence` 的 `errorMessage` 经过输出合规与 PII 掩码，并作为 assistant 消息写入会话历史；这两种状态不可确认（409 `run_not_confirmable`）。
每次模型调用的超时默认为 `llm_timeout`，超时以 `llm_unavailable` 结束。配置了 run 总时限时为 `min(llm_timeout, run 剩余时限)`：剩余时限不足 `run_min_llm_budget_seconds` 或被剩余时限截断的超时，均以 `run_timeout` 结束；配置了轮数上限时，超出以 `round_limit_exceeded` 结束。

模型响应后先累计真实 usage，再验收时限、Token 和完整性，之后才执行工具或判定答案终态。累计 Token 等于上限时可验收本次完整答案，但不再发起下一次调用；超过上限时为 `token_limit_exceeded`，不得以末轮没有工具调用绕过。由于 usage 由供应方在响应后返回，上限约束结果验收，不保证供应方实际消耗绝不超限。
`finish_reason = length` 表示响应截断，返回 `llm_output_incomplete`，不发布半份答案、不执行截断响应中的工具调用。超时或超限时保留已经取得的证据和真实 usage，但不得用中间报告回填成功。

失败（模型不可用、超限等）→ `status = "failed"`，`errorCode ∈ llm_unavailable | run_timeout | token_limit_exceeded | round_limit_exceeded | llm_output_incomplete | narrative_check_failed`（最后一项为尽调场景发布前事实校验不通过）。
违规输入 → `status = "blocked"`，`errorCode = compliance_input_rejected`；违规输出 → `errorCode = compliance_output_blocked`。`blocked` 时 `errorMessage` 为面向用户的拒答话术，不含命中词。
个人信息（身份证、手机号、银行卡、邮箱）在保存和送模型前掩码，`question`、`answer` 返回的都是掩码后的文本。

### GET /api/agent/runs/{runId}

返回持久化的执行状态、答案版本、证据引用、工具轨迹摘要。越权（非 owner）返回 403。

```json
{
  "runId": "…", "conversationId": "…", "scenarioId": "enterprise_dd",
  "question": "评估贷款申请 LA001 的尽调结论", "status": "needs_confirmation", "answer": "…", "answerVersion": 1,
  "model": "deepseek-v4.1-flash", "usage": {…}, "dataVersion": 1,
  "errorCode": null, "errorMessage": null,
  "evidenceIds": ["ev_…"],
  "toolTraces": [
    { "sequence": 1, "toolName": "get_loan_application", "status": "ok",
      "args": {"applicationId": "LA001"}, "durationMs": 12, "errorCode": null }
  ],
  "contextSnapshot": {
    "historyMessages": 4, "maxHistoryMessages": 12, "historyTokenBudget": 4000,
    "compressedRange": { "fromMessageId": 1, "toMessageId": 8, "count": 8 },
    "toolSummaryRuns": ["run_…"], "estimatedHistoryTokens": 820,
    "entities": { "applicationId": ["LA001"], "enterpriseId": ["E001"] },
    "roundsExecuted": 2, "toolCalls": 1,
    "toolSummaries": [{ "toolName": "run_dd_agents", "args": {…}, "isSuccess": true,
                        "result": "{…截断的关键数据…}", "evidenceIds": ["ev_…"] }],
    "missingInfo": [], "confirmationReasons": ["规则引擎结论为拒绝或转人工复核，需业务人员确认（…）"],
    "skillsApplied": [
      "business-verification@1.1.0", "financial-analysis@1.1.1",
      "opinion-scan@1.1.0", "fraud-detection@1.1.0",
      "credit-limit@1.2.1", "dd-report@2.1.3"
    ]
  },
  "startedAt": "…Z", "finishedAt": "…Z"
}
```

另有 `timings`（节点级耗时，来自持久化事件）：

```json
"timings": [
  { "node": "compliance", "stage": "input", "durationMs": 6 },
  { "node": "llm", "round": 1, "status": "ok", "durationMs": 3276 },
  { "node": "tool", "sequence": 1, "toolName": "run_dd_agents", "status": "ok", "durationMs": 2 },
  { "node": "compliance", "stage": "output", "durationMs": 0 },
  { "node": "run", "durationMs": 6329 }
]
```

异步 run 执行中（尚未落库）查询详情，返回 `status = "running"`，`toolTraces`、`timings` 为空，过程以 SSE 为准。

`contextSnapshot` 记录本次 run 的上下文来源，便于复核：`requestId` 为发起该 run 的请求 ID；`compressedRange` 为被压缩成摘要的历史消息 ID 范围（无压缩为 null）；`toolSummaryRuns` 为本次随历史带入工具结果摘要的前序 run；`entities` 为会话累积的实体槽位（新值在前）；`toolSummaries` 已做 PII 掩码，完整数据以 evidence 为准；`skillsApplied` 为本次 run 给实际规划角色装配的 Skill（`name@version`，按角色顺序，2026-10-24 新增，旧 run 无此键）。

运行时 Skill（2026-10-24 新增）：尽调六个角色 Agent 各有一个版本化 Skill（`ocft-backend/scenarios/dd04/skills/*.md`，front matter 含 `name`、`title`、`version`、`role`、`roles`、`inputs`、`outputs`，正文为输入契约、解读与成文规则）。角色执行时，Skill 拼在该角色 system 消息末尾；`run_dd_agents` 结果的 `roles.<角色>.skill` 与 `contextSnapshot.skillsApplied` 记录实际装配的 `name@version`。当前版本依次为 `business-verification@1.1.0`、`financial-analysis@1.1.1`、`opinion-scan@1.1.0`、`fraud-detection@1.1.0`、`credit-limit@1.2.1`、`dd-report@2.1.3`。Skill 只规定写法，不含数据；对外 API 响应形态不变。

### GET /api/agent/runs/{runId}/events

该 run 的真实阶段事件。异步 run 执行中实时推送（内存事件总线）；已结束的 run 从 `run_events` 表重放，两者序号一致。
每条事件带 `id: <eventIndex>`；断线后用请求头 `Last-Event-ID` 或查询参数 `?after=<eventIndex>` 续传，只返回序号更大的事件。无新事件时每 15 秒发送 `: keepalive` 注释行。越权 403。
浏览器原生 `EventSource` 不能设置 `Authorization` 或 `X-Actor-Id` 请求头，前端用 `fetch` 读取流。

| 事件 | data 字段（另含 `eventIndex`、`runId`） |
|------|------------------------------------------|
| `run_started` | `scenarioId, question, conversationId, attachmentCount` |
| `compliance_checked` | `stage: input\|output, isClean, durationMs` |
| `compliance_blocked` | `payload: {stage, code, category, reason}` |
| `llm_call_finished` | `round, status: ok\|error, errorCode, durationMs, totalTokens?, toolCalls?: string[]` |
| `tool_started` | `sequence, toolName` |
| `tool_finished` | `sequence, toolName, status, durationMs, errorCode, evidenceIds` |
| `plan_ready` | `plan: {mode: full\|followup, scope: loan\|enterprise, roles: string[], target: {applicationId, enterpriseId}, focus, configFile}`（尽调多 Agent，`roles` 为依赖闭包后的集合；`scope` 为本次尽调口径） |
| `role_started` | `role, name, parallelGroup`（当前 `parallel_analysis=true` 时，工商 / 财报 / 舆情 / 反欺诈 / 评级五个解读角色使用同一并行组；其确定性计算已在此前按依赖顺序完成） |
| `role_finished` | `role, name, status: ok\|degraded\|skipped\|failed, durationMs, llm, evidenceCount, errorCode, keyFindings` |
| `verify_finished` | `status: ok\|retry\|failed, attempt, issues: string[]`（发布前事实校验；`retry` 表示带问题清单重写） |
| `run_finished` | `status, errorCode, answerVersion, durationMs` |

#### 尽调多 Agent（`enterprise_dd`，ADR-0008）

- 主控只声明 `get_loan_application`、`find_enterprise`、`run_dd_agents`、`sql_query`（另有内置 `request_clarification`）。`run_dd_agents` 调度六个角色 Agent。当前 `parallel_analysis=true`：先按 `business`、`finance`、`opinion` → `fraud` → `rating` 的依赖顺序完成五个角色的确定性计算，再并行执行这五个角色的模型解读，最后由 `report` 汇总并进入事实校验；解读只消费已算出的结构化事实，不等待上游文字。设为 `false` 时按依赖顺序逐级执行。角色划分、依赖、每角色 `max_tokens` 与提示词在 `ocft-backend/scenarios/dd04/agents.yaml` 与 `prompts/`。
- `run_dd_agents` 入参含 `scope`：`loan`（默认，针对某笔贷款申请）或 `enterprise`（针对企业主体）。不传时按入参兜底：有 `applicationId` 为 `loan`，只给 `enterpriseId` 为 `enterprise`；非法值返回 `invalid_args` 且不调度角色。
- 贷款口径的结构化 `build_dd_report.dueDiligenceConclusion` 以准入建议开头（`建议准入` / `审慎准入` / `暂不准入`），紧接建议额度与期限，再以「依据：」列评级、一票否决与反欺诈命中；额度无法测算时写「额度无法测算，需补充材料后复核」。企业口径的结论以合作建议开头（`建议合作` / `审慎合作` / `暂不合作`），紧接建议授信额度，再以「依据：」列评级；不含申请贷款额度与期限。
- `mode=full`：报告角色的 Markdown 经事实校验后直接作为 `answer`，主控不再调用模型。`scope=loan` 输出五部分（企业概况 / 财务分析 / 风险提示 / 额度建议 / 风控条件，含申请贷款额度与建议授信额度）；`scope=enterprise` 同样五部分，额度建议只含建议授信额度（能力测算，产出 `calc_credit_limit` 证据），全篇不出现申请贷款额度、申请期限与担保方式。`mode=followup`：只跑所需角色及依赖，由主控成文，答案同样经事实校验。
- 事实校验：答案里带单位的数字、风险评级、规则编号（B/F 系列）、`ev_` 证据编号都必须能在本次工具结果里找到；企业口径额外校验不得出现申请贷款额度、申请额度、贷款期限、本次融资、放款前、投放前等贷款申请措辞（允许「建议授信额度 / 额度建议」）。不通过时带问题清单重写，次数见 `agents.yaml` 的 `verify.max_rewrites`，用尽仍不通过时 `status=failed`、`errorCode=narrative_check_failed`，已算出的结构化结果仍作为证据落库。
- 每个角色产出 `source_type=calculation` 的证据，`sourceRef` 含 `calc`（沿用单工具名，如 `rate_risk`、`calc_credit_limit`、`build_dd_report`）与 `role`。每次角色模型调用在 `/llm-calls` 中记一条，`purpose=role:<角色>`。
- 原始业务事实及库内 evidence 快照按源数据保留已知自然人原值；进入 run / 会话、模型请求、工具结果和模型审计预览前，法定代表人、实控人、自然人股东等已知自然人统一替换为 run 内代号，号码类 PII 另行掩码。企业全名、组织股东、关联企业和被担保方等企业 / 机构名称也先以代号外送，最终回答和澄清问题在输出合规、保存及发布前只还原本次 run 登记的企业 / 机构名称；自然人、信用代码、证件号和地址不还原，未知代号不得匹配其他实体。未入库的「…有限公司」与「法定代表人为 / 法人是 XX」等无冒号标注的原值同样在外送前遮蔽为 `[已脱敏企业]` / `[已脱敏]`。模型工具参数在本地执行前还原；证据 API、目录和导出继续使用独立掩码规则。
- 角色降级（模型输出两次不合规或预算不足）时数字照常给出、解读为空，终态进入 `needs_confirmation`。本场景 run 累计 token 上限取 `agents.yaml` 的 `controller.max_total_tokens`（默认 200000），优先于全局 `RUN_MAX_TOTAL_TOKENS`。
- 尽调相关输出不含外部汇总评级（`risk_level_summary` / `externalRiskLevel`）；`sql_query` 显式引用该列会被拒绝，`SELECT *` 结果会剔除该列。执行前 `enterprise_risk` 被替换为不含该列的子查询，CTE 列重命名、子查询、别名均无法取出该列。

审计（`/audit`）另有 `pii_redacted`（payload：`{stage: input|output, counts}`）；`run_started` 审计 payload 含 `requestId`、`attachmentCount`。

```
id: 5
event: tool_finished
data: {"eventIndex":5,"runId":"run_…","sequence":1,"toolName":"run_credit_rules","status":"ok","durationMs":5,"errorCode":null,"evidenceIds":["ev_…"]}
```

### GET /api/agent/runs/{runId}/evidence

该 run 的证据行（含当次快照），与 run 同权限，越权 403。

```json
{ "evidence": [
  { "evidenceId": "ev_…", "sourceType": "calculation",
    "sourceRef": { "table": "credit_applications", "keys": { "applicationId": "APP-2026-1004" }, "calc": "R001-R005" },
    "snapshot": { "applicationId": "APP-2026-1004", "…": "…" },
    "contentHash": "sha256 十六进制", "dataVersion": 1, "createdAt": "…Z" }
]}
```

`snapshot` 与 `sourceRef` 的取值经过 PII 掩码（手机号、身份证、银行卡、邮箱，只改值不改键）；库内保留原始快照，`contentHash` 是原始快照的哈希，用于库内复核。批量测评导出（results / 会话记录）同样掩码。

### GET /api/agent/catalog/{scenarioId}

当前场景的业务事实目录，供工作台表格展示。只含原始字段，不含评测标签，也不计算审批、拦截或核赔结论。`rows` 的取值经过 PII 掩码。身份沿用通用约定（Bearer 优先，`X-Actor-Id` 兼容）。未知场景返回 404 `unknown_scenario`。客服场景没有业务事实表，`rows` 是意图规则目录（I001–I007），不含某句原话的识别结论。

查询参数：
- `kind`（可选）：`enterprises` 企业基础信息，`applications` 审批表（默认），以及数据列表页用的 `shareholders` / `finances` / `public_opinions` / `lawsuits` / `related` / `guarantees` / `risks` / `schema_relationships`。非法值返回 400 `invalid_args`。
- `q`（可选，最长 100 字）在数据库中筛选当前表的可见字段，匹配编号、名称、类型、金额、状态和时间。审核状态关键词支持 `待处理`/`pending`、`待审核`/`pending_review`、`审核通过`/`approved`、`审核不通过`/`rejected`（旧词 `待尽调`、`待审批`、`已通过`、`已驳回` 仍作搜索别名）。

`total` 是全表条数，`matched` 是筛选后的条数，`rows` 最多返回 `limit`（100）条。可写表的每行含内部数字字段 `id`（不在 `columns` 里展示），供单行编辑/删除定位。

```json
{ "scenarioId": "enterprise_dd", "kind": "applications", "title": "审批表",
  "note": "金额单位为万元。风险评级由评分卡实时计算，不在目录中展示。",
  "query": "LA001", "total": 10, "matched": 1, "limit": 100,
  "columns": [{ "key": "applicationId", "label": "贷款编号" }, { "key": "enterpriseId", "label": "企业编号" }],
  "rows": [{ "id": 1, "applicationId": "LA001", "enterpriseId": "E001" }] }
```

审批表（`kind=applications`）含业务字段 `status`，共四态：`pending`（待处理）/ `pending_review`（待审核）/ `approved`（审核通过）/ `rejected`（审核不通过）。生成尽调报告后由 `pending` 自动推进到 `pending_review`；人工审核推进到 `approved` / `rejected`。  
`GET .../catalog/{scenarioId}?kind=applications&approvalStatus=pending|pending_review|approved|rejected|open` 可按状态筛选；`open` 表示待处理 + 待审核（智能尽调页的申请列表使用）。响应带 `statusCounts`（四态计数）。  
每行还带 `hasReport: boolean`（该申请是否已建档尽调报告）与审核留痕 `reviewReason` / `reviewedBy` / `reviewedAt`（未审核时为 null）。`hasReport` 供智能尽调的「查看报告」启用或置灰，不在 `columns` 里作为普通列展示；审核留痕也不在 `columns` 内。
改 `status` 需登录会话具备 `confirm` 权限（演示角色 `account_manager` / `admin`）；状态实际变为审核通过 / 审核不通过时，同一事务记录 `reviewedBy` / `reviewedAt`。

### POST /api/agent/catalog/{scenarioId}/{kind}/records

按表新增一条业务事实。身份沿用通用约定（Bearer 优先，`X-Actor-Id` 兼容）。`kind` 与目录相同，**不含** `schema_relationships`（对该 kind 返回 400 `invalid_args`）。请求体为 camelCase 业务字段对象（与对应 CSV/模型字段一致）；成功 200 返回 `{ "id", "kind", "row" }`（`row` 已 PII 掩码）。业务键冲突 409；校验失败 400；未知场景 404。

### PATCH /api/agent/catalog/{scenarioId}/{kind}/records/{id}

按内部 `id` 更新可写字段。语义与 POST 相同的 kind 限制。成功 200 返回更新后的 `{ "id", "kind", "row" }`；不存在 404；唯一键冲突 409。审批表改 `status` 需 `confirm` 权限。

### DELETE /api/agent/catalog/{scenarioId}/{kind}/records/{id}

按内部 `id` 删除。成功 200 `{ "id", "kind", "deleted": true }`；不存在 404；`schema_relationships` 400。

### POST /api/agent/catalog/{scenarioId}/applications/records/{id}/review

人工审核贷款申请（贷款管理-贷款申请列表的「审核」操作）。需登录会话同时具备 `applications` 与 `confirm` 权限。

```json
// 请求
{ "decision": "approved", "reason": "材料齐全，风险可控，同意按建议额度放款" }
// decision ∈ approved | rejected；reason 必填（去首尾空白后 1—500 字）
// 响应（与 PATCH 同构）
{ "id": 12, "kind": "applications", "row": { "applicationId": "LA001", "status": "approved",
  "reviewReason": "材料齐全，风险可控，同意按建议额度放款",
  "reviewedBy": "account_manager", "reviewedAt": "2026-10-25T02:10:00Z" } }
```

只有当前状态为 `pending_review` 的申请可审核，其余 409 `invalid_state`；`decision` 非法或原因为空 400 `invalid_args`；记录不存在 404 `not_found`；未知场景 404 `unknown_scenario`。状态、原因、审核人与 `catalog_reviewed` 审计记录在同一事务内写入，审计 `summary.keys` 带 `applicationId`、`reviewDecision`、`reason`。

写操作追加 `csv_import_audits`（`status` 为 `catalog_created` / `catalog_updated` / `catalog_deleted`，人工审核为 `catalog_reviewed`），不调用模型；不改变 CSV 增量导入「仅新增」语义。

### GET /api/agent/stats

全局运行统计，供运行看板使用。只有计数与耗时，不含问题、答案、证据内容；身份沿用通用约定（Bearer 优先，`X-Actor-Id` 兼容）。

```json
{ "totalRuns": 103, "statusCounts": { "succeeded": 67, "blocked": 16 },
  "blockedByCategory": { "crime": 9, "prompt_injection": 5 },
  "conclusionRuns": 78, "conclusionsWithEvidence": 73, "evidenceCount": 193,
  "toolUsage": { "run_credit_rules": 70 }, "confirmations": { "confirm": 2, "reject": 0 },
  "avgDurationMs": 3600, "p95DurationMs": 6600, "avgTotalTokens": 3147, "generatedAt": "…Z" }
```

`conclusionRuns` 为 `succeeded` / `needs_confirmation` 的 run 数，`conclusionsWithEvidence` 为其中至少有一条证据的 run 数。

### GET /api/agent/conversations

当前身份的历史会话，按最近更新倒序。身份沿用通用约定（Bearer 优先，`X-Actor-Id` 兼容）。只返回该身份自己的会话。

| 参数 | 说明 |
|------|------|
| `scenarioId` | 可选，只看一个场景；未知场景 404 `unknown_scenario` |
| `q` | 可选，按标题模糊搜索（最长 80 字） |
| `limit` | 可选，每页条数，默认 30，最大 100 |
| `offset` | 可选，偏移，默认 0 |

会话从第一次提问起绑定场景。用其他场景的 `scenarioId` 续接同一 `conversationId` 会返回 409 `conversation_scenario_mismatch`。

```json
{ "conversations": [
  { "conversationId": "…", "scenarioId": "credit_review", "title": "查一下申请 APP-2026-1001",
    "updatedAt": "…Z", "turnCount": 2, "lastStatus": "succeeded" }
], "total": 42, "limit": 30, "offset": 0, "hasMore": true }
```

`title` 是首问的前 60 字。`turnCount` 是用户消息条数。`lastStatus` 是该会话最近一次 run 的状态，没有 run 时为 null。`hasMore` 为是否还有下一页。

### GET /api/agent/conversations/{id}/messages

返回有权限访问的会话历史（越权 403）：

```json
{ "conversationId": "…", "messages": [
  { "id": 1, "role": "user", "content": "…", "runId": "run_…", "createdAt": "…Z" },
  { "id": 2, "role": "assistant", "content": "…", "runId": "run_…", "createdAt": "…Z" }
]}
```

user 消息的 `runId` 为处理它的 run（早于 2026-10-22 的历史数据可能为 null）。被输入合规拦截的提问保留在会话记录里，但不会进入后续轮次传给模型的历史。

### POST /api/agent/runs/{runId}/confirmations

业务人员对指定结论版本的确认/驳回。幂等：相同 `idempotencyKey` 重复提交返回同一 confirmationId。
过时 `answerVersion`（≠ 当前版本）返回 409。确认与审计在同一事务内写入。

```json
// 请求
{ "answerVersion": 1, "action": "confirm", "comment": "同意放款", "idempotencyKey": "uuid" }
// action ∈ confirm | reject
// 响应
{ "confirmationId": 101, "runId": "…", "answerVersion": 1, "action": "confirm",
  "actorId": "reviewer_zhang", "createdAt": "…Z" }
```

### 尽调报告（接口沿用 GET /api/agent/assets、GET /api/agent/assets/{assetId}）

页面名「尽调报告」（评审维度②的资产档案），接口路径与字段沿用 `assets` 命名，避免为改名动契约和表结构。

**报告本身没有状态**：不做确认 / 驳回 / 归档，因此不存在状态变更接口；审核结论记在贷款申请（`loan_application.status`：待处理 → 待审核 → 审核通过 / 审核不通过）。

完成的完整尽调 run 自动建档（贷款口径正文含五部分；企业口径正文含企业概况、财务分析、风险提示与风控条件，不含额度建议），同一 run 只建一次；追问、失败、澄清不建档。建档时若该申请的贷款状态仍为 `pending`（待处理），同一事务内推进为 `pending_review`（待审核），已审核的申请不覆盖；企业口径报告没有申请编号，不推进任何贷款状态。档案只指向 `runId`，正文与证据仍以 run / evidence 为准。

`GET /api/agent/assets?keyword=&applicationId=&enterpriseId=&kind=&limit=&offset=`

智能尽调列表点「查看报告」跳到「贷款管理-尽调报告」时带 `applicationId`，服务端只返回该贷款编号对应的报告；清除过滤后恢复全量列表。

```json
{ "assets": [ { "id": "ast_…", "scenarioId": "enterprise_dd", "applicationId": "LA001",
                "enterpriseId": "E001", "enterpriseName": "企业事实表中的名称", "conversationId": "…", "runId": "run_…",
                "kind": "report", "title": "LA001 企业信贷尽调报告",
                "applyAmount": 3000, "reportGeneratedAt": "…Z",
                "summary": "尽调结论：…", "evidenceCount": 9, "contentSha256": "…",
                "createdBy": "eval_runner", "createdAt": "…Z", "updatedAt": "…Z" } ],
  "total": 1, "limit": 30, "offset": 0, "hasMore": false }
```

`GET /api/agent/assets/{assetId}` 返回同一投影；不存在 404 `not_found`。

`enterpriseName` 为 `string | null`，读取时由企业事实表按 `enterpriseId` 关联，新旧档案均适用；企业资料缺失时为 null，不丢弃档案。关键词同时匹配企业名称，过滤后再分页、计数。页面使用中文名称生成展示标题，缺失时明确提示未登记；`title` 仍保留建档时标题，`runId` 仍用于原报告链接，界面正文不直接显示内部运行标识。

展示补充字段：`applyAmount: number | null` 为该 run 已保存的 `build_dd_report.creditSuggestion.applyAmount`（优先）或 `calc_credit_limit.applyAmount` 证据快照，单位万元；缺失返回 null（企业口径报告恒为 null），不从当前申请表回填历史金额。`reportGeneratedAt: string` 为关联 run 的 finishedAt，旧数据缺失时使用档案 createdAt，输出 ISO 8601 带 Z，不使用 updatedAt。列表与详情一致。

权限：报告列表与详情需 `confirm` 权限（登录会话校验；`X-Actor-Id` 评测调用不拦截）。已建档报告关联的 `GET /runs/{runId}`、`/evidence`、`/events`、`/audit` 不再限制 owner，进入报告即可查看轨迹与证据；未建档的普通对话 run 仍只有 owner 可看，越权 403。

表内 `status` / `version` / `archived_at` 与 `workspace_asset_events` 为历史列，保留以兼容既有库与历史行，不再对外返回、也不再有写接口。

### 会话记忆：GET / PATCH / DELETE /api/agent/conversations/{conversationId}/memory

记忆可查看、可纠正、可清除（9 题评审维度②）。只有会话 owner 可操作（越权 403，不存在 404）。记忆是下一轮会带给模型的内容：实体槽位（作为"会话已知实体"系统消息）和历史范围；已确认结论只读展示。

GET 返回：

```json
{ "conversationId": "…", "scenarioId": "credit_review",
  "entities": { "applicationId": ["APP-2026-1004"] },
  "allowedKeys": ["applicationId", "customerName"],
  "historyFromMessageId": null, "totalMessages": 4, "carriedMessages": 4,
  "confirmedConclusions": [ { "runId": "run_…", "answerVersion": 1, "answer": "≤200 字，PII 掩码",
                              "confirmedBy": "reviewer", "confirmedAt": "…Z" } ],
  "version": 2, "updatedBy": "tester", "updatedAt": "…Z",
  "events": [ { "id": 1, "eventType": "memory_corrected", "actorId": "tester",
                "payload": { "before": {}, "after": {}, "version": 2 }, "createdAt": "…Z" } ] }
```

- `PATCH`，body `{"entities": {"applicationId": ["APP-2026-1001"]}, "expectedVersion": 2}`：只改出现的键，空数组表示删除该键。键必须在 `allowedKeys` 内；每键最多 5 个值、每个不超过 64 字，去掉换行与控制字符，做 PII 掩码；未通过输入合规时返回 422 `memory_blocked`，格式不对返回 422 `invalid_memory`。`expectedVersion` 与当前版本不一致返回 409 `memory_version_conflict`。
- `DELETE ?scope=entities|history|all&expectedVersion=N`：`entities` 清空槽位；`history` 让现有消息不再带入模型（消息本身保留，`/messages` 仍可查看）；默认 `all`。
- 每次 run 结束会把本轮合并后的槽位写回记忆（`updatedBy = "agent"`）。纠正与清除写 `events`（只追加）；历史 run 的 `contextSnapshot` 不受影响。

### GET /api/agent/runs/{runId}/llm-calls

外部大模型调用审计（通用纪律第 2 条：外部调用的入参、时间、用途须留存）。与 run 同权限，越权 403。每次调用一条，按轮次排序：

```json
{ "calls": [
  { "id": 1, "round": 1, "purpose": "tool_loop", "model": "deepseek-v4.1-flash",
    "status": "ok", "errorCode": null, "messageCount": 2,
    "requestSha256": "实际请求体 {messages, tools} 的 sha256",
    "requestPreview": [ { "role": "user", "chars": 18, "preview": "评估申请 … 138****5678" } ],
    "toolNames": ["search_credit_applications", "…"],
    "responsePreview": { "content": "", "toolCalls": [ { "name": "run_credit_rules", "args": "{…}" } ] },
    "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 },
    "durationMs": 906, "startedAt": "…Z" }
]}
```

`requestPreview` 与 `responsePreview` 是 PII 掩码后的截断文本（每段 200 字，图片只记 `[图片]`）。不存完整请求；`requestSha256` 用于证明预览对应哪一次真实请求。调用失败时 `status = "error"`、`responsePreview = {}`。
收到响应但验收失败时，调用记录为 `status = "error"` 并保留响应预览、真实 usage 和错误码；`responsePreview.finishReason` 保留供应方结束原因（历史记录可能没有该字段）。

### GET /api/agent/runs/{runId}/audit

追加式审计事件（越权 403）：

```json
{ "events": [
  { "id": 1, "eventType": "run_started", "actorId": "demo_user", "answerVersion": null,
    "payload": {…}, "createdAt": "…Z" },
  { "id": 5, "eventType": "confirmation_created", "actorId": "reviewer_zhang",
    "answerVersion": 1, "payload": { "comment": "同意放款" }, "createdAt": "…Z" }
]}
```

### GET /api/health/live、GET /api/health/ready

- `live`：进程存活，恒 200。
- `ready`：配置校验（模型锁定）、数据库连通、Redis 连通（`checks.redis.ok`）、近期模型连通状态。任一项不通过即未就绪，返回 503 与原因。

## 登录与系统管理

### POST /api/auth/login

```json
{ "username": "admin", "password": "Admin@123" }
```

成功 200：`{ token, expiresInSeconds, user: { id, username, displayName, status, roleCode, roleName, permissions[] } }`。  
失败 401 `invalid_credentials`；停用 403 `user_disabled`。

### POST /api/auth/logout、GET /api/auth/me

需 `Authorization: Bearer <token>`。`me` 返回 `{ user }`；未登录 401。

### GET/POST /api/admin/roles、GET/POST /api/admin/users、PATCH /api/admin/users/{id}

需管理员（角色含 `admin` 权限）。用户创建字段：`username`、`displayName`、`password`、`roleCode`；更新可改 `displayName` / `roleCode` / `status` / `password`。

表：`sys_roles`、`sys_users`、`sys_sessions`（迁移 10）。密码 pbkdf2 哈希，会话只存 token 的 sha256。

演示种子（推荐 `admin`）：`admin/Admin@123`（全部权限含审批）、`account_manager/Demo@123`（客户经理，负责业务办理与确认，无系统管理；角色码 `account_manager`）、`viewer/View@123`（工作台+尽调1–5步共6项，无审批）。
权限码：`admin` / `workbench` / `dd_steps` / `catalog` / `applications` / `confirm` / `catalog_write`。Bearer 会话会校验；仅 `X-Actor-Id` 的评测调用不套 RBAC。

## 内部 ToolResult 契约（工具实现方遵守）

```text
ToolResult {
  isSuccess: bool,
  data: JSON,
  evidenceIds: string[],
  error?: { code: string, message: string, isRetryable: bool }
}
```

- 工具只读、参数化；`source_ref` 必须含表/主键或文档 ID；结果快照持久化为 evidence。
- 评测标签与预存结论（如 `is_fraud`、`decision`、`extracted_kpis`）不进入运行时数据库，只存于 `ocft-backend/eval/fixtures/`，供离线评分使用。
- 尽调舆情工具的 `events[]` 保留 `eventContent` / `eventSource`，分别来自 `enterprise_public_opinion.event_content` / `event_source`，外送及 API 输出沿用 PII 掩码；正文作为事实而不是指令。`已执行完毕` 按场景 `closed_statuses` 归为历史已结案件，仍保留原金额和历史司法风险计分，不计入 `openDefendantAmount`。

### POST /api/agent/dd/steps

尽调**单步核对**：按步骤直接调用与 Agent 相同的工具，只返回当前维度结果，供前端「财报解析 / 工商核验 / 舆情扫描 / 反欺诈检测 / 额度测算 / 尽调报告」页人工核对或导出结构化报告。身份沿用通用约定（Bearer 优先，`X-Actor-Id` 兼容）。不写 evidence 表、不创建 run、不读评测答案。

请求：

```json
{ "step": "business", "enterpriseId": "E001", "applicationId": "LA001" }
```

- `step`：必填；取值为 `business` | `finance` | `opinion` | `fraud` | `credit-risk` | `report`。缺失或取值非法由请求 Schema 返回 HTTP 422；请求体额外字段同样返回 422。
- `enterpriseId`、`applicationId`：Schema 均为可选 nullable 字段，但业务上至少提供一个；都省略或传空字符串时返回 400 `invalid_args`。仅传 `applicationId` 时由申请解析企业；仅传 `enterpriseId` 时服务端自动取该企业最近一笔贷款申请。
- 企业无贷款申请时，`credit-risk` 中 `rate_risk` 仍可成功、`calc_credit_limit` 为 `skipped/application_required`，整体通常为 `partial`；`report` 仅有的 `build_dd_report` 为 `skipped/application_required`，因没有成功工具，整体为 `error`。
- 前端按贷款申请选择并传 `applicationId`，企业由申请关联解析；跨步骤保留同一申请。企业编号入口仅为兼容调用。
- `report` 步工具为 `build_dd_report`（结构化五部分报告，数字来自同源计算）；单步页始终按所选贷款申请出贷款口径报告，企业口径（无额度）报告只在对话式尽调中生成。`sections.creditSuggestion.applyAmount` 为本次申请贷款额度（单位沿用 `unit`，通常万元），与建议额度分开；`steps` 保留申请额封顶步骤。
- 输出对 `data` 做 PII 掩码（与目录/证据外送一致）。

成功 200：

```json
{ "step": "business", "label": "工商核验", "status": "ok",
  "enterpriseId": "E001", "applicationId": null,
  "tools": [{ "toolName": "verify_business_info", "status": "ok",
    "errorCode": null, "message": null, "data": { "…" } }],
  "note": "单步核对：结果与 Agent 同工具同源…" }
```

`status`：全部工具成功为 `ok`；至少一个工具成功且另有失败/跳过为 `partial`；没有成功工具（全部失败或跳过）为 `error`。`step` 缺失或非法返回 422；企业 / 申请标识都未提供时返回 400 `invalid_args`；企业/申请不存在时对应工具 `status=error` 且 `errorCode=not_found`。

## POST /api/agent/data/imports

前端CSV增量新增接口，身份沿用通用约定（Bearer 优先，`X-Actor-Id` 兼容）。JSON请求：

```json
{"files":[{"fileName":"enterprise_basic.csv","content":"enterprise_id,...\n..."}]}
```

- 每次1—9个文件，UTF-8文本（允许BOM），文件名必须为9类现有业务CSV之一；可只传部分表。关系说明、问题和答案文件不接受。
- 仅新增：相同业务键且所有字段相同则跳过；同键不同内容拒绝，不覆盖、不删除。财务键为企业＋年度；案件/事件沿用现有唯一编号；股东键为企业＋股东名称＋类型，关联键为企业＋关联名称＋关系，担保键为企业＋被担保方＋方式＋期限。后三类候选键冲突不能表示新增合同，请确认数据语义后处理。
- 表头须与现有模型业务字段一致，可换顺序；整数、有限数字、日期、必填和企业关联在写入前校验。日期（`*_date` 字段）接受 `YYYY-MM-DD`、`YYYY/M/D`、`YYYY.M.D`（月日可不补零，分隔符须一致），入库统一规范为 `YYYY-MM-DD`；不存在的日期（如2月30日）拒绝。企业可来自现有库或同次基础表。
- 总文本字节数默认≤10MiB、总记录数≤20000，限制由settings读取。成功HTTP 200：`importId, status: imported, added, skipped, files: [{fileName, added, skipped}], errors: []`。
- 校验/内容冲突HTTP 422：`importId, status: rejected, added: 0, skipped, files, errors: [{fileName, row, field, errorCode, message}]`，整次不写业务事实。row是CSV记录序号（表头为1），最多返回前200条错误，不返回敏感原值。缺身份400；大小/行数超限413；并发唯一键冲突409，可重试。数据库失败500返回统一错误，不泄漏SQL。
- 每次已解析的成功/拒绝操作有独立追加式导入审计；成功的事实和审计同事务，失败回滚事实。明细候选键在当前单进程API内串行处理；多worker或其他进程同时写库不保证此类键并发去重。不是批次快照隔离，不更改既有CLI覆盖导入行为，不自动修改全局data_version。
- 前端 `api.importCsvFiles(actorId, files)` 使用 `File.text()`传输，HTTP 422的逐行报告保留给调用方；不调用模型。
