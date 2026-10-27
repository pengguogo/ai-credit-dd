"""法规引述发布门禁（AI 评委 J02；题目 6.1 输出合规、专属通用纪律 6"法律法规条款不得编造"）。

规则：答案里的法规引述（法名、条号、文号、标准号）必须能在本次 run 的证据原文中逐字找到，
找不到就整条答复拦截、转人工复核。

@why 本系统没有可信的法规库，模型写出的任何法名、条号都无法核验；Prompt 里写"不要引用法规"
     只能降低概率，不能作为强制合规项。所以在发布端兜底：
     - 允许：引述原样出现在数据里（如舆情事件原文写了"违反《某某法》第六十条"），可追溯到证据行；
     - 拦截：不存在的法名、条号、文号，以及真实法名配上数据里没有的条号；
     - 不碰：普通业务分析（季度、年份、"第一条发现"、案号、规则编号 F001）。
     与 checker 一样只做显式规则，不宣称理解语义；条号中文 / 阿拉伯数字不互认（保守拦截）。
"""
import re
from dataclasses import dataclass

from .checker import ComplianceDecision

CATEGORY = "unverified_regulation"
CODE = "compliance_output_blocked"
USER_MESSAGE = ("抱歉，系统生成的答复引用了无法在本次数据中核验的法规、条款或文号，已拦截。"
                "请转人工复核，或换个问法重新生成。")

_NUM = r"[0-9０-９一二三四五六七八九十百千零〇两]+"
# 书名号内的法规类名称：以法规类后缀结尾（可带"（2015 修正）"一类版本括注）
_LEGAL_SUFFIX = (r"(法|法典|条例|办法|规定|细则|规则|指引|准则|通知|意见|决定|标准|规范|指南"
                 r"|解释|公约|协议|守则|批复|令)")
_TITLE = re.compile(r"《([^《》\n]{1,60})》")
_TITLE_IS_LEGAL = re.compile(_LEGAL_SUFFIX + r"\s*([（(][^）)]{0,20}[）)])?$|(准则|条例|规定)第")
# 条号：第N条，可带"之一""第N款""第N项"
_ARTICLE = re.compile(rf"第\s*{_NUM}\s*条(\s*之\s*{_NUM})?(\s*第\s*{_NUM}\s*[款项])*")
# 文号：××发〔2020〕9号、银保监办发[2021]15号、××令第 5 号
_DOC_NO = re.compile(rf"[\u4e00-\u9fa5]{{0,10}}(发|字|函|令|规|办)\s*[〔\[【(（]\s*\d{{4}}\s*[〕\]】)）]\s*第?\s*\d+\s*号"
                     rf"|[\u4e00-\u9fa5]{{2,12}}令\s*第\s*{_NUM}\s*号")
# 标准号：GB/T 22239-2019、JR/T 0171-2020
_STANDARD = re.compile(r"\b(GB|GB/T|GB/Z|JR|JR/T|YD/T|WS/T)\s*\d{2,6}(\.\d+)?\s*[-—]\s*\d{4}\b", re.IGNORECASE)
# 不带书名号的法名：根据 / 依据 / 违反 ×× 法（条例、办法）+ 规定 / 第 / 要求
_BARE_LAW = re.compile(r"(根据|依据|依照|按照|参照|违反|适用)\s*([\u4e00-\u9fa5]{2,20}?(法典|法|条例|细则))"
                       r"(?=\s*(第|规定|之规定|要求|明确|有关|相关|中|的规定))")
# "方法、办法、做法……"不是法名；"规定"类在书名号里才算
_NOT_LAW = re.compile(r"(方|办|做|算|看|说|写|用|手|技|章|语|想|兵|疗|魔|笔|画)法$")
# 条号需要法律语境：同一分句里条号之前出现法规用语，或条号之后紧跟"规定 / 款"等
_LEGAL_CONTEXT = re.compile(r"《|》|法|条例|规定|办法|细则|根据|依据|依照|按照|违反|适用|监管")
_ARTICLE_TAIL = re.compile(r"\s*(之?规定|明确|要求|载明|所述|款|项)")
_CLAUSE_BREAKS = "。！？!?；;\n"


@dataclass(frozen=True)
class Citation:
    kind: str      # law_title | article | doc_number | standard | bare_law
    text: str      # 答案中的原文片段
    key: str       # 去空白、去书名号后用于在证据中查找的形式


def _squash(text: str) -> str:
    return re.sub(r"[\s《》]+", "", text or "")


def _clause_start(text: str, pos: int) -> int:
    return max((text.rfind(ch, 0, pos) for ch in _CLAUSE_BREAKS), default=-1) + 1


def find_citations(text: str) -> list[Citation]:
    """抽取答案中的法规引述。条号若紧跟在法名之后，与法名合并成一条（"《X法》第N条"整体核验）。"""
    text = text or ""
    found: list[Citation] = []
    titles: list[tuple[int, int, str]] = []
    for m in _TITLE.finditer(text):
        name = m.group(1).strip()
        if _TITLE_IS_LEGAL.search(name):
            titles.append((m.start(), m.end(), name))
            found.append(Citation("law_title", m.group(0), _squash(name)))
    bare: list[tuple[int, int, str]] = []
    for m in _BARE_LAW.finditer(text):
        name = m.group(2)
        if _NOT_LAW.search(name) or any(s <= m.start(2) < e for s, e, _ in titles):
            continue
        bare.append((m.start(2), m.end(2), name))
        found.append(Citation("bare_law", name, _squash(name)))
    for m in _ARTICLE.finditer(text):
        head = text[_clause_start(text, m.start()):m.start()]
        if not (_LEGAL_CONTEXT.search(head) or _ARTICLE_TAIL.match(text, m.end())):
            continue
        # 紧跟法名（中间至多几个字符，如"》第""法第"）时合并核验
        law = next((name for s, e, name in titles + bare if 0 <= m.start() - e <= 3), None)
        key = _squash((law or "") + m.group(0))
        found.append(Citation("article", (f"《{law}》" if law else "") + m.group(0), key))
    for m in _DOC_NO.finditer(text):
        found.append(Citation("doc_number", m.group(0), _squash(m.group(0))))
    for m in _STANDARD.finditer(text):
        found.append(Citation("standard", m.group(0), _squash(m.group(0)).upper()))
    return found


def check_regulation_citations(answer: str, sources: list[str]) -> ComplianceDecision:
    """答案中的每条法规引述都必须逐字出现在 sources（本次 run 证据原文）中，否则拦截。

    sources 传本次 run 的证据快照文本；不传用户问题：用户在问题里写的法规同样无法核验，
    模型照抄也要拦。"""
    citations = find_citations(answer)
    if not citations:
        return ComplianceDecision(is_clean=True)
    haystack = _squash("\n".join(sources or []))
    upper = haystack.upper()
    for c in citations:
        target = upper if c.kind == "standard" else haystack
        if c.key and c.key not in target:
            return ComplianceDecision(
                is_clean=False, code=CODE, category=CATEGORY, user_message=USER_MESSAGE,
                reason=f"法规引述无法在本次证据中核验（{c.kind}: {c.text[:40]}）")
    return ComplianceDecision(is_clean=True)
