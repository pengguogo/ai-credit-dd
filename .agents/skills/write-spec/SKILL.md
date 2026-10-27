---
name: write-spec
description: 为跨模块功能按同一标准串起需求、设计和任务。当功能跨两个以上负责人目录、涉及契约或表结构变更，或抽签后拆解赛题时使用。具体写法分别遵循 code-write-requirements、code-write-design、code-split-tasks。小改动和 bug 修复不要用。
---

# 编写 Spec

格式只以 `docs/40-specs/README.md` 为准。本 skill 不另定章节。

按顺序做，每步停下来等用户确认后再进入下一步：

1. `code-write-requirements`
2. `code-write-design`
3. `code-split-tasks`

之后按 `code-implement-task`、`code-write-test-cases`、`code-review-code`、`code-write-unit-tests` 继续。需求变更用 `code-update-spec`，先改文档再改代码。

小改动和 bug 修复不建 spec 目录，直接改代码。
