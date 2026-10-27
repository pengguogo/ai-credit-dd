# 尽调角色运行时 Skill 设计用例

状态：已确认

| 编号 | 追溯 | 类型 | 前置 | 操作 | 期望 | 验证 |
|------|------|------|------|------|------|------|
| TC-1 | 需求 1 | 正常 | 场景 enterprise_dd | 读取 `DD_ROLE_SKILLS` | 六个角色各有一个 Skill，名称、标题与设计一致；版本号是语义化版本；正文含触发条件、输入契约、禁止 | 单测 |
| TC-2 | 需求 1 | 异常 | front matter 缺字段或整块缺失 | `parse_skill` | 抛 `SkillError` | 单测 |
| TC-3 | 需求 1 | 异常 | 两个 Skill 认领同一角色 | `load_skills` | 抛 `SkillError` | 单测 |
| TC-4 | 需求 1 | 异常 | Skill 写了未知角色 | `load_skills` | 抛 `SkillError` | 单测 |
| TC-5 | 需求 2 | 正常 | 假模型，主控调用 run_dd_agents followup 只要 finance | 发起 run | 财报角色的 system 消息含财报解析 Skill，不含报告 Skill；`skillsApplied` 只有财报解析 Skill 一项 | 单测 |
| TC-6 | 需求 1 | 正常 | 仓库内 Skill 目录 | `load_skills(SKILL_DIR, ROLE_ORDER)` | 六个角色全部覆盖 | 单测 |
| TC-7 | 需求 3 | 正常 | dd-report Skill（当前 2.1.3） | 检查版式规则 | 含 `#` 标题与决策摘要；五个 `##` 章节按顺序；骨架含 `###` 小节与免责条款；禁用嵌套列表和引用块；篇幅上限与 Skill 一致；不披露本次申请额 | 单测 |
| TC-8 | 需求 1 | 红线 | 全部 Skill | 扫描下发文本 | 不出现申请 / 企业编号、`externalRiskLevel`、`expected`、答案文件名 | 单测 |
| TC-9 | 需求 3 | 正常 | 真实模型，多笔申请 | 完整尽调 | 报告符合骨架并通过事实校验，`skillsApplied` 含六个 Skill | 手工 |
| TC-10 | 需求 4 | 正常 | 用户已登录 | 打开 `/skills` | 展示主控编排内核与六个专业 Agent；六个 Skill 的 name@version、工具、输入输出和来源与场景配置一致 | 手工 |
| TC-11 | 需求 4 | 边界 | 技能中心已打开 | 搜索工具名并切换技能分类 | 只展示匹配项；无匹配时显示空状态，系统管理菜单仍位于其后 | 手工 |