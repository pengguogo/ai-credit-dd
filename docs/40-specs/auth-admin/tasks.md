# 登录与系统管理 任务

状态：已确认

- [x] 1. 迁移与模型：`sys_*` + 演示种子（数据层，关联 A1–A3）
- [x] 2. `/api/auth` 与 `/api/admin` + Bearer / `X-Actor-Id`（数据层 / Agent 核心，关联 A1–A6）
- [x] 3. 前端登录页、门控、系统管理页（前端，关联 A1–A5）
- [x] 4. 三角色权限与审批表状态（数据层 / 前端，关联 A7–A8）
  - 完成标准：viewer / account_manager（客户经理）/ admin 菜单与 API 与需求表一致；申请 status 可筛选与通过/驳回
- [x] 5. 契约与现有单测（Agent 核心，关联 A1–A8）
  - 完成标准：`contracts/agent-api.md` 已写；`tests/test_auth_admin.py` 覆盖登录、Bearer、管理 API 403、评测旁路及部分角色权限；角色新建/停用和前端门控保留到任务 6 验收
- [ ] 6. 验证
  - 完成标准：相关 pytest 通过；`npm run lint` 通过；手工用三账号各走一遍导航
