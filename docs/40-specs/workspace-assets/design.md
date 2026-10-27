# 报告列表（资产档案） 设计

关联需求：[requirements.md](requirements.md)　契约：[contracts/agent-api.md](../../../contracts/agent-api.md)　测试：[test-cases.md](test-cases.md)

## 方案
- 完成 run 后在 `run_service._apply_outcome` 同事务调用 `workspace_service.register_asset`；正文不含五部分标题时不建档。失败只告警，不影响已完成的 run。
- 档案表 `workspace_assets` 用 `run_id` 唯一约束保证幂等。
- **报告没有状态**：不写状态事件，不提供状态变更接口；建档同一事务内把该贷款申请从 `pending`（待处理）推进到 `pending_review`（待审核），已审核的申请不覆盖。
- 档案不复制正文：`summary` 仅摘「尽调结论」一句，`content_sha256` 供核对；报告与证据继续走 `/runs/{id}` 与 `/runs/{id}/evidence`。

## 数据
| 表 | 关键字段 | 说明 |
|----|----------|------|
| `workspace_assets` | `id`、`run_id`（唯一）、`application_id`、`enterprise_id`、`kind`、`title`、`summary`、`evidence_count`、`content_sha256`、`created_by`、`created_at` | 迁移 12 新建，只增不删 |
| `workspace_assets` 历史列 | `status`、`version`、`archived_at` | 早期报告复核流转用；保留列兼容既有库与历史行，不再写入语义、不再对外返回 |
| `workspace_asset_events` | `asset_id`、`event_type`、`from_status`、`to_status`、`actor_id`、`comment`、`created_at` | 历史表，报告无状态后不再写入 |

贷款申请状态（`loan_application.status`，迁移 11 / 13 / 14）：`pending`（待处理）→ `pending_review`（待审核）→ `approved`（审核通过）/ `rejected`（审核不通过）。报告生成触发第一步，人工审核触发第二步。

## 接口
见契约「报告列表」：`GET /api/agent/assets`、`GET /api/agent/assets/{assetId}`。原 `POST /api/agent/assets/{assetId}/status` 已移除；审核结论改用 `PATCH /api/agent/catalog/enterprise_dd/applications/records/{id}`（`status`，需 `confirm` 权限）。

2026-10-25 已确认变更：列表和详情读取时按企业编号左连接企业事实表，补齐企业名称；没有企业资料的档案仍返回。名称关键词参与同一数据库过滤，分页与计数保持一致；列表与详情使用同一投影。无模型调用、无新依赖，迁移 14 只改数据取值。

## 前端
`/workspace`「报告列表」页：关键词检索、报告表（报告 / 企业 · 贷款申请 / 证据 / 生成时间）、详情（摘要、企业名称、申请编号、生成人、生成时间、证据数、报告入口）。**没有状态筛选、状态徽标、复核意见、确认/驳回/归档按钮和状态流转时间线。** 列表与详情各自滚动：左侧检索与表头固定，右侧详情独立滚动。数据只来自后端 API，错误与空状态如实展示。

标题显示「企业名称 · 信贷尽调报告」，名称缺失显示通用报告标题，企业列提示「企业名称未登记」。编号仅显示带中文标签的申请编号；内部运行标识只用于报告链接。

## 红线逐条
- R1 模型：本功能不调用模型。
- R3/R4/R5：不写死答案、不读 `expected`、不按题号建档；建档只看 run 正文结构与工具结果。
- R6 证据：档案只关联 `runId` 与证据条数，证据仍在 `evidence` 表。

## 取舍
- 未做会议纪要/分派：赛题 6.1 的「会议与资产管理」按任务 + 产出物 + 检索闭环落地，避免引入与信贷尽调无关的日历模块。
- 报告不设状态：用户判定报告只是产出物，确认 / 驳回 / 归档会增加认知负担且与贷款申请审核重复；审核结论集中在贷款申请四态。
- 不删历史列：迁移约定只增不删，`status` / `version` / `archived_at` 与事件表保留以兼容既有库与历史行，界面与接口不再暴露。
- 未复制正文：避免同一结论出现两个版本；详情页「查看报告」跳报告预览。
