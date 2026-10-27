# 尽调环节运行时 Skill 任务

状态：已确认

- [x] 1. 六个 Skill 文件（场景与文档，关联需求 1、3）
  - 完成标准：`scenarios/dd04/skills/` 下 6 个 md，front matter 字段齐全，不含任何案例数据
- [x] 2. 加载、场景装配与下发（Agent 核心，关联需求 1、2）
  - 完成标准：`skills.py` 校验通过；各角色调用模型时 system 消息带本角色 Skill（合并 ADR-0008 后由工具结果下发改为角色下发）；`contextSnapshot.skillsApplied` 有记录
- [x] 3. 契约与导出（Agent 核心、前端，关联需求 2、3）
  - 完成标准：`contracts/agent-api.md` 已更新；导出不重复报告标题
- [x] 4. 设计用例与单测（关联需求 1–3）
  - 完成标准：`tests/test_dd_skills.py` 覆盖 test-cases.md 全部用例并通过
- [x] 5. 验证（关联需求 1–3）
  - 完成标准：pytest 全量通过；前端 lint / build 通过；真实模型多 Agent 完整尽调多笔申请均按骨架输出并通过事实校验

- [x] 6. Agent Skill 技能中心（前端，关联需求 4）
  - 完成标准：`/skills` 展示主控编排内核、六个版本化 Skill、工具绑定、契约、治理边界和依赖图；菜单位于系统管理前，支持搜索与分类筛选
- [x] 7. 技能中心与角色变更验证（前端 / 数据层，关联需求 1、2、4）
  - 完成标准：后端相关 pytest、前端 lint / build 与本地页面烟测通过