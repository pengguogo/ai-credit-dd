# 尽调角色运行时 Skill 设计

状态：已确认    对应需求：已实现

## 方案概述
- **Skill 文件**：放在 `ocft-backend/scenarios/dd04/skills/*.md`。YAML front matter 里的 `roles` 填 agents.yaml 的角色键；Markdown 正文包含触发条件、输入契约、数值换算与解读规则、输出格式、禁止。
- **加载**：`app/agent/skills.py` 的 `load_skills(dir, known_roles)` 校验四点：字段齐全、名称唯一、每个角色只被一个 Skill 认领、角色必须已知。结果缓存在进程内，改 Skill 要重启后端（开发时 uvicorn 加 `--reload-include "*.md"`）。`scenarios.py` 启动时调用 `dd_roles.role_skills()`，六个角色缺任何一个就直接失败。
- **下发**：`dd_roles.analyze` 和 `write_report` 构造 system 消息时，在角色提示词（`_role_common.md` + `prompts/<角色>.md`）后面拼上本角色的 Skill。所用版本按以下路径记录：
  1. `RoleResult.skill` 记下 `name@version`；
  2. 经 `run_dd_agents` 结果的 `roles.<角色>.skill` 返回；
  3. 汇总到 `run_ctx["skills_applied"]`，再到 `outcome.skills_applied`，最后写进 `contextSnapshot.skillsApplied`。
- **分工**：`prompts/*.md` 写角色职责和判断边界；Skill 写字段口径、数值换算、措辞和输出版式。报告提示词的 `#` / `##` / `###` 与 `dd-report` 骨架一致；免责条款写在骨架内（普通段落，避免引用块）。报告角色 `max_tokens` / `timeout_seconds` 见 `agents.yaml`。
- **前端**：`markdown.tsx` 区分三级标题与表格样式；PDF / Word 导出跳过与文档标题同名的标题，避免重复。`/skills` 使用 `DD_ROLES`、`REPORT_DIMS` 与只读场景说明组合主控 + 六角色目录，展示版本、工具、输入输出、治理边界、依赖编排和搜索筛选；不读取评测数据，也不暴露完整 Prompt。

## 涉及模块与负责人
- 场景与文档：场景包 `scenarios/dd04/skills/`、`prompts/report.md`
- Agent 核心：`app/agent/skills.py`、`dd_roles.py`、`dd_graph.py`、`scenarios.py`、`engine.py`，以及 `run_service.py` 一行
- 前端：`ocft-starter/src/lib/answer-export.ts`

## 接口 / 契约变更
[contracts/agent-api.md](../../../contracts/agent-api.md) 新增 `contextSnapshot.skillsApplied` 和 `run_dd_agents` 结果里的 `roles.<角色>.skill`。

## 数据变更
无表结构变化。

## 红线影响
- R1：无影响。仍只经 `app/llm.py` 调用模型，调用次数不增加。
- R2：无影响。Skill 是本仓库内的文件。
- R3：无影响。数字仍来自 dd_calc，报告仍经事实校验。
- R4：Skill 不含数据和答案，单测扫描确保不出现申请或企业编号。
- R5：不读评测标签；Skill 不引用外部汇总评级字段，单测扫描。
- R6：无影响。高风险仍需确认，报告 Skill 要求写"需业务人员确认"。
- R7：Skill 随角色消息一起经过代号化和 PII 掩码；禁止编造法规条文。
- R8、R9：无影响。

## 取舍
- **拼进角色消息，不随工具结果下发**：多 Agent 之后每个角色单独调模型，规则应跟着该角色走。主控写追问答案时，沿用角色已按 Skill 写好的解读。
- **代价**：每个角色的 prompt 增加约 0.6–1.2k tokens。
- **不写编号区间**：Skill 里不出现规则编号区间，因为事实校验会把本次未评估的编号判为错误。
