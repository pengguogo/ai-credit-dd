# 赛题 04 多 Agent 编排 任务

状态：已确认

- [x] 0. 运行时移除外部汇总评级（工具、Agent 核心，关联需求 1）
  - 完成标准：`dd_calc.rate_risk` / `build_report`、`due_diligence._RISK_FIELDS`、目录接口、主控提示词都不含该列；`sql_query` 显式引用时拒绝，`SELECT *` 时剔除；`tests/test_dd_answer_isolation.py` 8 项通过，全量 pytest 327 通过
- [ ] 1. 契约更新并通知全员（Agent 核心，关联需求 2、3、4、6）
  - 完成标准：`contracts/agent-api.md` 写明新增事件、`contextSnapshot` 新字段、`narrative_check_failed`
  - 结果：已写入事件表与「尽调多 Agent」一节；`contextSnapshot.plan / roles / tokens / configVersions` 尚未落地，角色信息目前在 SSE 事件、`llm_calls.purpose` 和 `run_dd_agents` 的工具摘要里。群通知待发
- [x] 2. 快照与代号化 `dd_snapshot.py`（Agent 核心，关联需求 1、5）
  - 完成标准：单测验证快照不含答案列；代号化后的文本里没有企业全名、法人、实控人、股东、关联企业名称、信用代码原文；编号保留
- [ ] 3. `agents.yaml`、提示词文件，以及 `RoleResult` 角色模板 `dd_roles.py`（Agent 核心，关联需求 2、4）
  - 完成标准：单测覆盖 `llm=false` 时只计算；`llm=true` 时校验失败重试 1 次后记为 `degraded`；计算抛 `ToolError` 时记为 `failed`
  - 结果：已覆盖降级与截断重试（上限翻倍）；`llm=false` 与计算失败两条路径尚无专门单测
- [x] 4. `dd_graph.py`：计算依赖、并行解读、汇合、跳过和计划闭包（Agent 核心，关联需求 2、3、6）
  - 完成标准：`parallel_analysis=true` 时，用假模型验证五个解读角色的 `role_started` 都早于其中任一 `role_finished`；确定性计算仍按依赖顺序完成；`roles=[rating]` 能补齐依赖；被跳过角色为 `skipped`；角色节点不访问 Session
  - 偏差：没有改 `engine.run` 分派。主控沿用场景工具循环，六角色子图由控制工具 `run_dd_agents` 调度；完整尽调报告经场景「终止工具」机制直接作为答案。
- [x] 5. 主控与调度（Agent 核心，关联需求 3）
  - 完成标准：假模型跑通完整尽调、单项追问、澄清、职责外四条路径，终态符合需求
  - 偏差：控制工具名为 `run_dd_agents`（设计稿为 `plan_due_diligence`），主控提示词在 `scenarios/dd04/prompts/controller.md`
- [x] 6. 事实校验器 `dd_verify.py` 与重写流程（Agent 核心，关联需求 4）
  - 完成标准：篡改数字、档位、规则编号、证据 ID 都能被拦截；重写一次后仍失败时返回 `narrative_check_failed`，且结构化报告仍有证据
  - 结果：免责声明改为确定性补齐（固定条款），不作为拦截项
- [x] 7a. 全局取消 6 轮 / 60 秒（Agent 核心，关联需求 6）
  - 完成标准：`run_max_tool_rounds` / `run_timeout_seconds` 默认为 `None`；超过 6 轮的工具调用能正常收尾；配置了数值时原行为照常；全量 pytest 328 通过
- [x] 7b. 多 Agent 的 token 预占、`llm.py` 参数化、并发事件串行化（Agent 核心，关联需求 6）
  - 完成标准：token 耗尽时尚未开始的角色记为 `degraded`；并发 emit 的序号唯一且连续
  - 偏差：没有改 `app/observability/events.py`，改为在 `dd_graph` 内用锁串行写入记录器（只有这里并发 emit）。场景级 token 上限在 `agents.yaml` 的 `controller.max_total_tokens`（默认 200000）
- [ ] 8. 前端角色泳道与新事件类型（前端，关联需求 2）
  - 完成标准：`npm run lint`、`npm run build` 通过；真实运行时能看到五个分析角色并行解读、最后报告汇总，以及 `degraded` / `skipped` 的诚实展示
  - 结果：第一版由王小文（Agent 开发）先做，`components/run/role-lanes.tsx` + 轨迹新增计划 / 事实校验行；lint、build 通过。浏览器内的真实运行效果待人工确认，交程柳后续优化
- [x] 9a. 评测从结构化证据导出六列（评测，关联需求 4 / enterprise-dd 需求 5）
  - 完成标准：`python -m eval.dd04 export` 对 10 笔申请写出六列 + status CSV；含 `needs_confirmation` 且结论齐全的行
- [ ] 9b. 双跑一致性检查（评测，关联需求 4）
  - 完成标准：同一申请两次完整尽调，`riskLevel` / 建议额度 / 命中规则编号 diff 为 0（专用脚本或单测尚未落地）
- [x] 10. 设计用例 `test-cases.md`（场景与文档，关联需求 1–6）
  - 完成标准：每条验收标准至少对应一条用例（确认前保持草稿）
- [ ] 11. 验证（关联需求 1–6）
  - 完成标准：`cd ocft-backend && python -m pytest tests -q` 通过；红线扫描 0 ERROR；`cd ocft-starter && npm run lint` 通过；真实模型跑 10 笔完整尽调并记录 P50 / P90 与 token
  - 进展：假模型单测与公开集真实复测已多轮归档；任务关闭前再跑一轮全量 pytest + 红线并登记数字
- [ ] 12. 文档：README 写入配置路径，登记开发日志和 INDEX（场景与文档，关联需求 2）
- [x] 13. 确认规则收窄（Agent 核心，关联需求 4）
  - 完成标准：`needsManualReview` 只由角色降级 / 失败、评分卡复核、额度 `creditError`、高风险等决定；模型自评 `needsReview` 记在 `reviewSuggestedBy`，不影响终态
- [x] 14. 合并兼容名称往返链路（Agent 核心、合规与可观测，关联需求 5）
  - 完成标准：服务层与引擎接口一致；主控、角色与工具共用同一 Masker；回复与澄清在输出合规前仅还原企业名称，自然人保持代号；未知代号不串实体。设计用例追溯 enterprise-dd TC-1 至 TC-6。

- [x] 15. 合规与事实校验修复（关联需求 4、5）：2026-10-24 用户授权最小整改：提问持久化及异步 meta 隐藏库内已知人名，最终答案/澄清保留自然人代号，仅企业名称可还原；证据 API 与导出对法人/实控人姓名掩码。发布前数值检查保留正负号，并对可识别科目及明确年度匹配；不变更业务阈值、额度或评级口径。

  - 本轮验证：后端463 passed（15项依赖弃用警告）；lint/build通过；扫描0 ERROR/3条注释误报。真实公开样例1条成功，余下公开集及Windows验收未重做。
