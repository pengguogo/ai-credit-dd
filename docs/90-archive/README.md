# 历史归档

> 本目录只用于追溯被替代的方案、旧提交评审和测试快照，不再维护，不得作为当前开发、验收、路演或提交依据。当前事实入口见 [文档索引](../INDEX.md)、根目录 [README](../../README.md)、[Agent API 契约](../../contracts/agent-api.md)和 [ADR](../20-architecture/adr/README.md)。
> `.gitattributes` 保留本说明文件，但从评委系统包中排除其余归档内容；具体历史文件仅在开发仓库和 Git 历史中可用。

| 目录 / 文件 | 内容 | 当前替代 |
|-------------|------|----------|
| `初版方案手册.md` | 抽签前初版设想，包含已废弃的静态样例、多模型和 fallback 假设 | README、AGENTS、当前 Spec |
| `topic04-planning/` | 赛题04前期分析、候选需求、候选设计和固定案例预览 | `docs/40-specs/enterprise-dd/`、`dd-multi-agent/`、`dd-skills/`、ADR-0008 |
| `architecture/` | 旧单主 Agent 基座架构分析 | README 架构、Agent API 契约、ADR-0004/0008 |
| `pitch/` | 旧9页大纲、6页/8分钟详细方案及当时的问答和故障预案 | `docs/60-pitch/` 当前8–10分钟真实链路材料 |
| `reviews/` | 固定旧 SHA 的 AI 评审、全量测试、整改、5242c83 JUnit 和其他证据 | 当前待办、最终 SHA 的重新验证 |

归档文档中的路径、测试数量、时限、功能状态和结论只对其声明的时间与 SHA 有效。归档内相对链接已按当前位置修复；历史本机 `file://` / `computer://` 来源和从未入库的材料仅保留为代码路径说明，不伪造可点击目标。

除本说明外的 `docs/90-archive/**` 通过 `.gitattributes` 的 `export-ignore` 排除出评委系统包，但仍保留在 Git 历史和开发仓库中。
