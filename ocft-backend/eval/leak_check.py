"""泄漏检查 — 题目 ID 与期望答案文本不得出现在应用代码中。

@why 红线 R5：禁止题号→答案映射、禁止按题 ID 特化。评测前扫描 app/，
     发现即阻止评测。只查 ≥ min_len 的期望文本，避免 "R002" 这类业务常用词误报；
     样本数据 seed.py 中天然含有申请编号等字段，跳过。
"""
from __future__ import annotations

from pathlib import Path

from .dataset import Item

SCAN_SUFFIXES = {".py", ".txt", ".md", ".json"}
SKIP_FILES = {"seed.py"}


def find_leaks(items: list[Item], expected: dict[str, dict], roots: list[Path],
               min_len: int = 8) -> list[str]:
    needles: dict[str, str] = {}
    for item in items:
        if len(item.id) >= 4:
            needles[item.id] = f"题目 ID {item.id}"
    for item_id, exp in expected.items():
        for key in ("containsAll", "containsAny"):
            for text in exp.get(key, []):
                if isinstance(text, str) and len(text) >= min_len:
                    needles[text] = f"{item_id} 的期望文本"
    findings: list[str] = []
    for root in roots:
        for path in sorted(Path(root).rglob("*")):
            if (not path.is_file() or path.suffix not in SCAN_SUFFIXES
                    or path.name in SKIP_FILES or "__pycache__" in path.parts):
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            for needle, label in needles.items():
                if needle in content:
                    findings.append(f"{path}: 出现{label}「{needle[:30]}」")
    return findings
