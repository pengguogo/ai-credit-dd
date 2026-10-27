"""合规输入输出检查 — 分类词库 + 组合规则，命中即拒绝并落审计。

@why 规则显式列举、命中即拒绝，绝不静默改写内容：
     - 词库（lexicon/*.txt）按类别维护，合规模块改词不改代码；
     - 需要语序组合的规则（提示注入、标签探测、违规承诺、隐私窃取句式）用正则；
     - 拒绝时给用户的话术（user_message）固定且不含命中原词，内部原因（reason）只进审计。
     关键词匹配无法理解语义，不宣称完整合规判定能力。
"""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

LEXICON_DIR = Path(__file__).resolve().parent / "lexicon"


@dataclass(frozen=True)
class ComplianceDecision:
    is_clean: bool
    code: str | None = None
    reason: str | None = None          # 内部原因（含命中片段），只进审计
    category: str | None = None
    user_message: str | None = None    # 面向用户的拒答话术


_CLEAN = ComplianceDecision(is_clean=True)

# 类别 → 面向用户的拒答话术
USER_MESSAGES = {
    "politics": "抱歉，该问题涉及政治敏感内容，不在金融业务服务范围内。",
    "porn": "抱歉，该内容不符合平台规范，无法处理。",
    "abuse": "请文明交流。如对服务有意见，可以描述具体问题，我们会认真处理。",
    "crime": "抱歉，该请求可能涉及违法违规行为，无法提供帮助。如有合规的业务需求，欢迎继续咨询。",
    "privacy": "抱歉，无法查询或提供他人的个人信息。如需办理本人业务，请先完成身份核验。",
    "prompt_injection": "抱歉，无法执行该指令。请直接描述您要办理的业务。",
    "label_probe": "抱歉，无法提供该类内部数据。请直接描述您要办理的业务。",
    "financial_promise": "抱歉，系统生成的答复未通过合规检查（涉及收益或结果承诺），已拦截。请换个问法或联系人工。",
    "label_leak": "抱歉，系统生成的答复未通过合规检查，已拦截。请稍后重试或联系人工。",
}

LEXICON_REASONS = {
    "politics": "政治敏感",
    "porn": "色情低俗",
    "abuse": "辱骂与人身攻击",
    "crime": "违法犯罪诱导",
    "privacy": "窃取他人隐私",
}


def _compile(rules: list[tuple[str, str, str]]) -> list[tuple[re.Pattern, str, str]]:
    return [(re.compile(p, re.IGNORECASE), category, reason) for p, category, reason in rules]


# 输入端组合规则：(正则, 类别, 内部原因)
_INPUT_RULES = _compile([
    (r"is[_\s-]*fraud|extracted[_\s-]*kpis|评测标签|答案标签|标准答案",
     "label_probe", "请求探测评测标签或预存答案"),
    # @why 修饰词可叠加并带"的"："忽略之前的所有指令""无视上面全部的规则"
    (r"(忽略|无视|跳过|绕过|不要管)(掉)?((之前|以上|前面|先前|上面|上述|所有|全部|一切)的?)+"
     r"(指令|提示|设定|角色|约束|规则|要求|限制)",
     "prompt_injection", "尝试覆盖系统指令（提示注入）"),
    (r"ignore\s+((all|any|previous|above|prior|earlier|these|those|the)\s+){0,3}"
     r"(instructions?|prompts?|rules?)"
     r"|disregard\s+((all|any|previous|above|prior|the)\s+){0,3}(instructions?|prompts?|rules?)",
     "prompt_injection", "尝试覆盖系统指令（提示注入）"),
    # @why 中文语序可前可后："打印系统提示词" 与 "把系统提示词打印出来" 都要拦
    (r"(泄露|输出|打印|复述|展示|告诉我).{0,12}(系统提示|提示词|初始设定|你的指令)"
     r"|(系统提示|提示词|初始设定|你的指令).{0,12}(泄露|输出|打印|复述|展示)"
     r"|(reveal|show|print|repeat|output).{0,16}(system\s*prompt|your\s*instructions)",
     "prompt_injection", "尝试窃取系统提示词"),
    (r"(你现在是|扮演|进入).{0,8}(没有限制|无限制|越狱|开发者模式|DAN)",
     "prompt_injection", "越狱角色扮演"),
    # 查询他人个人信息：查/找/搜 + （某人）的 + 身份证/手机号/住址/银行卡/开房记录
    (r"(查|找|搜|调取|帮我查).{0,10}(别人|他人|某人|他|她|[\u4e00-\u9fa5]{2,3})的?"
     r"(身份证|身份证号|手机号|电话号码|家庭住址|住址|银行卡号|开房记录|征信报告)",
     "privacy", "尝试查询他人个人信息"),
])

