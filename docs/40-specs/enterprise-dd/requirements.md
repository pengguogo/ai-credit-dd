# 企业信贷尽调 需求

状态：已确认    负责模块：Agent 核心、数据层、工具、评测、前端、合规与可观测

> **本轮变更优先于以下历史方案**：2026-10-24 用户授权最小整改：提问持久化及异步meta隐藏库内已知人名，最终答案/澄清保留自然人代号，仅企业名称可还原；证据API与导出对法人/实控人姓名掩码。发布前数值检查保留正负号，并对可识别科目及明确年度匹配；不变更业务阈值、额度或评级口径。旧版“还原全部名称”的验收仅对企业名称继续有效。

## 变更
- 2026-10-24：按已落地代码回写验收口径（多 Agent、点数制评分卡、额度 creditError、六列含 needs_confirmation、对话区 PDF/Word、导出脱敏范围）。同步：design 全文、tasks 1–9、TC-7 起、INDEX。
- 2026-10-24：`riskLevel` 改由点数制评分卡（`scenarios/dd04/scorecard.yaml`，10 项指标、合计点数分档）产出；反欺诈命中不再一票否决，改由额度模型的重大财务异常折减承接（`credit_model.yaml` incremental-v2）。档位名称保留「低-中风险」。同步：`contracts/dd04-credit-amount.md`。
- 2026-10-24：需求 3 第 1 条「`externalRiskLevel` 不得进入加权；与本系统评级不一致时 `needsManualReview=true`」被 [ADR-0008](../../20-architecture/adr/0008-赛题04采用主控加六角色多Agent编排.md) 决策 1 取代：运行时不读、不输出外部汇总评级，`needsManualReview` 只由本系统事实缺口触发。同步：[dd-multi-agent](../dd-multi-agent/requirements.md) 需求 1、tasks 0。
- 2026-10-24：需求 2 的界面导出由 markdown 改为 PDF。同步：design 方案概述与取舍、tasks 5、tasks 9。
- 2026-10-24：去掉右侧独立报告 Tab；成功回复后按 Agent 原文导出 PDF / Word。同步：design、tasks 5、tasks 9。
- 2026-10-24：扩展需求 6 的名称脱敏范围：用户问题、用户消息和会话标题保存经 PII 掩码与场景名称处理后的可读文本；库内已知自然人保存为代号，企业名称保留；发送给模型的当前问题、历史、工具结果和工具参数继续使用本次 run 代号。同步：design 方案概述与红线影响、tasks 3、test-cases TC-1 至 TC-6。

## 背景
赛题 04 要在一笔贷款申请上跑完财报、工商、舆情、反欺诈、额度与报告，并支持追问。评审核对风险评级、建议额度、结论是否来自事实，且现场可以重算。运行时不得读取公开测试集答案和 `reference_answer`（R4、R5）。完整尽调编排见 [dd-multi-agent](../dd-multi-agent/requirements.md)。

## 用户故事与验收标准
1. 作为客户经理，我希望对一笔申请跑完尽调。
   - WHEN 给出存在的 `applicationId` 并发起完整尽调 THEN 系统 SHALL 经主控调用 `run_dd_agents`：先按依赖顺序完成工商、财报、舆情、反欺诈、评级授信的确定性计算；当前 `parallel_analysis=true` 时再并行执行这五个角色的模型解读，最后由报告角色汇总并进入事实校验；`riskLevel` 与建议额度只取 `dd_calc`（证据 `source_ref.calc` 为 `rate_risk` / `calc_credit_limit` 等）；该次 run 至少有一条 `source_type=calculation` 的 evidence
   - IF `applicationId` 或 `enterpriseId` 不存在 THEN 系统 SHALL 返回 `errorCode=not_found`（或澄清终态），且响应中没有可用的 `riskLevel` 与正数建议额度
2. 作为客户经理，我希望看到可核对的报告。
   - WHEN 报告角色成功 THEN 对外正文 SHALL 按 dd-report Skill 骨架展示（决策摘要 + 企业概况 / 财务分析 / 风险提示 / 额度建议 / 风控条件）；结构化 `build_report.sections` 含上述五节；概况含企业编号、行业、经营状态、成立日期（注册资本 / 实缴资本以工商核验结果与报告正文为准，不强制写入 `sections.overview`）
   - 对话区 SHALL 展示 Agent 回复原文。WHEN 回复成功且有正文 THEN 提供「导出 PDF」「导出 Word」；下载内容与回复原文一致；导出对统一社会信用代码、证件号及文中「实控人 / 第一大股东」句式脱敏（不另做通用法人姓名替换）
