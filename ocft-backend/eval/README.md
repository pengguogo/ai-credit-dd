# eval · 评测

负责模块：评测。设计见 [eval-runner spec](../../docs/40-specs/eval-runner/design.md)。当前同时保留两条用途不同的链路：

- **通用 `default` 评测**：`eval.run` 直接读取通用 JSONL/JSON/CSV/XLSX，统一跑题、可选离线评分，并生成 `answers.json`、`results.csv`、`results.xlsx`、`summary.json` 和 `results.jsonl`。
- **赛题 04 专用评测**：`eval.dd04 prepare` 先把官方表格转换为无标签输入，仍由同一个 `eval.run` 执行，再用 `eval.dd04 export` 生成官方六列 CSV，并用 `eval.dd04 validate` 校验格式。

两者并存且不互相替代。`eval.run --export-format default` 的通用表格不是赛题 04 官方六列结果；赛题 04 六列必须走专用 `export`。完整现场步骤见 [赛题 04 现场非公开集操作卡](../../docs/50-runbooks/赛题04现场非公开集操作卡.md)。

## 1. 通用 `default` 评测

在 Windows PowerShell 中从 `ocft-backend` 目录执行：

```powershell
$Py = ".\.venv\Scripts\python.exe"

& $Py -m eval.run `
  --input ".\eval\datasets\public_sample.jsonl" `
  --output-dir ".\eval\output\default-public-sample" `
  --export-format default `
  --fresh

# 无 expected 的新题只运行、不评分
& $Py -m eval.run `
  --input "C:\现场数据\questions.xlsx" `
  --output-dir ".\eval\output\field-questions" `
  --export-format default `
  --fresh
```

| 参数 | 作用 |
|------|------|
| `--output-dir` | 输出目录；默认 `eval/output/<输入名>/`（已 gitignore） |
| `--fresh` | 删除该输出目录已有的 `results.jsonl` 后从头跑；不加则按题号断点续跑 |
| `--limit N` | 只跑前 N 题 |
| `--export-format default` | 生成通用 `answers.json`；当前通用 exporter 只有 `default` |
| `--skip-leak-check` | 跳过泄漏检查，不建议使用 |

需要已配置模型 Key。未配置或远程模型不可用时，每题如实记录失败与错误码，不生成模板答案。

## 2. 赛题 04 专用完整链路

以下命令从 `ocft-backend` 目录执行。`prepare` 只读取白名单业务字段并生成无标签 JSONL；不会把 `reference_answer`、`expected` 或公开答案交给 Agent。

```powershell
$Py = ".\.venv\Scripts\python.exe"
$Data = "..\docs\00-rules\赛题\赛题04_企业智能信贷尽调\data"
$Out = ".\eval\output\dd04-public"

# 1) 官方申请表 → 无标签输入
& $Py -m eval.dd04 prepare `
  --input "$Data\loan_application.csv" `
  --kind applications `
  --scenario-id enterprise_dd `
  --output "$Out\applications.jsonl"

# 2) 经统一业务入口实时运行
& $Py -m eval.run `
  --input "$Out\applications.jsonl" `
  --output-dir "$Out\runs" `
  --fresh

# 3) 同次 run 结果与已落库证据 → 官方六列 CSV + status CSV
& $Py -m eval.dd04 export `
  --applications "$Data\loan_application.csv" `
  --runs "$Out\runs\results.jsonl" `
  --output "$Out\official-results.csv"

# 4) 显式复验格式与完整性
& $Py -m eval.dd04 validate `
  --applications "$Data\loan_application.csv" `
  --results "$Out\official-results.csv"
```

公开自然语言问询同样先 `prepare` 再 `eval.run`：

```powershell
& $Py -m eval.dd04 prepare `
  --input "$Data\question_public.csv" `
  --kind questions `
  --scenario-id enterprise_dd `
  --output "$Out\questions.jsonl"

& $Py -m eval.run `
  --input "$Out\questions.jsonl" `
  --output-dir "$Out\question-runs" `
  --fresh
```

现场新业务表需要时先运行 `& $Py -m app.dd_import "C:\现场数据\业务表目录"`，再把上述申请表和输出路径替换为现场批次。正式执行前核对 `config.yaml` 指向的数据库，且不要把 PowerShell 示例中的占位路径原样执行。

### DD04 导出与校验边界

- `export` 只读取 `eval.run` 结果和同次 run 已落库证据，不读取参考答案，不补默认评级、额度或结论。
- `succeeded` 与已生成完整结论的 `needs_confirmation` 可进入六列；待确认状态另写入 `*-status.csv`。
- 缺失、失败或无法形成完整结构化结论时，六列如实写明未生成及状态/errorCode，不伪造业务结果。
- `export` 完成后会自动执行一次格式校验；单独运行 `validate` 便于交付前复验。
- `validate` 只检查 UTF-8 BOM、严格六列表头与顺序、编号和企业对应、重复/遗漏及空字段，**不评价评级、额度、结论或评分要点是否正确**。

赛题 04 只读数据体检另用：

```powershell
& $Py -m eval.dd04_data `
  --data-dir "$Data" `
  --output-dir ".\eval\output\dd04-data-audit"
