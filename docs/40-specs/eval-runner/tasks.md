# 评测框架 任务

状态：已确认

- [x] 1. 题目加载与校验 `dataset.py`（需求 1、3）
  - 完成：jsonl / json；ID 唯一、question 或 turns 必填、未知检查项报错；题目与 expected 分离
- [x] 2. 规则评分 `scoring.py`（需求 2）
  - 完成：status、containsAll、containsAny、notContains、toolsCalled、requireEvidence
- [x] 3. 泄漏检查 `leak_check.py`（需求 3）
  - 完成：`app/` 中出现题目 ID 或 ≥ 8 字期望文本即阻止评测
- [x] 4. Runner（需求 1、4）
  - 完成：逐题 `create_run`、单题错误隔离、断点续跑、`--fresh`/`--limit`、summary 与 answers 导出、可插拔导出格式
- [x] 5. 15 道公开样例题（需求 5）
- [x] 6. 测试：端到端（假模型）、expected 不进入模型、续跑、多轮同会话、错误隔离、导出、评分、泄漏检查、题目校验
- [x] 7. 验证：历史记录为 pytest 110 项通过；CLI 实跑在无 Key 时 13 题如实 failed、2 题正确 blocked；Skill、README、流程与日志已更新

## 实跑发现并修复

- "忽略之前的所有指令"未被拦截（修饰词叠加带"的"），已补规则与 2 条样例。