3. 作为评审，我希望结论可解释，且不抄外部汇总评级。
   - `riskLevel` SHALL 只来自 `scenarios/dd04/scorecard.yaml` 的档位名；运行时工具结果、证据与目录 SHALL 不含 `risk_level_summary` / `externalRiskLevel` 等外部汇总评级键（细则见 dd-multi-agent 需求 1）
   - `needsManualReview` SHALL 只由本系统事实缺口触发（无财务行、额度无法测算、角色降级 / 失败、评分卡要求复核等），不得因「与外部汇总评级不一致」置位
   - 反欺诈命中 SHALL 带规则编号、命中值和阈值；对外六列中的 `scoring_points` SHALL 可追溯本次 run 的计算证据（当前结构化字段可为固定六环节名列表，不以题号写死结论）
   - 对外档位是否只能是「低风险 / 中风险 / 高风险」：待确认。当前配置另有「低-中风险」，确认前不改档位名称
4. 作为客户经理，我希望用自然语言追问，也希望名称含糊时不要猜。
   - WHEN `find_enterprise` 的名称命中多家 THEN 系统 SHALL 返回 `matchStatus=ambiguous`，且该结果不含 `riskLevel` 与建议额度
   - 单项追问允许只调度相关角色。引擎不按题号写死角色序列
5. 作为评测人员，我希望导出官方六列结果。
   - WHEN 对一份贷款申请表执行 `python -m eval.dd04 export` THEN 系统 SHALL 写出 `utf-8-sig` 的六列 CSV（`application_id, enterprise_id, risk_level, suggested_credit_amount, due_diligence_conclusion, scoring_points`），并另写 `<stem>-status.csv`；`succeeded` 与 `needs_confirmation` 且结论齐全的行均导出结论；申请编号与输入一一对应
   - 导出过程 SHALL 不打开 `公开测试集答案.csv`，也不读取 `reference_answer`
6. 作为合规审查，我希望敏感字段不进模型。
   - WHEN 用户问题含企业全名、法人、实控人、股东、关联企业名称 THEN 系统 SHALL 在消息及会话记录中隐藏库内已知人名、保留企业名称，但发送给模型的当前问题和历史消息中的上述名称 SHALL 替换为本次 run 的代号；其他个人信息继续执行现有持久化掩码
   - 送入模型的当前问题、历史消息、工具结果、工具参数及 `llm_calls` 请求预览 SHALL 不含企业全名、法人、实控人、股东、关联企业名称的原文；模型生成的工具参数 SHALL 在本地执行前还原代号；企业编号和申请编号保留
   - WHEN 模型回复含本次 run 的代号 THEN 系统 SHALL 在输出合规检查、保存和发布前仅还原对应企业名称，自然人保持代号；未登记的代号 SHALL 不得映射到其他实体
   - 送入模型的统一社会信用代码、法人证件号 SHALL 使用不可逆号码掩码，不在输出侧还原
   - IF 模型调用失败 THEN 系统 SHALL 返回结构化 `errorCode`，且不填写风险评级或额度
7. 作为评审，我希望缺财务时不编造额度。
   - WHEN 企业在申请时点前没有任何可用完整年度财务行 THEN `calc_credit_limit` SHALL 抛结构化错误；评级角色结果含 `creditError`，建议额度不填正数；报告如实标缺；并触发人工复核信号（`needsManualReview` 或确认终态）

## 不做什么
- 数字（指标、规则、评级、额度）只由工具和 `scenarios/dd04/*.yaml` 计算；角色模型只写解释，不得改写计算结果。完整尽调的六角色可各自调用模型（见 ADR-0008），不回到「单主控顺序点六个计算工具、全程不调角色模型」的旧编排。
- 不编造利率百分点和法规条文。利率只输出配置里的方向。
- 不做 RAG、PDF/OCR、图数据库、外部工商接口和放款。30 秒不是官方时限，不作为验收。
- 不把 `enterprise_risk.risk_level_summary` 当作本系统评级。
