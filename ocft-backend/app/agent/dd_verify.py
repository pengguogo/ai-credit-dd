"""赛题 04 发布前事实校验（spec dd-multi-agent 需求 4）— 纯函数，不调模型、不访问数据库。

检查模型写的文本是否只引用了本次 run 工具 / 角色算出的事实：
1. 带单位的数字（万元、亿元、%、次、倍、个月、分）能在事实里找到。容差按文本写出的精度取半个末位
   （「2.9亿元」允许 ±0.05 亿元，「40%」允许 ±0.5 个百分点），并允许比率与百分数互换（0.4 ↔ 40%）；
2. 「风险评级 / 评级为」后面的档位等于评级角色的结果；
3. 出现的规则编号（B01–B99、F01–F99）是本次 run 评估过的规则；
4. 出现的证据编号 ev_xxx 属于本次 run。

@why 只拦「对不上」，不拦「没写」：完整性由报告的五部分标题与角色结构保证。
"""
from __future__ import annotations

import re
from collections.abc import Iterable

LEVELS = ("低-中风险", "低风险", "中风险", "高风险")

_NUMBER_WITH_UNIT = re.compile(
    r"(?<![A-Za-z0-9_.#-])(-?\d+(?:,\d{3})*(?:\.\d+)?)\s*(亿元|亿|万元|万|%|％|个百分点|次|倍|个月|分)")
_RATING_CLAIM = re.compile(r"(?:风险评级|风险档位|评级为|评级结果)\s*[:：为是]?\s*[「“\"]?\s*"
                           r"(低-中风险|低风险|中风险|高风险)")
_RULE_ID = re.compile(r"(?<![A-Za-z0-9])([BF]\d{2})(?![0-9])")
_EVIDENCE_ID = re.compile(r"\bev_[0-9a-f]{6,}\b")
_NUMBER_IN_TEXT = re.compile(r"-?\d+(?:\.\d+)?")
# 只约束能识别的财务科目；不能拿另一个科目或年度的同值替代证据。
_SUBJECTS = {
    "revenue": ("营业收入", "营收"),
    "netprofit": ("净利润",),
    "totalassets": ("总资产",),
    "totalliabilities": ("总负债",),
    "ownersequity": ("所有者权益", "净资产"),
    "operatingcashflow": ("经营现金流", "经营性现金流", "经营活动现金流"),
    "accountsreceivable": ("应收账款",),
    "inventory": ("存货",),
    "otherreceivable": ("其他应收款", "其他应收"),
}
_SUBJECT_PATTERN = re.compile("|".join(
    re.escape(alias) for aliases in _SUBJECTS.values() for alias in aliases))
_ALIAS_KEYS = {alias: key for key, aliases in _SUBJECTS.items() for alias in aliases}
# 紧挨在比率前面的减少类措辞：「营收同比下降 22.2%」对应工具里的 -0.2222。
# 「下降至 40%」是水平值不是变化量，不在此列（后面跟「至 / 到」时不算）。
_DECLINE_BEFORE = re.compile(r"(?:下降|下滑|减少|降幅|回落|降低|缩减|萎缩|下跌|跌幅|负增长|降)"
                             r"(?:了|约|大约|达|为|幅度|幅|超过|近)*\s*$")
# 科目名和金额之间出现运算或测算措辞时，金额是测算结果（如「净资产 × 0.4 得 5,880 万元」），
# 不能只拿该科目的原值去比
_CALC_BETWEEN = re.compile(r"[×xX*÷/=＝]|得|乘|系数|口径|上限|取小|测算|折算")
# 只认完整日期（2024-03-15、2024/3/15、2024年3月15日、2024年3月），不能误伤「2500-3000」这类额度区间
_DATE = re.compile(r"(?<!\d)\d{4}(?:-\d{2}-\d{2}|/\d{1,2}/\d{1,2}|年\d{1,2}月(?:\d{1,2}日)?)"
                   r"(?:[ T]\d{2}:\d{2}(?::\d{2})?)?")


