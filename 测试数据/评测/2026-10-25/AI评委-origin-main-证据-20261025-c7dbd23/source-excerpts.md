# 固定源码证据摘录

SHA: c7dbd231b955cb7a2dfcf317212773b8cd65eae4

## ocft-backend/app/agent/engine.py:171-196

```text
171: def _finish_with_answer(outcome: RunOutcome, scenario: Scenario,
172:                         content: str | None) -> RunOutcome:
173:     text = outcome._restore((content or "").strip())
174:     if not text:
175:         return _failed(outcome, "llm_unavailable", "模型返回空内容")
176:     outcome.answer = text
177:     _finalize_context(outcome, scenario)
178:     data_calls = [t for t in outcome.traces if t.tool_name != CLARIFY_TOOL]
179:     if data_calls and not outcome.evidence_ids:
180:         # 调用过工具却没拿到任何证据（如查无此申请）：不能算成功结论
181:         return _insufficient(outcome, "调用的工具均未取得数据证据")
182:     missing = _unresolved_not_found(outcome)
183:     if missing:
184:         # @why 用户要找的对象不存在时，即使模型又做了别的检索（拿到了无关证据），
185:         #      也不能把"查无此项"算作成功结论；只看工具返回，不看模型措辞（待办 1-9）
186:         return _insufficient(outcome, "未找到：" + "、".join(missing))
187:     if (not outcome.evidence_ids and scenario.conclusion_pattern
188:             and re.search(scenario.conclusion_pattern, text)):
189:         return _insufficient(outcome, "答案含结论但本次执行没有任何工具证据")
190:     reasons = _confirmation_reasons(outcome, scenario)
191:     if reasons:
192:         outcome.status = NEEDS_CONFIRMATION
193:         outcome.confirmation_reasons = reasons
194:         return outcome
195:     outcome.status = SUCCEEDED
196:     return outcome
```

## ocft-backend/app/agent/scenarios.py:77-108

```text
77:     "enterprise_dd": Scenario(
78:         scenario_id="enterprise_dd",
79:         system_prompt=ENTERPRISE_DD_SYSTEM,
80:         allowed_tools=_DD_TOOLS,
81:         entity_keys=("applicationId", "enterpriseId", "enterpriseName", "customerName"),
82:         # @why 主控正常只调用 run_dd_agents；单环节工具（rate_risk 等）虽不再声明给主控，但注册表仍会执行
83:         #      模型直接点名的已注册工具，所以针对它们的高风险规则保留作兜底，不是死代码
84:         confirmation_rules=(
85:             ConfirmationRule(
86:                 tool_name="rate_risk", field="riskLevel", values=frozenset({"高风险"}),
87:                 reason="评分卡风险评级为高风险，需业务人员确认"),
88:             ConfirmationRule(
89:                 tool_name="calc_credit_limit", field="riskLevel", values=frozenset({"高风险"}),
90:                 reason="额度测算对应高风险，需业务人员确认"),
91:             ConfirmationRule(
92:                 tool_name="build_dd_report", field="riskLevel", values=frozenset({"高风险"}),
93:                 reason="尽调报告风险评级为高风险，需业务人员确认"),
94:             ConfirmationRule(
95:                 tool_name=dd_graph.TOOL_NAME, field="riskLevel", values=frozenset({"高风险"}),
96:                 reason="评级授信 Agent 给出高风险，需业务人员确认"),
97:             ConfirmationRule(
98:                 tool_name=dd_graph.TOOL_NAME, field="needsManualReview", values=frozenset({True}),
99:                 reason="有角色 Agent 降级或失败、评分卡缺少主要依据或额度无法测算，需人工复核"),
100:         ),
101:         conclusion_pattern=r"风险评级|建议额度|尽调结论",
102:         sql_tables=_DD_TABLES,
103:         build_masker=build_masker,
104:         terminal_tools=(dd_graph.TOOL_NAME,),
105:         answer_check=_check_dd_answer,
106:         max_answer_rewrites=_AGENTS.max_rewrites,
107:         max_total_tokens=_AGENTS.max_total_tokens,
108:         thinking=_AGENTS.controller_thinking,
```

## ocft-backend/app/deps.py:32-66

