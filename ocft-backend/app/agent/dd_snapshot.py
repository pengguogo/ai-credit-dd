"""赛题 04 多 Agent：只读事实快照与敏感名称代号化（ADR-0008 决策 3、5；spec 需求 5）。

@why 角色在并行线程里执行，不能碰数据库 Session：由协调者在主线程一次读出快照并冻结，
     角色只读这份普通数据。答案列 risk_level_summary 不在 _RISK_FIELDS 里，快照天然不含。
@why 代号化：企业全名、法定代表人、实控人、股东、关联企业、被担保方、注册地址、
     统一社会信用代码、法人证件号送模型前替换为代号；代号只在本次 run 的内存里，
     映射不落库；发布前企业名称还原原名，自然人显示保留姓的脱敏形式（张*），信用代码、证件号和地址保留代号。
     模型用代号回调工具时，工具入参先在本地还原再查库。
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..domain.errors import ToolError
from ..models import (EnterpriseBasic, EnterpriseGuarantee, EnterpriseRelated,
                      EnterpriseShareholder, LoanApplication)
from ..compliance.pii import mask_person_name
from ..tools import due_diligence as dd

# 去掉这些后缀后的简称也一并替换（如「某某科技有限公司」→「某某科技」），减少简称泄漏
_ORG_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司", "股份公司", "合伙企业", "合作社", "事务所", "集团", "公司")
# 简称少于该长度不单独替换：过短的词误伤正常文本
_MIN_ALIAS_CHARS = 4
# 已知实体先代号化；明确标注但未入库的自由文本字段不能原样外送。
# 不猜测无标签的任意中文词，也不遮掉企业编号或正常业务问句。
_ENTITY_LABEL = r"(?:法定代表人|法人姓名|法人|实际控制人|实控人|股东姓名|企业名称|公司名称|企业)"
_ENTITY_DELIMITERS = r"\r\n，,。；;！？!?、\"'{}\[\]：:"
_ENTITY_CODE = re.compile(r"(?:企业|人员|关联方|信用代码|证件号|注册地址)[A-Za-z0-9_-]+|E\d+")
_LABELED_ENTITY = re.compile(
    r"(" + _ENTITY_LABEL + r"\s*[:：]\s*)("
    r"(?:" + _ENTITY_CODE.pattern + r")(?=\s|[" + _ENTITY_DELIMITERS + r"]|$)"
    r"|[^" + _ENTITY_DELIMITERS + r"]+?"
    r"(?=\s*(?:" + _ENTITY_LABEL + r"\s*[:：]|[" + _ENTITY_DELIMITERS + r"]|$)))")
# R03：无冒号标签的自然语句。人员角色后跟「为 / 是」（不含「是否」）同样视为标注；
# 未入库的「…有限公司」整体遮蔽。已知实体先换成代号，这里只兜底未知原值。
_PERSON_LABEL = r"(?:法定代表人|法人代表|法人|实际控制人|实控人)"
_PERSON_PHRASE = re.compile(
    r"(" + _PERSON_LABEL + r"\s*(?:为|是(?!否))\s*)([^" + _ENTITY_DELIMITERS + r"\s]+)")
_PERSON_APPOINTMENT = re.compile(
    r"(由\s*)([^" + _ENTITY_DELIMITERS + r"\s]{2,20}?)(\s*(?:担任|出任|任职为)\s*" + _PERSON_LABEL + r")")
_UNKNOWN_ORG = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9（）()]{2,60}?"
    r"(?:股份有限公司|有限责任公司|有限公司|股份公司|合伙企业|合作社|事务所|集团公司|公司)"
    r"(?:[（(](?:有限合伙|普通合伙|特殊普通合伙)[）)])?")
# 新增样本可能尚未入库；明确字段按语义兜底，不依赖姓名/企业字典命中。
_PERSON_FIELDS = frozenset(("legalperson", "legalrepresentative", "legalrepresentativename",
    "actualcontroller", "shareholdername", "topshareholder", "法定代表人", "法人", "实际控制人", "实控人"))
_ORG_FIELDS = frozenset(("enterprisename", "companyname", "borrowername", "relatedenterprisename",
    "guaranteedparty", "企业名称", "公司名称", "被担保方"))
_ADDRESS_FIELDS = frozenset(("registeraddress", "registeredaddress", "注册地址", "住所"))


@dataclass
class Masker:
    """外送用 mask，工具入参用 unmask，发布给用户仅用 restore_names 还原企业名称。"""
    forward: dict[str, str] = field(default_factory=dict)
    _pattern: re.Pattern | None = None
    _name_codes: set[str] = field(default_factory=set, repr=False)
    # 人员代号 → 对外展示的脱敏姓名（张三 → 张*）；发布时代号按此替换，原名不出本地
    _person_display: dict[str, str] = field(default_factory=dict, repr=False)

    def add_person(self, original: str | None, code: str) -> None:
        text = (original or "").strip()
        self.add(text, code)
        if text and self.forward.get(text) == code:
            self._person_display.setdefault(code, mask_person_name(text))

    def add(self, original: str | None, code: str, *, restore_on_output: bool = False) -> None:
        text = (original or "").strip()
        if len(text) < 2 or text in self.forward:
            return
        self.forward[text] = code
        if restore_on_output:
            self._name_codes.add(code)
        self._pattern = None

    def add_org(self, name: str | None, code: str) -> None:
        self.add(name, code, restore_on_output=True)
        text = (name or "").strip()
        for suffix in _ORG_SUFFIXES:
            if text.endswith(suffix) and len(text) - len(suffix) >= _MIN_ALIAS_CHARS:
                self.add(text[: -len(suffix)], code, restore_on_output=True)
                break

    def _regex(self) -> re.Pattern | None:
        if self._pattern is None and self.forward:
            # 长词优先，避免「某某科技」先于「某某科技有限公司」被替换
            names = sorted(self.forward, key=len, reverse=True)
            self._pattern = re.compile("|".join(re.escape(n) for n in names))
        return self._pattern

    def mask(self, text: str) -> str:
        if not text:
            return text
        # tool arguments / 工具结果可能是含 Unicode 转义的 JSON 字符串，先解码再逐字段脱敏。
        if text.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(text)
            except (ValueError, RecursionError):
                pass
            else:
                if isinstance(parsed, (dict, list)):
                    return json.dumps(self.mask_obj(parsed), ensure_ascii=False)
        pattern = self._regex()
        if pattern is not None:
            text = pattern.sub(lambda m: self.forward[m.group(0)], text)
        text = _LABELED_ENTITY.sub(
            lambda m: m.group(0) if _ENTITY_CODE.fullmatch(m.group(2).strip())
            else m.group(1) + "[已脱敏]", text)
        text = _PERSON_APPOINTMENT.sub(
            lambda m: m.group(1) + (m.group(2) if _ENTITY_CODE.fullmatch(m.group(2))
                                    else "[已脱敏]") + m.group(3), text)
        text = _PERSON_PHRASE.sub(
            lambda m: m.group(0) if _ENTITY_CODE.fullmatch(m.group(2)) or m.group(2) == "[已脱敏]"
            else m.group(1) + "[已脱敏]", text)
        return _UNKNOWN_ORG.sub("[已脱敏企业]", text)

    def mask_obj(self, value):
        """JSON 结构逐值替换（只改字符串值，不改键）。"""
        if isinstance(value, str):
            return self.mask(value)
        if isinstance(value, dict):
            out = {}
            for key, raw in value.items():
                masked = self.mask_obj(raw)
                normalized = re.sub(r"[_\s-]", "", str(key)).lower()
                category = ("人员" if normalized in _PERSON_FIELDS else
                            "企业" if normalized in _ORG_FIELDS else
                            "地址" if normalized in _ADDRESS_FIELDS else None)
                if (category and isinstance(masked, str) and masked.strip()
                        and not _ENTITY_CODE.fullmatch(masked)
                        and masked not in self.forward.values()
                        and "[已脱敏" not in masked and "*" not in masked):
                    masked = f"[已脱敏{category}]"
                out[key] = masked
            return out
        if isinstance(value, list):
            return [self.mask_obj(v) for v in value]
        return value

    def unmask(self, text: str) -> str:
        """代号 → 原文：同一代号对应多个原文时取最长的那个（企业全名优先于简称）。"""
        return self._restore(text)

    def restore_names(self, text: str) -> str:
        """发布用：企业名称还原为原名，人员代号替换为保留姓的脱敏姓名，号码类代号保持掩码。"""
        return self.display_persons(self._restore(text, names_only=True))

    def display_persons(self, text: str) -> str:
        """人员代号（人员E001-1）与库内已知全名 → 脱敏姓名（张*）；未登记的代号原样保留。

        @why 早期回答里可能直接写着全名（代号化之前生成），输出时同样按库内已知人名遮成「张*」。
        """
        if not text or not self._person_display:
            return text
        persons = {name: self._person_display[code] for name, code in self.forward.items()
                   if code in self._person_display}
        if persons:
            names = re.compile("|".join(re.escape(n) for n in sorted(persons, key=len, reverse=True)))
            text = names.sub(lambda match: persons[match.group(0)], text)
        pattern = re.compile("(?:" + "|".join(
            re.escape(code) for code in sorted(self._person_display, key=len, reverse=True)
        ) + r")(?![0-9A-Za-z_-])")
        return pattern.sub(lambda match: self._person_display[match.group(0)], text)

    def repair_legacy_person_codes(self, text: str, enterprise_ids: list[str] | tuple[str, ...] = ()) -> str:
        """历史回答修复：旧版姓名遮罩把「人员E001-1」误写成「****01-1」，按同一编号还原成脱敏姓名。

        尾号可能同时对上多家企业（E001-1 与 E101-1），先限定在本次报告涉及的企业内匹配；
        仍不唯一则原样保留，不猜。
        """
        if not text or "****" not in text or not self._person_display:
            return text
        scoped = [code for code in self._person_display
                  if any(code.startswith(f"人员{eid}-") for eid in enterprise_ids)]
        pool = scoped or list(self._person_display)

        def repl(match: re.Match) -> str:
            tail = match.group(1)
            hits = [code for code in pool if code.endswith(tail) and code[: -len(tail)].startswith("人员E")]
            return self._person_display[hits[0]] if len(hits) == 1 else match.group(0)
        return re.sub(r"\*{4}(\d+-\d+)(?![0-9A-Za-z_-])", repl, text)

    def _restore(self, text: str, *, names_only: bool = False) -> str:
        if not text:
            return text
        backward: dict[str, str] = {}
        for original, code in self.forward.items():
            if names_only and code not in self._name_codes:
                continue
            if len(original) > len(backward.get(code, "")):
                backward[code] = original
        if not backward:
            return text
        # 单次替换且校验代号边界：未知 E0010 不能误匹配 E001，也不二次替换还原出的原名。
        pattern = re.compile("(?:" + "|".join(
            re.escape(code) for code in sorted(backward, key=len, reverse=True)
        ) + r")(?![0-9A-Za-z_-])")
        return pattern.sub(lambda match: backward[match.group(0)], text)


def build_masker(db: Session) -> Masker:
    """按全库企业构造映射：主控定位阶段还不知道是哪家企业，问题里也可能直接写企业名。"""
    masker = Masker()
    persons: dict[str, str] = {}
    orgs: dict[str, str] = {}

    def person(eid: str, name: str | None) -> None:
        text = (name or "").strip()
        if text and text not in persons:
            persons[text] = f"人员{eid}-{sum(1 for v in persons.values() if v.startswith(f'人员{eid}-')) + 1}"
            # 人名只在本地工具入参还原原名；发布答案显示保留姓的脱敏形式（张*）。
            masker.add_person(text, persons[text])

    def org(eid: str, name: str | None) -> None:
        text = (name or "").strip()
        if text and text not in orgs and text not in masker.forward:
            orgs[text] = f"关联方{eid}-{sum(1 for v in orgs.values() if v.startswith(f'关联方{eid}-')) + 1}"
            masker.add_org(text, orgs[text])

    basics = db.query(EnterpriseBasic).order_by(EnterpriseBasic.enterprise_id).all()
    for row in basics:
        eid = row.enterprise_id
        masker.add_org(row.enterprise_name, f"企业{eid}")
        masker.add(row.credit_code, f"信用代码{eid}")
        masker.add(row.legal_person_id, f"证件号{eid}")
        masker.add(row.register_address, f"注册地址{eid}")
        person(eid, row.legal_person)
        person(eid, row.actual_controller)
    for row in db.query(EnterpriseShareholder).order_by(EnterpriseShareholder.id).all():
        if "自然人" in (row.shareholder_type or "") or len((row.shareholder_name or "").strip()) <= 4:
            person(row.enterprise_id, row.shareholder_name)
        else:
            org(row.enterprise_id, row.shareholder_name)
    for row in db.query(EnterpriseRelated).order_by(EnterpriseRelated.id).all():
        org(row.enterprise_id, row.related_enterprise_name)
    for row in db.query(EnterpriseGuarantee).order_by(EnterpriseGuarantee.id).all():
        org(row.enterprise_id, row.guaranteed_party)
    return masker


SCOPES = ("loan", "enterprise")


def resolve_scope(scope: str | None, application_id: str | None) -> str:
    """尽调口径：显式值优先；未传时有申请编号按本笔贷款，只给企业按企业主体。"""
    if scope is None or scope == "":
        return "loan" if application_id else "enterprise"
    if scope not in SCOPES:
        raise ToolError("invalid_args", f"scope 只能是 {' / '.join(SCOPES)}")
    return scope


@dataclass(frozen=True)
class Snapshot:
    """一次尽调的只读事实：企业十类事实（不含答案列）＋ 贷款口径下的申请行。"""
    application_id: str
    enterprise_id: str
    loan: dict
    bundle: dict
    # loan：针对某笔申请（建议额度 + 申请额）；enterprise：企业主体（建议额度，无申请额）
    scope: str = "loan"

    def copy_bundle(self) -> dict:
        # 纯函数只读输入，但仍给每个角色一份深拷贝，防止误改共享快照
        return copy.deepcopy(self.bundle)


def load_snapshot(db: Session, application_id: str | None = None,
                  enterprise_id: str | None = None, scope: str | None = None) -> Snapshot:
    """在主线程读取并冻结快照；找不到申请或企业抛 ToolError(not_found)。

    scope=loan：给企业编号时取该企业最近一笔申请；企业没有任何申请时 loan 为空申请（额度角色会如实失败）。
    scope=enterprise：只加载企业事实，即使传了申请编号也不读取贷款行；仍测算建议授信额度，报告不出现申请贷款额度。
    """
    resolved = resolve_scope(scope, application_id)
    loan_row: LoanApplication | None = None
    if application_id:
        loan_row = dd._loan(db, application_id)
        if loan_row is None:
            raise ToolError("not_found", f"申请 {application_id} 不存在")
        enterprise_id = loan_row.enterprise_id
        if resolved == "enterprise":
            loan_row = None
    elif enterprise_id:
        if dd._basic(db, enterprise_id) is None:
            raise ToolError("not_found", f"企业 {enterprise_id} 不存在")
        if resolved == "loan":
            loan_row = (db.query(LoanApplication)
                        .filter(LoanApplication.enterprise_id == enterprise_id)
                        .order_by(LoanApplication.apply_date.desc()).first())
    else:
        raise ToolError("invalid_args", "需要 applicationId 或 enterpriseId")
    bundle = dd._bundle(db, enterprise_id)
    if bundle is None:
        raise ToolError("not_found", f"企业 {enterprise_id} 不存在")
    loan = dd._dump(loan_row, dd._LOAN_FIELDS) if loan_row is not None else {
        "application_id": "", "enterprise_id": enterprise_id, "apply_amount": None,
        "loan_purpose": "", "loan_term_months": None, "apply_date": None, "guarantee_type": ""}
    # JSON 往返：去掉 ORM 类型，保证快照是普通数据
    bundle = json.loads(json.dumps(bundle, ensure_ascii=False, default=str))
    loan = json.loads(json.dumps(loan, ensure_ascii=False, default=str))
    return Snapshot(application_id=loan.get("application_id") or "",
                    enterprise_id=enterprise_id, loan=loan, bundle=bundle, scope=resolved)
