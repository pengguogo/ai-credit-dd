# 文档索引

> 团队内部导航。对外介绍见根目录 [README.md](../README.md)，AI 开发规范唯一来源见 [AGENTS.md](../AGENTS.md)。
> 状态只使用：`生效`（当前依据）/ `草稿`（仍需确认或验收）/ `归档`（仅供追溯，不再维护）。
> 固定结构的 Spec 目录以 requirements 为入口，默认覆盖同目录的 design、tasks、test-cases；无需逐文件重复登记。

## 分层约定

| 目录 | 用途 |
|------|------|
| `00-rules/` | 官方规则原文和主办方材料 |
| `10-strategy/` | 当前工程策略、分工、流程和开发日志 |
| `20-architecture/` | 当前架构入口、依赖清单和 ADR |
| `30-standards/` | 编码、Git、红线和评审规范 |
| `40-specs/` | 功能 requirements / design / tasks / test-cases |
| `50-runbooks/` | 可照做的启动、评测、提交与故障处理手册 |
| `60-pitch/` | 当前路演与答辩材料 |
| `90-archive/` | 被替代的方案、评审和测试快照；不作为当前事实依据 |

接口契约统一放根目录 [`contracts/`](../contracts)，提交材料放 [`submission/`](../submission)。

## 官方规则

| 文档 | 状态 | 说明 |
|------|------|------|
| [比赛规则要求](00-rules/比赛规则要求.md) | 生效 | 通用比赛规则 |
| [通用提交材料说明](00-rules/通用提交材料说明.md) | 生效 | 通用交付格式与自查要求 |
| [赛题04题目说明](00-rules/赛题/赛题04_企业智能信贷尽调/题目说明.md) | 生效 | 赛题04七项功能、评测与业务自查基准 |
| [赛题04提交材料说明](00-rules/赛题/赛题04_企业智能信贷尽调/提交材料说明.md) | 生效 | 赛题04专属交付要求；与通用说明冲突时优先 |

## 策略与过程

[交付材料缺失扫描-20261025-59ae9e8](10-strategy/交付材料缺失扫描-20261025-59ae9e8.md)（归档）：59ae9e8 材料实物、CSV格式与封包缺口快照。

| 文档 | 状态 | 说明 |
|------|------|------|
| [工程规划与得分策略](10-strategy/工程规划与得分策略.md) | 生效 | 工程优先级和赛题04策略 |
| [模块分工表](10-strategy/模块分工表.md) | 生效 | 模块归属、负责人和交付分工 |
| [企业信贷尽调报告内容要素调研](10-strategy/尽调报告内容要素调研.md) | 生效 | 报告章节、5C 映射及数据缺口；具体 Skill 版本以场景文件为准 |
| [项目开发流程](10-strategy/开发流程.md) | 生效 | 当前阶段、完成项和剩余门禁 |
| [赛题04准备验证](10-strategy/赛题04准备验证.md) | 生效 | 数据体检、输入隔离和格式校验 |
| [赛题04交付清单](10-strategy/赛题04交付清单.md) | 草稿 | 正式材料与封包门禁，随交付进度更新 |
| [开发日志](10-strategy/开发日志.md) | 生效 | 追加式历史过程与提交记录，不回写旧事实 |
| [AI评委整体评测（2026-10-25）](10-strategy/AI评委整体评测-20261025.md) | 生效 | 固定 c423fc6：当前20条真实复测、525项回归、14项分级风险；第9节按用户四档标准复评主观维度 |
| [最新origin/main逐条评分（2026-10-25）](../测试数据/评测/2026-10-25/AI评委逐条评分-origin-main-20261025.md) | 生效 | 固定c7dbd231：24条能力评分、7项功能、9项材料及17+16自查；3项P0防线缺口，570项回归与20条真实运行 |

## 架构、规范与契约

| 文档 | 状态 | 说明 |
|------|------|------|
| [技术选型](20-architecture/技术选型-开发语言与前端.md) | 生效 | Python/FastAPI 与 React/TS/Vite 选型 |
| [自研边界与依赖清单](20-architecture/自研边界与依赖清单.md) | 生效 | 自研模块、第三方依赖和运行时 Skill |
| [待办清单](20-architecture/待办清单.md) | 生效 | 当前赛时阻塞项、材料状态和最终交付门禁 |
| [ADR 目录](20-architecture/adr/README.md) | 生效 | 0001–0008 决策及取代关系 |
| [编码规范](30-standards/coding.md) | 生效 | Python、React、分层与命名 |
| [红线清单](30-standards/redlines.md) | 生效 | 比赛红线到工程约束的映射 |
| [Git协作规范](30-standards/git-workflow.md) | 生效 | 分支、提交与比赛期间凭据例外 |
| [评审清单](30-standards/review-checklist.md) | 生效 | 合入前验证和文档门禁 |
| [Agent API 契约](../contracts/agent-api.md) | 生效 | `/api/agent/*` 唯一对外契约 |
| [赛题04额度证据契约](../contracts/dd04-credit-amount.md) | 生效 | 额度、时点、政策版本与错误边界 |