```text
32: def require_actor_ctx(
33:     x_actor_id: str | None = Header(default=None),
34:     authorization: str | None = Header(default=None),
35:     db: Session = Depends(get_db),
36: ) -> ActorContext:
37:     resolved = auth_service.resolve_token(db, _bearer_token(authorization))
38:     if resolved is not None:
39:         user, role = resolved
40:         return ActorContext(actor_id=user.username, role=role)
41:     if x_actor_id and x_actor_id.strip():
42:         return ActorContext(actor_id=x_actor_id.strip(), role=None)
43:     raise ApiError(400, "actor_id_required", "缺少登录凭证或 X-Actor-Id 请求头")
44: 
45: 
46: def require_actor(
47:     ctx: ActorContext = Depends(require_actor_ctx),
48: ) -> str:
49:     """Agent 接口身份：登录 token → username；否则允许演示头 X-Actor-Id。"""
50:     return ctx.actor_id
51: 
52: 
53: def enforce_session_permission(ctx: ActorContext, code: str, *, message: str | None = None) -> None:
54:     """仅对 Bearer 登录会话校验权限；X-Actor-Id 评测调用不拦截。"""
55:     if ctx.role is None:
56:         return
57:     auth_service.require_permission(ctx.role, code, message=message)
58: 
59: 
60: def require_session(
61:     authorization: str | None = Header(default=None),
62:     db: Session = Depends(get_db),
63: ) -> tuple[SysUser, SysRole]:
64:     resolved = auth_service.resolve_token(db, _bearer_token(authorization))
65:     if resolved is None:
66:         raise ApiError(401, "unauthorized", "请先登录")
```

## ocft-backend/app/compliance/citations.py:88-110

```text
88:         found.append(Citation("doc_number", m.group(0), _squash(m.group(0))))
89:     for m in _STANDARD.finditer(text):
90:         found.append(Citation("standard", m.group(0), _squash(m.group(0)).upper()))
91:     return found
92: 
93: 
94: def check_regulation_citations(answer: str, sources: list[str]) -> ComplianceDecision:
95:     """答案中的每条法规引述都必须逐字出现在 sources（本次 run 证据原文）中，否则拦截。
96: 
97:     sources 传本次 run 的证据快照文本；不传用户问题：用户在问题里写的法规同样无法核验，
98:     模型照抄也要拦。"""
99:     citations = find_citations(answer)
100:     if not citations:
101:         return ComplianceDecision(is_clean=True)
102:     haystack = _squash("\n".join(sources or []))
103:     upper = haystack.upper()
104:     for c in citations:
105:         target = upper if c.kind == "standard" else haystack
106:         if c.key and c.key not in target:
107:             return ComplianceDecision(
108:                 is_clean=False, code=CODE, category=CATEGORY, user_message=USER_MESSAGE,
109:                 reason=f"法规引述无法在本次证据中核验（{c.kind}: {c.text[:40]}）")
110:     return ComplianceDecision(is_clean=True)
```

## ocft-backend/app/agent/dd_snapshot.py:26-42

```text
26: _ORG_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司", "集团", "公司")
27: # 简称少于该长度不单独替换：过短的词误伤正常文本
28: _MIN_ALIAS_CHARS = 4
29: # 已知实体先代号化；明确标注但未入库的自由文本字段不能原样外送。
30: # 不猜测无标签的任意中文词，也不遮掉企业编号或正常业务问句。
31: _ENTITY_LABEL = r"(?:法定代表人|法人姓名|法人|实际控制人|实控人|股东姓名|企业名称|公司名称|企业)"
32: _ENTITY_DELIMITERS = r"\r\n，,。；;！？!?、\"'{}\[\]：:"
33: _ENTITY_CODE = re.compile(r"(?:企业|人员|关联方|信用代码|证件号|注册地址)[A-Za-z0-9_-]+|E\d+")
34: _LABELED_ENTITY = re.compile(
35:     r"(" + _ENTITY_LABEL + r"\s*[:：]\s*)("
36:     r"(?:" + _ENTITY_CODE.pattern + r")(?=\s|[" + _ENTITY_DELIMITERS + r"]|$)"
37:     r"|[^" + _ENTITY_DELIMITERS + r"]+?"
38:     r"(?=\s*(?:" + _ENTITY_LABEL + r"\s*[:：]|[" + _ENTITY_DELIMITERS + r"]|$)))")
39: 
40: 
41: @dataclass
42: class Masker:
```

## ocft-backend/app/agent/dd_snapshot.py:85-98

