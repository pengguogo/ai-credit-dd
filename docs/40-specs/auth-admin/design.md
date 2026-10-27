# 登录与系统管理 设计

状态：已确认    对应需求：已确认

## 方案概述
- 表：`sys_roles` / `sys_users` / `sys_sessions`（迁移 10）；演示角色权限启动时同步，旧 `reviewer` 角色编码在保留用户关联的前提下迁移为 `account_manager`。
- API：`/api/auth/*` 登录登出；`/api/admin/*` 角色与用户 CRUD（管理员）。密码哈希存库，Bearer 会话。
- Agent：`require_actor` 优先读 Bearer；无 Bearer 时兼容 `X-Actor-Id`（评测旁路，不套演示 RBAC）。写接口与确认、审批、目录写按权限码校验。
- 前端：`LoginPage` / `BootSplash` / `AdminPage`；`App.tsx` 路由门控；`permissions` 裁切导航与按钮。
- 贷款申请审核：`loan_application.status` 最终为四态 `pending`（待处理）/ `pending_review`（待审核）/ `approved`（审核通过）/ `rejected`（审核不通过）。迁移 11 引入状态字段，迁移 14 统一旧值；生成尽调报告后 `pending` 自动推进到 `pending_review`，客户经理人工审核，与 Agent 结论确认分离。

## 涉及模块与负责人
数据层（模型、迁移、种子）；Agent 核心统筹（契约、deps）；前端（登录与管理页）。

## 接口 / 契约变更
[contracts/agent-api.md](../../../contracts/agent-api.md) 登录与管理章节。

## 数据变更
迁移 10：系统角色/用户/会话。迁移 11：申请 `status`；迁移 14：旧申请状态统一为四态。表结构只增不删。启动种子同步将旧 `reviewer` 角色原位改码为 `account_manager`，并将旧用户名 `reviewer_demo` 原位改为 `account_manager`；会话与运行记录的 owner 字段同步改名以保留访问，追加式审计、确认及资产事件不改写。若新旧角色或账号已并存，则先迁移关联再移除旧种子记录，不删除历史业务数据。

## 红线影响
- R1–R5、R8：无影响。
- R6：确认接口仍审计；权限不足 403，不绕过确认留痕。
- R7：登录失败如实 401；不在前端写死业务结论。
- R9：演示口令仅种子；真实密钥仍只放 `.env`。

## 取舍
选择演示级账号体系 + 权限码列表，放弃 SSO 与完整 RBAC 引擎。评测继续 `X-Actor-Id` 以免改全部 pytest。
