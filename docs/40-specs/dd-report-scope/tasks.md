# 尽调口径区分（企业 / 本笔贷款）任务

状态：已确认

- [x] 1. `run_dd_agents` 增加 `scope` 入参与兜底推断，校验非法值（Agent 核心，关联需求 1、4）
  - 完成标准：`scope=enterprise` 时 `applicationId=null`、可有建议授信额度、无申请额；未传 scope 且有 `applicationId` 时为 loan；非法值 `invalid_args`。
- [x] 2. 快照与角色按口径执行（Agent 核心，关联需求 2、3）
  - 完成标准：`load_snapshot(scope="enterprise")` 不附加贷款行；评级角色按能力测算建议授信额度；报告证据用企业键；章节校验按五部分。
- [x] 3. `dd_calc.build_report` 支持 enterprise 口径（数据层与工具，关联需求 2）
  - 完成标准：`sections` 含 `creditSuggestion` 且无 `applyAmount`，结论为合作建议 + 建议授信额度；`loan` 默认输出不变。
- [x] 4. 提示词与 Skill 分口径（场景与文档，关联需求 1、2）
  - 完成标准：`controller.md` 写明判断规则；`report.md` 与 `dd-report.md` 含企业口径骨架（五部分、只写建议授信额度、禁用申请贷款额度与放款措辞）。
- [x] 5. 报告建档识别企业口径（服务，关联需求 3）
  - 完成标准：企业口径报告也能建档，标题用企业编号，`applyAmount=null`，不推进贷款状态。
- [x] 6. 前端预览与结构化导出按口径隐藏申请额度（前端，关联需求 3）
  - 完成标准：`scope=enterprise` 时渲染额度建议与建议授信额度 KPI，不渲染申请贷款额度；导出不含「申请贷款额度」。
- [x] 7. 契约与文档同步（场景与文档，关联需求 1–4）
  - 完成标准：`contracts/agent-api.md` 写明 scope 与两种报告结构；`docs/INDEX.md` 登记本 spec；开发日志追加一条。
- [x] 8. 设计用例：覆盖全部验收标准（场景与文档，关联需求 1…4）
  - 完成标准：`test-cases.md` 已确认，每条验收标准至少一条用例。
- [x] 9. 单测与验证（评测 / Agent 核心，关联需求 1…4）
  - 完成标准：`python -m pytest tests -q`、`npm run lint`、`npm run build` 通过；前后端启动后企业口径报告有建议授信额度、无申请贷款额度，申请口径报告不变。
- [x] 10. 贷款口径尽调结论改为先结论后依据（Agent 核心、场景与文档，关联需求 5）
  - 完成标准：结构化 `dueDiligenceConclusion` 以准入建议开头并带额度、期限，随后「依据：」；report 提示词与 dd-report Skill 明确该顺序；额度无法测算时如实说明。
- [x] 11. 企业口径结论改合作建议并拦截贷款申请措辞（Agent 核心、场景与文档，关联需求 2、5）
  - 完成标准：企业结论以「建议合作 / 审慎合作 / 暂不合作」开头并含建议授信额度，再写「依据：」；企业正文出现申请贷款额度、放款前、投放前、贷款期限等措辞时被 `dd_verify.check_scope` 拦下并重写；「建议授信额度」不被拦截。
