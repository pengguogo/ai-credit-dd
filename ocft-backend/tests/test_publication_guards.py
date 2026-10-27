"""评委 P0 回归（R01 无证据发布 / R02 SQL 别名绕过评级隔离 / R03 未标注实体外送）。

故障注入只替换模型网络边界；名称均为合成测试值，不引用任何答案取值。
"""
import json

import pytest

from app.agent.dd_snapshot import Masker
from app.agent.engine import NO_EVIDENCE_MESSAGE
from app.agent.scenarios import SCENARIOS
from app.db import SessionLocal
from app.tools import registry
from conftest import HEADERS, model_reply

_LEAK_KEYS = {"riskLevelSummary", "ratingHint", "risk_level_summary"}


def _create(client, question):
    resp = client.post("/api/agent/runs", json={"question": question}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _messages(client, conversation_id):
    return client.get(f"/api/agent/conversations/{conversation_id}/messages",
                      headers=HEADERS).json()["messages"]


# ---- R01 ----

@pytest.mark.parametrize("claim", [
    "该企业没有对外担保，也没有逾期，可以放款。",
    "建议拒贷。",
    "经营状况良好，无重大风险。",
])
def test_business_claim_without_evidence_is_not_published(client, fake_llm, claim):
    fake_llm["replies"] = [model_reply(content=claim)]
    run = _create(client, "请核查 E003 的对外担保和逾期，能否放款？")
    assert run["status"] == "insufficient_evidence" and run["errorCode"] == "evidence_missing"
    assert run["answer"] is None and run["evidenceIds"] == []
    assert run["errorMessage"] == NO_EVIDENCE_MESSAGE
    history = json.dumps(_messages(client, run["conversationId"]), ensure_ascii=False)
    assert claim not in history


@pytest.mark.parametrize("question, reply", [
    ("你们好", "你好！有什么可以帮你？"),
    ("今天天气怎么样", "今天晴，气温 25 度。"),
    ("1+1 等于几", "等于 2。"),
])
def test_out_of_scope_question_gets_fixed_guide(client, fake_llm, question, reply):
    fake_llm["replies"] = [model_reply(content=reply)]
    run = _create(client, question)
    assert run["status"] == "needs_clarification"
    assert run["errorCode"] == "clarification_required"
    assert run["answer"] is None and run["evidenceIds"] == []
    assert run["errorMessage"] == SCENARIOS["enterprise_dd"].guide_message
    # 模型原文不发布，也不进会话历史；只调用一次模型（不触发事实校验重写）
    assert len(fake_llm["calls"]) == 1
    history = json.dumps(_messages(client, run["conversationId"]), ensure_ascii=False)
    assert reply not in history


@pytest.mark.parametrize("question", [
    "这家公司能放款吗",
    "帮我看看授信额度",
    "LA999 怎么样",
])
def test_business_question_without_evidence_stays_insufficient(client, fake_llm, question):
    fake_llm["replies"] = [model_reply(content="可以放款。")]
    run = _create(client, question)
    assert run["status"] == "insufficient_evidence"
    assert run["errorMessage"] == NO_EVIDENCE_MESSAGE


def test_evidence_backed_answer_still_succeeds(client, fake_llm):
    from conftest import tool_call
    fake_llm["replies"] = [
        model_reply(tool_calls=[tool_call("c1", "get_loan_application",
                                          '{"applicationId": "LA001"}')]),
        model_reply(content="已查到该笔贷款申请。"),
    ]
    run = _create(client, "查一下 LA001 的申请信息")
    assert run["status"] == "succeeded" and run["evidenceIds"]


# ---- R02 ----

@pytest.mark.parametrize("sql", [
    "WITH t(c0,c1,c2,c3,c4,c5,c6,rating_hint,c8) AS (SELECT * FROM enterprise_risk) "
    "SELECT c1 AS enterprise_id, rating_hint FROM t LIMIT 10",
    "SELECT * FROM (SELECT * FROM enterprise_risk) AS x",
    "SELECT r.* FROM enterprise_risk r",
    "WITH t AS (SELECT * FROM enterprise_risk) SELECT * FROM t",
    "SELECT * FROM enterprise_risk UNION ALL SELECT * FROM enterprise_risk",
    # 同名 CTE 遮蔽真表 + 库名前缀 + 位置别名（评委对抗探针）
    "WITH enterprise_risk(c0,c1,c2,c3,c4,c5,c6,rating_hint,c8) AS "
    "(SELECT * FROM main.enterprise_risk) SELECT c1, rating_hint FROM enterprise_risk",
    "WITH enterprise_risk(c0,c1,c2,c3,c4,c5,c6,rating_hint,c8) AS "
    "(SELECT * FROM enterprise_risk) SELECT c1, rating_hint FROM enterprise_risk",
    "WITH x AS (WITH enterprise_risk AS (SELECT * FROM main.enterprise_risk) "
    "SELECT * FROM enterprise_risk) SELECT * FROM x",
    "SELECT * FROM main.enterprise_risk",
])
def test_sql_alias_cannot_expose_stored_rating(client, sql):
    ctx = {"run_id": "run_r02", "data_version": 1,
           "sql_tables": SCENARIOS["enterprise_dd"].sql_tables}
    with SessionLocal() as db:
        result, records, _ = registry.execute_tool(db, ctx, "sql_query", json.dumps({"sql": sql}))
    payload = json.dumps([result.data, [r.snapshot for r in records]], ensure_ascii=False)
    for level in ("低风险", "中风险", "高风险"):
        assert level not in payload, sql
    if result.is_success:
        assert not {k for row in result.data["rows"] for k in row} & _LEAK_KEYS


def test_sql_fact_columns_on_shielded_table_still_work(client):
    ctx = {"run_id": "run_r02", "data_version": 1,
           "sql_tables": SCENARIOS["enterprise_dd"].sql_tables}
    sql = ("SELECT r.enterprise_id, r.overdue_count FROM enterprise_risk r "
           "JOIN loan_application l ON r.enterprise_id = l.enterprise_id LIMIT 3")
    with SessionLocal() as db:
        result, records, _ = registry.execute_tool(db, ctx, "sql_query", json.dumps({"sql": sql}))
    assert result.is_success and result.data["rows"] and records
    assert "overdueCount" in result.data["rows"][0]


# ---- R03 ----

def test_unlabeled_unknown_company_and_person_are_masked():
    masker = Masker()
    masker.add("已知测试人甲", "人员E999-1")
    raw = "请分析测试城云端演练科技有限公司的偿债能力，法定代表人为欧阳演练。"
    masked = masker.mask(raw)
    assert "测试城云端演练科技有限公司" not in masked and "欧阳演练" not in masked
    assert "偿债能力" in masked and masker.mask(masked) == masked
    assert masker.mask("法人为已知测试人甲") == "法人为人员E999-1"
    assert masker.mask("法人是否变更？") == "法人是否变更？"


def test_unlabeled_unknown_entities_never_reach_model(client, fake_llm):
    fake_llm["replies"] = [model_reply(content="请提供企业编号以便核验。")]
    _create(client, "请分析测试城云端演练科技有限公司的偿债能力，法定代表人为欧阳演练。")
    sent = json.dumps(fake_llm["calls"][0]["messages"], ensure_ascii=False)
    assert "测试城云端演练科技有限公司" not in sent and "欧阳演练" not in sent

@pytest.mark.parametrize('question,company,person', [
    ('请调查云端演练合伙企业，由欧阳演练担任法定代表人。', '云端演练合伙企业', '欧阳演练'),
    ('请调查星河演练股份公司，法定代表人：司马演练。', '星河演练股份公司', '司马演练'),
    ('请调查北辰演练合作社，法定代表人是上官演练。', '北辰演练合作社', '上官演练'),
])
def test_entity_variants_never_reach_model(client, fake_llm, question, company, person):
    fake_llm['replies'] = [model_reply(content='请提供申请编号以便核验。')]
    _create(client, question)
    sent = json.dumps(fake_llm['calls'], ensure_ascii=False)
    assert company not in sent and person not in sent


def test_nested_json_unknown_sensitive_fields_are_masked():
    masker = Masker()
    raw = {'enterpriseName': '云端演练合伙企业', 'legalRepresentative': '欧阳演练',
           'registeredAddress': '演练市测试路合成地址八号', 'applyAmount': 1234.5,
           'applicationId': 'SYNTHETIC-LOAN'}
    payload = [{'role': 'assistant', 'tool_calls': [{'id': 'safe-call', 'type': 'function',
                'function': {'name': 'find_enterprise', 'arguments': json.dumps(raw)}}]}]
    masked = masker.mask_obj(payload)
    args = json.loads(masked[0]['tool_calls'][0]['function']['arguments'])
    for key in ('enterpriseName', 'legalRepresentative', 'registeredAddress'):
        assert raw[key] not in args[key]
    assert args['applyAmount'] == 1234.5 and args['applicationId'] == 'SYNTHETIC-LOAN'
    assert masker.mask_obj(masked) == masked
    assert json.loads(payload[0]['tool_calls'][0]['function']['arguments']) == raw


def test_model_generated_tool_arguments_are_masked_before_replay(client, fake_llm):
    from conftest import tool_call
    args = json.dumps({'name': '云端演练合伙企业', 'note': '由欧阳演练担任法定代表人。'}, ensure_ascii=False)
    fake_llm['replies'] = [model_reply(tool_calls=[tool_call('privacy-replay', 'find_enterprise', args)]),
                           model_reply(content='未找到对应企业，请补充申请编号。')]
    _create(client, '请核查 E001。')
    assert len(fake_llm['calls']) == 2
    for call in fake_llm['calls']:
        sent = json.dumps(call['messages'], ensure_ascii=False)
        assert '云端演练合伙企业' not in sent and '欧阳演练' not in sent


def test_legacy_history_with_unknown_names_is_masked_before_model(client, fake_llm):
    from app.models import Message
    fake_llm['replies'] = [model_reply(content='请提供申请编号。')]
    first = _create(client, '请核查申请信息。')
    raw = '历史补充：云端演练合伙企业，由欧阳演练担任法定代表人。'
    with SessionLocal() as db:
        db.add(Message(conversation_id=first['conversationId'], role='user', content=raw))
        db.commit()
    fake_llm['replies'] = [model_reply(content='请补充对应申请编号。')]
    resp = client.post('/api/agent/runs', headers=HEADERS,
                       json={'question': '继续核查偿债能力。', 'conversationId': first['conversationId']})
    assert resp.status_code == 200
    sent = json.dumps(fake_llm['calls'][-1]['messages'], ensure_ascii=False)
    assert '云端演练合伙企业' not in sent and '欧阳演练' not in sent
    assert '偿债能力' in sent


def test_unknown_names_are_absent_at_sdk_request_boundary(client, monkeypatch):
    from types import SimpleNamespace
    from app import llm
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='请提供申请编号。', tool_calls=[]),
                                     finish_reason='stop')],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            model='deepseek-v4.1-flash')

    class FakeClient:
        chat = SimpleNamespace(completions=SimpleNamespace(create=create))

        def with_options(self, **_kwargs):
            return self

    monkeypatch.setattr(llm, '_get_client', lambda: FakeClient())
    _create(client, '请核验云端演练合伙企业，由欧阳演练担任法定代表人。')
    assert calls
    payload = json.dumps(calls, ensure_ascii=False)
    assert '云端演练合伙企业' not in payload and '欧阳演练' not in payload


