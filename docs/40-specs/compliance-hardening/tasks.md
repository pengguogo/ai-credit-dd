# 合规补强 任务

状态：已确认

- [x] 1. 分类词库与加载（需求 1）
  - 完成：`lexicon/` 五类词表 + 白名单；`ComplianceDecision.category`
- [x] 2. 补齐注入与承诺规则（需求 1）
  - 完成："忽略上面所有规则"、"收益保证10%"、越狱角色扮演、查他人信息句式均被拦
- [x] 3. 用户拒答话术（需求 2）
  - 完成：blocked run 的 `errorMessage` 为分类话术，不含命中词；命中词只进审计
- [x] 4. PII 脱敏并接入 run 链路（需求 3）
  - 完成：消息、run.question、送模型内容、答案均为掩码；审计 `pii_redacted`（input / output）
- [x] 5. 合规样例集与拦截率测试（需求 4）
  - 完成：9 类每类 ≥ 5 条（label_leak 2 条），拦截率 100%；14 条正常样例误拦 0
- [x] 6. 验证：历史记录为 pytest 96 项通过、红线扫描 0 ERROR；README 合规节写明覆盖范围与局限
