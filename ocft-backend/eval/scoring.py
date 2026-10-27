"""规则评分 — 可复现、零费用，不用模型打分。

检查项：
    status                 期望终态，字符串或列表（任一即可）
    containsAll            回复必须包含全部文本
    containsAny            回复至少包含其一（用于同义词，如 ["拒绝", "不予通过"]）
    notContains            回复不得包含
    toolsCalled            必须调用过的工具（全部）
    requireEvidence        true 时必须有证据
    riskLevel              风险评级（对照公开测评集）；「中风险」避免误命中「低-中风险」
    suggestedCreditAmount  建议额度区间或拒贷口径；字符串或同义词列表
    dueDiligenceConclusion 尽调结论关键事实（字符串或列表）；数字支持亿/万换算与千分位
    scoringPoints          官方评分要点（分号串或列表）；软匹配词干，默认可覆盖率 0.6
    dueDiligenceConclusionMinCoverage / scoringPointsMinCoverage  覆盖率阈值（0~1）
回复文本 = answer；被拦截或失败时取 errorMessage（面向用户的话术）。
"""
from __future__ import annotations

import re

# 评分要点末尾评价词，去掉后用词干在回复里找覆盖
_POINT_SUFFIXES = (
    "计算正确", "影响评估", "占比关注", "增长分析", "波动分析", "建议合理",
    "质量好", "有依据", "及被执行",
    "正确", "合理", "完整", "明确", "关注", "分析", "评估", "建议",
    "汇总",
)


def response_text(result: dict) -> str:
    return result.get("answer") or result.get("errorMessage") or ""


def _risk_level_hit(text: str, level: str) -> bool:
    """「中风险」是「低-中风险」的子串，必须用更严的标记，避免误命中。"""
    markers = (f"**{level}**", f"风险评级：{level}", f"风险评级：**{level}**",
               f"风险评级{level}", f"评级{level}", f"评级：{level}")
    if level == "中风险":
        return any(m in text for m in markers)
    return level in text or any(m in text for m in markers)


def _normalize_amount_text(text: str) -> str:
    """去掉千分位逗号，统一连字符，便于「2,500–3,000」命中「2500-3000」。"""
    return (text.replace(",", "").replace("，", "")
            .replace("–", "-").replace("—", "-").replace("～", "-"))


def _expand_units(text: str) -> str:
    """亿→万数值展开，便于「2.86亿」命中回复里的「28600」。"""
    def repl(match: re.Match[str]) -> str:
        value = float(match.group(1))
        return f"{value * 10000:g}万"

    normalized = _normalize_amount_text(text).replace("万元", "万").replace(" ", "").replace("**", "")
    normalized = normalized.replace("存量贷款", "现有贷款").replace("贷款余额", "现有贷款")
    normalized = re.sub(r"(-?\d+(?:\.\d+)?)亿", repl, normalized)
    return re.sub(r"-?\d+\.\d+", lambda m: f"{float(m.group()):g}", normalized)


def _credit_options(expected_amount: str | list[str]) -> list[str]:
    if isinstance(expected_amount, list):
        return [str(x) for x in expected_amount]
    amount = str(expected_amount)
    if any(token in amount for token in ("拒贷", "极小")):
        # 系统对高风险常输出 0 万元，与官方「拒贷/极小额度」同口径
        return [amount, "拒贷", "极小额度", "0 万", "额度 0", "额度为 0", "**0 万**", "**0**"]
    return [amount]


def _as_list(value: str | list[str], sep: str = ";") -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(sep) if part.strip()]


def _coverage_threshold(expected: dict, key: str, default: float) -> float:
    raw = expected.get(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, value))


def _fact_hit(text: str, fact: str) -> bool:
    """保守匹配完整事实，支持单位换算；不能只因别的科目出现相同数字就记正确。"""
    normalized = _expand_units(fact)
    expanded = _expand_units(text)
    if normalized and re.search(r"(?<![\d.\-])" + re.escape(normalized) + r"(?!\d)", expanded):
        return True
    # 财务表格/趋势句允许同一科目下多个期间值；不能跨科目拼数字。
    parts = re.split(r"(-?\d+(?:\.\d+)?)", normalized)
    if len(parts) != 3 or not parts[0] or parts[2] not in {"", "%", "万", "倍"}:
        return False
    for clause in re.split(r"[，。；;\n]", expanded):
        if parts[0] not in clause or re.search(r"不是|不等于|并非", clause):
            continue
        values = re.findall(r"-?\d+(?:\.\d+)?", clause.split(parts[0], 1)[1])
        if parts[2] and parts[2] not in clause:
            continue
        if any(float(value) == float(parts[1]) for value in values):
            return True
    return False


