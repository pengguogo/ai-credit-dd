# 合规补强 设计

状态：已确认    对应需求：已实现

## 方案概述

```text
输入 → redact_pii（掩码）→ check_input（分类词库 + 注入规则）→ 引擎 → check_output → redact_pii → 发布
```

- 词库按类别存 `app/compliance/lexicon/*.txt`，一行一个词，`#` 为注释，可由合规模块直接维护，不改代码。
- 注入、标签探测、金融违规承诺等需要组合语序的规则仍用正则，集中在 `checker.py`。
- PII 识别在 `app/compliance/pii.py`：身份证 18 位校验位、手机号、银行卡 Luhn、邮箱。

## 涉及模块

| 文件 | 改动 |
|------|------|
| `app/compliance/lexicon/` | 新增：politics、porn、abuse、crime、privacy 五个词表 |
| `app/compliance/checker.py` | 加载词表；`ComplianceDecision` 增加 `category`、`user_message` |
| `app/compliance/pii.py` | 新增：`redact(text) -> (masked, counts)` |
| `app/services/run_service.py` | 输入先脱敏再保存与送模型；拦截时 `errorMessage` 用 `user_message`；输出脱敏；审计记 `pii_redacted` |
| `tests/compliance_cases.py`、`tests/test_compliance.py` | 样例集 + 拦截率断言 |

## 契约变更

无新增字段。`errorMessage` 在 `blocked` 时变为面向用户的话术；审计新增事件类型 `pii_redacted`（payload：`{stage, counts}`）。已同步 `contracts/agent-api.md`。

## 红线影响

- R7 合规强制项：直接增强。
- R3 证据可追溯：审计只记类别和命中词，不记 PII 原文。
- R4 禁 Mock：拒答话术是固定的合规提示，不包含任何业务结论。

## 取舍

- 关键词匹配简单可解释，但有误拦和漏拦，需要靠样例集持续补充；重访条件：赛题提供合规样例或误拦率明显升高。
- 掩码而非拒绝 PII：用户自带个人信息咨询业务是正常场景，拒绝会伤体验。
