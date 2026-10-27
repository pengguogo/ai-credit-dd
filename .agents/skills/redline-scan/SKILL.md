---
name: redline-scan
description: 扫描代码中的比赛红线风险：硬编码答案、运行时访问评测标签、绕过 llm.py 的模型客户端、非锁定模型名、密钥泄漏、模板化假结论。合入 main 前、提交前、或怀疑有 Mock 答案时使用。
---

# 红线扫描

## 1. 运行脚本

在仓库根目录执行：

```bash
python .agents/skills/redline-scan/scripts/scan.py
```

脚本只读，按规则输出 `[级别] 规则 文件:行号 内容`，有 ERROR 时退出码为 1。

## 2. 人工复核

脚本是关键字扫描，会有误报和漏报。对每条命中判断：

| 规则 | 判定为违规 | 可接受 |
|------|------------|--------|
| eval-label | 运行时代码（tools / agent / services / routers / 前端）读取该字段 | 模型注释、合规拦截规则、评分器 |
| llm-client | `llm.py` 之外创建模型客户端 | — |
| model-name | 写死了其他模型名 | `config.py` 中的锁定常量 |
| secret | 真实密码、Key、带凭据的连接串 | `.env.example` 中的空值或占位符 |
| fallback-answer | 模型失败时返回拼接好的业务结论 | 明确标注"降级、仅展示规则事实"的结构化输出 |
| answer-column | 运行时工具读取预存的结论列 | 离线评分 |

再人工检查脚本覆盖不到的：
- Prompt 中是否出现"如果问 X 就回答 Y"或具体样例题答案。
- 种子数据是否带结论列（`decision`、`evidence`、`decision_reason` 等）且可被工具读到。
- 是否存在题目 ID → 答案的映射。

## 3. 汇报

按"违规 / 需确认 / 误报"三类列出，违规项给出修复方向和目录负责人（见 `AGENTS.md`）。已登记的待处理事项见 `docs/30-standards/redlines.md` 末尾，不必重复报告为新问题。