def _point_stems(point: str) -> list[str]:
    stems = [point]
    current = point
    for _ in range(3):
        matched = False
        for suffix in _POINT_SUFFIXES:
            if current.endswith(suffix) and len(current) > len(suffix) + 1:
                current = current[: -len(suffix)]
                stems.append(current)
                matched = True
                break
        if not matched:
            break
    if current.startswith("识别") and len(current) > 2:
        stems.append(current[2:])
    return stems


def _scoring_point_hit(text: str, point: str) -> bool:
    expanded = _expand_units(text)
    for stem in _point_stems(point):
        if len(stem) >= 2 and (stem in text or stem in expanded):
            return True
    return False


def _coverage_check(name: str, items: list[str], hits: list[str], threshold: float,
                    add) -> None:
    ratio = (len(hits) / len(items)) if items else 1.0
    passed = ratio + 1e-9 >= threshold
    missed = [item for item in items if item not in hits]
    detail = (f"文本匹配覆盖（不代表业务正确） {len(hits)}/{len(items)}={ratio:.0%}（阈值 {threshold:.0%}）"
              + (f"；命中 {hits}" if hits else "")
              + (f"；未命中 {missed}" if missed else ""))
    add(name, passed, detail)


def score(result: dict, expected: dict | None) -> dict | None:
    """返回 {score, passed, checks: [{name, passed, detail}]}；无 expected 返回 None（只跑不评）。"""
    if not expected:
        return None
    text = response_text(result)
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    if "status" in expected:
        allowed = expected["status"] if isinstance(expected["status"], list) else [expected["status"]]
        add("status", result.get("status") in allowed,
            f"实际 {result.get('status')}，期望 {'/'.join(allowed)}")
    for needle in expected.get("containsAll", []):
        add(f"containsAll:{needle}", needle in text, "已包含" if needle in text else "未包含")
    if expected.get("containsAny"):
        hits = [n for n in expected["containsAny"] if n in text]
        add("containsAny", bool(hits),
            f"命中 {hits}" if hits else f"未包含任一 {expected['containsAny']}")
    for needle in expected.get("notContains", []):
        add(f"notContains:{needle}", needle not in text, "未出现" if needle not in text else "出现了")
    called = set(result.get("toolNames") or [])
    for tool in expected.get("toolsCalled", []):
        add(f"toolsCalled:{tool}", tool in called, "已调用" if tool in called else f"实际调用 {sorted(called)}")
    if expected.get("requireEvidence"):
        count = len(result.get("evidence") or [])
        add("requireEvidence", count > 0, f"证据 {count} 条")
    if "riskLevel" in expected:
        level = str(expected["riskLevel"])
        hit = _risk_level_hit(text, level)
        add("riskLevel", hit, f"期望 {level}" + ("，已命中" if hit else "，未在回复中命中"))
    if "suggestedCreditAmount" in expected:
        options = _credit_options(expected["suggestedCreditAmount"])
        norm_text = _normalize_amount_text(text)
        hits = [o for o in options
                if o in text or _normalize_amount_text(o) in norm_text]
        add("suggestedCreditAmount", bool(hits),
            f"命中 {hits}" if hits else f"未包含任一 {options}")
    if "dueDiligenceConclusion" in expected:
        facts = _as_list(expected["dueDiligenceConclusion"])
        threshold = _coverage_threshold(expected, "dueDiligenceConclusionMinCoverage",
                                        1.0 if isinstance(expected["dueDiligenceConclusion"], list) else 0.5)
        hits = [fact for fact in facts if _fact_hit(text, fact)]
        _coverage_check("dueDiligenceConclusion", facts, hits, threshold, add)
    if "scoringPoints" in expected:
        points = _as_list(expected["scoringPoints"])
        threshold = _coverage_threshold(expected, "scoringPointsMinCoverage", 0.6)
        hits = [point for point in points if _scoring_point_hit(text, point)]
        _coverage_check("scoringPoints", points, hits, threshold, add)

    if not checks:
        return None
    passed = sum(c["passed"] for c in checks)
    return {"score": round(passed / len(checks), 4), "passed": passed == len(checks), "checks": checks}
