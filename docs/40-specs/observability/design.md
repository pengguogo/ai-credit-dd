# 可观测性 设计

状态：已确认    对应需求：已实现

## 方案概述
- `app/observability/request_id.py`：纯 ASGI 中间件（不缓冲流式响应），读取或生成 `X-Request-Id`，写入 ContextVar，记录访问日志。外部传入值只接受 `[A-Za-z0-9._-]{1,64}`，防日志注入。
- `app/observability/logging.py`：JSON formatter，只挂在 `ocft` 命名空间。
- `app/observability/events.py`：`EventBus`（每个 run 一个通道，Condition 通知，结束后保留 5 分钟）与 `RunEventRecorder`（分配序号、推送总线、留存待落库）。
- 引擎新增 `emit` 回调，产出 `llm_call_finished` / `tool_started` / `tool_finished`；服务层产出 `run_started` / `compliance_checked` / `compliance_blocked` / `run_finished`。
- 事件在 run 结束时写入新表 `run_events`，与 run / trace / audit 同一事务。
- 异步模式：请求线程校验场景与会话归属，预分配 runId / conversationId，后台线程（复制 ContextVar，独立会话）调用同一个 `create_run`。先提交事务再关闭通道，保证读者切到数据库时已能读到。

## 涉及模块与负责人
合规与可观测（`app/observability/`）；Agent 核心（engine 埋点、run_service、router）。

## 接口 / 契约变更
[contracts/agent-api.md](../../../contracts/agent-api.md)：`mode`、202、`X-Request-Id`、`timings`、SSE 事件表与续传。POST 响应补上 `evidenceIds`（原来恒为空）。移除废弃的 `ocft-backend/contracts/`。

## 数据变更
新增表 `run_events`（`create_all` 会自动创建，已有库无需迁移）。旧 run 没有事件行时，SSE 仍按 trace + audit 重建。

## 红线影响
- 日志不记录问题、答案、工具数据；异步模式的 running 视图返回掩码后的问题。
- 不改变答题链路：sync / async / 评测共用 `create_run`。

## 取舍
- 内存总线而非数据库轮询：实时性好、零依赖；代价是多进程时执行中的推送不跨进程，结束后不受影响。比赛单进程部署，够用。
- 事件结束时一次落库，而非逐条提交：保持"同一事务"约定，执行中的数据只在内存里。
