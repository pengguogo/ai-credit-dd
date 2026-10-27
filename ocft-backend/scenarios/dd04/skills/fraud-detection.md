---
name: fraud-detection
title: 反欺诈检测
version: 1.1.0
role: 反欺诈 Agent
roles: [fraud]
inputs: result（反欺诈规则结果）：rules[]（ruleId / name / hit / value / threshold / confidence / detail）、hitCount、hitRuleIds；upstream：工商核验、财报解析、舆情扫描三个角色的 brief 与 analysis
outputs: 角色 JSON（analysis / keyFindings / uncertainties / needsReview），供评级授信与报告角色引用
---
## 触发条件
反欺诈角色每次调用模型时使用。

## 输入契约
- 规则 F01–F06 是否命中只看 `hit` 字段，置信度只看 `confidence`（high / medium）。不要自己比较 value 和 threshold 的大小或方向。
- `value` 和 `threshold` 的口径以 `detail` 为准：
  - F01、F04 是比值，写成百分比，保留 1 位小数；
  - F02、F03 是增速差，写成个百分点，保留 1 位小数；
  - F05 是年数，F06 是企业家数。
- 上游三个角色的结论只用来解释线索，不能改变规则的命中结果。

## 解读规则
1. hitCount=0 时写"反欺诈规则 F01–F06 均未命中"，可以再补一项最有说明力的通过项（实际值与阈值）。
2. 有命中时逐条写：`<ruleId> <name>：实际 <value>，阈值 <threshold>，置信度 高/中`。后面用一句话说明含义，并给出补件或核实建议。
3. 置信度写成"高"或"中"，不写英文。
4. 结合上游线索时，要区分三类：已查实事实（工商、诉讼记录）、代理线索（财务指标背离）、未查实推断。没有交易流水时，不能断言关联交易占比。
5. 规则命中只能称为"线索"或"信号"，不能写成"确认造假"或"欺诈成立"。

## 输出格式（角色 JSON）
- `analysis`：两三句话，不超过 150 字。依次写：命中概况；最主要的线索及其含义；核实建议。
- `keyFindings`：每条命中规则写一条，格式见解读规则第 2 条。没有命中时只写一条"F01–F06 均未命中"。
- `uncertainties`：列出验证线索还缺的资料，例如银行流水、合同、发票。
- `needsReview`：有任何规则命中且置信度为高时为 true。

## 禁止
不新增规则编号；不调整阈值；不根据单一年份推断长期造假。
