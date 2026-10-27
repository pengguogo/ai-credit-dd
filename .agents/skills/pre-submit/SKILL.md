---
name: pre-submit
description: 比赛作品提交前的全量检查：一键启动、模型锁定、评测与非公开题导出、红线扫描、README 与密钥检查。赛时周六 20:00 干净环境验证和 10/25 正式提交前使用。
---

# 提交前检查

逐项执行，每项记录"通过 / 失败 + 原因"，最后输出清单。任一红线项失败，结论为"不可提交"。

## 1. 资格项

- [ ] 干净目录克隆仓库，按 README 执行一键启动（双击 `start.bat`，即 `start.ps1` 离线模式；改过依赖或前端时先跑 `pack-offline.ps1` 并提交 `vendor/`、`ocft-starter/dist/`），前后端都起来。
- [ ] `GET /api/health/ready`：`modelLock.model == "deepseek-v4.1-flash"`，database ok。
- [ ] 前端提一个真实问题，能看到答案、工具轨迹、证据。
- [ ] 无低代码平台依赖（检查 `requirements.txt`、`package.json`、代码中的外部域名）。

## 2. 红线

- [ ] 运行 `redline-scan` skill，无未处理命中。
- [ ] `git ls-files` 中无 `.env`、数据库文件；`git log -p` 近期提交无密码 / Key。
- [ ] 抽查 3 个 run：`GET /api/agent/runs/{id}` 有 evidence；确认一次结论后 `/audit` 有 `confirmation_created`。
- [ ] 合规样例（提示注入、违规承诺、标签探测）均被拦截且有审计。

## 3. 评测与提交物

- [ ] 运行 `run-eval` skill 跑公开题，记录正确率。
- [ ] 对非公开题批量运行，导出提交文件（格式以官方要求为准），检查题数一致、无空答案、失败题标明原因。
- [ ] 提交文件与本次代码版本（commit hash）对应，记录在提交说明中。

## 4. 文档

- [ ] README：启动步骤可照做；运行时 MCP / Skill 接入方式已写清（规则硬要求）；模型说明正确。
- [ ] `docs/INDEX.md` 无失效链接；开发流程时序图状态已更新。

## 5. 输出

清单 + 结论（可提交 / 不可提交）+ 阻塞项负责人。
