# 引擎补强（状态机 / 超时 / 上下文）需求

状态：已实现    负责模块：Agent 核心

## 背景
对应待办 1-1、1-4、1-2，影响"Agent 工程架构完善度"客观分与红线 5（结论必须有证据）。引擎原来只产出 `succeeded` / `failed`，查不到数据也显示成功；60 秒时限只在轮次之间检查；多轮对话丢失上一轮查到的数据。

## 用户故事与验收标准
1. 作为业务人员，我希望系统在查不到数据、信息不足、结论高风险时给出不同的终态，以便知道下一步该补充信息还是去确认。
   - WHEN 调用过数据工具但无任何证据 THEN 终态 SHALL 为 `insufficient_evidence`，`errorMessage` 为说明文本
   - WHEN 答案含结论（场景 `conclusion_pattern`）而本次无证据 THEN 终态 SHALL 为 `insufficient_evidence`
   - WHEN 模型调用 `request_clarification` THEN 终态 SHALL 为 `needs_clarification`，不再调用模型
   - WHEN 工具结果命中场景 `confirmation_rules` THEN 终态 SHALL 为 `needs_confirmation`，`answerVersion = 1`
   - 样例 pub-008（不存在的申请）落在 `insufficient_evidence` 或 `needs_clarification`
2. 作为运维，我希望一次 run 不会超过时限。
   - 每次模型调用超时 SHALL 为 `min(llm_timeout, 剩余时限)`；剩余不足 `run_min_llm_budget_seconds` 时直接以 `run_timeout` 结束
   - IF 超时由剩余时限截断 THEN errorCode SHALL 为 `run_timeout`
3. 作为用户，我希望追问"她能通过吗"时 Agent 记得上一轮查到的申请。
   - 历史 SHALL 带上前序 run 的工具结果摘要与会话实体槽位
   - 超出 token 预算 SHALL 把最旧消息压缩为摘要，并注明消息 ID 范围
   - `GET /runs/{runId}` SHALL 返回 `contextSnapshot`
   - 样例 pub-009 第二轮不重复检索即可作答

## 不做什么
- 不用模型做历史摘要（抽取式压缩，零额外 token）
- 不做实时 SSE（属于 1-3）
- 不引入精确 tokenizer，token 估算按字符数近似
