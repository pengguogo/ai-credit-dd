# 0004 用 LangGraph 封装有界工具循环

状态：已采纳    日期：2026-10-22    提出方：Agent 核心

## 背景

比赛禁止的是扣子等可视化低代码平台，不禁止代码形态的 Agent 框架。0002 选择完全自研循环，是为了证明编排可读、可审计。现有 `engine.run` 已把轮数、时限、token、终态和工具校验写在本仓库里。调度本身是一条固定的「模型 → 工具 → 再模型」边，适合交给图来走，而不必把模型和工具协议一起交出去。

## 决策

用 LangGraph 只做调度：`app/agent/graph.py` 有 `model`、`tools` 两个节点。模型节点调用 `llm.complete_with_tools`，工具节点调用现有注册表。终态判定函数留在 `engine.py`。不使用框架自带的 ChatModel 或 ToolNode，不启用 checkpointer，不把业务确认改成图中断。

`langgraph==1.2.16` 与 `langchain-core==1.6.13` 写入 `requirements.txt`。不引入完整 `langchain`、CrewAI 或 AutoGen。

## 后果

- 好处：下一跳由显式的边表达，以后若要加分支，可以在这张图上加节点，而不重写模型入口和证据事务。
- 代价：多两个依赖及其传递依赖；提交包按 v1.1 离线内置时要带上这些 wheel。编排调度不再是纯自研。
- 重访条件：若确认必须暂停后从同一次 run 恢复，再评估 checkpointer 或 interrupt，并另写 ADR。不把检查点交给框架的默认存储器，除非证据与审计仍在同一事务。
