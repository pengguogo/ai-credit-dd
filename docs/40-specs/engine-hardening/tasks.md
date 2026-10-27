# 引擎补强 任务

状态：已确认

- [x] 1. 终态判定与内置澄清工具（需求 1）
  - 完成：`insufficient_evidence` / `needs_clarification` / `needs_confirmation` 均可产出；说明文本走 errorMessage 并进入会话历史
- [x] 2. 场景配置：实体键、确认规则、结论正则（需求 1、3）
- [x] 3. 单次模型调用时限（需求 2）
  - 完成：慢模型测试在时限内以 `run_timeout` 结束
- [x] 4. 工具摘要、实体槽位、历史压缩（需求 3）
  - 完成：`contextSnapshot` 可在 run 详情查看
- [x] 5. 契约更新、样例题（pub-002/003/004/005/010 期望改为 `needs_confirmation`；新增 pub-016 澄清、pub-017 查无此人、pub-018 多轮指代）
- [x] 6. 验证：历史记录为 pytest 150 项通过、红线扫描 0 ERROR；真实模型评测 17/18（pub-017 为评分同义词缺失，已补“未检索到”）
