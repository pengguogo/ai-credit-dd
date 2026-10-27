# 尽调角色运行时 Skill 需求

状态：已实现    负责人：Agent 核心、场景与文档

## 变更
- 2026-10-25：新增只读“Agent Skill 技能中心”，集中展示主控编排内核与六个版本化业务 Skill 的角色、工具、输入输出契约、治理边界和依赖图。同步：design 前端方案、tasks 6–7、TC-10/11。
- 2026-10-24：需求 3 报告骨架现已演进至 `dd-report` 2.1.3（决策摘要 + `##` 五章 + `###` 小节；篇幅 ≤2500 字，并区分本笔申请额度和建议授信额度）。澄清 front matter：`roles` 为绑定键，`role` 为展示名。同步：design 方案概述、test-cases TC-7。
- 2026-10-24：合并 ADR-0008（主控 + 六角色多 Agent）。Skill 原来随主控的工具结果下发，现在改为拼进各角色调用模型时的 system 消息；`triggerTools` 改为 `roles`。同步：design 方案概述、TC-3/4/5/6。

## 背景
六个角色 Agent 调用模型时，输入是计算结果 JSON。角色提示词只写了职责和判断边界，数值换算、措辞和版式没有固定，同一输入多次运行时输出会漂移。题目说明的"Skill 管理"要求可复用的 Skill，并带触发条件和输入输出契约；"结构化、稳定输出"也是评分项。2026-10-24，用户要求给每个角色加 Skill，并要求尽调报告版式简洁、专业。

## 用户故事与验收标准
1. 作为评审，我希望每个角色都有版本化的 Skill，写明触发条件、输入契约和输出规则，以便核对 Agent 的读法和写法。
   - WHEN 后端启动 THEN 系统 SHALL 从 `scenarios/dd04/skills/` 为六个角色（business / finance / opinion / fraud / rating / report）各加载一个 Skill。每个 Skill 都包含 name、title、version、role（展示名）、roles（绑定 agents.yaml 角色键）、inputs、outputs 和正文规则。
   - IF Skill 文件缺字段、同一角色被两个 Skill 认领、写了未知角色，或有角色没有 Skill THEN 系统 SHALL 在启动时抛 `SkillError`，不能带着错误配置运行。
2. 作为角色 Agent，我希望调用模型时拿到本角色的规则，以便按统一口径成文。
   - WHEN 某角色调用模型 THEN system 消息 SHALL 包含本角色 Skill 全文，且不包含其他角色的 Skill。
   - WHEN run 结束 THEN `contextSnapshot.skillsApplied` SHALL 按角色顺序记录所用的 `name@version`。
3. 作为业务人员，我希望完整尽调报告版式固定、简洁、专业。
   - WHEN 完整尽调 THEN 报告 SHALL 按当前 `dd-report` Skill 骨架输出：`#` 报告标题、编号与决策摘要、五个 `##` 章节（企业概况 / 财务分析 / 风险提示 / 额度建议 / 风控条件）及骨架内 `###` 小节，最后含「测算建议，非授信审批」的说明行。只用前端渲染器支持的 Markdown（标题、列表、表格、粗体）；正文汉字控制在 Skill 规定上限内（当前 2500）。
   - WHEN 评级相同 THEN 结论用语 SHALL 一致：低风险写「建议准入」，低-中风险和中风险写「审慎准入」，高风险或有否决项写「暂不准入」。
4. 作为评审或业务人员，我希望集中查看主控与六个专业 Agent 的能力，以便理解 Agent–Skill 技术链路。
   - WHEN 登录用户打开 `/skills` THEN 系统 SHALL 展示主控编排内核与六个版本化 Skill 的 Agent 角色、name@version、工具绑定、输入输出、治理边界、配置来源及依赖图。
   - WHEN 用户搜索或切换技能分类 THEN 系统 SHALL 只展示匹配卡片；无匹配时展示空状态。
   - WHEN 顶栏导航显示 THEN “Agent 技能中心” SHALL 位于“系统管理”之前，且所有已登录用户均可访问。

## 不做什么
- 不增加模型调用次数，数字仍只来自 dd_calc。
- Skill 不含任何申请或企业的数据、结论或答案，也不引用外部汇总评级。
- 不改对外 API 响应结构，只新增 `contextSnapshot.skillsApplied` 和 `roles.<角色>.skill`。
