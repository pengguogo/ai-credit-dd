"""合规：分类拦截、误拦、拒答话术、PII 掩码，并输出每类拦截率。"""
import pytest

from app.compliance.checker import USER_MESSAGES, check_input, check_output
from app.compliance.pii import redact
from compliance_cases import INPUT_BLOCK, INPUT_PASS, OUTPUT_BLOCK, OUTPUT_PASS

_INPUT_CASES = [(cat, text) for cat, texts in INPUT_BLOCK.items() for text in texts]
_OUTPUT_CASES = [(cat, text) for cat, texts in OUTPUT_BLOCK.items() for text in texts]


@pytest.mark.parametrize("category, text", _INPUT_CASES)
def test_input_blocked_with_category(category, text):
    decision = check_input(text)
    assert not decision.is_clean, f"漏拦：{text}"
    assert decision.code == "compliance_input_rejected"
    assert decision.category == category, f"{text} 归类为 {decision.category}"


@pytest.mark.parametrize("text", INPUT_PASS)
def test_normal_input_passes(text):
    decision = check_input(text)
    assert decision.is_clean, f"误拦：{text} → {decision.reason}"


@pytest.mark.parametrize("category, text", _OUTPUT_CASES)
def test_output_blocked(category, text):
    decision = check_output(text)
    assert not decision.is_clean and decision.category == category
    assert decision.code == "compliance_output_blocked"


@pytest.mark.parametrize("text", OUTPUT_PASS)
def test_normal_output_passes(text):
    assert check_output(text).is_clean


def test_user_message_has_no_hit_word():
    decision = check_input("怎么洗钱不被发现")
    assert decision.user_message == USER_MESSAGES["crime"]
    assert "洗钱" not in decision.user_message
    assert "洗钱" in decision.reason  # 命中词只进内部原因（审计）


def test_block_rate_report():
    """每类拦截率 100%、正常样例误拦 0；同时打印报告（pytest -s 可见）。"""
    lines = []
    for category, texts in INPUT_BLOCK.items():
        hit = sum(not check_input(t).is_clean for t in texts)
        lines.append(f"input/{category}: {hit}/{len(texts)}")
        assert hit == len(texts)
    for category, texts in OUTPUT_BLOCK.items():
        hit = sum(not check_output(t).is_clean for t in texts)
        lines.append(f"output/{category}: {hit}/{len(texts)}")
        assert hit == len(texts)
    false_block = sum(not check_input(t).is_clean for t in INPUT_PASS) \
        + sum(not check_output(t).is_clean for t in OUTPUT_PASS)
    lines.append(f"false_block: {false_block}/{len(INPUT_PASS) + len(OUTPUT_PASS)}")
    print("\n".join(lines))
    assert false_block == 0


# ---- PII ----

@pytest.mark.parametrize("text, kind, raw", [
    ("身份证 110101199003077571", "idCard", "110101199003077571"),
    ("手机 13800138000", "mobile", "13800138000"),
    ("卡号 6222 0212 3456 7894", "bankCard", "6222021234567894"),
    ("邮箱 zhang.san@example.com", "email", "zhang.san@example.com"),
])
def test_pii_masked(text, kind, raw):
    masked, counts = redact(text)
    assert counts.get(kind) == 1
    assert raw not in masked.replace(" ", "")


def test_pii_validation_avoids_false_positive():
    # 校验位错误的 18 位数字、Luhn 不通过的 16 位数字、申请编号不应被掩码
    text = "编号 110101199003077572 流水 1234567812345678 申请 APP-2026-1003"
    masked, counts = redact(text)
    assert counts == {} and masked == text


def test_redact_obj_masks_values_keeps_structure_and_input():
    from app.compliance.pii import redact_obj
    raw = {"mobile": "13812345678", "phoneInt": 13812345678, "amount": 13800,
           "ok": True, "items": [{"idCard": "11010519491231002X"}, None, 3.5],
           "13812345678": "键不改"}
    out = redact_obj(raw)
    assert out["mobile"] == "138****5678" and out["phoneInt"] == "138****5678"
    assert out["amount"] == 13800 and out["ok"] is True          # 普通数字、布尔不变
    assert out["items"] == [{"idCard": "110105********002X"}, None, 3.5]
    assert "13812345678" in out                                   # 只改值不改键
    assert raw["mobile"] == "13812345678"                         # 不修改入参


@pytest.mark.parametrize("text, raw, masked", [
    # 对公账号不走 Luhn：有"账号"上下文时兜底掩码
    ("账号571900123456789", "571900123456789", "账号***********6789"),
    ("ACCOUNT NO.:571900123456789", "571900123456789", "ACCOUNT NO.:***********6789"),
    # JSON 里的敏感字段名：值整体掩码
    ('{"account_no": "571900123456789"}', "571900123456789", '{"account_no": "***********6789"}'),
    ('{"账号": 571900123456789}', "571900123456789", '{"账号": "***********6789"}'),
    # 已能按号码规则识别的仍用原格式
    ('{"mobile": "13812345678"}', "13812345678", '{"mobile": "138****5678"}'),
])
def test_account_numbers_masked_by_context_and_field(text, raw, masked):
    out, counts = redact(text)
    assert raw not in out and out == masked and counts


def test_context_rule_does_not_mask_amounts_or_internal_ids():
    text = "账户余额 1234567890.00 元，账户编号 A01，交易流水号 TXN_000001"
    assert redact(text) == (text, {})


def test_credit_code_masks_in_text_and_sensitive_fields():
    from app.compliance.pii import redact_obj

    raw = "91310000MA1FL3K72A"
    masked, counts = redact(f"统一社会信用代码：{raw}")
    assert raw not in masked and counts.get("creditCode") == 1
    assert redact_obj({"credit_code": raw})["credit_code"] != raw


def test_redact_obj_masks_sensitive_keys_even_without_valid_checksum():
    from app.compliance.pii import redact_obj
    out = redact_obj({"account_no": "571900123456789", "accountId": "ACCT_00001",
                      "card_number": "8d62061fae79496c", "nested": [{"手机号": "13812345678"}]})
    assert out["account_no"] == "***********6789"
    assert out["accountId"] == "ACCT_00001"                # 系统内部编号不掩码（工具要用）
    assert out["card_number"] == "************496c"         # 06 题电子钱包号也只留后 4 位
    assert out["nested"][0]["手机号"] == "138****5678"


def test_name_alias_map_redacts_restores_and_ignores_unknown_alias():
    from app.compliance.names import NameAliasMap

    aliases = NameAliasMap(["杭州云启网络科技有限公司", "张三"])
    text = "尽调杭州云启网络科技有限公司，法人张三"
    masked = aliases.redact_text(text)

    assert "杭州云启网络科技有限公司" not in masked
    assert "张三" not in masked
    assert aliases.restore_text(masked) == text
    assert aliases.restore_text("未知代号") == "未知代号"


def test_name_alias_map_replaces_nested_values_but_not_keys_or_ids():
    from app.compliance.names import NameAliasMap

    aliases = NameAliasMap(["杭州云启网络科技有限公司"])
    value = {"enterpriseName": "杭州云启网络科技有限公司", "enterpriseId": "E001"}

    assert aliases.redact_obj(value) == {
        "enterpriseName": "实体#1", "enterpriseId": "E001"}
    assert aliases.restore_obj({"name": "实体#1", "unknown": "实体#9"}) == {
        "name": "杭州云启网络科技有限公司", "unknown": "实体#9"}