## 功能 Spec

[开源自建与在线演示](40-specs/open-source-demo/requirements.md)（草稿）：自建使用自有凭据；线上专用 Key、隔离演示库、限额与公开资料边界，待需求确认。

| Spec | 状态 | 当前说明 |
|------|------|----------|
| [Spec规范与模板](40-specs/README.md) | 生效 | 唯一规格格式与八步流程 |
| [尽调发布门禁P0修复](40-specs/dd04-publication-guards/design.md) | 草稿 | J01无证据拒发、J02禁止具体法规引用；仅设计，未实施 |
| [合规补强](40-specs/compliance-hardening/requirements.md) | 生效 | 分类词库、PII 脱敏、拒答和审计 |
| [评测框架](40-specs/eval-runner/requirements.md) | 生效 | 通用评测与赛题04专用导出 |
| [引擎补强](40-specs/engine-hardening/requirements.md) | 生效 | 终态、调用时限和上下文 |
| [可观测性](40-specs/observability/requirements.md) | 生效 | 请求 ID、耗时、异步 run 和 SSE |
| [附件拒绝策略](40-specs/multimodal-input/requirements.md) | 生效 | 非空附件同步拒绝，不创建 run、不调用模型 |
| [尽调角色运行时 Skill](40-specs/dd-skills/requirements.md) | 生效 | 六角色版本化 Skill、主控编排能力与前端 Agent Skill 技能中心 |
| [数据列表维护](40-specs/catalog-crud/requirements.md) | 生效 | 目录及业务表 CRUD |
| [CSV增量导入](40-specs/csv-incremental-import/requirements.md) | 生效 | 仅新增、冲突整批拒绝和审计 |
| [信贷金额专项修复](40-specs/credit-amount-correction/requirements.md) | 生效 | 金额规则已实现；正确率以实测为准 |
| [企业信贷尽调](40-specs/enterprise-dd/requirements.md) | 生效 | 多 Agent、证据和报告主链路 |
| [赛题04多Agent编排](40-specs/dd-multi-agent/requirements.md) | 生效 | 主控加六角色及事实校验 |
| [赛题04业务验收](40-specs/dd04-business-acceptance/requirements.md) | 生效 | 公开申请、问询、评级、额度及全文要点逐项验收 |
| [尽调口径区分（企业/本笔贷款）](40-specs/dd-report-scope/requirements.md) | 生效 | 主控判断 scope；企业口径报告不含额度与申请贷款额度，贷款口径保持五部分 |
| [登录与系统管理](40-specs/auth-admin/requirements.md) | 生效 | 三角色权限、登录和系统管理 |
| [前端工作台](40-specs/frontend-workbench/requirements.md) | 生效 | 对话、轨迹、证据、确认和报告导出 |
| [报告列表（资产档案）](40-specs/workspace-assets/requirements.md) | 生效 | 企业名称展示、报告检索与报告入口；报告无状态（不确认/驳回/归档） |
| [尽调五步依赖与单步核对](40-specs/enterprise-dd/五步依赖与单步核对.md) | 草稿 | 五步输入、依赖和人工核对约定 |

## 操作、路演与提交

