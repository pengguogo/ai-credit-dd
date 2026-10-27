# 已提交版本 fe2e9ae 的独立评审证据

- 被评审提交：`fe2e9aecdeaa35f9a22387459b17688dd28580f1`。
- [报告](../AI评委逐条评分-已提交版-fe2e9ae-20261024.md)；与既有 c6ab7ff 评审分开，不覆盖旧报告。
- 隔离方式：`git archive fe2e9aecdeaa35f9a22387459b17688dd28580f1`导出到`/tmp/ocft-judge-fe2e9ae`；不是当前工作区，也不是新建Git分支。
- [验证记录](verification.json)：测试输出摘要、扫描人工复核、六列CSV内容、固定版本题目说明逐字节匹配结果。
- [离线反例脚本](reproduce.py)及[结果](reproduction.json)：符号/科目错配、法人名称恢复、图片消息截获、提交dist路由与旧评测88项哈希复核。脚本复用了已提交反例，仅改隔离根目录及本次结果输出位置。
- 执行反例：`/tmp/ocft-topic04-review-venv/bin/python /Users/dawn/ai马拉松/docs/10-strategy/已提交版评委证据-fe2e9ae/reproduce.py`。依赖已安装的本机评审环境；不是交付给评委的一键命令。
- [新增评分器反例](scorer-counterexamples.json)：`score({'answer':'经营现金流为负。'}, {'scoringPoints':['现金流为正']})`及`score({'answer':'其他应收款800万元。'}, {'dueDiligenceConclusion':['经营现金流800万元']})`均返回1.0/通过。
- [lint日志](lint.log)、[build日志](build.log)：隔离源码，复用相同package.json及lock对应的现有node_modules，构建输出到`/tmp/ocft-judge-fe2e9ae-build`。非干净离线安装测试；没有覆盖提交dist。
- pytest原始工具输出为427 passed、15 warnings、9.11秒，退出0；命令在隔离ocft-backend执行`/tmp/ocft-topic04-review-venv/bin/python -m pytest tests -q`。本目录保存摘要而非完整stdout日志，不将旧425项日志冒充本轮日志。
- 扫描执行`/tmp/ocft-topic04-review-venv/bin/python .agents/skills/redline-scan/scripts/scan.py`，退出0；ERROR0/WARN3，均为seed.py:4注释，人工判误报。
- 本轮未调用真实模型、未运行Windows启动、未业务确认、未浏览器交互验收、未发送材料。真实模型成绩明确复用Git已提交批次；88个文件中仅eval/scoring.py及eval/dataset.py有变更。
- 固定GitHub规则页404；本地固定Git对象T文件与HEAD完全一致。[DeepSeek第一方说明](https://api-docs.deepseek.com/news/news260910/)支持deepseek-flash别名，实际服务端身份本轮未调用核验。
