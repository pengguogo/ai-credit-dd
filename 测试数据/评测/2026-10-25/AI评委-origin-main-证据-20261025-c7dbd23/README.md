# origin/main固定版本评委证据 · 2026-10-25

固定SHA：`c7dbd231b955cb7a2dfcf317212773b8cd65eae4`。本轮证据独立于本地未提交的c423fc6旧报告。

- [逐条评分报告](../AI评委逐条评分-origin-main-20261025.md)：自定义2分制35/48，红线独立不放行；不是官方分数。
- [评分明细JSON](scorecard.json)：全部24条已评条款及判分理由；官方非公开与现场主观评测待验证。
- [版本及源码hash](version.json)、[运行manifest](live/manifest.json)：git fetch后固定，运行代码前后hash不变，临时库不影响共享开发库。
- [真实运行申请](live/applications/results.jsonl)、[问询](live/questions/results.jsonl)、[汇总](summary.json)、[字段对照](field-comparison.json)。
- [完整申请证据](live/applications/evidence.json)、[完整问询证据](live/questions/evidence.json)：同run脱敏证据。
- [官方六列CSV](live/official-results.csv)、[状态CSV](live/official-results-status.csv)：本次10笔实际结果；不自动替换正式交付文件。
- [52要点候选摘录](scoring-point-candidates.md)：只检索真实正文，不自动判业务正确或计算覆盖率。
- [LA001重复](repeat/applications/results.jsonl)、[重复证据](repeat/applications/evidence.json)、[8次外送抽查](repeat/outbound-audit.json)：仅对已知实体精确字串检查；responseModel实为deepseek-flash。
- [故障注入/纯函数探针](probe-result.json)、[探针脚本](probe.py)：无证据成功、身份确认、法规拦截/正文缺口、未来事件、趋势/评分口径、未知实体、SQL别名隔离。
- [源码固定摘录](source-excerpts.md)：均来自该SHA，不能用当前工作区同路径版本替代。
- [后端测试](pytest.log)、[JUnit](pytest.xml)、[前端lint](lint.log)、[构建](build.log)、[扫描](redline.log)。570通过，15条告警；lint/build成功；扫描0ERROR/3注释WARN。
- [提交实物检查](artifact-audit.json)、[视频容器](video-metadata.json)、[PDF首屏渲染](test-report-page-1.png)：只读检查，不冒充完整播放或目标机验收。

复现脚本固定源目录为`/tmp/ocft-origin-main-judge-20261025-c7dbd23`，先从该SHA导出；视频因export-ignore须从同SHA blob额外恢复。依赖使用项目venv；pytest因原venv退出139，改用`/tmp/ocft-topic04-review-venv/bin/python`，Python3.12。材料脚本的pypdf来自Codex bundled runtime。所有脚本均在临时SQLite运行，模型真实评测有实际调用费用；probe只在模型边界使用假模型，不得当真实业务正确率。

原始JSONL/证据保留失败与待确认，不回填。官方非公开集尚未取得；合成探针和仓库演练样本不称为官方非公开集。主批次559127 token，单笔重复33194 token，未换算费用、未证明比赛总预算。模型供应方别名与主办方指定模型对应关系仍需证据。
