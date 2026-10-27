# 尽调口径区分（企业 / 本笔贷款）设计用例

状态：已确认

| 编号 | 追溯 | 类型 | 前置 | 操作 | 期望 | 验证 |
|------|------|------|------|------|------|------|
| TC-1 | 需求 1 | 正常 | 合成企业与贷款数据 | 主控以 `{enterpriseId, mode=full, scope=enterprise}` 调用 `run_dd_agents` | 返回 `scope=enterprise`、`applicationId=null`，可有 `suggestedCreditAmount`，报告五部分且无「申请贷款额度」 | 单测 |
| TC-2 | 需求 1 | 正常 | 同上 | 调用 `{applicationId, mode=full}`（不传 scope） | 口径推断为 loan，报告含五部分与额度建议 | 单测 |
| TC-3 | 需求 1 | 异常 | 同上 | 调用 `{enterpriseId, mode=full, scope="group"}` | `invalid_args`，无角色启动事件、无证据 | 单测 |
| TC-4 | 需求 2 | 正常 | 企业快照 | `dd_calc.build_report(..., scope="enterprise")` | `sections` 含 overview/financialAnalysis/riskAlerts/creditSuggestion/riskConditions；`creditSuggestion` 无 `applyAmount`；结论含建议授信额度与合作建议，不含「申请贷款额度」 | 单测 |
| TC-5 | 需求 2 | 边界 | 企业快照 | `scope=enterprise` 跑完整尽调 | 有 `calc_credit_limit` 证据（企业键）；评级角色有建议授信额度、`applyAmount` 为空 | 单测 |
| TC-6 | 需求 2 | 正常 | 企业快照 | `write_report` 收到五部分正文 | 校验通过并保存；缺「风险提示」时按缺章节降级，不放宽 | 单测 |
| TC-7 | 需求 3 | 正常 | 企业口径完整 run | 运行结束后读取 `workspace_service.register_asset` | 建一条档案，`applicationId=null`、`applyAmount=null`，贷款状态不变 | 单测 |
| TC-8 | 需求 3 | 正常 | 企业口径报告 run | 前端预览与结构化导出 | 有额度建议与建议授信额度 KPI，无申请贷款额度 KPI；导出文本不含「申请贷款额度」 | 手工 |
| TC-9 | 需求 4 | 正常 | 官方贷款样本 | 以 `{applicationId, mode=full}` 跑完整尽调 | 五部分齐全、额度建议与申请额并列，`calc_credit_limit` 证据存在 | 单测 |
| TC-10 | 需求 1、2 | 红线 | 配置与提示词 | 读取 controller / report / dd-report | 含口径判断与企业禁用申请贷款额度措辞；不含任何题号答案或 expected | 单测 |
| TC-11 | 需求 5 | 正常 | 贷款快照与额度结果 | `build_report(scope="loan")` | 结论以「建议准入 / 审慎准入 / 暂不准入」开头，紧跟建议额度与期限，「依据：」在其后 | 单测 |
| TC-12 | 需求 5 | 边界 | 额度无法测算 | `build_report(scope="loan")`，`credit` 为空 | 结论先给准入建议，再写「额度无法测算」与补件复核，不出现额度数值 | 单测 |
| TC-13 | 需求 2、5 | 正常 | 企业快照 | `build_report(scope="enterprise")` | 结论以「建议合作 / 审慎合作 / 暂不合作」开头并含建议授信额度，「依据：」在后；全文无「申请贷款额度」 | 单测 |
| TC-14 | 需求 2 | 异常 | 企业口径模型输出带贷款措辞 | 报告首稿写「申请贷款额度…放款前…」 | 事实校验拦下并重写；最终正文不含该措辞，`verify_finished` 先 retry 后 ok；重写用尽则 `narrative_check_failed` | 单测 |
| TC-15 | 需求 2 | 边界 | 企业口径正文含「投放前」「贷款期限」或仅「建议授信额度」 | 调用 `dd_verify.check_scope` | 前两者返回 scope issue；仅建议授信额度返回空；loan 口径返回空 | 单测 |
