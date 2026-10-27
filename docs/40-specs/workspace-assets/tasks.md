# 报告列表（资产档案） 任务

2026-10-25 新增任务 7–9：已确认；按下列顺序在本次会话执行。

- [x] 1. 数据与迁移（数据层与工具，需求 1）
  - 完成标准：迁移 12 建 `workspace_assets` / `workspace_asset_events`；全量迁移测试与既有库幂等通过。
- [x] 2. 服务与自动建档（Agent 核心，需求 1、2）
  - 完成标准：完成后 run 同事务建档一次；非完整报告不建档；状态机与版本冲突明确报错。
- [x] 3. API 与契约（Agent 核心，需求 2）
  - 完成标准：列表 / 详情 / 状态三个端点可用；`confirm` 权限与 `X-Actor-Id` 口径正确；契约已更新。
- [x] 4. 前端「报告列表」页（前端，需求 3）
  - 完成标准：`/workspace` 可检索、筛选、确认/驳回/归档/重开并即时刷新；lint、typecheck、build 通过。
- [x] 5. 测试（测试维护，需求 1–3）
  - 完成标准：服务与 API 用例覆盖建档幂等、检索、状态流转、非法流转、版本冲突、追问不建档；全量 pytest 通过。
- [x] 6. 验证与留痕（评测 / 交付，需求 3）
  - 完成标准：真实 run 自动建档；HTTP 走通确认与归档；页面截图留证；开发日志登记。
- [x] 7. 企业名称投影与检索（Agent 核心，需求 4，TC-WA-08、09）
  - 文件：`contracts/agent-api.md`、`ocft-backend/app/schemas.py`、`ocft-backend/app/services/workspace_service.py`、`ocft-backend/tests/test_workspace_assets.py`。
  - 先补并运行失败用例，再实现企业事实表左连接与名称检索，列表、详情、状态响应新增 `enterpriseName: string | null`；名称缺失仍保留档案；历史标题和事件不回写。新建档系统备注使用中文。
  - 完成标准：`.venv/Scripts/python.exe -m pytest tests/test_workspace_assets.py -q` 通过，覆盖企业名称、检索、分页、缺失资料与历史事件保留。
  - 实际验证：`tests/test_workspace_assets.py` 7 passed；全量后端 `549 passed, 1 skipped`。
- [x] 8. 中文业务界面（前端，需求 4，TC-WA-10）
  - 文件：`ocft-starter/src/lib/types.ts`、`ocft-starter/src/components/workspace/workspace-page.tsx`。
  - 按已确认文案改列表与详情；名称用 API 字段、标题用名称生成；删除运行编号行；申请编号加中文标签；时间线翻译状态和旧系统备注。保留原始 `runId` 报告链接。
  - 完成标准：`npm run lint`、`npm run build` 通过；浏览器确认中文名称、名称检索、时间线与报告链接，无技术标识出现在正文。
  - 实际验证：`npm run lint` 和 `npm run build` 通过；浏览器确认名称、申请编号标签和中文时间线，截图见 `output/playwright/workspace-chinese.png`；原报告链接保留 `runId` 查询参数但不显示。
- [x] 9. 验证与离线交付同步（评测 / 交付，需求 4）
  - 文件：`ocft-starter/dist/`、`docs/10-strategy/开发流程.md`、`docs/10-strategy/开发日志.md`、`docs/INDEX.md`。
  - 完成标准：相关 pytest、前端 lint/build、红线扫描通过；运行 `pack-offline.ps1` 同步离线产物；前后端启动并核验页面，截图留证；如实记录测试和启动结果，不重跑与本改动无关的模型业务评测。
  - 实际验证：红线扫描 `0 ERROR / 3 WARN`（均为既有 `seed.py` 说明注释）；`pack-offline.ps1 -PythonVersions @()` 构建 dist 成功并保持内置 Python 哈希不变；`/api/health/ready` 200，前端 :5173 和后端 :8000 已运行。
- [x] 10. 报告去状态 + 贷款申请四态（Agent 核心 / 数据层，需求 1、2、5）
  - 文件：`ocft-backend/app/migrations.py`（迁移 14）、`models.py`、`services/workspace_service.py`、`schemas.py`、`routers/agent.py`、`services/catalog.py`、`services/catalog_write.py`、`services/csv_import_service.py`、`dd_import.py`、`tests/`。
  - 完成标准：报告列表 / 详情不再返回状态、版本、事件与状态计数；状态接口移除；贷款申请四态，报告生成后待处理 → 待审核且不覆盖已审核结论；迁移可重复执行。
  - 实际验证：全量后端 `553 passed / 1 skipped`；共享库迁移 14 后 `pending_review 10 / pending 4 / approved 1`，`approvalStatus=pending_review` 与关键词 `待审核` 均命中 10；真实 run（LA101）`succeeded`，申请由待处理变待审核并自动建档。
- [x] 11. 前端与报告正文（前端，需求 2、3）
  - 文件：`ocft-starter/src/components/workspace/workspace-page.tsx`、`components/catalog/data-catalog.tsx`、`components/catalog/data-list-page.tsx`、`lib/catalog-tables.ts`、`lib/types.ts`、`lib/api.ts`、`components/report/preview/report-document.tsx`、`report-preview-page.tsx`、`App.tsx`。
  - 完成标准：报告列表无状态筛选、徽标、复核意见、确认/驳回/归档与状态时间线；申请筛选为全部 + 四态，仅待审核可审核；报告正文无「审计与确认状态」。
  - 实际验证：`npm run lint` 0 error（3 条既有 `dimension-page.tsx` warning）；`npm run build` 通过并重建 `dist/`；浏览器在 :5173 与 :8000 确认筛选计数 `全部 15 / 待处理 4 / 待审核 10 / 审核通过 1 / 审核不通过 0`、待审核行有通过/不通过、报告列表与详情无状态、报告正文无审计与确认状态；截图 `output/playwright/loan-status-four-states.png`、`loan-status-review-actions.png`、`report-list-no-status.png`。
