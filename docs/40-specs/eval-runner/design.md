# 评测框架 设计

状态：已确认    对应需求：已实现

## 方案概述

```text
题目文件 ─load_dataset─▶ (题目, expected) 分离
             │                   │
             ▼                   │（只给评分器）
      泄漏检查 leak_check          │
             ▼                   │
   逐题 run_service.create_run ◀── 与 HTTP 同一入口
             ▼                   ▼
   results.jsonl（逐题追加）── scoring.score ──▶ summary.json
             ▼
   exporters[format] ──▶ answers.json
```

## 模块（`ocft-backend/eval/`）

| 文件 | 职责 |
|------|------|
| `dataset.py` | 读 `.jsonl` / `.json`；校验 ID 唯一、`question` 或 `turns` 必填、`expected` 只允许已知检查项；返回题目与 expected 两份数据 |
| `scoring.py` | 规则评分：`status`、`containsAll`、`containsAny`、`notContains`、`toolsCalled`、`requireEvidence`；得分 = 通过项 / 检查项 |
| `leak_check.py` | 在 `app/` 中搜索题目 ID 与 ≥ 8 字的期望文本（跳过样本数据 `seed.py`） |
| `run.py` | CLI：建表与幂等种子 → 泄漏检查 → 逐题执行 → 续跑 → 汇总 → 导出 |
| `datasets/public_sample.jsonl` | 15 道公开样例题 |

多轮题用 `turns`，同一会话依次提问，取最后一轮作答；工具与证据汇总所有轮次。

## 题目格式

```json
{"id": "pub-001", "question": "…", "scenarioId": "credit_review",
 "expected": {"status": "succeeded", "containsAny": ["通过"], "toolsCalled": ["run_credit_rules"], "requireEvidence": true}}
```

## 输出（默认 `eval/output/<题目文件名>/`，已 gitignore）

- `results.jsonl`：`id, status, answer, errorCode, errorMessage, runIds, conversationId, toolNames, evidence[], usage, durationMs, eval?`
- `summary.json`：总数、各终态数、错误码分布、正确率、平均分、无证据答案数、平均耗时、总 token、失败题及失败检查项
- `answers.json`：按导出格式生成

## 红线影响

- R4/R5：expected 在加载时剥离，Agent 只收到问题文本；测试断言 expected 中的标记文本从未出现在模型消息中；泄漏检查阻止题号或答案进入代码。
- 唯一 pipeline：直接调用 `create_run`，与 HTTP、前端同一路径。

## 取舍

- 规则评分对措辞敏感（如"拒绝" vs "不予通过"）：用 `containsAny` 列出同义词缓解；赛题给出标准格式后按格式评分。
- 串行执行：15 题约数分钟；非公开题量大时再评估限流后并发。