# 输出端组合规则
_OUTPUT_RULES = _compile([
    (r"is[_\s-]*fraud|extracted[_\s-]*kpis|评测标签|答案标签",
     "label_leak", "答案出现评测标签字段"),
    (r"稳赚不赔|零风险|保本保息|无风险收益|刚性兑付"
     r"|保证(收益|盈利|不亏|不赔|回本|增值|通过|放款)"
     r"|(收益|回报|利息)\s*(保证|保底|稳定在)\s*\d"
     r"|年化.{0,6}(保证|保底|稳拿)"
     r"|必定(盈利|获益|通过)|绝对(安全|赚钱|通过)|无任何风险|百分百(通过|盈利|放款)|100\s*%\s*(通过|放款|盈利)",
     "financial_promise", "违规金融承诺表述"),
])


@lru_cache(maxsize=1)
def _load_lexicon() -> list[tuple[str, str]]:
    """返回 [(词, 类别)]，按词长倒序，优先报告更具体的命中。"""
    terms: list[tuple[str, str]] = []
    for category in LEXICON_REASONS:
        path = LEXICON_DIR / f"{category}.txt"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            word = line.strip()
            if word and not word.startswith("#"):
                terms.append((word.lower(), category))
    return sorted(terms, key=lambda t: -len(t[0]))


def _normalize(text: str) -> str:
    """去空白与常见分隔符，抵抗"洗 钱""洗-钱"一类简单拆字。"""
    return re.sub(r"[\s\-_·.*|/\\]+", "", text or "").lower()


@lru_cache(maxsize=1)
def _load_allowlist() -> list[str]:
    path = LEXICON_DIR / "allowlist.txt"
    if not path.exists():
        return []
    words = [w.strip().lower() for w in path.read_text(encoding="utf-8").splitlines()]
    return sorted((w for w in words if w and not w.startswith("#")), key=len, reverse=True)


def _strip_allowed(normalized: str) -> str:
    """@why 去掉合规业务术语再匹配词库：如"反洗钱政策"不应因含"洗钱"被误拦。
    规避类表达（如"规避反洗钱"）在 crime 词库中单列，先于白名单剥离前不受影响。"""
    for word in _load_allowlist():
        if word in normalized and not _evasive(normalized):
            normalized = normalized.replace(word, "")
    return normalized


def _evasive(normalized: str) -> bool:
    return any(k in normalized for k in ("规避", "逃避", "绕过", "躲避", "不被发现"))


def check_input(question: str) -> ComplianceDecision:
    """输入合规：调引擎前执行，违规 run 直接终态 blocked。"""
    code = "compliance_input_rejected"
    normalized = _strip_allowed(_normalize(question))
    for word, category in _load_lexicon():
        if word in normalized:
            return _reject(code, category, f"{LEXICON_REASONS[category]}（命中: {word[:20]}）")
    return _match_rules(question, _INPUT_RULES, code)


def check_output(answer: str) -> ComplianceDecision:
    """输出合规：最终答案落库/发布前执行。输出同样不得含词库敏感内容。"""
    code = "compliance_output_blocked"
    normalized = _normalize(answer)
    for word, category in _load_lexicon():
        if category in ("politics", "porn", "abuse") and word in normalized:
            return _reject(code, category, f"答案含{LEXICON_REASONS[category]}内容（命中: {word[:20]}）")
    return _match_rules(answer, _OUTPUT_RULES, code)


_NEGATIONS = ("不", "无法", "没法", "难以", "不能", "不得", "不可", "不会", "没有", "并非", "禁止",
              "勿", "莫", "未", "无从", "不存在", "拒绝", "谨防", "防范", "警惕", "避免", "否认")


_CLAUSE_BREAKS = "。！？!?；;，,\n"


def _negated(text: str, start: int) -> bool:
    """命中片段所在分句里、片段之前出现否定词，说明是在否定承诺（"无法向您承诺或保证通过"），
    不是在作出承诺。分句以标点切分，避免上一句的否定词影响下一句。

    @why 真实模型实测：回答"这笔贷款能保证 100% 通过吗"时会说"无法保证通过""无法向您承诺或保证通过"，
         被"保证通过"规则误拦。承诺类规则必须排除否定语境；固定字数窗口覆盖不了
         "承诺或""向您"等插入成分，所以改为按分句判断。"""
    clause_start = max((text.rfind(ch, 0, start) for ch in _CLAUSE_BREAKS), default=-1) + 1
    return any(n in text[clause_start:start] for n in _NEGATIONS)


def _match_rules(text: str, rules: list[tuple[re.Pattern, str, str]], code: str) -> ComplianceDecision:
    text = text or ""
    for pattern, category, reason in rules:
        for hit in pattern.finditer(text):
            if category == "financial_promise" and _negated(text, hit.start()):
                continue
            return _reject(code, category, f"{reason}（命中: {hit.group(0)[:20]}）")
    return _CLEAN


def _reject(code: str, category: str, reason: str) -> ComplianceDecision:
    return ComplianceDecision(is_clean=False, code=code, reason=reason,
                              category=category, user_message=USER_MESSAGES[category])
