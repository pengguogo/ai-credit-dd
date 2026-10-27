# 报告列表（资产档案） 设计用例

2026-10-25 状态梳理变更：报告无状态、贷款申请四态，用例 1–6、10 已按新口径调整。

| 编号 | 场景 | 预期 | 自动化 |
|----|------|------|--------|
| TC-WA-01 | 完整报告 run 完成后建档 | 生成档案，`runId` 唯一；重复调用返回同一条 | `test_register_is_idempotent_and_indexes_scope` |
| TC-WA-02 | 追问 / 澄清 / 失败答案 | 不建档 | `test_followup_answer_is_not_registered_as_asset` |
| TC-WA-03 | 按关键词 / 企业 / 申请检索 | 命中档案，分页与计数一致 | `test_register_is_idempotent_and_indexes_scope`、`test_workspace_api_list_and_detail` |
| TC-WA-04 | 报告无状态 | 列表与详情响应不含 `status` / `version` / `events` / 状态计数；状态操作接口已移除 | `test_report_has_no_status_or_events` |
| TC-WA-05 | 报告生成推进贷款申请 | 待处理 → 待审核；已审核通过 / 审核不通过不被覆盖 | `test_register_advances_pending_application_to_pending_review`、`test_register_does_not_override_decided_application` |
| TC-WA-06 | 不存在档案 | 404 `not_found` | `test_workspace_api_list_and_detail` |
| TC-WA-07 | 风险结论名称由规则生成 | 高风险户包含标准风险术语；干净户不误报 | `test_dd_risk_conclusions.py` |
| TC-WA-08 | 新旧档案企业名称、名称检索和分页 | 从企业事实表取名称；列表与详情一致；名称匹配影响 total 与 hasMore；报告关联不变 | `test_workspace_enterprise_name_and_search` |
| TC-WA-09 | 企业资料缺失 | 缺失返回 null 且档案仍可查询；读接口不回写历史标题 | `test_workspace_missing_enterprise_keeps_archive` |
| TC-WA-10 | 浏览器查看报告列表及报告入口 | 名称、申请标签、说明为业务中文；无状态筛选/徽标/复核按钮与状态时间线；正文无内部运行标识；原报告可打开 | 浏览器走查与截图 |
