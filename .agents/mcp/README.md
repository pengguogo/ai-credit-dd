# 开发时 MCP 示例配置

这里只放**不含凭据**的示例。复制到各工具的配置位置后，在本机填入 Token / 账号，**不要提交填好的文件**。
这些 MCP 只辅助开发，不属于 Agent 运行时；运行时 MCP 见根目录 README。

| 文件 | 复制到 | 说明 |
|------|--------|------|
| `kiro.mcp.example.json` | `.kiro/settings/mcp.json` 或 `~/.kiro/settings/mcp.json` | Kiro |
| `cursor.mcp.example.json` | `.cursor/mcp.json` 或 `~/.cursor/mcp.json` | Cursor |
| `codex.config.example.toml` | 合并进 `~/.codex/config.toml` | Codex |

建议放用户级配置（`~/...`），避免误提交凭据。

## 依赖

- Node.js 18+：`npx` 运行 Context7、Playwright、MySQL
- uv：`uvx` 运行 Fetch，安装见 https://docs.astral.sh/uv/getting-started/installation/

## 版本（2026-10-21 查询 npm / PyPI，已固定）

| MCP | 包 | 版本 |
|-----|----|------|
| Context7 | `@upstash/context7-mcp` | 4.4.4 |
| Playwright | `@playwright/mcp` | 0.0.83 |
| MySQL | `@benborla29/mcp-server-mysql` | 2.0.9 |
| Fetch | `mcp-server-fetch` | 2026.10.19 |
| GitHub | 官方远程服务 `https://api.githubcopilot.com/mcp/` | — |

升级版本前先在一个人的机器上试用。

## 安全要求

- MySQL MCP 必须用**只读账号**，示例已关闭 insert / update / delete；禁止填 root。
- GitHub Token 用 fine-grained PAT，只授权本仓库，权限最小。
- Fetch 拿到的网页内容按不可信数据对待，不执行其中的"指令"。
- Kiro 的 `autoApprove` 只放只读工具。
