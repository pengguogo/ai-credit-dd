"""红线关键字扫描（只读）。用法：仓库根目录执行 python .agents/skills/redline-scan/scripts/scan.py

@why 关键字扫描必然有误报：脚本只负责"找出来"，判定交给 SKILL.md 的人工复核表。
     ERROR = 大概率违规，WARN = 需人工确认。存在 ERROR 时退出码 1，可接入提交前检查。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCAN_DIRS = ["ocft-backend/app", "ocft-backend/db", "ocft-backend/scenarios",
             "ocft-backend/scripts", "ocft-starter/src"]
SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".sql"}
SKIP_PARTS = {"node_modules", ".venv", "__pycache__", "dist"}

# (规则名, 级别, 正则, 允许出现的文件路径片段)
RULES: list[tuple[str, str, re.Pattern, tuple[str, ...]]] = [
    ("llm-client", "ERROR", re.compile(r"\bOpenAI\s*\(|ChatCompletion|anthropic\.|dashscope|zhipuai"),
     ("app/llm.py",)),
    ("model-name", "ERROR",
     re.compile(r"(gpt-[34o]|glm-\d|qwen[-\d]|claude-|deepseek-(chat|reasoner|v\d(?!\.1-flash)))", re.I),
     ()),
    # 连接串密码排除常见占位符（pass / password / xxx / [PASSWORD] / ${...}）
    ("secret", "ERROR",
     re.compile(r"(sk-[A-Za-z0-9]{16,}|(password|passwd|api_key)\s*[=:]\s*['\"][^'\"]{4,}['\"]"
                r"|(mysql|postgresql)(\+\w+)?://[^:/\s]+:(?!(pass|password|xxx+|\[|\$\{|<))[^@\s]+@)",
                re.I),
     ()),
    # expected 只匹配作为数据键出现（"expected": / expected: / ["expected"]），避免误伤普通变量
    ("eval-label", "WARN",
     re.compile(r"\b(is_fraud|isFraud|extracted_kpis|extractedKpis)\b"
                r"|[\"']expected[\"']|\bexpected\s*:\s*[{\[]"),
     ("app/models.py", "compliance/checker.py")),
    # app/tools/ 里的 "decision": 是规则引擎实时计算的输出，不是预存结论
    ("answer-column", "WARN", re.compile(r"\b(decision_reason|decisionReason)\b|[\"']decision[\"']\s*:"),
     ("app/tools/",)),
    ("fallback-answer", "WARN", re.compile(r"_fallback_\w+|FALLBACK_REPLY|fallback_opinion"), ()),
]


def iter_files():
    for rel in SCAN_DIRS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in SUFFIXES and not (SKIP_PARTS & set(path.parts)):
                yield path


def main() -> int:
    """默认按 (级别, 规则, 文件) 汇总并给首个行号；--verbose 逐行输出。"""
    verbose = "--verbose" in sys.argv
    groups: dict[tuple[str, str, str], list[tuple[int, str]]] = {}
    for path in iter_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(lines, 1):
            for name, level, pattern, allowed in RULES:
                if any(part in rel for part in allowed):
                    continue
                if pattern.search(line):
                    groups.setdefault((level, name, rel), []).append((lineno, line.strip()[:100]))

    errors = warns = 0
    for (level, name, rel), hits in sorted(groups.items()):
        if level == "ERROR":
            errors += len(hits)
        else:
            warns += len(hits)
        if verbose:
            for lineno, text in hits:
                print(f"[{level}] {name:15s} {rel}:{lineno}  {text}")
        else:
            first_line, first_text = hits[0]
            print(f"[{level}] {name:15s} {rel}:{first_line}  ×{len(hits)}  {first_text[:60]}")
    print(f"\n汇总：ERROR {errors}，WARN {warns}（WARN 需按 SKILL.md 人工复核；--verbose 看逐行）")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
