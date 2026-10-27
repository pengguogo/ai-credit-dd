# 合入前评审清单

逐项勾选；不适用的写 N/A。

## 红线（任一不过不合入）

- [ ] 没有写死某题答案、结论或"标准话术"（Prompt、工具、种子、前端）
- [ ] 运行时未读取评测标签 / `expected`
- [ ] 模型调用只经 `app/llm.py`
- [ ] 没有密码、Key、真实连接串
- [ ] 失败路径返回结构化错误，不是模板化假结论

## 工程

- [ ] 依赖方向正确（router 不直接访问 ORM / LLM）
- [ ] 新工具：已注册、参数 schema 完整、输出字段白名单、产出证据
- [ ] 新接口：`/contracts` 已先更新
- [ ] 写操作与审计在同一事务
- [ ] 新依赖固定版本，并登记到 [自研边界与依赖清单](../20-architecture/自研边界与依赖清单.md)
- [ ] 未接入扣子等低代码平台。编排框架只使用已采纳 ADR 允许的范围（当前 [ADR-0004](../20-architecture/adr/0004-用LangGraph封装有界工具循环.md)：LangGraph 只调度）；模型只经 `llm.py`，工具只经注册表，不使用框架 ChatModel，不启用 checkpointer

## 验证

- [ ] 后端可启动，`/api/health/ready` 结果符合预期
- [ ] 相关 pytest 通过；涉及前端时 `npm run lint` 与 `npm run build`（含 `tsc -b`）均通过
- [ ] 依赖或前端有变化时，已运行根目录 `pack-offline.ps1` 重建离线包，并核对 `vendor/` 与 `ocft-starter/dist/`
- [ ] 改动涉及答题链路时，跑过一次 eval
- [ ] 文档新增已登记 [docs/INDEX.md](../INDEX.md)
- [ ] [开发日志](../10-strategy/开发日志.md) 已追加本次记录（含提交号）
