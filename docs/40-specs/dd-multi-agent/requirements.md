# 赛题 04 多 Agent 编排 需求

状态：已确认    负责人：Agent 核心

> **本轮变更优先于以下历史方案**：2026-10-24 用户授权最小整改：提问持久化及异步meta隐藏库内已知人名，最终答案/澄清保留自然人代号，仅企业名称可还原；证据API与导出对法人/实控人姓名掩码。发布前数值检查保留正负号，并对可识别科目及明确年度匹配；不变更业务阈值、额度或评级口径。旧版“还原全部名称”的验收仅对企业名称继续有效。

## 变更
- 2026-10-24：按代码回写：控制工具名为 `run_dd_agents`；免责声明改为发布前确定性补齐（不作校验失败条件）；模型自评 `needsReview` 不单独触发确认；六列导出含 `needs_confirmation`。同步：design 方案概述与终态、tasks 1/6/9/13、test-cases.md、INDEX。
- 2026-10-24：同步陈修活已确认的名称往返要求，并恢复远端更新后丢失的本地实现。同步 design 快照与代号化、tasks 14、enterprise-dd TC-1 至 TC-6、agent-api 契约、ADR-0008 决策 5。
- 2026-10-24：需求 6 由「场景级预算（180 秒 / 14 次调用 / 12 万 token）」改为「默认不限轮数与总时长，保留 token 上限与单次调用超时」。原因：比赛规则没有轮数和时限要求，用户确认取消。同步：ADR-0008 决策 4、design「运行限制」、tasks 7（全局取消部分已完成）。

## 背景
赛题 04 的提交材料要求写明多 Agent 的角色划分、协作协议和编排配置路径，自查第 15 条要求同一企业连续跑两次结论一致。现有实现是单个主控 Agent 调用全部工具，并且外部汇总评级（与公开答案一致）会送进模型，触及红线 R5。决策见 [ADR-0008](../../20-architecture/adr/0008-赛题04采用主控加六角色多Agent编排.md)。

## 用户故事与验收标准

1. 作为评审，我希望运行时读不到与公开答案一致的外部汇总评级。
   - 尽调工具的结果和证据快照 SHALL 不含 `risk_level_summary`、`externalRiskLevel`、`externalConsistent`、`externalUsedInScore` 等键；主控和角色提示词 SHALL 不提及外部汇总评级
   - WHEN `sql_query` 在任意位置显式引用 `risk_level_summary`（选择列、过滤、分组、关联） THEN 系统 SHALL 返回 `errorCode=not_allowed`，且不产生证据
   - WHEN `sql_query` 执行 `SELECT * FROM enterprise_risk` THEN 结果和证据 SHALL 不含该列，其余事实列照常返回
   - 业务目录接口 SHALL 不展示、也不按该列检索

2. 作为客户经理，我希望一次完整尽调由六个角色协作完成，并能看到每个角色的真实执行。
   - WHEN 对存在的申请发起完整尽调且 `parallel_analysis=true` THEN 系统 SHALL 先按依赖顺序完成 `business`、`finance`、`opinion`、`fraud`、`rating` 的确定性计算，再并行执行这五个角色的模型解读，最后执行 `report` 与事实校验；SSE SHALL 推送 `plan_ready`、各角色 `role_started` / `role_finished` 和 `verify_finished`
   - 五个并行解读角色的 `role_started` SHALL 都早于其中任何一个的 `role_finished`；`fraud` 与 `rating` 的解读只读取此前算好的上游结构化事实，不等待上游文字解读；WHEN `parallel_analysis=false` THEN 角色按依赖顺序逐级执行
   - 每个角色 SHALL 至少产出一条证据；开启模型分析的角色在 `llm_calls` 中各有一条 `purpose=role:<角色>` 的记录
   - 角色划分、依赖、并行开关、每角色 max_tokens 和提示词 SHALL 只来自 `scenarios/dd04/agents.yaml` 及其引用的提示词文件

3. 作为客户经理，我希望单项追问只跑必要的角色，且不会跳过依赖。
   - WHEN 主控计划只包含 `rating` THEN 系统 SHALL 自动补齐 `fraud`、`business`、`finance`、`opinion`，`plan_ready.plan.roles` 为补齐后的集合
   - WHEN 只问单一财务指标 THEN 系统 SHALL 只执行 `finance`，其余角色为 `skipped`，最终由主控成文
   - IF 申请或企业不存在，或名称命中多家 THEN 主控 SHALL 调用 `request_clarification`，终态为 `needs_clarification`，且不执行任何角色

4. 作为评审，我希望数字只来自工具计算，同一输入的结论稳定。
   - 角色模型的输出 SHALL 通过结构校验；连续两次校验不通过时，该角色 SHALL 记为 `degraded`：计算结果保留，`analysis` 为空；模型自评的 `needsReview` 只记入 `reviewSuggestedBy`，不单独决定终态
   - 发布前的事实校验 SHALL 检查：文本中带单位的数字都能在角色结果里找到（允许舍入误差）；风险档位等于评级角色结果；规则编号属于本次命中；证据引用属于本次 run
   - 「测算建议，非授信审批」SHALL 在发布前由代码确定性补齐（普通段落），不作为事实校验失败条件
   - IF 事实校验经 1 次重写后仍不通过 THEN 终态 SHALL 为 `failed`、`errorCode=narrative_check_failed`，结构化报告仍作为证据落库，但不作为答案发布
   - WHEN 同一申请连续两次完整尽调 THEN 两次的 `riskLevel`、建议额度、命中规则编号 SHALL 完全一致

5. 作为合规审查，我希望模型看不到企业全名、法人和信用代码。
   - 送入模型的角色输入和主控消息 SHALL 不含企业全名、法人、实控人、股东、关联企业名称、统一社会信用代码、法人证件号的原文；`enterpriseId` 和 `applicationId` 保留
   - 用户问题及会话记录 SHALL 隐藏库内已知自然人名称；最终回答及澄清问题 SHALL 在输出合规检查、保存和发布前只还原本次 run 登记的企业名称，自然人保持代号；信用代码、证件号及地址 SHALL 不还原，未知代号 SHALL 不映射到其他实体；导出沿用独立脱敏规则

6. 作为运维，我希望运行不被轮数或总时长截断，但失控时仍能停下。
   - 默认 SHALL 不限工具循环轮数、不限 run 总时长（`run_max_tool_rounds` / `run_timeout_seconds` 为 `None`）；WHEN 超过原 6 轮 THEN run SHALL 继续执行，不返回 `round_limit_exceeded`
   - 单次模型调用 SHALL 仍受 `llm_timeout_seconds` 约束；run 累计 token SHALL 仍受上限约束，超出时返回 `token_limit_exceeded`，尚未开始的角色记为 `degraded` 并停止调用模型
   - WHEN 通过环境变量配置了轮数或总时限 THEN 原有的 `round_limit_exceeded` / `run_timeout` 行为 SHALL 照常生效
   - 角色节点 SHALL 不访问数据库 Session；证据、轨迹、事件、模型调用审计由主线程统一写入，与 run 同一事务；并发写入事件时序号 SHALL 唯一且连续

## 不做什么
- 角色之间不做开放式对话，不在角色内补查数据库（ADR-0008 决策 3）。
- 不新增数据表，不改评分卡、额度模型的阈值与口径。
- 不做跨进程断点续跑；不引入新依赖。
- 记忆失效、会议资产、运行时 Skill 不在本 spec 范围内。