```text
85:             text = pattern.sub(lambda m: self.forward[m.group(0)], text)
86:         return _LABELED_ENTITY.sub(
87:             lambda m: m.group(0) if _ENTITY_CODE.fullmatch(m.group(2).strip())
88:             else m.group(1) + "[已脱敏]", text)
89: 
90:     def mask_obj(self, value):
91:         """JSON 结构逐值替换（只改字符串值，不改键）。"""
92:         if isinstance(value, str):
93:             return self.mask(value)
94:         if isinstance(value, dict):
95:             return {k: self.mask_obj(v) for k, v in value.items()}
96:         if isinstance(value, list):
97:             return [self.mask_obj(v) for v in value]
98:         return value
```

## ocft-backend/app/services/memory_service.py:76-108

```text
76: def view(db: Session, conversation_id: str, actor_id: str) -> dict:
77:     conversation = _owned(db, conversation_id, actor_id)
78:     row = get_memory_row(db, conversation_id)
79:     cutoff = row.history_from_message_id if row else None
80:     total = db.query(func.count(Message.id)).filter(Message.conversation_id == conversation_id).scalar() or 0
81:     carried_q = db.query(func.count(Message.id)).filter(Message.conversation_id == conversation_id)
82:     if cutoff is not None:
83:         carried_q = carried_q.filter(Message.id >= cutoff)
84:     scenario = SCENARIOS.get(conversation.scenario_id or "")
85:     confirmed = (db.query(AnswerConfirmation, AgentRun)
86:                  .join(AgentRun, AgentRun.id == AnswerConfirmation.run_id)
87:                  .filter(AgentRun.conversation_id == conversation_id,
88:                          AnswerConfirmation.action == "confirm")
89:                  .order_by(AnswerConfirmation.created_at).all())
90:     events = (db.query(MemoryEvent).filter(MemoryEvent.conversation_id == conversation_id)
91:               .order_by(MemoryEvent.id.desc()).limit(20).all())
92:     return {
93:         "conversation_id": conversation_id,
94:         "scenario_id": conversation.scenario_id,
95:         "entities": current_entities(db, conversation_id),
96:         "allowed_keys": list(scenario.entity_keys) if scenario else [],
97:         "history_from_message_id": cutoff,
98:         "total_messages": total,
99:         "carried_messages": carried_q.scalar() or 0,
100:         "confirmed_conclusions": [{
101:             "run_id": run.id, "answer_version": conf.answer_version,
102:             "answer": _preview(run.answer), "confirmed_by": conf.actor_id,
103:             "confirmed_at": conf.created_at} for conf, run in confirmed],
104:         "version": row.version if row else 0,
105:         "updated_by": row.updated_by if row else None,
106:         "updated_at": row.updated_at if row else None,
107:         "events": [{"id": e.id, "event_type": e.event_type, "actor_id": e.actor_id,
108:                     "payload": e.payload or {}, "created_at": e.created_at} for e in events],
```

## ocft-backend/app/services/memory_service.py:150-161

```text
150: def correct(db: Session, conversation_id: str, actor_id: str, entities: dict,
151:             expected_version: int | None) -> dict:
152:     """纠正槽位：只改请求里出现的键；空数组表示删除该键。"""
153:     conversation = _owned(db, conversation_id, actor_id)
154:     if not isinstance(entities, dict) or not entities:
155:         raise ApiError(422, "invalid_memory", "entities 不能为空")
156:     scenario = SCENARIOS.get(conversation.scenario_id or "")
157:     allowed = set(scenario.entity_keys) if scenario else set()
158:     unknown = sorted(set(entities) - allowed)
159:     if unknown:
160:         raise ApiError(422, "invalid_memory",
161:                        f"不支持的记忆项 {unknown}，本场景可纠正：{sorted(allowed)}")
```

## ocft-backend/app/services/run_service.py:615-641

