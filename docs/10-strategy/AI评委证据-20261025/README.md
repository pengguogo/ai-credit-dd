# 本次AI评委评测证据

日期：2026-10-25，北京时间。基线：`c423fc602e6ae5bec746aaa1f68a8136bba2f195`。入口：[整体评测报告](../AI评委整体评测-20261025.md)。

- `live/`：独立SQLite、真实模型统一入口的官方10申请+10问询；无标签输入在`inputs/`，参考只在运行结束后的`analyze.py`离线读取。
- `live/manifest.json`：运行代码/配置/业务数据92文件哈希、输入哈希、临时数据库位置、开始结束时间；前后运行文件无变化。
- `live/*/results.jsonl`：逐条原始答案、终态、runId、用量；`evidence.json`为同批完整脱敏证据。CSV/XLSX来自运行器，不是手填答案。
- `live/official-results.csv`与`-status.csv`：官方六列与同行状态，10笔完整；仅本次评审产物，未替换根目录正式提交候选。
- `field-comparison.json`、`summary.json`：离线字段比对与量化汇总。评级10/10，数值额度8/8；另外2笔拒贷/极小额度参考不算数值精确一致。无“全文正确率”或官方评分。
- `repeat/`：额外1次LA001重复运行；同输入两次评级、额度与五章节一致，正文不逐字相同；不能外推全部样本稳定。
- `probe.py`、`probe-result.json`、`probe.log`：故障注入与纯函数反例；临时SQLite、模型网络边界替身，不是生产出现频率。包含自报确认身份、无证据结论、虚构法规、否定趋势、评分混用、未来事件。
- `pytest.log/xml`、`lint.log`、`build.log`、`redline.log`：本次完整工程检查记录。后端525通过；3条红线WARN是说明注释。
- `current-ui.png`：本次通过浏览器查看当前工作台的截图，仅证明该页显示；七功能历史走查仍须按原版本引用。
- `baseline-diff.json`：旧业务验收92文件中15个已变化，故重新跑当前批次。

本机实际使用的Python：`/tmp/ocft-topic04-review-venv/bin/python`；测试目录`ocft-backend/`。这是现有依赖环境，没有联网安装依赖。前端使用现有node_modules，构建产物输出至`/tmp/ai-judge-20261025-build`。

```bash
# 仓库根目录；假模型探针，不调用真实模型
/tmp/ocft-topic04-review-venv/bin/python docs/10-strategy/AI评委证据-20261025/probe.py
# 仓库根目录；只读本批临时数据库与结果，离线参考比对
/tmp/ocft-topic04-review-venv/bin/python docs/10-strategy/AI评委证据-20261025/analyze.py
# 后端目录；原始真实运行命令（产生模型费用）
/tmp/ocft-topic04-review-venv/bin/python ../docs/10-strategy/AI评委证据-20261025/run_current.py
```

真实运行脚本拒绝已存在的输出目录，重跑请复制脚本并换新目录，不清空或覆盖本证据。`analyze.py`依赖manifest记录的临时库；跨机器可直接读取已经导出的完整脱敏证据与字段比对，不应依赖临时库持久存在。探针与分析脚本会更新各自结果文件，需要保留本次快照时先复制整个目录。

本次未执行修复、提交、推送、Windows运行验收、正式封包或投递。当前开发环境地址：http://localhost:5173（页面），http://localhost:8000（后端）。
