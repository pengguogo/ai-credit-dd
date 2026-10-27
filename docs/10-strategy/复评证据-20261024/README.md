# 复评证据 · 2026-10-24（代码 9ecfefa）

AI 评委扫描报告（80 分，`eea0d32`）复评后的真实模型结果。证据由 `python -m eval.run --input eval/datasets/public_sample.jsonl --fresh` 生成，未手工改写。

## 结果

| 项 | judge-final-2 |
|----|----------------|
| 题数 | 16（官方公开集 LA001–LA010 + 回归 dd-001–dd-006） |
| 准确率 / 平均分 | **100% / 1.0000** |
| 终态 | 12 succeeded · 2 needs_confirmation（LA003、LA006 高风险否决）· 2 needs_clarification（dd-004、dd-005） |
| 失败 / 无证据结论 | **0 / 0** |
| 平均耗时 / 总 token | 16.8 s / 471,524 |
| 评级 / 额度命中 | 10/10 · 10/10 |
| 两轮一致性 | judge-final-1 vs final-2 逐题终态一致 **16/16** |

## 逐题

| 题号 | 终态 | 得分 | 检查 |
|------|------|------|------|
| LA001 | succeeded | 1.00 | 7/7 |
| LA002 | succeeded | 1.00 | 7/7 |
| LA003 | needs_confirmation | 1.00 | 7/7 |
| LA004 | succeeded | 1.00 | 7/7 |
| LA005 | succeeded | 1.00 | 7/7 |
| LA006 | needs_confirmation | 1.00 | 7/7 |
| LA007 | succeeded | 1.00 | 7/7 |
| LA008 | succeeded | 1.00 | 7/7 |
| LA009 | succeeded | 1.00 | 7/7 |
| LA010 | succeeded | 1.00 | 7/7 |
| dd-001 – dd-006 | 4 succeeded · 2 needs_clarification | 1.00 | 全过 |

## 口径与边界

- `riskLevel`、`suggestedCreditAmount`、`dueDiligenceConclusion`、`scoringPoints` 只交给 `eval/scoring.py`；Agent 运行时读不到 `expected`。
- 被拦截或失败时评分取 `errorMessage`；本轮无此类样本。
- 答案是模型真实输出，企业名称按既有策略还原，自然人 / 信用代码 / 证件号 / 地址保持代号；`results.csv` 为 utf-8-sig。
- 本目录只证明公开集与回归集的规则检查通过，不等于官方业务正确率，也不替代业务签核、非公开集与 Windows 干净机验收。
- 文件：`judge-final-2-results.jsonl`（逐题完整记录）、`judge-final-2-summary.json`（汇总）、`judge-final-2-results.csv`（表格版）；`judge-final-1-*` 供一致性对照。