```text
615:     返回 (传给模型的 messages, 写入 context_snapshot 的元信息)。
616:     """
617:     limit = settings.context_max_history_messages + settings.context_max_compressed_messages
618:     query = db.query(Message).filter(Message.conversation_id == conversation_id)
619:     cutoff = memory_service.history_from(db, conversation_id)
620:     if cutoff is not None:
621:         # 记忆被清除过：更早的消息不再带入模型（消息本身保留，界面可查看）
622:         query = query.filter(Message.id >= cutoff)
623:     rows = list(reversed(query.order_by(Message.id.desc()).limit(limit).all()))
624:     run_ids = {row.run_id for row in rows if row.run_id}
625:     runs = db.query(AgentRun).filter(AgentRun.id.in_(run_ids)).all() if run_ids else []
626:     snapshots = {run.id: run.context_snapshot or {} for run in runs}
627:     # @why 被合规拦截的提问不再送给模型：否则下一轮模型会"补答"违规问题
628:     blocked = {run.id for run in runs if run.status == T.BLOCKED}
629:     rows = [row for row in rows if row.run_id not in blocked]
630:     items = [ctx.HistoryMessage(
631:         message_id=row.id, role=row.role, content=row.content, run_id=row.run_id,
632:         tool_summaries=snapshots.get(row.run_id, {}).get("toolSummaries", [])
633:         if row.role == "assistant" else []) for row in rows]
634:     # 实体槽位以会话记忆为准（待办 0-6：可被人工纠正 / 清除）；旧会话没有记忆记录时退回最近 run 的快照
635:     entities = memory_service.current_entities(db, conversation_id)
636:     messages, meta = ctx.build_history(
637:         items, entities=entities,
638:         max_recent=settings.context_max_history_messages,
639:         token_budget=settings.context_history_token_budget)
640:     return messages, {**meta, "entities": entities}
641: 
```

## ocft-backend/app/services/run_service.py:655-687

```text
655: def _evidence_texts(db: Session, evidence_ids: list[str]) -> list[str]:
656:     """本次 run 证据快照原文（未掩码），供法规引述核验逐字比对。"""
657:     if not evidence_ids:
658:         return []
659:     rows = db.query(Evidence.snapshot).filter(Evidence.id.in_(evidence_ids)).all()
660:     return [json.dumps(snapshot, ensure_ascii=False, default=str) for (snapshot,) in rows]
661: 
662: 
663: def _apply_outcome(db: Session, run: AgentRun, outcome: engine.RunOutcome,
664:                    actor_id: str, recorder: RunEventRecorder) -> None:
665:     # 输出合规：凡是给用户看的模型文本（结论、澄清问题、证据不足说明）落库/发布前都检查
666:     if outcome.status in _MODEL_TEXT_STATUSES and outcome.answer:
667:         check_started = time.monotonic()
668:         output_decision = check_output(outcome.answer)
669:         if output_decision.is_clean:
670:             # 法规引述门禁（J02）：法名 / 条号 / 文号须能在本次证据原文中逐字找到，否则拦截转人工
671:             output_decision = check_regulation_citations(
672:                 outcome.answer, _evidence_texts(db, outcome.evidence_ids))
673:         recorder.emit("compliance_checked", {"stage": "output",
674:                                              "isClean": output_decision.is_clean,
675:                                              "durationMs": _elapsed_ms(check_started)})
676:         if not output_decision.is_clean:
677:             blocked_payload = {"stage": "output", "code": output_decision.code,
678:                                "category": output_decision.category,
679:                                "reason": _redacted(output_decision.reason)}
680:             _audit(db, run.id, "compliance_blocked", actor_id, blocked_payload)
681:             recorder.emit("compliance_blocked", {"payload": blocked_payload})
682:             outcome.status = T.BLOCKED
683:             outcome.answer = None
684:             outcome.error_code = output_decision.code
685:             outcome.error_message = output_decision.user_message
686:         else:
687:             outcome.answer, out_counts = redact_pii(outcome.answer)
```

## ocft-backend/app/services/workspace_service.py:1-10

```text
1: """报告列表：尽调产出物的建档与检索。
2: 
3: @why 报告本身不需要状态：确认 / 驳回 / 归档这套流转已去掉，审核结论记在贷款申请
4:       （loan_application.status：待处理 → 待审核 → 审核通过 / 审核不通过），报告只表示
5:       「这次 run 产出了一份报告」。正文不复制，档案只用 runId 指向原报告与证据，
6:       避免同一结论出现两个版本。
7: """
8: from __future__ import annotations
9: 
10: import hashlib
```

## ocft-backend/app/services/workspace_service.py:54-83