def collect_facts(sources: Iterable[object]) -> dict:
    """从工具 / 角色结果里收集可引用的数字、规则编号和评级档位。"""
    numbers: set[float] = set()
    rule_ids: set[str] = set()
    levels: set[str] = set()
    subjects: dict[str, list[tuple[object, float]]] = {}

    def walk(node: object, key: str | None = None, year=None) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            numbers.add(float(node))
            normalized = (key or "").replace("_", "").lower()
            # 工具两种拼写均指其他应收款。
            normalized = "otherreceivable" if normalized == "otherreceivables" else normalized
            if normalized in _SUBJECTS:
                subjects.setdefault(normalized, []).append((year, float(node)))
            return
        if isinstance(node, str):
            if key in ("ruleId", "code") and _RULE_ID.fullmatch(node):
                rule_ids.add(node)
            if key == "riskLevel" and node in LEVELS:
                levels.add(node)
            # 字符串里的数字（如「2500-3000」「担保圈关联 2 家」）也是工具给出的事实。
            # @why 先去掉日期：「2024-03-15」会拆出 2024、3、15，让「15 万元」之类的编造数字蒙混过关
            numeric_text = _DATE.sub(" ", node).replace(",", "")
            numeric_text = re.sub(r"(?<=\d)-(?=\d)", " ", numeric_text)
            for match in _NUMBER_IN_TEXT.findall(numeric_text):
                try:
                    numbers.add(float(match))
                except ValueError:
                    pass
            for match in _RULE_ID.findall(node):
                rule_ids.add(match)
            return
        if isinstance(node, dict):
            year = node.get("year", year)
            for k, v in node.items():
                walk(v, k, year)
        elif isinstance(node, list):
            for item in node:
                walk(item, key, year)

    for source in sources:
        walk(source)
    return {"numbers": numbers, "ruleIds": rule_ids, "levels": levels, "subjects": subjects}


def _decimals(text: str) -> int:
    return len(text.split(".", 1)[1]) if "." in text else 0


def _candidates(value: float, unit: str) -> list[tuple[float, float]]:
    """文本数值 → [(换算到事实口径的值, 容差)]。"""
    raw_tol = 0.5
    return {
        "亿元": [(value * 10000, raw_tol * 10000)], "亿": [(value * 10000, raw_tol * 10000)],
        "万元": [(value, raw_tol)], "万": [(value, raw_tol)],
        "%": [(value / 100, raw_tol / 100), (value, raw_tol)],
        "％": [(value / 100, raw_tol / 100), (value, raw_tol)],
        "个百分点": [(value / 100, raw_tol / 100), (value, raw_tol)],
    }.get(unit, [(value, raw_tol)])


def _matches(text_value: str, unit: str, numbers: set[float], declining: bool = False) -> bool:
    value = float(text_value.replace(",", ""))
    scale = 10 ** (-_decimals(text_value))
    candidates = _candidates(value, unit)
    if declining and value > 0:
        # 「下降 22.2%」= -22.2%；「降至」是水平值不在此列。不用绝对值放过正负方向错误
        candidates = [(-target, tol) for target, tol in candidates]
    for target, tol in candidates:
        tolerance = tol * scale + 1e-9
        for fact in numbers:
            if abs(fact - target) <= tolerance:
                return True
    return False


