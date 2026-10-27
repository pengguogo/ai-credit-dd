# ocft-starter · 前端

信贷审批 Agent 工作台。React 19 + TypeScript + Vite 8 + Tailwind CSS 4，组件层用 shadcn/ui（`base-nova`，源码在 `src/components/ui/`），动效用 Motion。选型见 [ADR-0001](../docs/20-architecture/adr/0001-后端语言与前端框架.md)。

## 启动

```bash
npm install
npm run dev        # http://localhost:5173，/api 代理到 http://127.0.0.1:8000
npm run lint       # oxlint
npm run build      # tsc -b 类型检查 + vite 构建
```

全栈一键启动见根目录 [README](../README.md)。

## 页面

- 顶栏分两层：上层 Logo / 系统信息 / 身份；下层导航分「工作区」与「尽调维度」。
- 工作台 `/`：左侧企业基础信息与审批表；中间对话；右侧轨迹 / 证据 / 审计。
- 数据列表 `/tables/<表名>`：如 `/tables/loan_application`；侧栏只显示中文名，表名只在 URL。
- 尽调五步 `/report/<slug>?enterpriseId=`：把主控调度拆成单角色页，选企业 →「分析本步」→ 结构化展示该步工具结果（不经模型；可展开原始 JSON）。切换步骤保留企业并自动重跑。见 [五步依赖与单步核对](../docs/40-specs/enterprise-dd/五步依赖与单步核对.md)。

演示路径：工作台点企业编号 → 提问 → 看轨迹 → 看证据；或顶栏进单步页抽检某一维。

## 目录

```text
src/
├── main.tsx / App.tsx          # 入口与布局
├── index.css                   # 品牌色 + shadcn 主题变量
├── lib/
│   ├── types.ts                # API 类型，与 contracts/agent-api.md 一一对应
│   ├── api.ts                  # 请求封装 + SSE 读流（fetch，带 X-Actor-Id，Last-Event-ID 重连）
│   └── format.ts               # 状态文案、工具 / 拦截类别中文名
├── hooks/
│   ├── use-agent-session.ts    # 提问 → 异步 run → 事件 → 详情 / 证据 / 审计 → 确认
│   └── use-backend.ts          # 就绪检查、运行统计
├── components/
│   ├── catalog/data-catalog.tsx # 业务表与企业编号快速填入
│   ├── chat/chat-panel.tsx     # 对话与各状态的诚实展示
│   ├── run/                    # 轨迹、证据、审计与确认
│   ├── markdown.tsx            # 模型答案的安全 Markdown 渲染（不用 innerHTML）
│   └── ui/                     # shadcn/ui 组件源码
└── data/scenario.ts            # 场景说明与提问模板（不含任何答案）
```

## 约定

- 业务数据只来自后端 API（[契约](../contracts/agent-api.md)），前端不生成、不伪造答案。
- 澄清、证据不足、合规拦截、执行失败、网络错误都有独立展示，显示真实错误码。
- 浏览器原生 `EventSource` 不能带 `X-Actor-Id`，事件流用 `fetch` 读取。
- 规范总入口：[AGENTS.md](../AGENTS.md)。
