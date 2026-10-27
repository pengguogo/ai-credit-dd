# 可观测性 需求

状态：已实现    负责模块：合规与可观测（事件埋点涉及 Agent 核心）

## 背景
对应待办 1-3、3-4。原来没有 `app/observability/`；SSE 在执行结束后才重放，前端看不到过程；看不到每个节点的耗时；`tool_finished` 缺 `evidenceIds`。

## 用户故事与验收标准
1. 作为演示用户，我希望边执行边看到步骤。
   - WHEN `POST /runs` 带 `mode: "async"` THEN 系统 SHALL 立即返回 202 与 runId，执行中经 SSE 实时推送事件
   - SSE 事件 SHALL 带 `id`，支持 `Last-Event-ID` / `?after=` 续传；空闲时发心跳
   - 结束后重放的事件 SHALL 与实时推送一致（同序号、同内容）
2. 作为排障人员，我希望任一 run 都能查到每个节点的耗时。
   - `GET /runs/{runId}` SHALL 返回 `timings`：输入/输出合规、每轮模型调用、每次工具调用、整个 run
3. 作为排障人员，我希望能把日志、run、审计串起来。
   - 所有响应 SHALL 带 `X-Request-Id`；该值写入 `contextSnapshot.requestId` 与 `run_started` 审计
   - 日志 SHALL 为 JSON，只含标识、状态、耗时、计数，不含问题、答案、工具数据

## 不做什么
- 不引入消息中间件、OpenTelemetry 等依赖；多进程部署下执行中的实时推送只在本进程可见
- 不做指标聚合与告警
