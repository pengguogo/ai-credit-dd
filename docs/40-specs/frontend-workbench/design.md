# 前端工作台 设计

状态：已确认    对应需求：已确认

## 方案概述
- 技术栈按 [ADR-0001](../../20-architecture/adr/0001-后端语言与前端框架.md)：React 19 + TypeScript + Vite + Tailwind + shadcn/ui（`base-nova`）+ Motion + ECharts。
- 鉴权：`useAuth` + Bearer；未登录渲染 `LoginPage`；导航与路由按权限码裁切（见 auth-admin）。
- 数据流：`useAgentSession` 以 `mode: "async"` 发起 run → `streamRunEvents`（Bearer；`Last-Event-ID` 重连）→ `run_finished` 后取详情、证据、审计 → 确认后刷新审计。
- 布局：工作台左对话 / 右执行详情（轨迹含多 Agent 协作 `role-lanes`、证据、审计与确认）；数据列表与尽调五步（`/report/*` + `POST /dd/steps`）为独立路由；系统管理为 Admin 页。
- 模型答案为 Markdown（自写渲染器，支持 `###` 与表格样式）；回答可按原文导出 PDF/Word（`lib/answer-export.ts`）。

## 涉及模块与负责人
前端（`ocft-starter/`）；Agent 核心（证据、统计、SSE、尽调步骤接口）；鉴权见 auth-admin。

## 接口 / 契约变更
[contracts/agent-api.md](../../../contracts/agent-api.md)：证据与统计、多 Agent 事件、auth/admin、`/dd/steps`。messages 中 user 消息带 `runId`。

## 数据变更
无。前端不直连库。

## 红线影响
- 红线 3：`src/data/` 仅场景说明与提问模板，无标注答案字段。
- 红线 5：结论旁显示证据数；证据不足时明确未给出结论。
- 合规：被拦截提问不进入模型历史。

## 取舍
- 轨迹用内置 Trace + 角色泳道映射 SSE，不用 AI SDK 消息结构。
- 统计仍为全局口径（含评测批量）；未按身份过滤。
- 导出不新增后端接口，浏览器端生成文件。