def check(text: str, sources: Iterable[object], *, evidence_ids: Iterable[str] = (),
          expected_level: str | None = None) -> list[dict]:
    """返回问题清单 [{type, snippet, detail}]；空列表表示通过。"""
    # Markdown强调不改变断言含义；保留证据ID中的下划线。
    text = (text or "").replace("*", "").replace("`", "")
    facts = collect_facts(sources)
    issues: list[dict] = (_check_sign_transitions(text or "", facts)
                          + _check_monotonic_trends(text or "", facts))
    for match in _NUMBER_WITH_UNIT.finditer(text or ""):
        number, unit = match.group(1), match.group(2)
        numbers = facts["numbers"]
        clause = re.split(r"[。；;\n，,、]", text[:match.start()])[-1]
        # 百分比等派生指标不使用原始科目金额；只绑定金额类断言。
        if unit in {"亿元", "亿", "万元", "万"}:
            labels = list(_SUBJECT_PATTERN.finditer(clause))
            # @why 科目名与金额之间有运算 / 测算措辞时，金额是测算结果，按全部事实比对
            if labels and not _CALC_BETWEEN.search(clause[labels[-1].end():]):
                key = _ALIAS_KEYS[labels[-1].group()]
                # @why 只在子句里恰好提到一个年度时按年度绑定。「2021—2023 年营业收入分别为
                #      10,500 万元、…」「2021 年至 2023 年」提到多个年度，取最后一个会拿 2023 年的值
                #      去比 2021 年的数字，误拦正确引用；这时只按科目绑定
                years = set(re.findall(r"(?<!\d)(20\d{2})(?!\d)", clause))
                numbers = {value for year, value in facts["subjects"].get(key, [])
                           if len(years) != 1 or str(year) in years}
        # @why 只对比率放开方向词：金额的正负必须写对（「经营现金流 800 万元」不能冒充 -800）
        declining = (unit in {"%", "％", "个百分点"} and not number.startswith("-")
                     and bool(_DECLINE_BEFORE.search(clause)))
        if not _matches(number, unit, numbers, declining):
            issues.append({"type": "number", "snippet": match.group(0),
                           "detail": f"{match.group(0)} 在本次工具结果中找不到对应数值"})
    level = expected_level or (next(iter(facts["levels"])) if len(facts["levels"]) == 1 else None)
    if level:
        for match in _RATING_CLAIM.finditer(text or ""):
            if match.group(1) != level:
                issues.append({"type": "risk_level", "snippet": match.group(0),
                               "detail": f"文本评级为{match.group(1)}，评级结果为{level}"})
    for rule_id in sorted(set(_RULE_ID.findall(text or ""))):
        if rule_id not in facts["ruleIds"]:
            issues.append({"type": "rule_id", "snippet": rule_id,
                           "detail": f"规则编号 {rule_id} 不在本次评估的规则里"})
    allowed = set(evidence_ids)
    for evidence_id in sorted(set(_EVIDENCE_ID.findall(text or ""))):
        if evidence_id not in allowed:
            issues.append({"type": "evidence_id", "snippet": evidence_id,
                           "detail": f"证据编号 {evidence_id} 不属于本次 run"})
    return issues


# 企业口径允许「建议授信额度 / 额度建议」；禁止绑定某笔贷款申请的措辞，
# 出现即按事实校验问题重写，避免企业尽调报告退化成某笔贷款尽调。
_ENTERPRISE_BANNED = (
    "申请贷款额度", "申请额度", "贷款期限", "本次融资", "放款前", "投放前",
)


def check_scope(text: str, scope: str) -> list[dict]:
    """按尽调口径核对正文：企业口径不得出现申请额与放款安排措辞。"""
    if scope != "enterprise":
        return []
    body = text or ""
    hits: list[str] = []
    issues: list[dict] = []
    for phrase in sorted(_ENTERPRISE_BANNED, key=len, reverse=True):
        # 长短语优先，避免「申请贷款额度」同时报出「申请额度」
        if phrase in body and not any(phrase in hit for hit in hits):
            hits.append(phrase)
            issues.append({"type": "scope", "snippet": phrase,
                           "detail": f"企业口径报告不得出现「{phrase}」，请删除申请额与放款安排表述"})
    return issues