```text
54:     """
55:     if not application_id:
56:         return
57:     loan = (db.query(LoanApplication)
58:             .filter(LoanApplication.application_id == application_id).first())
59:     if loan is not None and (loan.status or "pending") == "pending":
60:         loan.status = "pending_review"
61: 
62: 
63: def register_asset(db: Session, run, actor_id: str) -> WorkspaceAsset | None:
64:     """run 完成后建档（同一 run 只建一次），并把该申请的贷款状态推进到待审核。
65: 
66:     @why 只在有完整五部分报告的终态建档：追问、失败、澄清没有产出物，不制造空档案；
67:          证据条数取本次 run 实际落库数，供检索时判断材料是否齐全。
68:     @why status / version 是历史列，保留默认值只为兼容既有库，不再对外暴露。
69:     """
70:     existing = db.query(WorkspaceAsset).filter(WorkspaceAsset.run_id == run.id).first()
71:     if existing is not None:
72:         return existing
73:     answer = run.answer or ""
74:     if not all(marker in answer for marker in REPORT_MARKERS):
75:         return None
76:     entities = (run.context_snapshot or {}).get("entities") or {}
77:     application_id = next((items[0] for key, items in entities.items()
78:                            if key == "applicationId" and items), None)
79:     enterprise_id = next((items[0] for key, items in entities.items()
80:                           if key == "enterpriseId" and items), None)
81:     evidence_count = db.query(Evidence).filter(Evidence.run_id == run.id).count()
82:     asset = WorkspaceAsset(
83:         id=_new_id(), scenario_id=run.scenario_id,
```

## ocft-backend/app/tools/dd_calc.py:304-345

```text
304: def _decay(event_date: str | None, as_of: str | None, per_year: float) -> float:
305:     start, end = _year_of(event_date), _year_of(as_of)
306:     if start is None or end is None:
307:         return 1.0
308:     return per_year ** max(end - start, 0)
309: 
310: 
311: def scan_public_opinion(bundle: dict, cfg: dict, as_of: str | None) -> dict:
312:     sentiment = cfg.get("sentiment") or {}
313:     impact = cfg.get("impact") or {}
314:     decay = _num(cfg.get("decay_per_year")) or 0.85
315:     closed = set(cfg.get("closed_statuses") or [])
316:     defendants = set(cfg.get("defendant_roles") or [])
317:     lawsuit_weights = cfg.get("lawsuit") or {}
318:     events = []
319:     score = _num(cfg.get("base_score")) or 0
320:     for row in bundle["opinions"]:
321:         delta = sentiment.get(row.get("sentiment"), 0) * impact.get(row.get("impact_level"), 1)
322:         weight = _decay(row.get("event_date"), as_of, decay)
323:         points = delta * weight
324:         score += points
325:         events.append({
326:             "eventId": row.get("event_id"),
327:             "eventDate": row.get("event_date"),
328:             "eventType": row.get("event_type"),
329:             "eventContent": row.get("event_content"),
330:             "eventSource": row.get("event_source"),
331:             "sentiment": row.get("sentiment"),
332:             "impactLevel": row.get("impact_level"),
333:             "points": _round(points, 2),
334:         })
335:     lawsuits = []
336:     open_defendant_amount = 0.0
337:     for row in bundle["lawsuits"]:
338:         is_closed = row.get("case_status") in closed
339:         is_defendant = row.get("litigation_role") in defendants
340:         if not is_closed and is_defendant:
341:             key = "open_defendant"
342:             amount = _num(row.get("amount")) or 0
343:             open_defendant_amount += amount
344:         elif not is_closed:
345:             key = "open_other"
```

## ocft-backend/app/tools/dd_calc.py:811-847

