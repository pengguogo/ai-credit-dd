"""个人信息（PII）识别与掩码。

@why 用户自带个人信息咨询业务是正常场景：掩码而非拒绝。
     身份证校验位、银行卡 Luhn 校验用来降低误判（随便一串数字不会被当成卡号）。
     掩码保留首尾少量字符，便于业务人员核对是哪一条，又不暴露完整号码。
"""
import re

_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK = "10X98765432"

_ID_CARD = re.compile(r"(?<![0-9A-Za-z])[1-9]\d{16}[\dXx](?![0-9A-Za-z])")
_CREDIT_CODE = re.compile(
    r"(?<![0-9A-Z])(?=[0-9A-HJ-NPQRTUWXY]{18}(?![0-9A-Z]))"
    r"(?=[0-9A-Z]{0,17}[A-Z])[0-9A-HJ-NPQRTUWXY]{18}(?![0-9A-Z])", re.IGNORECASE)
_BANK_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)")
_MOBILE = re.compile(r"(?<!\d)(?:\+?86[ -]?)?1[3-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _valid_id_card(value: str) -> bool:
    body, check = value[:17], value[17].upper()
    total = sum(int(d) * w for d, w in zip(body, _ID_WEIGHTS))
    return _ID_CHECK[total % 11] == check


def _valid_luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _mask(value: str, keep_head: int, keep_tail: int) -> str:
    return value[:keep_head] + "*" * max(len(value) - keep_head - keep_tail, 4) + value[-keep_tail:]


# 字段名表示账号 / 卡号 / 证件号 / 联系方式时，无论值能否通过校验都整体掩码（保留后 4 位）。
# @why 银行账号、对公账号不走 Luhn（如 571900123456789），只靠号码校验会漏；
#      结构化数据（证据快照、工具结果 JSON）里有字段名可依据。比较时去掉 _ - 空格并转小写。
#      不含 accountId / customerId 这类系统内部编号：它们是工具入参，掩码后工具就查不到了
SENSITIVE_KEYS = frozenset(k.replace("_", "").replace("-", "").lower() for k in (
    "account_no", "account_number", "acct_no", "bank_account", "账号", "账户号", "帐号", "银行账号",
    "card_no", "card_number", "bank_card", "卡号", "银行卡号",
    "id_card", "id_card_no", "id_no", "id_number", "证件号", "证件号码", "身份证", "身份证号",
    "legal_person_id", "legal_person_id_no", "legal_person_id_number", "legal_representative_id",
    "credit_code", "unified_social_credit_code", "social_credit_code", "信用代码", "统一社会信用代码",
    "mobile", "phone", "phone_number", "tel", "telephone", "手机", "手机号", "联系电话", "电话",
    "legal_person", "actual_controller", "shareholder_name", "法定代表人", "法人", "实际控制人", "实控人",
    "top_shareholder",
))
_NAME_KEYS = frozenset(k.replace("_", "").lower() for k in (
    "legal_person", "actual_controller", "shareholder_name", "top_shareholder",
    "法定代表人", "法人", "实际控制人", "实控人"))
# 文本里"账号：xxxx"这类带上下文关键词的长数字串（8~30 位，可含空格 / 连字符）
_CONTEXT_NUMBER = re.compile(
    r"((?:账号|帐号|账户|卡号|证件号码?|ACCOUNT\s*NO\.?|A/C)\s*[:：]?\s*)(\d[\d -]{6,28}\d)", re.IGNORECASE)
_CREDIT_CONTEXT = re.compile(
    r"((?:统一社会信用代码|社会信用代码|信用代码|USCC)\s*[:：]?\s*)"
    r"([0-9A-HJ-NPQRTUWXY]{18})", re.IGNORECASE)
# JSON 文本里的敏感字段："account_no": "571900..." 或 "account_no": 5719...
_JSON_FIELD = re.compile(r'"([^"\\]{1,40})"(\s*:\s*)("(?:[^"\\]|\\.)*"|-?\d{6,})')


def _norm_key(key: str) -> str:
    return key.replace("_", "").replace("-", "").replace(" ", "").lower()


def is_sensitive_key(key: object) -> bool:
    return isinstance(key, str) and _norm_key(key) in SENSITIVE_KEYS


def mask_field_value(value: str) -> str:
    """敏感字段整体掩码：只保留后 4 位；4 位及以下全部打码。"""
    value = str(value)
    if len(value) <= 4:
        return "*" * max(len(value), 4)
    return "*" * max(len(value) - 4, 4) + value[-4:]


def mask_person_name(name: str) -> str:
    """自然人姓名对外展示形式：保留姓氏，其余用一个 * 代替（张三 → 张*，欧阳修远 → 欧*）。

    @why 赛题合规要求界面、日志与导出中的敏感字段脱敏；保留姓便于业务人员核对是哪一位，
         又不暴露全名。复姓不单独识别，统一只留首字，宁可少露。
    """
    text = (name or "").strip()
    return (text[0] + "*") if text else text


def _mask_sensitive(value: str, counts: dict[str, int]) -> str:
    """敏感字段的值：先按号码规则掩码（格式与其他地方一致，如 138****5678）；规则没命中再整体掩码。"""
    if not value or set(value) <= {"*"} or "*" * 4 in value:
        return value                      # 已掩码
    masked, sub_counts = redact(value)
    if sub_counts:
        for kind, n in sub_counts.items():
            counts[kind] = counts.get(kind, 0) + n
        return masked
    counts["sensitiveField"] = counts.get("sensitiveField", 0) + 1
    return mask_field_value(value)


def redact(text: str | None) -> tuple[str, dict[str, int]]:
    """返回 (掩码后文本, {类型: 数量})。"""
    if not text:
        return text or "", {}
    counts: dict[str, int] = {}

    def field_repl(m: re.Match) -> str:
        key, sep, raw = m.group(1), m.group(2), m.group(3)
        if not is_sensitive_key(key):
            return m.group(0)
        inner = raw[1:-1] if raw.startswith('"') else raw
        if _norm_key(key) in _NAME_KEYS and raw.startswith('"') and "*" not in inner:
            # 姓名字段保留姓（张三 → 张*），与结构化输出口径一致
            counts["personName"] = counts.get("personName", 0) + 1
            return f'"{key}"{sep}"{mask_person_name(inner)}"'
        masked = _mask_sensitive(inner, counts)
        return m.group(0) if masked == inner else f'"{key}"{sep}"{masked}"'

    def context_repl(m: re.Match) -> str:
        digits = re.sub(r"[ -]", "", m.group(2))
        counts["accountNo"] = counts.get("accountNo", 0) + 1
        return m.group(1) + mask_field_value(digits)

    text = _JSON_FIELD.sub(field_repl, text)

    def credit_repl(m: re.Match) -> str:
        counts["creditCode"] = counts.get("creditCode", 0) + 1
        return m.group(1) + mask_field_value(m.group(2))

    text = _CREDIT_CONTEXT.sub(credit_repl, text)

    def sub(pattern: re.Pattern, kind: str, validate, head: int, tail: int, src: str) -> str:
        def repl(m: re.Match) -> str:
            raw = m.group(0)
            digits = re.sub(r"[ -]", "", raw)
            if validate and not validate(digits):
                return raw
            counts[kind] = counts.get(kind, 0) + 1
            return _mask(digits, head, tail)
        return pattern.sub(repl, src)

    out = sub(_CREDIT_CODE, "creditCode",
              lambda value: sum(char.isalpha() for char in value) >= 2, 2, 4, text)
    out = sub(_ID_CARD, "idCard", _valid_id_card, 6, 4, out)
    out = sub(_BANK_CARD, "bankCard", _valid_luhn, 4, 4, out)
    out = sub(_MOBILE, "mobile", None, 3, 4, out)
    # 号码规则之后再兜底"账号：xxxx"：通过校验的证件号 / 卡号已按各自格式掩码，这里只剩校验不过的账号
    out = _CONTEXT_NUMBER.sub(context_repl, out)

    def mask_email(m: re.Match) -> str:
        counts["email"] = counts.get("email", 0) + 1
        name, domain = m.group(0).split("@", 1)
        return name[:1] + "***@" + domain
    out = _EMAIL.sub(mask_email, out)
    return out, counts


def redact_obj(value: object, *, _names: tuple[str, ...] | None = None) -> object:
    """对 JSON 结构逐值掩码，返回新对象（不修改入参）。用于界面 / API / 导出的输出侧。

    @why 证据快照、目录行是结构化数据：整体转 JSON 再掩码会破坏结构，逐字段掩码只改值、不改键。
         整数形态的号码（如手机号存成 int）转成字符串判断，命中才改成掩码字符串，否则原样返回。
         字段名属于 SENSITIVE_KEYS 时整体掩码（账号不一定能通过 Luhn）。
    """
    if _names is None:
        # 结构化姓名字段也用于遮罩同一结果的说明文本，避免 detail 再泄漏原名。
        names: set[str] = set()

        def collect(node):
            if isinstance(node, dict):
                for key, item in node.items():
                    if _norm_key(str(key)) in _NAME_KEYS and isinstance(item, str) and len(item) >= 2:
                        names.add(item)
                    collect(item)
            elif isinstance(node, (list, tuple)):
                for item in node:
                    collect(item)
        collect(value)
        _names = tuple(sorted(names, key=len, reverse=True))
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _norm_key(str(k)) in _NAME_KEYS and isinstance(v, str) and len(v.strip()) >= 2:
                # 姓名字段：保留姓（张三 → 张*），与说明文本中的同名替换一致
                out[k] = mask_person_name(v)
            elif is_sensitive_key(k) and isinstance(v, (str, int)) and not isinstance(v, bool):
                out[k] = _mask_sensitive(str(v), {})
            else:
                out[k] = redact_obj(v, _names=_names)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_obj(v, _names=_names) for v in value]
    if isinstance(value, str):
        for name in _names:
            value = value.replace(name, mask_person_name(name))
        return redact(value)[0]
    if isinstance(value, int) and not isinstance(value, bool):
        masked, counts = redact(str(value))
        return masked if counts else value
    return value