| 文档或实物 | 状态 | 说明 |
|------------|------|------|
| [操作手册目录](50-runbooks/README.md) | 生效 | 当前 runbook 导航和 A6 验收边界 |
| [密钥管理](50-runbooks/密钥管理.md) | 生效 | 密文配置、主密钥和轮换 |
| [启动排障与赛时故障处理](50-runbooks/启动排障与赛时故障处理.md) | 生效 | Windows 启动和依赖故障处理 |
| [赛题04准备工具](50-runbooks/赛题04准备工具.md) | 生效 | 数据体检、prepare 与六列校验 |
| [赛题04现场非公开集操作卡](50-runbooks/赛题04现场非公开集操作卡.md) | 生效 | import → prepare → run → export → validate |
| [路演材料目录](60-pitch/README.md) | 生效 | 当前赛题04路演唯一入口 |
| [赛题04演示脚本](60-pitch/赛题04演示脚本.md) | 生效 | 8–10分钟真实运行、轨迹、证据、终态、追问与导出；最终 SHA 复跑后录制 |
| [答辩一页纸](60-pitch/答辩一页纸.md) | 生效 | 架构、真实基线和主动披露边界 |
| [提交材料说明](../submission/README.md) | 草稿 | 当前实物、缺项、A6 和封包步骤 |
| [赛题04技术方案](../submission/dd04/技术方案.md) | 草稿 | MD 与 PDF 已生成；最终 SHA 须复核重出 |
| [赛题04测试报告](../submission/dd04/测试报告.md) | 草稿 | MD 与 PDF 已生成；全文业务验收未通过，最终 SHA 须复核重出 |
| [尽调报告样例 E001](../submission/dd04/artifacts/尽调报告样例_E001.md) | 草稿 | M9 PDF/MD 已生成；最终 SHA 须复核重出 |
| [manifest 草稿](../submission/dd04/manifest.draft.yaml) | 草稿 | 生成稿、队名 XLSX 已存在；手机、邮箱和最终 SHA 待补 |
| [第三方组件与 License 声明](../submission/dd04/第三方声明/智算先锋队_赛题04_第三方组件与License声明.md) | 草稿 | 已生成；依赖冻结后须重生成并核对 |
| [`pack_dd04.py`](../submission/pack_dd04.py) | 生效 | 封包脚本已存在；最终冻结后重包 |
| [系统输出目录](../系统输出/README.md) | 生效 | 公开输出和 A4 衍生演练结果边界 |
| [评测模块说明](../ocft-backend/eval/README.md) | 生效 | 通用与赛题04专用评测命令 |

## 当前实测与交付边界

- [`dd04-business-acceptance` 业务验收](../测试数据/评测/2026-10-24/dd04-business-acceptance/业务验收报告.md)：申请 8 `succeeded` / 2 `needs_confirmation` / 0 `failed`；问询 9 `succeeded` / 1 `needs_confirmation`；评级 10/10；8 个可数值比较额度 8/8；506 项测试通过。**全文业务验收仍未通过**，不能用回归测试通过代替业务正确性。
- [A5 浏览器走查](../测试数据/评测/2026-10-25/a5-walkthrough/README.md)已完成，M4 四张脱敏截图已生成。
- [官方非公开测评报告（2026-10-25）](../测试数据/评测/2026-10-25/6e97cb3-官方非公开集/非公开测评报告.md)：LA011–LA030 共 20 笔，14 `succeeded` / 5 `needs_confirmation` / 1 `failed`，19/20 出具评级与额度；无答案，不计一致率。
- [`00e905f`](../测试数据/评测/2026-10-25/00e905f/公开评测报告.md)只作为归档输出，不代表当前代码，也不覆盖后续业务验收事实。
- 现有技术方案、测试报告、M9 样例及其他正式材料绑定旧 SHA；`f9594d9` / `d70ba07` 之后的变更尚未完成材料复核，最终冻结 SHA 上必须重验、按变化重出并重包。
- 当前仍缺：异机 A6、官方非公开输入与输出、最终 SHA 的重验重包及组委会回执；8:45 演示视频已放入 `submission/dd04/artifacts/`。队名统一为 **智算先锋队**。

## 报告体验优化

- [结论分层、业务用语与依据定位](40-specs/dd-report-readability/requirements.md)：[设计](40-specs/dd-report-readability/design.md) · [任务](40-specs/dd-report-readability/tasks.md) · [验证用例](40-specs/dd-report-readability/test-cases.md)。

## 历史归档

| 归档 | 状态 | 替代关系 |
|------|------|----------|
| [归档说明](90-archive/README.md) | 归档 | 归档内容统一入口和使用边界 |
| `90-archive/初版方案手册.md` | 归档 | 被当前 README、AGENTS、ADR 与 Spec 取代 |
| `90-archive/topic04-planning/` | 归档 | 赛题04前期分析，被 enterprise-dd、dd-multi-agent、dd-skills 与 ADR-0008 取代 |
| `90-archive/architecture/` | 归档 | 旧基座架构，被 README、Agent API 契约和 ADR 取代 |
| `90-archive/pitch/` | 归档 | 旧路演材料，被 `docs/60-pitch/` 取代 |
| `90-archive/reviews/` | 归档 | 固定旧 SHA 的评审、测试、整改和证据，不代表当前版本 |

归档说明保留在 `git archive` 中；其余 `docs/90-archive/**` 通过 `.gitattributes` 排除出评委系统包。归档内容只用于开发仓库追溯，不作为当前开发、验收或路演依据。