```text
811: def _credit_steps(inputs: dict, policy: dict, amount: Decimal, level: str,
812:                   is_blocked: bool, anomalies: list[dict]) -> tuple[list[dict], str]:
813:     revenue = max(inputs["revenue"], Decimal(0)) * policy["revenue"]
814:     equity = max(inputs["ownersEquity"], Decimal(0)) * policy["equity"]
815:     capacity = min(revenue, equity)
816:     rated = capacity * policy["rating"]
817:     ceiling = Decimal(0) if is_blocked else min(amount, rated)
818:     # @why 多项重大财务异常（反欺诈线索）不一票否决，而是审慎压降：区间整体按折减比例测算
819:     discounted = len(anomalies) >= policy["discountMinHits"]
820:     low_ratio = policy["discountLow"] if discounted else 1 - policy["band"]
821:     high_ratio = policy["discountHigh"] if discounted else Decimal(1)
822:     # @why 取整档位按金额分段：大额按大步长报价（如 2000 万以上按 500 万），小额按基础步长
823:     large = policy["largeThreshold"] is not None and ceiling >= policy["largeThreshold"]
824:     step = policy["largeStep"] if large else policy["step"]
825:     low = _floor_step(ceiling * low_ratio, step)
826:     high = _floor_step(ceiling * high_ratio, step)
827:     if low > high:
828:         low = high
829:     suggested = str(low) if low == high else f"{low}-{high}"
830:     values = [
831:         ("营收口径上限", f"营业收入 × {policy['revenue']}", revenue),
832:         ("净资产口径上限", f"max(所有者权益, 0) × {policy['equity']}", equity),
833:         ("财务能力取小", "min(营收口径, 净资产口径)，保留零值", capacity),
834:         ("评级调整", f"财务能力 × {level}系数{policy['rating']}", rated),
835:         ("申请额封顶", "min(申请额, 评级后能力)；高风险/否决为0", ceiling),
836:     ]
837:     steps = [{"step": name, "formula": formula, "value": float(value)}
838:              for name, formula, value in values]
839:     steps.append({"step": "重大财务异常折减",
840:                   "formula": (f"命中 {len(anomalies)} 项（≥{policy['discountMinHits']} 项折减）："
841:                               f"区间 = 硬上限 × [{low_ratio}, {high_ratio}]"),
842:                   "value": [item["code"] for item in anomalies]})
843:     steps.append({"step": "输出区间", "formula": f"下界=硬上限×{low_ratio}，上界=硬上限×{high_ratio}；"
844:                   f"均向下取整至{step}万元", "value": suggested})
845:     return steps, suggested
846: 
847: 
```

## ocft-backend/app/config.py:14-34

```text
14: REQUIRED_MODEL = "deepseek-v4.1-flash"
15: 
16: # 同一模型（V4.1 Flash）在不同接口上的 API 模型 ID；不在白名单内的任何值
17: # 一律拒绝启动，防止静默换成别的模型
18: ALLOWED_API_MODELS = frozenset({"deepseek-flash", REQUIRED_MODEL})
19: DEFAULT_API_MODEL = "deepseek-flash"
20: 
21: 
22: class Settings(BaseSettings):
23:     model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
24: 
25:     llm_base_url: str = "https://api.deepseek.com"
26:     llm_api_key: str = ""
27:     # 产品身份：比赛指定模型，记录在 run 与健康检查中，唯一合法值
28:     llm_model: str = REQUIRED_MODEL
29:     # 线上 API 的模型 ID：DeepSeek 公共接口对 V4.1 Flash 使用 deepseek-flash；
30:     # 若使用主办方提供的接口，按其文档改成 deepseek-v4.1-flash。仅允许白名单内的值。
31:     llm_api_model: str = DEFAULT_API_MODEL
32: 
33:     @field_validator("llm_model", "llm_api_model", mode="before")
34:     @classmethod
```

## ocft-backend/app/config.py:61-68

```text
61: 
62:     # SSE 无新事件时的心跳间隔（秒），防止代理断开空闲连接
63:     sse_keepalive_seconds: float = 15.0
64: 
65:     # 样本数据版本：灌入种子时递增，evidence 据此标记数据快照版本
66:     data_version: int = 1
67:     csv_import_max_bytes: int = 10 * 1024 * 1024
68:     csv_import_max_rows: int = 20000
```

## submission/pack_dd04.py:307-333

```text
307:         f"{prefix}_截图01_尽调报告_完整.png": DD04 / "artifacts" / "截图01_尽调报告_完整.png",
308:         f"{prefix}_截图02_财务分析.png": DD04 / "artifacts" / "截图02_财务分析.png",
309:         f"{prefix}_截图03_风险提示与反欺诈.png": DD04 / "artifacts" / "截图03_风险提示与反欺诈.png",
310:         f"{prefix}_截图04_自然语言问询.png": DD04 / "artifacts" / "截图04_自然语言问询.png",
311:     }
312:     missing: list[str] = []
313:     for dest_name, src in optional_map.items():
314:         if not _copy_if_exists(src, staging / dest_name):
315:             missing.append(dest_name)
316: 
317:     appendix = staging / "附录"
318:     appendix.mkdir(exist_ok=True)
319:     appendix_map = {
320:         f"{prefix}_尽调报告样例_E001.pdf": DD04 / "artifacts" / "尽调报告样例_E001.pdf",
321:         f"{prefix}_尽调报告样例_E001.md": DD04 / "artifacts" / "尽调报告样例_E001.md",
322:         f"{prefix}_演示脚本.md": ROOT / "docs" / "60-pitch" / "演示脚本.md",
323:     }
324:     for dest_name, src in appendix_map.items():
325:         if not _copy_if_exists(src, appendix / dest_name):
326:             missing.append(f"附录/{dest_name}")
327: 
328:     required_always = [
329:         "README.md", "manifest.yaml",
330:         f"{prefix}_可运行系统包.zip",
331:         f"{prefix}_团队与元信息表.xlsx",
332:         f"第三方声明/{prefix}_第三方组件与License声明.md",
333:         f"系统输出/{prefix}_公开测评集结果.csv",
```