def _check_monotonic_trends(text: str, facts: dict) -> list[dict]:
    """明确逐年/持续增减须逐期成立，不用首尾变化冒充单调趋势。"""
    issues = []
    for clause in re.split(r"[。；;\n，,]", text):
        for claim in re.finditer(r"(?:逐年|持续|连续)(增长|上升|增加|下降|降低|减少|走弱|下滑)", clause):
            prefix = clause[:claim.start()]
            labels = list(_SUBJECT_PATTERN.finditer(prefix))
            if not labels or re.search(r"是否|需核实|待核实|若|假如|并未|并非|不是", prefix):
                continue
            # 比率不是分子/分母科目本身；这里只核验明确的原始科目趋势。
            last = labels[-1]
            if re.search(r"[/／]|比值|比率|占比|增速|增长率", prefix):
                continue
            key = _ALIAS_KEYS[last.group()]
            yearly: dict[int, set[float]] = {}
            for year, value in facts["subjects"].get(key, []):
                if str(year).isdigit():
                    yearly.setdefault(int(year), set()).add(value)
            years = [int(y) for y in re.findall(r"(20\d{2})\s*年", prefix)]
            for start, end in re.findall(r"(20\d{2})\s*[—–至-]\s*(20\d{2})", prefix):
                years.extend((int(start), int(end)))
            if len(set(years)) >= 2:
                periods = list(range(min(years), max(years) + 1))
            else:
                periods = sorted(y for y in yearly if not years or y <= years[-1])
            valid = len(periods) >= (3 if "三年" in prefix else 2) and all(
                len(yearly.get(y, set())) == 1 for y in periods)
            if valid:
                values = [next(iter(yearly[y])) for y in periods]
                up = claim.group(1) in {"增长", "上升", "增加"}
                valid = all(b > a if up else b < a for a, b in zip(values, values[1:]))
            if not valid:
                snippet = clause[:claim.end()].strip()
                issues.append({"type": "trend", "snippet": snippet,
                               "detail": f"{snippet} 与同科目逐年事实不符或缺少对应期间依据"})
    return issues


def _check_sign_transitions(text: str, facts: dict) -> list[dict]:
    """只核对明确的正负转换断言；不把补件问题当成已发生的事实。"""
    issues = []
    for sentence in re.split(r"[。；;\n，,]", text):
        start = 0
        for claim in re.finditer(r"由(负)转正|由(正)转负", sentence):
            clause = sentence[start:claim.end()]
            prefix = sentence[start:claim.start()]
            start = claim.end()
            labels = list(_SUBJECT_PATTERN.finditer(prefix))
            if not labels or re.search(r"是否|需核实|待核实|若|假如|并未|并非", clause):
                continue
            key = _ALIAS_KEYS[labels[-1].group()]
            yearly: dict[int, set[float]] = {}
            for year, value in facts["subjects"].get(key, []):
                if str(year).isdigit():
                    yearly.setdefault(int(year), set()).add(value)
            years = [int(year) for year in re.findall(r"(20\d{2})\s*年", clause)]
            periods = sorted(set(years)) if len(set(years)) >= 2 else sorted(
                year for year in yearly if not years or year <= years[-1])[-2:]
            valid = len(periods) >= 2 and all(year in yearly for year in years) and all(
                len(yearly.get(y, set())) == 1 for y in (periods[0], periods[-1]))
            if valid:
                before = next(iter(yearly[periods[0]]))
                after = next(iter(yearly[periods[-1]]))
                valid = before < 0 < after if claim.group(1) else before > 0 > after
            if not valid:
                issues.append({"type": "trend", "snippet": clause.strip(),
                               "detail": f"{clause.strip()} 缺少同科目对应期间的正负转换依据"})
    return issues


def render_issues(issues: list[dict], limit: int = 12) -> str:
    lines = [f"- {item['detail']}" for item in issues[:limit]]
    if len(issues) > limit:
        lines.append(f"- 另有 {len(issues) - limit} 处")
    return "\n".join(lines)
