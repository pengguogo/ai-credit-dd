# 前端工作台 任务

状态：已确认

- [x] 1. TypeScript + shadcn/ui 初始化，依赖固定版本并登记（需求 1）
- [x] 2. API 类型与客户端、SSE 读流与重连（需求 1）
- [x] 3. 对话面板与各状态展示（需求 2）
- [x] 4. 执行详情：轨迹（Trace + Motion）、证据、审计与确认（需求 1）
- [x] 5. 运行看板：后端 `/stats` + ECharts 懒加载（需求 3）
- [x] 6. 后端：证据接口、统计接口、被拦截提问不进模型历史；契约更新
- [x] 7. 删除带标注字段的静态样例与旧组件
- [x] 8. 登录门控与 RBAC 导航（需求 4；交叉 auth-admin）
  - 完成标准：未登录进登录页；菜单与路由按权限裁切；Bearer 调用 Agent
- [x] 9. 多 Agent 协作视图（需求 1；交叉 dd-multi-agent 任务 8）
  - 完成标准：`role-lanes` 展示计划 / 并行卡片 / 校验；状态只来自事件
- [x] 10. 尽调五步页与回答导出（需求 4；交叉 enterprise-dd）
  - 完成标准：`/report/*` 可调 `/dd/steps`；对话区可导出 PDF / Word
- [ ] 11. 验证（关联需求 1–4）
  - 完成标准：`cd ocft-starter && npm run lint` 通过；`npm run build` 通过；手工走通登录 → 提问 → 轨迹/泳道 → 证据 → 确认 → 导出