## contracts/agent-api.md:294-320

```text
294: 页面名「尽调报告」（评审维度②的资产档案），接口路径与字段沿用 `assets` 命名，避免为改名动契约和表结构。
295: 
296: **报告本身没有状态**：不做确认 / 驳回 / 归档，因此不存在状态变更接口；审核结论记在贷款申请（`loan_application.status`：待处理 → 待审核 → 审核通过 / 审核不通过）。
297: 
298: 完成的完整尽调 run（正文含五部分报告）自动建档，同一 run 只建一次；追问、失败、澄清不建档。建档时若该申请的贷款状态仍为 `pending`（待处理），同一事务内推进为 `pending_review`（待审核），已审核的申请不覆盖。档案只指向 `runId`，正文与证据仍以 run / evidence 为准。
299: 
300: `GET /api/agent/assets?keyword=&applicationId=&enterpriseId=&kind=&limit=&offset=`
301: 
302: ```json
303: { "assets": [ { "id": "ast_…", "scenarioId": "enterprise_dd", "applicationId": "LA001",
304:                 "enterpriseId": "E001", "enterpriseName": "企业事实表中的名称", "conversationId": "…", "runId": "run_…",
305:                 "kind": "report", "title": "LA001 企业信贷尽调报告",
306:                 "applyAmount": 3000, "reportGeneratedAt": "…Z",
307:                 "summary": "尽调结论：…", "evidenceCount": 9, "contentSha256": "…",
308:                 "createdBy": "eval_runner", "createdAt": "…Z", "updatedAt": "…Z" } ],
309:   "total": 1, "limit": 30, "offset": 0, "hasMore": false }
310: ```
311: 
312: `GET /api/agent/assets/{assetId}` 返回同一投影；不存在 404 `not_found`。
313: 
314: `enterpriseName` 为 `string | null`，读取时由企业事实表按 `enterpriseId` 关联，新旧档案均适用；企业资料缺失时为 null，不丢弃档案。关键词同时匹配企业名称，过滤后再分页、计数。页面使用中文名称生成展示标题，缺失时明确提示未登记；`title` 仍保留建档时标题，`runId` 仍用于原报告链接，界面正文不直接显示内部运行标识。
315: 
316: 展示补充字段：`applyAmount: number | null` 为该 run 已保存的 `build_dd_report.creditSuggestion.applyAmount`（优先）或 `calc_credit_limit.applyAmount` 证据快照，单位万元；缺失返回 null，不从当前申请表回填历史金额。`reportGeneratedAt: string` 为关联 run 的 finishedAt，旧数据缺失时使用档案 createdAt，输出 ISO 8601 带 Z，不使用 updatedAt。列表与详情一致。
317: 
318: 权限：报告列表与详情需 `confirm` 权限（登录会话校验；`X-Actor-Id` 评测调用不拦截）。已建档报告关联的 `GET /runs/{runId}`、`/evidence`、`/events`、`/audit` 不再限制 owner，进入报告即可查看轨迹与证据；未建档的普通对话 run 仍只有 owner 可看，越权 403。
319: 
320: 表内 `status` / `version` / `archived_at` 与 `workspace_asset_events` 为历史列，保留以兼容既有库与历史行，不再对外返回、也不再有写接口。
```

## ocft-backend/app/tools/sql_query.py:58-107

