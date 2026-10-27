# 赛题 04 多 Agent + 运行时 Skill 公开集复测

- 代码：`e853286`（多 Agent 编排 + 六角色运行时 Skill + 敏感信息脱敏），真实模型 `deepseek-v4.1-flash`
- 输入：`inputs/applications.jsonl`，与 [dd04-multi-agent](../dd04-multi-agent/) 同一份 10 笔申请
- 命令：`cd ocft-backend && python -m eval.run --input <inputs/applications.jsonl> --output-dir <applications/> --fresh`
- 对照基线：[dd04-multi-agent](../dd04-multi-agent/batch-summary.json)（`28be540`，加入 Skill 之前）

## 结果

| | 基线（28be540） | 本次（e853286） |
|---|---|---|
| 终态 | 10 笔 `needs_confirmation` | 5 笔 `succeeded`，5 笔 `needs_confirmation`（其中 3 笔高风险） |
| 风险评级与参考一致 | 5/10 | 5/10 |
| 建议额度与参考一致 | 5/8（数值参考） | 7/10（含 LA003、LA006 两笔拒贷） |
| 耗时 | 平均 54.3 秒 | P50 48.2 秒，P90 73.8 秒，最长 84.2 秒 |
| token | 平均约 36.0k | 平均 35.6k |

逐笔见 [application-comparison.csv](application-comparison.csv)，汇总见 [batch-summary.json](batch-summary.json)。

## 解读

- 编排层：10 笔全部跑完，没有失败、截断或事实校验不通过；运行时 Skill 给 `needsReview` 定了规则后，低风险误报待确认明显减少。
- 准确率卡在规则计算层：评级偏低一档的 LA002 / 004 / 005 / 008 来自评分卡阈值；LA010 由严重反欺诈否决判为高风险、额度 0（参考为中风险、1500–2000）。是否调整需团队拍板，不按公开答案调参。
- LA002、LA007 为低风险但进入待确认，原因未逐笔复核。
- 官方六列导出只收 `succeeded`，本次 5 笔待确认（含正确拒贷的 LA003、LA006）不会进入结果文件，导出口径待评测负责人确认。

## 边界

单字段离线比对，参考列只在评测侧读取，不进入运行时；不等于全文正确率或正式提交完成率。

- 脱敏：`applications/` 下的导出除评测导出自带的号码类掩码外，归档前把企业全名、法定代表人、实控人、股东、关联方、被担保方、注册地址、统一社会信用代码、法人证件号统一替换为代号（如 `企业E001`、`人员E001-1`），与运行时代号同一套规则；扫描确认原文 0 处。`results.xlsx` 为二进制无法逐值掩码，未归档（同内容见 `results.csv`）。
- 证据快照中的长内容被导出截断，额度在截断时从最终答案中提取（去掉千分位）。
