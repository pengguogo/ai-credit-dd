# AI评委本轮复核证据（2026-10-24）

范围：当前工作区完整作品，HEAD c6ab7ff1088c37d0291b10e1992606050d21d8f4；不修改业务代码，不调用真实模型，不修改评测标签，不自动业务确认。

- [完整报告](../AI评委逐条评分-2026-10-24-复核版.md)
- [离线反例脚本](reproduce.py)：历史执行命令中的路径针对当时本机，当前仅保留源码与结果用于追溯。
- [六列导出内容核验](export-check.json)：10笔同一scoring_points字符串、结论42至59字，附模拟分数算术核验。
- [反例/哈希/材料盘点](reproduction.json)：两类错误放行、名称还原、图片消息截获、提交dist路由、88文件哈希核对。图片只用合成占位data URL，未传真实敏感数据或发网络请求。
- [pytest](pytest.log)：425 passed，15 warnings，6.45秒，假模型/临时SQLite；退出0。
- [lint](lint.log)：退出0。
- [build](build.log)：退出0；Node版本及bundle体积有警告；产物写到临时目录，未覆盖提交dist。
- [红线扫描](redline.log)：0 ERROR/3 WARN，三条均为seed.py说明已移除标签的注释，经人工复核是误报；不等于动态路径合规保证。

规则来源为本地四份随赛资料。固定GitHub链接本轮404，未确认任何新通知。DeepSeek API身份映射已核[第一方发布页](https://api-docs.deepseek.com/news/news260910/)，其说明V4.1-Flash使用deepseek-flash调用。

旧真实模型批次：`测试数据/评测/2026-10-24/official-rerun-c6ab7ff`。与当前88个记录文件逐一哈希核对无变化；既有结果用于评分证据，不能称本轮重新跑过官方集。材料盘点跳过.git/node_modules/.venv/vendor，仅表示仓库查找范围内结果，不涵盖仓库外素材。