```text
58: # 列级黑名单：白名单表里与评测答案一致的预存结论列（ADR-0008 决策 1）。
59: # 显式引用（SELECT / WHERE / ORDER BY 等任意位置）直接拒绝；SELECT * 的结果里剔除该列。
60: _FORBIDDEN_COLUMNS = frozenset({"risk_level_summary"})
61: 
62: 
63: def _referenced_tables(stmt: exp.Expression) -> set[str]:
64:     """提取语句引用的真实表名（小写；CTE 别名不是表，剔除）。"""
65:     cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
66:     return {t.name.lower() for t in stmt.find_all(exp.Table)
67:             if t.name.lower() not in cte_names}
68: 
69: 
70: def _validate_read_only(sql: str, allowed: frozenset[str] = _ALLOWED_TABLES) -> set[str]:
71:     """Guard（语法树级）：单条只读语句 + 涉及表全在白名单。
72: 
73:     allowed：本次可查的表（场景子集，必须是全局白名单的子集）。
74:     返回涉及的表名集合；违规抛 ValueError（plain 函数契约）。
75:     """
76:     allowed = allowed & _ALLOWED_TABLES
77:     stripped = sql.strip().rstrip(";").strip()
78:     if not stripped:
79:         raise ValueError("SQL 为空")
80:     if ";" in stripped:
81:         raise ValueError("不允许多语句")
82:     matched = _FORBIDDEN_FUNCTIONS.search(stripped)
83:     if matched:
84:         raise ValueError(f"检测到危险函数 {matched.group()!r}，sql_query 只允许只读查询")
85:     try:
86:         statements = [s for s in sqlglot.parse(stripped) if s is not None]
87:     except ParseError as exc:
88:         raise ValueError(f"SQL 语法无法解析: {exc}") from exc
89:     if len(statements) != 1:
90:         raise ValueError("不允许多语句")
91:     stmt = statements[0]
92:     if not isinstance(stmt, _ALLOWED_STATEMENT_TYPES):
93:         raise ValueError(f"仅支持只读查询（SELECT/WITH/UNION/DESCRIBE），"
94:                          f"当前语句类型为 {type(stmt).__name__}")
95:     tables = _referenced_tables(stmt)
96:     illegal = sorted(tables - allowed)
97:     if illegal:
98:         raise ValueError(f"表不在白名单内: {', '.join(illegal)}；"
99:                          f"当前可查 {', '.join(sorted(allowed))}")
100:     # @why 也覆盖 WHERE / GROUP BY 里的引用：按该列过滤同样能把答案带出来
101:     blocked = sorted({c.name.lower() for c in stmt.find_all(exp.Column)} & _FORBIDDEN_COLUMNS)
102:     if blocked:
103:         raise ValueError(f"列不可查询: {', '.join(blocked)}")
104:     return tables
105: 
106: 
107: def scenario_tables(run_ctx: dict) -> frozenset[str]:
```

## ocft-backend/app/tools/sql_query.py:145-160

```text
145: def _execute(sql: str, engine) -> tuple[list[dict], bool]:
146:     """在 engine 上执行只读 SQL：fetchmany 到上限即停（控内存）。
147: 
148:     返回 (行, 是否截断)；超时抛 ValueError（结果丢弃，诚实失败）。
149:     """
150:     started = time.monotonic()
151:     with engine.connect() as conn:
152:         rows = [{_to_camel(column): _jsonable(value) for column, value in row.items()
153:                  if str(column).lower() not in _FORBIDDEN_COLUMNS}
154:                 for row in conn.execute(text(sql)).mappings().fetchmany(_MAX_ROWS + 1)]
155:     elapsed = time.monotonic() - started
156:     if elapsed > _MAX_SECONDS:
157:         raise ValueError(f"查询耗时 {elapsed:.1f}s 超过 {_MAX_SECONDS:.0f}s 上限，结果已丢弃")
158:     truncated = len(rows) > _MAX_ROWS
159:     return (rows[:_MAX_ROWS] if truncated else rows), truncated
160: 
```

## .gitattributes:24-30

```text
24: 测试数据/评测/2026-10-24/** export-ignore
25: # 所有被替代的方案、评审与测试快照均不进入评委系统包；保留归档说明作为导航
26: docs/90-archive/** export-ignore
27: docs/90-archive/README.md -export-ignore
28: 
29: # 演示视频 23.6MB：提交包需要，但不重复打进可运行系统包（外层 assemble 从 artifacts 取）
30: submission/dd04/artifacts/*.mp4 export-ignore
```
