# 可观测性 任务

状态：已确认

- [x] 1. 请求 ID 中间件 + JSON 日志（需求 3）
- [x] 2. 事件总线与记录器；引擎与服务层埋点（需求 1、2）
- [x] 3. `run_events` 表；SSE 实时推送、续传、心跳；旧 run 兼容重放（需求 1）
- [x] 4. `POST /runs` 异步模式（202）；执行中详情返回 running（需求 1）
- [x] 5. 详情 `timings`（需求 2）
- [x] 6. 契约更新；移除 `ocft-backend/contracts/`；POST 响应补 `evidenceIds`
- [x] 7. 验证：历史记录为 pytest 158 项通过；uvicorn + 真实模型实测中事件在 1.0s / 3.9s / 4.9s / 6.9s 逐步到达
