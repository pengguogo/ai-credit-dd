# OCFT 金融科技 Agent · 企业智能信贷尽调

![比赛第二名 · 攻坚先锋奖](https://img.shields.io/badge/2026金融壹账通AI黑客马拉松-第二名%20·%20攻坚先锋奖-gold)

> 🏆 **2026 金融壹账通 AI 黑客马拉松第二名 · 攻坚先锋奖**（智算先锋队）。名次由项目作者确认，奖项名称依据获奖照片。

> 📦 **开源说明**：本仓库是比赛私有仓库的公开版，以 MIT 协议开源（见 [LICENSE](LICENSE)）。比赛期间入库的 `.env`、`master.key` 和云数据库地址已移除，相关凭据已失效。自建时复制 `ocft-backend/.env.example` 为 `.env`，填入自己的模型 Key；数据库默认用本地 SQLite。下文中“随包提供凭据、解压即可用”的说明只适用于比赛评审包。

2026 金融科技 Agent 黑客松参赛作品，参赛团队：**智算先锋队**。当前主场景为赛题 04 企业智能信贷尽调（`enterprise_dd`）：从企业业务数据出发，完成工商、财务、舆情、反欺诈、评级授信分析，生成可追溯的尽调报告，并支持自然语言追问与批量结果导出。

技术栈：**Python / FastAPI / LangGraph / MySQL / Redis + React / TypeScript / Vite**。底座同时保留信贷审批、反欺诈、智能理赔、文档抽取与智能客服场景；赛题 04 为默认场景。

- 运行时模型锁定 `deepseek-v4.1-flash`，配置成其他模型启动即失败
- 工具循环与尽调多角色编排由 LangGraph 调度，预算与终态在本仓库判定，没有使用低代码平台
- 保存结论对应的数据快照（evidence）、工具轨迹、业务确认与合规记录；事实解释正确性仍须逐项核验
- HTTP、SSE、批量评测共用同一个 `run()` 入口，没有演示专用路径

> 文档核对日期：2026-10-25，源码基线 `59ae9e8`。功能已实现不等于最终验收通过；下文历史运行结果均注明证据版本。本次 README 更新未重跑模型、全量测试或 Windows 验收。

## 阅读入口

| 目标 | 入口 |
|------|------|
| 评委机启动 | [快速开始](#快速开始)、[启动排障](docs/50-runbooks/启动排障与赛时故障处理.md) |
| 了解功能与架构 | [功能总览](#功能总览)、[架构](#架构)、[接口契约](contracts/agent-api.md) |
| 导入数据、批量评测 | [数据导入](#赛题-04-数据导入10-张-csv)、[评测](#评测)、[现场操作卡](docs/50-runbooks/赛题04现场非公开集操作卡.md) |
| 查看结果与提交材料 | [验证与交付状态](#验证与交付状态)、[系统输出](系统输出/README.md)、[提交材料](submission/README.md) |
| 参与开发 | [开发](#开发)、[开发规范](#开发规范)、[文档索引](docs/INDEX.md) |

## 功能总览

| 功能 | 当前实现与边界 |
|------|----------------|
| 工商核验 | 根据已导入资料核对经营状态、股权、实控人、关联企业与担保关系；不等于外部工商平台实时核验 |
| 财报解析 | 对结构化年度科目计算指标、增长率与异常；当前不支持上传 PDF / 图片后自动 OCR 解析 |
| 舆情扫描 | 对已导入舆情、涉诉事件分类与评分；不声明具备实时全网采集能力 |
| 反欺诈检测 | 按可配置规则识别异常，保留命中事实与依据；规则命中不等于认定欺诈 |
| 评级与额度 | 按评分卡、额度政策确定性测算，再由模型解读；阈值经公开集校准，不代表银行生产政策 |
| 报告生成 | 六角色协作生成报告，支持企业口径与本笔贷款口径、报告预览及 PDF / Word 导出；贷款口径区分申请额与建议额度 |
| 自然语言问询 | 通过同一模型与工具入口查询企业事实、解释报告，记录执行轨迹与证据 |
| 工作台与管理 | 登录、角色权限、企业业务数据维护、增量 CSV 导入、报告列表及运行时 Skill 展示 |

## 验证与交付状态

| 范围 | 已有证据 | 边界 |
|------|----------|------|
| 公开集复验 | [`c7dbd23` 独立评审](测试数据/评测/2026-10-25/AI评委逐条评分-origin-main-20261025.md)：10 申请为 8 成功 / 2 待确认；10 问询为 9 成功 / 1 待确认；评级 10/10，8 笔数值额度区间一致 | 历史版本结果；拒贷方向兼容另计，不能推出全文要点全部正确或当前版本通过 |
| 官方非公开集 | [`e87748b` 对应批次](测试数据/评测/2026-10-25/6e97cb3-官方非公开集/非公开测评报告.md)：LA011–LA030 共 20 笔，14 成功 / 5 待确认 / 1 失败；19 笔生成评级与额度 | 只有输入、没有标准答案，不计算业务一致率；LA024 事实校验失败如实保留 |
| 页面与媒体 | A5 浏览器走查、4 张脱敏截图、演示视频均有归档 | 不同材料绑定不同版本；最终版本需核对差异与演示一致性 |
| 正式材料 | 技术方案、测试报告、报告样例 PDF / MD、团队元信息和第三方声明已存在 | 联系方式已补；最终 SHA、材料版本一致性与最终封包仍需复核 |
| 交付验收 | 内置 Python、离线 wheels、前端 dist 与 Windows 启动脚本已提供 | 异机干净 Windows 验收、最终包解压自检及组委会回执尚未闭环 |

正式命名的[公开结果](系统输出/智算先锋队_赛题04_公开测评集结果.csv)目前由旧主批与后续补测组成；[非公开结果](系统输出/智算先锋队_赛题04_非公开测评集结果.csv)已是官方 20 笔结果，不能再称为衍生演练占位。两者均有同名 `-status.csv` 记录终态与 runId。最终冻结版本应按代码差异补齐必要复验、更新材料并重新封包。

历史评审曾发现证据发布、SQL 字段隔离、敏感实体脱敏等防线缺口；评审报告与整改设计不等于修复验收。**当前不宣称全文业务验收、全部红线防线或正式提交已通过。** 材料实物与版本差异可结合[提交材料说明](submission/README.md)与[系统输出说明](系统输出/README.md)核对；其中沿用旧状态的描述，以实际文件和对应批次证据为准。

## 快速开始

赛题 04 的数据体检、评测输入准备与官方结果格式校验见 [准备工具手册](docs/50-runbooks/赛题04准备工具.md)；提交材料进度见 [交付清单](docs/10-strategy/赛题04交付清单.md)。

正式交付与一键启动面向 Windows 10 / 11（x64）；仓库不提供 macOS / Linux / Docker 一键交付脚本。

### 评委 / 评测机：克隆后一键启动（不联网安装任何依赖）

克隆或解压后，双击根目录的 `start.bat`，或执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Offline
```

浏览器访问 http://127.0.0.1:8000 。首次启动需解压内置 Python、创建虚拟环境并安装本地依赖，实际耗时取决于机器；后续启动复用已有环境。评委机**不需要预装 Python 或 Node.js**。脚本优先复用项目内兼容的 `.venv`；没有时使用内置 Python，不修改系统 Python。

**“离线”指安装依赖不访问网络。** 完整尽调仍须连接远程模型接口、MySQL 与 Redis；完全断网时不能完成真实模型推理。验收需分别记录无外网安装启动结果，以及获准网络下的业务运行结果。

工作台、登录、系统管理、数据列表和尽调页面支持直接访问与刷新，例如 `/report/business?enterpriseId=E001`。后端仅将这些已知前端路由的 GET/HEAD 请求回退到页面入口；未知 API、未知页面和缺失资源仍返回 404。报告预览使用独立页面 `/report-preview.html?runId=<运行编号>`，读取本次落库结果，不重新答题。

### 依赖与离线内置说明（《通用提交材料说明》1.1(1)）

全部运行依赖随包提供，解压后在无外网环境下完成安装与启动；启动脚本不执行任何联网的 `pip install` / `npm install`。

| 依赖 | 版本 | 包内位置 | 离线安装方式 |
|------|------|----------|--------------|
| Python 运行时 | 3.14.9（python.org 官方 Windows x64 构建，NuGet 包） | `vendor/python/python-3.14.9-win-amd64.zip` | `start.ps1` 首次运行解压到 `vendor/python/runtime/`，再用它创建 `ocft-backend/.venv`；不读取、不依赖系统 Python |
| 后端 Python 库（15 个直接依赖 + 传递依赖，共 60 个 wheel） | 锁定在 `ocft-backend/requirements.txt` | `vendor/wheels/win_amd64-py3.14/`（另备 py3.11 / 3.12 / 3.13 三套，供开发机已有虚拟环境复用） | `pip install --no-index --find-links vendor/wheels/win_amd64-py3.14 -r ocft-backend/requirements.txt` |
| 前端页面 | 构建自 `ocft-starter/package.json`（锁定在 `package-lock.json`） | `ocft-starter/dist/` | 无需安装，后端在 :8000 直接提供，**运行时不需要 Node.js** |
| 模型权重、字体、词典 | — | — | 不需要：模型为远程 API；页面不加载外部字体或 CDN；合规词库在 `ocft-backend/app/compliance/lexicon/` 内 |
| 配置与凭据 | — | `ocft-backend/.env`、`config.yaml`（`enc:` 密文）、`master.key` | 比赛期间随私有仓库提供，无需手工填写；赛后删除并轮换 |

手工离线安装（不用一键脚本时，在仓库根目录执行）：

```powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory("$PWD\vendor\python\python-3.14.9-win-amd64.zip", "$PWD\vendor\python\runtime")
vendor\python\runtime\tools\python.exe -m venv ocft-backend\.venv
ocft-backend\.venv\Scripts\python.exe -m pip install --no-index --find-links vendor\wheels\win_amd64-py3.14 -r ocft-backend\requirements.txt
cd ocft-backend; .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

运行时需要外网访问的只有两项外部服务，都不是依赖下载：模型接口（`deepseek-v4.1-flash`）和阿里云 MySQL / Redis（需放行评测机出口 IP）。

### 凭据说明

- 包内凭据：`ocft-backend/.env` 与 `config.yaml` 中的模型 Key、数据库连接串都是 `enc:` 密文，由同包的 `ocft-backend/master.key` 解密，解压即可用。仅供本次评审，比赛结束后删除并轮换全部凭据。
- 改用自己的模型 Key：在 `ocft-backend` 目录执行 `.venv\Scripts\python.exe -m app.secret_box encrypt`（按提示粘贴明文，不回显），把输出的 `enc:...` 填到 `.env` 的 `LLM_API_KEY`，重启即可；也可以直接填明文。`LLM_MODEL` 留空，运行时锁定 `deepseek-v4.1-flash`。
- 自检：启动后访问 http://127.0.0.1:8000/api/health/ready 。配置、MySQL 或 Redis 不可用时返回 503；LLM 从未真实调用时可能以 `unknown` 随 200 返回，因此该响应不证明模型网络或 Key 可用。正式运行前应另跑一次无敏感数据的真实 smoke run；模型调用失败会返回结构化错误，不生成假结论。详见 [密钥管理](docs/50-runbooks/密钥管理.md)。

### 赛题 04 数据导入（10 张 CSV）

官方数据为 10 张 CSV：9 张业务表（`enterprise_basic`、`enterprise_finance`、`enterprise_shareholder`、`enterprise_lawsuit`、`enterprise_public_opinion`、`enterprise_related`、`enterprise_guarantee`、`enterprise_risk`、`loan_application`）加关系说明 `schema_relationships.csv`。三条导入路径按场景选择：

1. **默认样例（无需操作）**：后端启动时自动执行迁移并幂等灌入 `ocft-backend/scenarios/dd04/data/` 下的样例数据；业务表已有数据时跳过，重启绝不重灌。
2. **整批换数据（覆盖式）**：把 10 张 CSV 放进一个目录（文件名须与上表一致），在 Windows PowerShell 中从仓库根目录执行：

   ```powershell
   Set-Location ".\ocft-backend"
   $Py = ".\.venv\Scripts\python.exe"
   & $Py -m app.dd_import "C:\现场数据\业务表目录" # 缺省目录为 scenarios/dd04/data
   ```

   同名表按主键覆盖更新，其他企业的行保留；`question_public.csv`、`公开测试集答案.csv` 等问询与答案文件自动跳过，不会入库。现场拿到非公开集 CSV 时优先用这条路径。
3. **增量新增（不覆盖）**：工作台业务数据页各表的「导入」按钮（按表弹窗），或直接调 `POST /api/agent/data/imports`（契约见 [agent-api.md](contracts/agent-api.md)）。每次 1–9 个文件，仅接受上述 9 张业务 CSV；同业务键且字段全同的行跳过，同键不同内容整次拒绝；`schema_relationships.csv`、问询与答案文件不接受。适合给现有库追加新企业。

导入完成后即可在页面发起尽调，或按 [批量测评](#赛题-04-批量入口与六列导出) 跑批。无论哪条路径，运行时都不读取任何答案或评测标签。

### 开发

前置条件（仅开发需要）：Python 3.11–3.14、Node.js `^20.19.0 || >=22.12.0`（当前 Vite 的 engines 要求），以及可访问的模型、MySQL 与 Redis。

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1              # 一键启动（已有 node_modules 时为开发模式）
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Dev         # 刚克隆、没有 node_modules 时强制开发模式
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Reinstall   # 依赖有更新时，重装后再启动
```

开发模式会联网安装前后端依赖，启动后端（:8000）和 Vite 前端（:5173），并打印就绪状态。没有 `node_modules` 且离线包齐全时，脚本会自动切到离线模式。按 Ctrl-C 会停止全部服务。脚本不清库，也不重灌数据。

- 前端：http://127.0.0.1:5173（离线模式为 http://127.0.0.1:8000）
- API 文档：http://127.0.0.1:8000/docs
- 就绪检查：http://127.0.0.1:8000/api/health/ready（检查模型锁定与配置、MySQL、Redis；LLM 为 `unknown` 时 200 不代表模型端点已连通，需用近期成功调用或真实 smoke run 确认）

数据库统一用 MySQL，连接在 `ocft-backend/config.yaml` 的 database 段配置；SQLite 只用于自动化测试。敏感配置以 `enc:...` 密文存储，见 [密钥管理](docs/50-runbooks/密钥管理.md)。

### 常用验证命令

后端在 `ocft-backend` 目录执行，使用假模型与临时 SQLite，不调用真实模型：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

前端在 `ocft-starter` 目录执行：

```powershell
npm run lint
npm run build
```

仓库根目录执行红线扫描（仍需结合人工评审，扫描通过不等于全部红线验收通过）：

```powershell
.\ocft-backend\.venv\Scripts\python.exe .agents/skills/redline-scan/scripts/scan.py
```

### 更新离线包

改了 `requirements.txt` 或前端代码后，在有网的 Windows 机器上重新打包，并把 `vendor/` 与 `ocft-starter/dist/` 一起提交：

```powershell
powershell -ExecutionPolicy Bypass -File .\pack-offline.ps1      # 3.11–3.14 各一套 wheel + 内置 Python + 前端构建
```

网络不稳时加 `-IndexUrl https://pypi.tuna.tsinghua.edu.cn/simple` 换镜像；只更新部分版本用 `-PythonVersions 3.12,3.14`。

## 架构

```text
前端工作台 ──POST /api/agent/runs（async）+ SSE 实时事件──▶ routers/agent.py
                                              │
                                   services/run_service.py（单事务）
                                              │
          ┌──────────── 输入合规 compliance/checker.py ────────────┐
          │                                                         │
          ▼                                                     blocked
   agent/graph.py 用 LangGraph 调度 model ↔ tools
          │  engine.py 按配置检查累计 token / 单次调用时限并判定终态
          │  llm.py（唯一模型入口，原生 tool calling）
          ▼
   tools/registry.py 参数校验 → tools/*.py 只读查询 / 规则计算
          │  enterprise_dd → run_dd_agents → dd_graph.py
          │  按依赖顺序完成五角色确定性计算 → 前五角色并行解读 → report（报告）→ 事实校验
          │
          ▼
   evidence 证据快照 → 输出合规 → agent_runs / tool_traces / messages / audit_logs
          │
          ▼
   POST /runs/{runId}/confirmations 业务确认（幂等、版本校验、审计）
```

run 终态：`succeeded | needs_confirmation | needs_clarification | blocked | insufficient_evidence | failed`。接口详见 [contracts/agent-api.md](contracts/agent-api.md)，架构决策见 [ADR-0004](docs/20-architecture/adr/0004-用LangGraph封装有界工具循环.md) 与 [ADR-0008](docs/20-architecture/adr/0008-赛题04采用主控加六角色多Agent编排.md)。

### 赛题 04 场景配置（改阈值不改代码）

| 配置 | 路径 | 用途 |
|------|------|------|
| 角色编排 | `ocft-backend/scenarios/dd04/agents.yaml` | 六角色依赖、Prompt 路径、模型开关、重试与输出 token 上限 |
| 评分卡 | `ocft-backend/scenarios/dd04/scorecard.yaml` | 点数制风险评级：各指标阈值档与档位映射 |
| 额度政策 | `ocft-backend/scenarios/dd04/credit_model.yaml` | 额度测算系数、上限与取整规则（团队模拟政策） |
| 反欺诈规则 | `ocft-backend/scenarios/dd04/fraud_rules.yaml` | F01 等规则阈值，命中由工具按当年数据计算 |
| 财务指标 | `ocft-backend/scenarios/dd04/metrics.yaml` | 财报口径、周转分母与指标警戒线 |
| 舆情打分 | `ocft-backend/scenarios/dd04/opinion.yaml` | 舆情/涉诉评分参数：基础分、衰减、情感与影响权重 |

评分卡与额度政策中的阈值档位经公开测评集校准（公开题拟合，技术方案中如实披露）；运行时只从导入事实重算，不读取任何答案。

运行预算以 [app/config.py](ocft-backend/app/config.py) 和 [agents.yaml](ocft-backend/scenarios/dd04/agents.yaml) 为准：默认不限制总轮数和总墙钟时间，不承诺 60 秒完成；全局累计 token 上限为 1,048,576，赛题 04 覆盖为 200,000。默认单次模型调用超时 30 秒，报告角色为 60 秒。可通过 `RUN_MAX_TOOL_ROUNDS`、`RUN_TIMEOUT_SECONDS` 设置总限制；角色重试次数和输出 token 上限在 `agents.yaml` 配置。以上是内部保护参数，不是官方评分时限。

## 目录结构

```text
ocft-ai-marathon/
├── README.md                  # 本文件：项目介绍（对外）
├── AGENTS.md                  # AI 开发规范唯一来源（Cursor / Codex / Kiro 共用）
├── start.bat / start.ps1      # 一键启动（Windows；评委双击 start.bat，离线安装）
├── pack-offline.ps1           # 离线包打包：Python wheel + 内置 Python + 前端构建产物
├── vendor/                    # 离线包（入库）：wheels/win_amd64-py3.11~3.14、python/ 内置解释器
├── submission/                # 提交包材料：manifest 模板、第三方组件清单、数据脱敏说明、技术难点说明
├── contracts/                 # 接口契约（唯一来源，变更先改这里）
├── docs/                      # 过程文档，按层归档，导航见 docs/INDEX.md
│   ├── INDEX.md
│   ├── 00-rules/              # 官方规则原文
│   ├── 10-strategy/           # 工程策略、分工、开发流程、开发日志
│   ├── 20-architecture/       # 架构设计 + adr/ 决策记录
│   ├── 30-standards/          # 编码、红线、Git、评审清单
│   ├── 40-specs/              # 功能 spec（requirements / design / tasks）
│   ├── 50-runbooks/           # 启动、提交演练、故障处理
│   ├── 60-pitch/              # 路演脚本、答辩一页纸
│   └── 90-archive/            # 已被取代的旧文档
├── .agents/
│   ├── skills/                # 项目 Skill（Agent Skills 标准位置，见下文）
│   └── mcp/                   # 开发时 MCP 示例配置（不含凭据）
├── .cursor/rules/             # Cursor 薄层规则 → 指向 AGENTS.md
├── .kiro/steering/            # Kiro 薄层规则 → 指向 AGENTS.md
├── ocft-backend/              # Python FastAPI 后端
│   ├── app/
│   │   ├── routers/           # HTTP 层（agent.py 为主入口；其余为待迁移的旧场景路由）
│   │   ├── services/          # 用例编排与事务（run_service）
│   │   ├── agent/             # graph.py 调度循环，engine.py 判定终态，场景注册
│   │   ├── tools/             # 工具注册表与工具实现
│   │   ├── compliance/        # 输入输出合规检查
│   │   ├── domain/            # 状态、ToolResult、Evidence、错误类型
│   │   ├── models.py          # ORM：业务表 + Agent 执行表
│   │   ├── llm.py             # 模型唯一入口
│   │   └── config.py          # 配置与模型锁定
│   ├── db/                    # 只保留命令行入口 python -m db.seed（迁移 + 样例数据）；数据库层在 app/db.py、app/migrations.py
│   ├── scenarios/dd04/        # 赛题 04 场景包：评分卡 / 额度等 yaml 配置，skills/ 下六个环节的运行时 Skill
│   ├── eval/                  # 评测：题目加载、规则评分、泄漏检查、批量执行与导出
│   └── tests/                 # pytest：工具、编排、合规、可观测、密钥、评测、迁移、离线页面；数量以本次测试输出为准
├── ocft-starter/              # React 19 + TypeScript + Vite + Tailwind + shadcn/ui 前端
│   └── src/                   # 业务表 + 对话 + 执行轨迹 / 证据 / 审计确认，见 ocft-starter/README.md
└── assets/                    # 品牌素材
```

## 开发规范

所有人和所有 AI 工具都遵守 [AGENTS.md](AGENTS.md)，细则在 [docs/30-standards/](docs/30-standards/)：

| 文档 | 内容 |
|------|------|
| [redlines.md](docs/30-standards/redlines.md) | 比赛红线对应的工程约束，以及每条怎么自查 |
| [coding.md](docs/30-standards/coding.md) | 分层、Python、工具、命名、前端、测试 |
| [git-workflow.md](docs/30-standards/git-workflow.md) | 分支、提交信息、合并 |
| [review-checklist.md](docs/30-standards/review-checklist.md) | 合入 main 前逐项勾选 |

跨模块功能采用轻量 SDD，先写 spec 再写代码。流程和模板见 [docs/40-specs/README.md](docs/40-specs/README.md)。

各工具读取规范的方式如下：

| 工具 | 读取方式 |
|------|----------|
| Codex | 原生读取根目录 `AGENTS.md`，Skill 放在 `.agents/skills/` |
| Cursor | 原生读取 `AGENTS.md`；`.cursor/rules/redlines.mdc` 设为常驻，强调红线 |
| Kiro | `.kiro/steering/project.md` 设为常驻，引用 `AGENTS.md` |

## Skill（开发辅助）

Skill 是带 `SKILL.md`（frontmatter 写 name 和 description，正文是操作步骤）的目录，遵循开放的 Agent Skills 标准，放在 `.agents/skills/<name>/`。AI 根据 description 判断何时调用，也可以点名调用（如 Codex 中输入 `$redline-scan`）。这些 Skill 只辅助开发，不参与 Agent 运行时。

| Skill | 作用 | 什么时候用 |
|-------|------|------------|
| [`code-write-requirements`](.agents/skills/code-write-requirements/SKILL.md) | 按统一模板写需求：背景、用户故事、可验证验收标准、排除项 | 写需求文档；确认前不进入设计 |
| [`code-write-design`](.agents/skills/code-write-design/SKILL.md) | 按已确认需求写设计：方案、模块、契约链接、数据变更、红线逐条、取舍 | 写设计；需求未确认不用 |
| [`code-split-tasks`](.agents/skills/code-split-tasks/SKILL.md) | 把已确认设计拆成可勾选任务，每条有完成标准，最后一条是验证 | 拆 task |
| [`code-write-test-cases`](.agents/skills/code-write-test-cases/SKILL.md) | 把验收标准写成可追溯的设计用例表，不写测试代码 | 写设计用例；须在单测之前确认 |
| [`code-implement-task`](.agents/skills/code-implement-task/SKILL.md) | 按未完成任务改代码，完成标准满足才勾选 | 按 task 开发 |
| [`code-write-unit-tests`](.agents/skills/code-write-unit-tests/SKILL.md) | 按已确认设计用例写 pytest，假模型 + 临时库，追溯用例编号 | 写单元测试 |
| [`code-review-code`](.agents/skills/code-review-code/SKILL.md) | 按评审清单和 spec 追溯审查，只出阻塞项与建议 | 代码审查、合入前 |
| [`code-update-spec`](.agents/skills/code-update-spec/SKILL.md) | 先改需求，再同步设计、任务、设计用例和契约，确认后才改代码 | 需求变更 |
| [`write-spec`](.agents/skills/write-spec/SKILL.md) | 按上面前三步串起需求、设计、任务；格式见 [spec 规范](docs/40-specs/README.md) | 跨模块功能开工前、抽签后拆赛题 |
| [`add-tool`](.agents/skills/add-tool/SKILL.md) | 按规范新增 Agent 工具：注册、参数 schema、字段白名单、证据、单测 | 接入新数据源或规则 |
| [`add-scenario`](.agents/skills/add-scenario/SKILL.md) | 新增场景包：数据表、工具、system prompt、样例题 | 抽签后装配赛题场景 |
| [`run-eval`](.agents/skills/run-eval/SKILL.md) | 跑公开样例题，输出正确率与按原因归类的失败题 | 每次改动答题链路后 |
| [`redline-scan`](.agents/skills/redline-scan/SKILL.md) | 脚本扫描硬编码答案、评测标签、多余模型客户端、密钥，再加人工复核表 | 合入 main 前、提交前 |
| [`pre-submit`](.agents/skills/pre-submit/SKILL.md) | 提交前全检：一键启动、模型锁定、红线、eval、导出、README | 周六 20:00 干净环境验证、10/25 提交 |

`redline-scan` 自带脚本，可直接运行：`python .agents/skills/redline-scan/scripts/scan.py`（加 `--verbose` 逐行输出）。`run-eval` 调用 `python -m eval.run`。

## Skill（运行时）

赛题 04 已接入六个运行时 Skill，与上述开发辅助 Skill 分开。每个角色调用模型时，[app/agent/skills.py](ocft-backend/app/agent/skills.py) 按 frontmatter 的 `roles` 加载对应文件，将输入输出契约、解读边界与成文规则加入该角色的模型消息；报告重写同样使用报告 Skill。不执行 Skill 文件中的代码，也不通过低代码平台编排。

| Skill | 版本 | 触发角色 | 输入与输出契约 |
|---|---|---|---|
| [business-verification](ocft-backend/scenarios/dd04/skills/business-verification.md) | 1.1.0 | 工商核验 `business` | 工商核验计算结果 → 角色 JSON |
| [financial-analysis](ocft-backend/scenarios/dd04/skills/financial-analysis.md) | 1.1.1 | 财报解析 `finance` | 年度科目、指标及增长率 → 角色 JSON |
| [opinion-scan](ocft-backend/scenarios/dd04/skills/opinion-scan.md) | 1.1.0 | 舆情扫描 `opinion` | 舆情、案件明细及事件重算分 → 角色 JSON |
| [fraud-detection](ocft-backend/scenarios/dd04/skills/fraud-detection.md) | 1.1.0 | 反欺诈 `fraud` | 规则命中及工商、财务、舆情上游结果 → 角色 JSON |
| [credit-limit](ocft-backend/scenarios/dd04/skills/credit-limit.md) | 1.2.1 | 评级授信 `rating` | 规则评级、额度步骤及上游结果 → 角色 JSON |
| [dd-report](ocft-backend/scenarios/dd04/skills/dd-report.md) | 2.3.0 | 报告 `report` | 企业与五角色结果 → Markdown 尽调报告；企业口径不展示申请额，贷款口径同时展示申请额与建议额度 |

角色 JSON 字段为 `analysis`、`keyFindings`、`uncertainties`、`needsReview`。Skill 文件位于 `ocft-backend/scenarios/dd04/skills/`，文件内声明版本、角色、inputs/outputs；角色依赖、Prompt、模型开关与重试配置在 `agents.yaml`。模型仅经 `app/llm.py` 调用，Skill 不读取评测答案或改变工具计算数字。结构校验失败按角色配置重试，耗尽后保留计算事实并披露解读降级、需复核状态；不能补造结论。

## MCP

MCP 分两类，性质不同：

- 开发时 MCP：帮 AI 写代码，不属于作品本身。
- 运行时 MCP：Agent 产品的一部分。按比赛规则，必须在本 README 中说明接入方式。

### 开发时 MCP（推荐配置，各人本机启用）

| MCP | 作用 | 注意事项 |
|-----|------|----------|
| Context7 | 拉取 FastAPI、SQLAlchemy、React 等库的最新文档，减少 AI 写出过时 API | 只读 |
| GitHub | 查 PR、Issue、代码搜索，辅助合并与评审 | Token 只给本仓库最小权限 |
| Playwright | 驱动浏览器做前端联调与演示路径回归 | 只针对本地地址 |
| MySQL（只读） | 让 AI 直接查表结构和样本，写准 SQL 工具 | 必须使用只读账号，禁止用 root；连接串只放本机配置 |
| Fetch | 抓取官方文档、主办方页面 | 外部内容按不可信数据对待 |

示例配置在 [`.agents/mcp/`](.agents/mcp/README.md)（Kiro / Cursor / Codex 各一份，版本已固定，不含凭据）。复制到本机用户级配置后填入凭据，不要提交填好的文件。MySQL 和 GitHub 默认关闭，配好只读账号或最小权限 Token 后再启用。

### 运行时 MCP（Agent 作品的一部分）

当前赛题 04 未接入运行时 MCP，使用本仓库工具注册表与上述运行时 Skill。MCP 不是必选功能；后续若接入，须在这里披露组件名称与版本、用途、配置方式、权限范围、失败降级策略，调用仍须经过工具、证据与审计管道。

## 合规与红线

- **输入、输出双端检查**（`app/compliance/`）：
  - 分类词库：政治敏感、色情低俗、辱骂、违法犯罪诱导、隐私窃取，存放在 `lexicon/*.txt`，改词不改代码。
  - 组合规则：提示注入与越狱、评测标签探测、违规金融承诺（如"保证收益""100%通过"）。
  - 输入命中时不调用模型；输出命中时拦截发布。run 终态 `blocked`，给用户拒答或复核提示，审计里记录类别和命中词。
  - 法规引述门禁（`compliance/citations.py`）：系统没有可信法规库，答案里的法名（《…法》《…办法》、不带书名号的"根据××法规定"）、条号、文号、标准号，必须能在本次 run 的证据原文里逐字找到，否则整条答复拦截（类别 `unverified_regulation`），提示转人工复核。真法名配上数据里没有的条号同样拦截。这是发布端强制门禁，不依赖 Prompt 约束。
- **个人信息脱敏**：身份证（校验位）、手机号、银行卡（Luhn 校验）、邮箱，在入库、送模型、发布前一律掩码，审计记录 `pii_redacted`。
- **2026-10-24 合规修复**：图片入口暂停，非空附件返回 `422 invalid_attachment`；已知自然人提问及回答保留代号，法人/实控人/股东等结构化字段与同一结果的姓名说明脱敏。仅企业名称可在本地答案还原；历史记录未追溯改写。
- **效果核验**：合规样例与回归断言见 `tests/compliance_cases.py`、`tests/test_compliance.py`；可运行 `pytest tests/test_compliance.py -s` 复验。本次未运行该测试，不把历史样例通过率作为当前实测结果。
- **局限**：关键词与正则匹配理解不了语义，变体和谐音可能漏拦，需要靠样例集持续补充。
- 模型失败返回结构化错误，不生成模板化的假结论。
- 评测标签与 `expected` 必须与运行时隔离；SQL 字段访问等旁路仍须独立检查，不能仅靠正常路径的输入隔离判断通过。

完整清单与待处理事项见 [docs/30-standards/redlines.md](docs/30-standards/redlines.md)。

## 评测

```powershell
Set-Location ".\ocft-backend"
$Py = ".\.venv\Scripts\python.exe"
& $Py -m eval.run --input ".\eval\datasets\public_sample.jsonl" # 跑题 + 评分 + 导出
& $Py -m eval.run --input "C:\现场数据\题目目录" --output-dir ".\eval\output\现场批次" # 批量测评：目录内 .jsonl / .json / .csv / .xlsx 全部跑
```

批量测评输出 `results.csv`（utf-8-sig）和 `results.xlsx`，每题一行：题目、终态、答案、证据来源、runId 等，列含义见 [eval/README.md](ocft-backend/eval/README.md#输出)。csv / xlsx 题目首行为表头，需要 `id` 与 `question`（或中文"题号""问题"）列。

- 每道题都走 `run_service.create_run`，与前端、HTTP 是同一个入口，没有评测专用路径。
- 带 `expected` 的题按规则评分，检查终态、必含文本、禁含文本、必调工具、必有证据；没有 `expected` 的非公开题只跑不评。
- 结果逐题写入 `results.jsonl`，支持断点续跑；同时生成 `summary.json`（正确率、失败原因）和 `answers.json`（提交文件）。
- `expected` 只交给评分器。运行前会做泄漏检查：应用代码里出现题目 ID 或答案文本，就阻止评测。
- 当前 `eval/datasets/public_sample.jsonl` 为 6 道底座回归题和 LA001–LA010 共 16 题；历史底座成绩不代表当前版本或赛题 04 业务正确率。详见 [ocft-backend/eval/README.md](ocft-backend/eval/README.md)。
- 官方公开测评集是 10 笔贷款申请，须逐笔核对风险评级、建议额度、尽调结论和评分要点；`question_public.csv` 是独立问询自测集，不能把两者合称官方 20 笔申请。`expected`、官方参考答案及 `eval/fixtures/public_answers.csv` 仅离线评分可读。
- 官方非公开测评集现场只提供输入；系统实际运行、导出结果并如实保留失败和待确认，不预录答案。详细权重未公开，不把内部评分或文本覆盖检查当成官方得分。

### 赛题 04 批量入口与六列导出

下面在 Windows PowerShell 中从 `ocft-backend` 目录执行；运行命令会调用模型并产生费用。先从业务文件准备不含答案的输入，再走统一 `eval.run`：

```powershell
$Py = ".\.venv\Scripts\python.exe"
$Data = "..\docs\00-rules\赛题\赛题04_企业智能信贷尽调\data"
$Out = ".\eval\output\dd04-public"

& $Py -m eval.dd04 prepare --input "$Data\loan_application.csv" --kind applications --scenario-id enterprise_dd --output "$Out\applications.jsonl"
& $Py -m eval.run --input "$Out\applications.jsonl" --output-dir "$Out\runs" --fresh
& $Py -m eval.dd04 export --applications "$Data\loan_application.csv" --runs "$Out\runs\results.jsonl" --output "$Out\official-results.csv"
& $Py -m eval.dd04 validate --applications "$Data\loan_application.csv" --results "$Out\official-results.csv"
```

官方六列为 `application_id,enterprise_id,risk_level,suggested_credit_amount,due_diligence_conclusion,scoring_points`。`eval.dd04 export` 读取实际运行结果与证据，导出成功和待确认结论，并另写 `official-results-status.csv`；待确认不等于已审批。失败不会回填业务答案，缺失结果须披露，格式校验失败不靠默认结论补齐。`validate` 只检查编号、表头、BOM及完整性，不判断业务正确或计算官方分数。

现场非公开批次先按实际输入格式准备，再用独立输出目录执行同一路径；导出与校验的 `--applications` 改为该批输入，不能沿用公开集编号。当前通用入口支持 JSON/JSONL/CSV/XLSX，**尚不支持 PDF 输入**。PDF 来源的现场输入需先确认格式适配范围，不能声称已经支持。

## 从零自研

- 没有使用扣子、Dify 等 Agent 平台，也没有使用 CrewAI、AutoGen。
- 编排调度使用 LangGraph，包含通用模型工具循环和赛题 04 六角色依赖图。工具协议、证据链、审计、合规、规则引擎，以及模型调用入口，都是本仓库自己写的代码。第三方依赖还有 Web 框架、ORM、模型 HTTP SDK。

自研模块与全部依赖见 [自研边界与依赖清单](docs/20-architecture/自研边界与依赖清单.md)，调度层决策见 [ADR-0004](docs/20-architecture/adr/0004-用LangGraph封装有界工具循环.md)。从零到一的过程可以从三处追溯：

| 记录 | 内容 |
|------|------|
| [开发日志](docs/10-strategy/开发日志.md) | 每一步做了什么、为什么做，关联提交号 |
| [ADR 决策记录](docs/20-architecture/adr/README.md) | 关键技术决策的背景、备选方案与取舍 |
| `git log` | 代码演进的原始记录 |

## 开发流程

完整时序图和状态表见 [docs/10-strategy/开发流程.md](docs/10-strategy/开发流程.md)。这是活文档，每完成一步都会更新。概览如下：

```mermaid
flowchart LR
    A[选型与模块化基座 ✅] --> B[红线·证据·审计·评测底座 ✅]
    B --> C[赛题04主控+六角色与确定性工具 ✅]
    C --> D[业务验收与浏览器走查 🔄]
    D --> E[最终SHA重验·异机A6·材料重出 🔄]
    E --> F[官方非公开已有批次·最终版本复验 🔄]
    F --> G[投递回执与路演 ⏳]
```

## 文档导航

团队文档统一登记在 [docs/INDEX.md](docs/INDEX.md)。

| 材料 | 入口 |
|------|------|
| 官方题目与交付要求 | [题目说明](docs/00-rules/赛题/赛题04_企业智能信贷尽调/题目说明.md)、[提交材料说明](docs/00-rules/赛题/赛题04_企业智能信贷尽调/提交材料说明.md) |
| 技术方案与测试报告 | [技术方案](submission/dd04/技术方案.md)、[测试报告](submission/dd04/测试报告.md) |
| 截图、视频与 PDF | [材料目录](submission/dd04/artifacts/) |
| 系统结果与评测证据 | [系统输出说明](系统输出/README.md)、[测试数据说明](测试数据/README.md) |
| 路演与答辩 | [演示脚本](docs/60-pitch/赛题04演示脚本.md)、[答辩一页纸](docs/60-pitch/答辩一页纸.md) |
| 封包与交付进度 | [提交包说明](submission/README.md)、[交付清单](docs/10-strategy/赛题04交付清单.md) |

各材料应结合其日期、SHA 与 runId 阅读；旧版本评测和归档截图不能自动作为当前版本验收依据。
