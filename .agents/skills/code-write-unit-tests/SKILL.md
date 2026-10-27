---
name: code-write-unit-tests
description: 按已确认的设计用例编写后端 pytest，使用假模型和临时库，每条测试追溯用例编号。当用户要写单元测试、补测试、把设计用例落地为单测时使用。不读取评测 expected，不引入新的测试框架。
---

# 写单元测试

先读同功能的 `test-cases.md`、`docs/30-standards/coding.md` 第 6 节，以及 `ocft-backend/tests/conftest.py`。接口测试的写法对齐 `ocft-backend/tests/test_catalog.py`。

前端仓库没有测试运行器。验证方式为「手工」的用例不写测试文件；回复里列出这些编号，留给人工看。不要新增 Jest、Vitest 或其他测试依赖，除非 design 已写明并登记到依赖清单。

## 门禁

设计用例状态不是「已确认」时停下来，先用 `code-write-test-cases` 确认。不要按口头需求直接写测试。

## 步骤

1. 只实现验证列为「单测」或「接口」且期望不是「作废」的行。
2. 放在 `ocft-backend/tests/test_<功能名蛇形>.py`。文件已存在就追加，不另起第二套夹具。
3. 一个用例一个测试函数。文档字符串以用例编号开头，例如 `"""TC-1 未知场景返回 unknown_scenario。"""`。
4. 使用已有夹具：
   - HTTP：`client` 与 `HEADERS`（`X-Actor-Id`）。
   - 模型：`fake_llm`，只替换 `llm.complete_with_tools`。响应用 `model_reply` / `tool_call`。
   - 不请求真实模型，不连接云数据库。`conftest.py` 已把测试指到临时 SQLite。
5. 断言写期望列里的可观察结果（状态码、`errorCode`、字段有无、证据条数）。不断言私有函数调用次数，除非设计用例的期望就是次数。
6. 工具、合规规则、规则引擎除成功路径外，覆盖设计用例中的异常与红线行：输出不得含白名单外字段，不得含 `is_fraud`、`extracted_kpis`、`expected`。
7. 运行 `cd ocft-backend && python -m pytest tests/test_<文件>.py -q`。失败就改测试或改实现；改实现若偏离验收标准，停下来走 `code-update-spec`。
8. 全部对应用例都有通过的测试后，勾选 tasks 里的单测任务，并写上命令和通过数量。

## 禁止

- 从 `eval/` 或评分夹具读取 `expected` 来当断言。
- 为了让测试变绿而放宽断言，或跳过失败用例。
- 在测试里写死某道赛题的标准答案。
