# 企业信贷尽调 设计

状态：已确认    对应需求：已确认

> **本轮变更优先于以下历史方案**：2026-10-24 用户授权最小整改：提问持久化及异步meta隐藏库内已知人名，最终答案/澄清保留自然人代号，仅企业名称可还原；证据API与导出对法人/实控人姓名掩码。发布前数值检查保留正负号，并对可识别科目及明确年度匹配；不变更业务阈值、额度或评级口径。旧版“还原全部名称”的验收仅对企业名称继续有效。

## 方案概述
场景 `enterprise_dd`：主控仍走现有 LangGraph 工具循环，可用工具含定位、澄清、`run_dd_agents`、`sql_query`；完整尽调与依赖闭包由 `run_dd_agents` 子图完成（见 [dd-multi-agent 设计](../dd-multi-agent/design.md)）。计算只读库内事实和 `scenarios/dd04/` 下 `metrics.yaml`、`opinion.yaml`、`fraud_rules.yaml`、`scorecard.yaml`（点数制 score-points-v2）、`credit_model.yaml`（incremental-v2）。运行时不读、不输出 `risk_level_summary`。

评级：`rate_risk` 按评分卡点数合计分档；否决项以配置为准（失信、限高、未结逾期等）。额度：`calc_credit_limit` 在缺可用财报等情况下抛 `ToolError`；角色层写入 `creditError`，不编造正数额度。`needsManualReview` / 确认终态由事实缺口、角色降级或失败、额度无法测算、评分卡复核及高风险等确定性规则触发，不以外部汇总评级或模型自评 `needsReview` 单独决定终态。

名称往返：用户问题先执行通用 PII 掩码和场景名称处理，再写入 `AgentRun.question`、用户消息及会话标题；企业名称保留为明文，库内已知自然人保存为本次 run 的代号。主控、角色、工具参数共享 `Scenario.build_masker` / `dd_snapshot.Masker` 的 run 内映射；号码不可逆掩码；最终回复在输出合规前仅还原企业名称，自然人保持代号。证据原值只落本地库。

导出：`python -m eval.dd04 export` 从同次 run 已落库证据组装官方六列，并写 status 旁路文件；不读答案。界面无独立报告 Tab；对话区按 Agent 原文导出 PDF/Word（系统字体 + 最小 OOXML），脱敏规则见 `answer-export.ts`。尽调五步单步核对走 `POST /api/agent/dd/steps`（见草稿 [五步依赖与单步核对](./五步依赖与单步核对.md)）。

## 涉及模块与负责人
工具与 `scenarios/dd04/`（数据层）；`dd_graph` / `dd_roles` / 场景提示词与 Skill（Agent 核心）；名称代号映射（合规与可观测）；六列导出（评测）；对话区导出与角色泳道（前端）。不改 `app/llm.py` 的模型锁定。

## 接口 / 契约变更
见 [contracts/agent-api.md](../../../contracts/agent-api.md)（多 Agent 事件、`run_dd_agents`、`/dd/steps`）与 [contracts/dd04-credit-amount.md](../../../contracts/dd04-credit-amount.md)。界面导出只消费本轮 `answer` 文本，不新增导出 HTTP 接口。

## 数据变更
无。十张事实表已由迁移 8 创建。答案文件继续由 `app/dd_import.py` 跳过。`enterprise_risk.risk_level_summary` 列可保留入库，运行时不读。

## 红线影响
- R1：无影响。仍只经 `app/llm.py`。
- R2：无影响。LangGraph 只调度；角色与计算为本仓库代码。
- R3：无影响。评级、额度和报告继续写 calculation 证据。
- R4：无影响。不写入任何申请的标准结论；失败如实返回错误。
- R5：导出与导入都不读答案文件和 `reference_answer`；运行时不读外部汇总评级。
- R6：无影响。高风险与确定性复核仍走确认规则。
- R7：模型请求中的名称以 run 内代号替换；持久化提问隐藏库内已知自然人、保留企业名称；最终回复在输出合规前仅还原企业名称，自然人保持代号。失败仍返回结构化错误。
- R8：无影响。不改一键启动。
- R9：无影响。不新增密钥。

## 取舍
选择「主控工具循环 + `run_dd_agents` 六角色子图」：数字稳定、材料可写多 Agent。放弃旧版「六环节只当工具、角色从不调模型」。若评审要求更少 token，可在 `agents.yaml` 关闭采集角色的 `llm`。

档位名称维持 yaml 现状。官方是否只接受三档仍待确认。

报告导出选择对话区按原文导出 PDF/Word，放弃右侧独立报告页与证据快照重排版，也放弃第三方导出库。