def test_unknown_legal_person_id_is_masked_without_checksum_bypass(client, fake_llm):
    raw_id = '999999999999999999'  # 合成无效证件号，仍须按字段语义脱敏。
    fake_llm['replies'] = [model_reply(content='请提供申请编号。')]
    _create(client, json.dumps({'legalPersonId': raw_id, 'applyAmount': 1234.5}, ensure_ascii=False))
    sent = json.dumps(fake_llm['calls'], ensure_ascii=False)
    assert raw_id not in sent and '1234.5' in sent


def test_same_name_cte_cannot_reach_disallowed_table():
    from app.tools.sql_query import _validate_read_only
    with pytest.raises(ValueError, match="白名单"):
        _validate_read_only("WITH evidence AS (SELECT * FROM main.evidence) SELECT * FROM evidence")


def test_prefixed_and_cte_fact_queries_still_work(client):
    ctx = {"run_id": "run_r02b", "data_version": 1,
           "sql_tables": SCENARIOS["enterprise_dd"].sql_tables}
    for sql in ("SELECT enterprise_id, overdue_count FROM main.enterprise_risk",
                "WITH t AS (SELECT enterprise_id, overdue_count FROM enterprise_risk) SELECT * FROM t"):
        with SessionLocal() as db:
            result, _, _ = registry.execute_tool(db, ctx, "sql_query", json.dumps({"sql": sql}))
        assert result.is_success and result.data["rows"], sql
