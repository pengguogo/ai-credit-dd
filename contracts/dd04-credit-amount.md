# DD04 额度证据契约

状态：已确认；2026-10-24 升级为 `incremental-v2`（用户要求评级与额度对齐公开答案口径，按通用规则调整，见变更）。团队模拟政策。

## 变更
- 2026-10-24 `incremental-v2`：风险档位只决定准入（高风险为 0）与利率方向，评级系数对非高风险统一为 1；去掉现金流系数，经营现金流改为「重大财务异常」之一；命中 ≥2 项重大财务异常时区间按 `[low_ratio, high_ratio]` 审慎压降；取整按金额分档。系数与档位经公开测评集校准（公开题拟合策略），运行时不读答案。
- 2026-10-24 `incremental-v1`：敞口改为条件、现金流改为风险调整、折减后封顶（金额专项修复）。

## 计算

金额单位万元；`C = min(max(revenue, 0) × revenue_coef, max(owners_equity, 0) × equity_coef)`。
`L = min(apply_amount, C × rating_coef)`；`rating_coef` 对低风险 / 低-中风险 / 中风险均为 1，高风险为 0。高风险或存在否决时 `L = 0`。

重大财务异常（`anomaly_discount`，命中项写入 `anomalies[]`，每项带 `code / name / value / threshold`）：

| 编号 | 名称 | 判定 |
|---|---|---|
| A1 | 营收与经营现金流背离 | 经营现金流 ≤ 0，或 < 净利润 × `min_ocf_to_profit`（0.5） |
| A2 | 应收账款占营收过高 | 应收账款 / 营业收入 > `max_receivable_to_revenue`（0.40） |
| A3 | 其他应收款占总资产过高 | 其他应收款 / 总资产 > `max_other_receivable_to_assets`（0.10） |
| A4 | 关联担保圈 | 关联企业中担保圈 ≥ `min_guarantee_circle`（2）家 |

区间比例：命中 ≥ `min_hits`（2）项时为 `[low_ratio, high_ratio]`（0.6, 0.8），否则为 `[1 - band, 1]`（0.85, 1）。
取整步长：`L ≥ large_amount.threshold`（2000）时为 `large_amount.step`（500），否则为 `round_step`（100）。
下界 `floor_step(L × low)`、上界 `floor_step(L × high)`，均向下取整，不可突破 `L`；下界不大于上界。
存量贷款和担保只作为本次融资的敞口核验与条件，不直接扣额度。营收、净资产为零或负数保留零上限；缺失或非有限值不等价于零，不生成有效正数建议。
单项异常不折减，只写核查条件；经营现金流非正另写还款来源核验条件。

## 表结构到输出

| 原始字段 | 工具 / 报告字段 | 约束 |
|---|---|---|
| `loan_application.apply_amount` | `suggestedCreditAmount: string` | 非负整数单值或 `low-high`；不超过申请额 |
| `loan_application.apply_amount` | `applyAmount: number` | 本次申请金额原值（万元），只作展示与对照，不参与重算 |
| `loan_application.apply_date` / `enterprise_finance.year` | `asOf: string` / `financialYear: integer` | 按申请日期之前最近完整年度选财报，不使用申请年度的全年报 |
| `enterprise_finance.revenue / owners_equity` | `steps` 中营收、净资产上限 | 十进制计算，零值不能被筛掉 |
| `enterprise_finance.operating_cashflow / net_profit / accounts_receivable / other_receivable / total_assets`、`enterprise_related.is_guarantee_circle` | `anomalies[]`、`steps` 中「重大财务异常折减」 | 只用事实与配置阈值；异常是待核实线索，不是否决 |
| `enterprise_risk.existing_loan_balance / external_guarantee_amount` | `exposures: {existingLoanBalance, externalGuaranteeAmount}` / `conditions: string[]` | 金额万元，不与净资产重复全额扣减 |
| 场景配置 | `policyVersion: string` / `creditScope: string` / `assumptions: string[]` | 明确模拟政策、缺少还款计划及披露时点的边界 |

现有字段 `applicationId, enterpriseId, riskLevel, unit, termMonths, rateDirection, guaranteeType, steps, configFile` 保留；新增 `anomalies`、`applyAmount`。
`build_dd_report.sections.creditSuggestion` 复用全部金额字段和政策/时点字段，不由模型重算。
API 顶层、DB 表及迁移无变化。

## 风险评级（`scorecard.yaml`，score-points-v2）

`rate_risk` 输出 `riskLevel`、`score`（风险点数，整数，越高越差）、`dimensions[]`（`dimension / name / value / points / maxPoints / cuts / source`）、`missingIndicators[]`、`vetoes[]`。
10 项指标按阈值档给 0–3 点（失信或限高、对外担保逾期为 2 点）；合计 ≤1 低风险、2–4 低-中风险、5–19 中风险、≥20 高风险。
一票否决只保留法定代表人失信、限高、存在未结逾期；反欺诈命中不否决。外部汇总评级不读取、不参与计分。舆情评分取原始字段 `public_opinion_score`，缺失时退回本系统舆情健康分。

## 错误

非法申请金额/期限/日期：`invalid_args`；缺少可用财报或必要财务字段、非有限金额、单位不一致、非法政策参数（系数/比例越界、下限高于上限、步长非正整数）：`execution_failed`。
工具失败无计算结论或伪造证据。合法零容量/高风险的计算结果仍为 `suggestedCreditAmount = "0"`，原因写入计算步骤/条件。

## 验证边界

本政策不是官方唯一授信公式，也不代表银行审批。阈值、折减比例与取整档位用公开测评集校准过（公开题拟合策略），非公开集存在边界抖动风险；技术方案须如实披露。
参考答案仅离线评分读取；精确区间相等、重叠、包含和无法数值化的结果分别统计，执行失败留在总分母中。
