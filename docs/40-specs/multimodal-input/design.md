# 多模态输入 设计

状态：已确认    对应需求：已实现

## 方案概述
附件采用入口拒绝，而非视觉透传：

1. `AgentRunCreateIn` 保留可选 `attachments` 字段，用于兼容既有调用方并完成结构校验。
2. `run_service.create_run` 与 `start_run_async` 在分配 run/conversation、打开事件通道、落库或调用引擎前执行 `_validate_attachments`；空附件返回空列表，任何非空附件抛出 422 `invalid_attachment`。
3. `engine.run` 保留非空附件失败的纵深保护，防止绕过 service 后调用模型。
4. 前端不提供图片选择、粘贴、预览或提交能力。

## 涉及模块与负责人
- Agent 核心：`app/schemas.py`、`app/routers/agent.py`、`app/services/run_service.py`、`app/agent/engine.py`
- 前端：工作台输入组件
- 契约：沿用 `contracts/agent-api.md` 的 `attachments` 字段和拒绝响应

## 接口 / 契约变更
请求可以省略 `attachments` 或传空数组。任何非空附件同步返回 422；通过 schema 校验的非空附件返回 `errorCode=invalid_attachment`，且没有 runId。

## 数据变更
无。拒绝发生在 run、会话、消息、事件和审计写入之前，不保存附件计数、URL 或像素。

## 红线影响
- R1：无模型调用，不新增模型入口。
- R2：拒绝逻辑由仓库代码实现。
- R3～R6：不产生业务结论、证据、评测标签读取或确认记录。
- R7：附件不外送、不落库；错误结构化返回。
- R8：无新依赖。
- R9：无凭据变化。

## 取舍
选择同步拒绝以封闭原图外送风险；放弃图片原样直传、视觉 content block 和历史图片回放。只有本地图像脱敏方案完成并重新确认 Spec 后才重访。
