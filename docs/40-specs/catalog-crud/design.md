# 数据列表维护 设计

状态：已确认    对应需求：已实现

## 方案概述
1. 前端：上传从 `DataCatalog` 移除；`DataListPage` 按当前 `kind` 挂单文件导入弹窗；可写表提供记录表单（新增/编辑）与删除确认；`schema_relationships` 改为节点流程图（只读）。
2. 后端：目录行附带内部 `id`；新增 `POST/PATCH/DELETE /api/agent/catalog/{scenarioId}/{kind}/records[/{id}]`；`schema_relationships` 拒绝写入。审计写入既有 `csv_import_audits`（status=`catalog_*`），无新迁移。
3. CSV 导入契约不变，仅前端约束文件名。

## 涉及模块与负责人
数据层：`catalog.py` 行带 id、`catalog_write.py` 写服务；路由/schemas。前端：`data-list-page`、导入弹窗、记录表单、关系图。契约：`contracts/agent-api.md`。

## 接口 / 契约变更
见 [agent-api.md](../../../contracts/agent-api.md) 目录写操作与目录行 `id` 说明。

## 数据变更
无表结构迁移。

## 红线影响
R1/R2：无模型/低代码；R3：审计摘要；R4/R5：白名单字段，风险汇总仍不把外部评级当结论；R7：错误脱敏；R8：无新依赖；R9：无凭据。

## 取舍
复用导入审计表避免新迁移；表单字段对齐各表 CSV/模型列；关系图用 SVG/HTML 自绘，不引入图编辑库。
