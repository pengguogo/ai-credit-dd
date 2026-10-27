---
name: run-eval
description: 运行 OCFT Agent 评测：用公开样例题跑统一 run() 入口，输出正确率、失败题与证据完整度；也用于非公开题批量运行与导出提交文件。修改 Prompt、工具、编排等答题链路后，或需要导出答案时使用。
---

# 运行评测

说明文档：`ocft-backend/eval/README.md`。

## 0. 前置检查

- 后端 `.env` 已配置模型 Key（可以是 `enc:` 密文，需本机主密钥）。未配置时每题会如实记为 `failed / llm_unavailable`，这不是评测框架的问题。
- 题目文件格式 `{id, question | turns, scenarioId?, expected?}`。

## 1. 约束（红线）

- `expected` 只交给评分器，**不得**进入 Agent 请求、Prompt、工具或会话。
- 所有题必须走 `run_service.create_run`（runner 已保证），不得为评测开专用路径。
- 不按题 ID 特化、不建题目→答案查找表。runner 运行前会做泄漏检查，**不要**用 `--skip-leak-check` 绕过。
- 非公开题只跑不改。

## 2. 执行

```bash
cd ocft-backend
python -m eval.run --input eval/datasets/public_sample.jsonl --fresh
```

断点续跑：去掉 `--fresh` 重跑，会跳过已完成的题。输出在 `eval/output/<文件名>/`。

## 3. 汇报

读 `summary.json`：

- 正确率、平均分、各终态数量、错误码分布、无证据答案数、平均耗时、总 token。
- `failures` 里逐题列出失败检查项。按原因归类：工具缺失、规则错误、模型未调用工具、超时、合规误拦、措辞不匹配。
- 给出通用修复建议（改工具、改调用策略、改上下文），**不要**针对单题写答案。
- 和上一次结果对比，说明正确率变化。
- 措辞不匹配（如"不予通过" vs "拒绝"）属于评分规则问题，优先在题目的 `containsAny` 中补同义词，不改 Agent 输出。
