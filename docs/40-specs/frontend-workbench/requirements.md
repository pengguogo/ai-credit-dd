# 前端工作台 需求

状态：已确认    负责模块：前端（鉴权见 auth-admin；多 Agent 泳道见 dd-multi-agent）

## 变更
- 2026-10-24：删除「不做登录 / X-Actor-Id 输入框」；补充登录门控、RBAC 导航、多 Agent 协作视图、尽调五步、回答 PDF/Word。同步：design、tasks、INDEX；交叉 [auth-admin](../auth-admin/requirements.md)、[enterprise-dd](../enterprise-dd/requirements.md) 需求 2、[dd-multi-agent](../dd-multi-agent/requirements.md) 需求 2。

## 背景
对应待办 1-8，影响主观分（交互体验、演示完整度）和红线 3（前端不得写死结论）。工作台已接真实 Agent、确认与审计；演示需要登录与角色权限裁切菜单。

## 用户故事与验收标准
1. 作为评委，我希望 5 步以内看完「提问 → 工具 → 证据 → 结论 → 确认」。
   - 点示例问题后，右侧轨迹 SHALL 随 SSE 事件逐行出现
   - 完整尽调时 SHALL 展示多 Agent 协作区块（主控计划、五个分析角色并行解读、报告汇总、事实校验），状态只来自后端事件
   - 证据页 SHALL 展示来源（表 / 主键 / 条件）、哈希、数据版本，可展开快照
   - `succeeded` / `needs_confirmation` SHALL 可确认或驳回（具备 `confirm` 权限时），审计时间线即时更新
2. 作为业务人员，我希望异常情况说清楚。
   - 澄清、证据不足、合规拦截、执行失败、网络错误 SHALL 各有独立展示，带真实错误码
3. 作为评委，我希望看到业务价值数据。
   - 看板 SHALL 只来自 `/api/agent/stats`，无执行记录时如实显示为空
4. 作为演示用户，我希望按角色看到可用功能。
   - 未登录 SHALL 进入登录页；登录后顶栏按权限显示工作台 / 数据列表 / 尽调五步 / 系统管理
   - 成功回复且有正文时 SHALL 提供「导出 PDF」「导出 Word」（口径见 enterprise-dd 需求 2）

## 不做什么
- 不在前端写死业务结论或评测答案
- 不接入评测正确率（离线报告，不在运行时读取评测结果）
- 不做暗色主题；移动端以保证可用为主，不单独做完整适配
- 登录、角色与 Admin API 细节以 [auth-admin](../auth-admin/requirements.md) 为准；评测脚本仍可用 `X-Actor-Id` 旁路
