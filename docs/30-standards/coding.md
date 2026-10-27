# 编码规范

> AGENTS.md 只放摘要，细则在这里。原则：与仓库已采用的写法保持一致，优先于个人习惯。

## 1. 后端分层（Python / FastAPI）

```text
routers/   HTTP 校验与序列化 —— 不直接访问 ORM、不调用 LLM
services/  用例编排与事务边界 —— 一个用例一次 commit
agent/     graph.py 用 LangGraph 调度 model/tools；engine.py 判定终态与上限；场景注册、上下文策略
tools/     工具：@register_tool 声明 + 纯逻辑 handler
compliance/ 输入输出合规（纯函数）
domain/    状态常量、ToolResult、EvidenceRecord、错误类型 —— 不 import FastAPI/SQLAlchemy/openai
models.py  ORM；llm.py 模型唯一入口；config.py 配置唯一入口
```

依赖方向只能向下：`routers → services → agent/tools/compliance → domain`。反向 import 视为违规。

## 2. Python 约定

- Python 3.11+，全部函数签名带类型注解。
- 配置只从 `app.config.settings` 读，禁止在业务代码里 `os.environ`。
- 错误要类型化：工具内抛 `ToolError(code, message)`，模型错误为 `LLMError`；禁止 `except Exception: pass`。
- 不静默降级：失败返回结构化错误（`errorCode` + `message`），由上层如实展示。
- 金额、比率涉及结论时用 `Decimal` 或受控计算，并把公式写进证据。
- 关键设计用 `@why` 注释说明原因，不写"做了什么"的废话注释。
- 新依赖写入 `requirements.txt`，使用固定版本（`==`）。

## 3. 工具（Tool）约定

- 声明：`@register_tool(name, description, parameters)`，参数 JSON Schema 属性名用 camelCase。
- 返回：`(ToolResult, list[EvidenceRecord], parsed_args)`，见 `app/tools/credit.py`。
- 只读、参数化；输出字段走显式白名单，防止新增列（含评测标签）泄漏给 LLM。
- 每条有效数据都产出 `EvidenceRecord`，`source_ref` 足以重现查询。
- 场景只能使用 `Scenario.allowed_tools` 白名单内的工具。

## 4. 命名

| 位置 | 风格 | 示例 |
|------|------|------|
| DB 表/列、Python 变量 | snake_case | `answer_version` |
| API JSON、TS/JS、工具参数 | camelCase | `answerVersion` |
| 工具名、场景 ID | snake_case | `run_credit_rules`、`credit_review` |
| 错误码 | snake_case | `run_timeout` |
| ID 前缀 | `run_`、`ev_` + 12 位 hex | `run_ab12cd34ef56` |

时间：DB 存 naive UTC，API 输出 ISO 8601 带 `Z`。

## 5. 前端（React / Vite）

- TypeScript strict；API 类型在 `src/lib/types.ts`，与 `/contracts` 一一对应，所有请求经 `src/lib/api.ts`。
- 组件放 `src/components/`，函数组件 + Hooks，文件名 kebab-case（与 shadcn/ui 一致）；`src/components/ui/` 是 shadcn 组件源码，可改但保持原有导出。
- 模型输出用 `components/markdown.tsx` 渲染，只生成 React 元素，禁止 `dangerouslySetInnerHTML`。
- 业务数据一律来自后端 API；`src/data/` 只允许放场景说明类静态内容，不得冒充 Agent 输出。
- 加载、失败、拦截、证据不足四种状态都要有明确 UI，不假装成功。
- 可访问性：交互元素可键盘操作，图片有 `alt`，颜色不是唯一信息载体。
- 提交前 `npm run lint` 无错误，`npm run build`（含 `tsc -b` 类型检查）通过。

## 6. 测试

- 后端测试放 `ocft-backend/tests/`，使用 pytest；工具 handler、合规规则、规则引擎必须有单测。
- 测试数据放测试内 fixture，不复用评测集 `expected`。
- 评测（`eval/`）与单测分开：单测保证代码正确，评测衡量答题效果。
