# 尽调口径区分（企业 / 本笔贷款）设计

状态：已确认    对应需求：已确认

## 方案概述
`run_dd_agents` 新增 `scope: loan | enterprise`，由主控按问题判断；未传时按入参兜底（有 `applicationId` 为 loan，只给 `enterpriseId` 为 enterprise）。口径随快照冻结进六个角色：

- `enterprise`：`Snapshot.application_id` 为空、不加载任何贷款行；评级授信角色仍测算建议授信额度（`calc_credit_limit` 无申请额封顶，`applyAmount=null`）；报告角色按五个章节写作与校验；`build_report(scope="enterprise")` 产出 `creditSuggestion`（无 `applyAmount`），结论为合作建议 + 建议授信额度。
- `loan`：行为与现状一致（五部分、额度建议、申请额并列）。

报告正文的事实校验、证据落库、终止工具路径不变，只按口径切换摘要字段与禁用措辞。

**结论顺序（2026-10-25 追加）**：贷款口径的尽调结论改成「先结论、后依据」。正文由 `report.md` 与 `dd-report` Skill 约束：第一句给准入建议（建议准入 / 审慎准入 / 暂不准入）与建议额度、期限，第二句以「依据：」列 1–3 条事实；结构化 `build_report.dueDiligenceConclusion` 同步按同一顺序生成（`_loan_conclusion`），报告预览、报告列表摘要与导出直接复用。额度无法测算时先给准入建议，再写额度无法测算、需补件复核。

**企业口径的结论与措辞（2026-10-25 复核追加，后按用户明确修正）**：企业口径结论为合作建议（建议合作 / 审慎合作 / 暂不合作）+ 建议授信额度 +「依据：」，由 `_enterprise_conclusion` 生成；允许「建议授信额度 / 额度建议」。`dd_verify.check_scope` 扫描企业口径正文，命中「申请贷款额度」「申请额度」「贷款期限」「本次融资」「放款前」「投放前」即作为 issue 进入既有重写流程；重写用尽仍不通过则 `narrative_check_failed`，不发布正文。

## 涉及模块与负责人
- Agent 核心（`app/agent/dd_graph.py`、`dd_roles.py`、`dd_snapshot.py`、`dd_verify.py`）：scope 入参、快照口径、角色计算、章节校验、证据表键、企业措辞拦截。
- 数据层与工具（`app/tools/dd_calc.py`）：`build_report(..., scope)`、企业能力额度与合作结论。
- 场景与文档（`scenarios/dd04/prompts/controller.md`、`report.md`、`skills/dd-report.md`、`rating.md`）：口径判断与两套写作骨架。
- 前端（`components/report/preview/*`、`lib/dd-report-export.ts`）：按 `scope` 隐藏申请贷款额度 KPI，保留建议授信额度。
- 服务（`app/services/workspace_service.py`）：企业口径报告建档识别。
- 契约：`contracts/agent-api.md`。

## 接口 / 契约变更（链接 /contracts）
- `run_dd_agents` 入参新增 `scope`（可选，`loan|enterprise`）；`plan_ready.target` 与工具结果增加 `scope`。工具结果在 enterprise 口径下 `applicationId=null`、可有 `suggestedCreditAmount`、无 `applyAmount`。
- `build_dd_report.sections` 在 enterprise 口径下仍有 `creditSuggestion`，但不含 `applyAmount`；顶层 `suggestedCreditAmount` 可有值。
- 报告建档判定从「含五部分标题」改为「含企业概况 + 财务分析 + 风险提示 +（额度建议或风控条件）」。
- 详见 [Agent API](../../../contracts/agent-api.md)。

## 数据变更（表、字段、迁移方式）
无表结构变更。证据 `source_ref.table` 在 enterprise 口径下：评级证据 `enterprise_risk`，报告与额度证据 `enterprise_basic`；不产生 `loan_application` 证据。

## 红线影响（对照 30-standards/redlines.md 逐条说明）
- R1：无影响，模型仍只经 `app/llm.py`。
- R2：无影响，口径判断在代码与提示词内完成。
- R3：无影响，企业口径的评级、额度与报告证据照常落库，每节结论仍可追溯。
- R4：无影响，不写死任何样本结论；口径判断只用问题文本与入参。
- R5：无影响，不读取 `expected` 或评测标签；loan 口径仍由主控按申请编号定位。
- R6：无影响，确认流不变。
- R7：无影响，合规检查不变。
- R8：无影响，不新增依赖。
- R9：无影响，不新增凭据。

## 取舍（选择了什么、放弃了什么、何时重访）
- 用工具入参 `scope` 而不是主控在正文里自我约束：申请额字段与禁用措辞由确定性代码裁剪，模型无法偷偷补出申请贷款额度。
- 未传 `scope` 时按入参兜底而不是报错：保持既有调用与单测可用，同时让只给企业的入口自动落到企业口径。
- 企业口径仍测算建议授信额度（能力上限），但不绑定申请额、期限与担保：满足「主体尽调要额度建议、不要某笔申请额度」；若日后要单独企业授信政策再重访。
- 五步单页仍按所选申请出 loan 报告：该页面本身就是按申请核对，不在本轮范围。