```

金额诊断 `eval.dd04_credit` 只用于离线差异分析，不是 Agent 答题或正式提交入口；参考答案只能在评分侧读取。

## 3. 通用输出

| 文件 | 内容 |
|------|------|
| `results.jsonl` | 每题终态、答案、错误码、runId、工具、证据摘要、usage、耗时与可选评分明细 |
| `summary.json` | 终态/错误分布、可选评分、无证据答案数、耗时、token 与失败检查项 |
| `answers.json` | `default` exporter 生成的通用答案文件 |
| `results.csv` | 通用结果表，UTF-8 BOM，Excel 可直接打开 |
| `results.xlsx` | 与通用 CSV 对应的 Excel 文件 |

通用 CSV/XLSX 列为：`id`、`问题`、`场景`、`终态`、`答案`、`错误码`、`调用工具`、`证据数`、`证据来源`、`runId`、`耗时ms`、`评分通过`。以 `=`、`+`、`@` 等开头的文本会加单引号，避免被 Excel 当作公式。

每题都通过 `run_service.create_run` 执行，与前端和 HTTP 共用业务路径。可使用 runId 在 `/api/agent/runs/{runId}` 与审计页面追溯轨迹。评测身份固定为 `X-Actor-Id: eval_runner`。

## 4. 输入格式与 PDF 边界

`eval.run --input` 支持单个文件或目录。目录按文件名读取 `.jsonl`、`.json`、`.csv`、`.xlsx`，跳过 Excel `~$` 锁文件；题目 ID 必须唯一。

**当前不支持 PDF 作为评测输入。** 若现场收到 PDF，须先人工或使用评委允许的工具转换为与官方结构一致的 CSV/XLSX，并人工核对表头、行数、编号与金额单位，再走 DD04 专用链路。前端可把已发布回答导出为 PDF/Word，这与 PDF 输入能力无关。

通用 CSV/XLSX 首行必须有 `id` 与 `question`（或 `turns`），可选 `scenarioId` 和仅供评分侧使用的 `expected`：

| 字段 | 可用表头 |
|------|----------|
| `id` | id、编号、题号、序号、题目编号 |
| `question` | question、问题、题目、问题描述 |
| `scenarioId` | scenarioId、scenario、场景 |
| `turns` | turns、多轮（JSON 数组） |
| `expected` | expected、期望（JSON 对象，可选，仅评分侧） |

JSONL 每行一题；例如：

```json
{"id":"demo-la001","question":"企业编号：E001。请对贷款申请 LA001 完成企业信贷尽调，并提供结论与证据。","scenarioId":"enterprise_dd"}
{"id":"demo-q002","question":"企业编号：E003。该企业的资产负债率是多少？是否存在偿债风险？","scenarioId":"enterprise_dd"}
```

`expected` 支持终态、文本覆盖、工具、证据、风险评级、建议额度、尽调结论和评分要点等检查；它在加载时与题目分离，只交给评分器，不进入 Agent 请求、Prompt、工具或会话。每次运行默认检查 `app/` 是否泄漏题号或较长期望文本。

## 5. 目录与红线

| 路径 | 内容 |
|------|------|
| `datasets/public_sample.jsonl` | 底座回归 6 题 + 官方公开测评集 LA001–LA010；`expected` 含终态/工具/证据，以及对照 `public_answers.csv` 的 `riskLevel` / `suggestedCreditAmount` / `dueDiligenceConclusion` / `scoringPoints`，只交评分器 |
| `fixtures/public_answers.csv` | 官方公开测试集答案副本（离线对照），**仅评分与诊断可读**，运行时不得访问 |
| `fixtures/sample_labels.json` | 样例数据的评测标签，**仅评分器可读**，Agent 工具、Prompt、会话、前端都不得访问 |
| `output/` | 本地运行产物，默认不提交 |

公开数据只能用于发现通用缺陷并改进规则、配置和策略；不得在 Prompt、工具、种子数据或前端写死单题答案，不得建立题号到结论的映射。`expected` 在加载时与题目分离，只交评分器，绝不进入 Agent 请求、Prompt、工具或会话。

## 赛题04逐项业务复核

`dd04_review` 只处理已经完成的真实 run，不调用模型、不改写正文、不把参考传给 Agent。先独立保存同 run 完整脱敏证据，再读取离线参考；初始每项都是“无法确认”。

```powershell
# 在 ocft-backend 目录执行；使用与真实运行相同的数据库配置，确保能读到历史证据。
$Py = ".\.venv\Scripts\python.exe"
& $Py -m eval.dd04_review prepare --runs "<结果目录>\results.jsonl" --reference "<官方参考CSV>" --kind applications --output-dir "<新复核目录>"
# 问询使用 --kind questions，reference 指向 question_public.csv。
# 逐项检查 review.json，填写 decision、answerQuote、evidenceIds、reason；findings 记录额外主张错误。
& $Py -m eval.dd04_review summarize --review "<复核目录>\review.json" --output "<复核目录>\review-summary.json"
```

判定只用“满足／部分满足／不满足／无法确认”。工具拒绝重复、漏题、漏要点、串 run 证据、不存在的摘录，以及无正文或无证据的满足判定；不验证语义蕴含，不自动给全文正确率或官方得分。`financialTableChecks` 只核对识别到的同科目、同年度财务表格单元格及其单位、精度，不能覆盖自由叙述。`businessConfirmed=false` 不因 AI 复核而改变，业务确认仍走既有接口。

本轮范围、设计用例和命令见 [业务验收 spec](../../docs/40-specs/dd04-business-acceptance/requirements.md)。对应旧 SHA 的报告已归档，统一从 [归档说明](../../docs/90-archive/README.md) 进入；归档内容只供开发追溯，不作为当前交付事实。
