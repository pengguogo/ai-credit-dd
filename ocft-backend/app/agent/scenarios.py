"""场景注册 — 当前比赛只保留企业智能信贷尽调。"""
from dataclasses import dataclass, field
from typing import Callable

from . import dd_graph
from .dd_roles import load_agents_config, role_skills
from .dd_snapshot import build_masker


@dataclass(frozen=True)
class ConfirmationRule:
    """高风险结论需业务确认：本次 run 中 tool_name 成功返回的 data[field] 命中 values 时，
    终态为 needs_confirmation。判定只看运行时工具结果，不读任何评测标签。"""
    tool_name: str
    field: str
    values: frozenset[str]
    reason: str


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    system_prompt: str
    allowed_tools: list[str]
    entity_keys: tuple[str, ...] = ()
    confirmation_rules: tuple[ConfirmationRule, ...] = field(default_factory=tuple)
    conclusion_pattern: str | None = None
    # 为 True 时，本次没有任何工具证据的普通回答一律判证据不足（不靠关键词识别结论）
    require_evidence: bool = False
    # 能力外引导（仅 require_evidence 场景生效）：本次没调用任何数据工具、且用户问题不命中
    # business_intent_pattern 时，以固定的 guide_message 结束为 needs_clarification。
    # 两者任一为 None 时不启用，行为与原证据不足门禁一致。
    guide_message: str | None = None
    business_intent_pattern: str | None = None
    sql_tables: tuple[str, ...] = ()
    # 以下为可选扩展点（ADR-0008），缺省时场景行为与单 Agent 工具循环完全一致
    # 敏感名称代号化：db → Masker；外送模型的全部内容先 mask，工具入参先 unmask 再查库
    build_masker: Callable | None = None
    # 终止工具：成功结果带 finalAnswer 时直接以它作为最终答案；带 terminalError 时以失败结束
    terminal_tools: tuple[str, ...] = ()
    # 发布前校验：(text, tool_data, evidence_ids) -> (text, issues)；有问题时带清单重写
    answer_check: Callable | None = None
    max_answer_rewrites: int = 1
    # 场景级 run 累计 token 上限；None 用全局 run_max_total_tokens
    max_total_tokens: int | None = None
    # 主控工具循环的模型推理开关；None 沿用接口默认（开启）
    thinking: bool | None = None


# 主控 Agent 的提示词与角色划分都来自 scenarios/dd04/（agents.yaml + prompts/），改配置不改代码。
# @why 进程启动时读一次：Scenario 是不可变注册项；角色侧提示词每次调度都重新读取。
_AGENTS = load_agents_config()
ENTERPRISE_DD_SYSTEM = _AGENTS.controller_prompt
# 六个角色的运行时 Skill（scenarios/dd04/skills/）：启动时校验齐全，缺失或格式错误直接失败
DD_ROLE_SKILLS = role_skills()

# 主控只做定位、调度和追问成文：六个专业环节由 run_dd_agents 调度的角色 Agent 完成（ADR-0008）。
# 单环节计算工具仍注册在工具表里（评测与单测直接调用），但不再声明给主控。
_DD_TOOLS = [
    "get_loan_application",
    "find_enterprise",
    dd_graph.TOOL_NAME,
    "sql_query",
]


def _check_dd_answer(text: str, tool_data: list, evidence_ids: list[str]):
    return dd_graph.check_answer(text, tool_data, evidence_ids)

# @why 问候、闲聊、能力外问题不该显示“证据不足”，改给固定引导（不用模型原文，保证不夹带业务断言）。
#      只按用户输入判定且宁严勿宽：出现任何业务信号（编号、企业代号、信贷/财务词）都仍走证据不足门禁。
_DD_GUIDE_MESSAGE = (
    "您好，我是企业信贷尽调智能体，专注企业贷款申请的尽职调查，暂不处理与尽调无关的问题。\n\n"
    "我可以帮您：\n"
    "- 对一笔贷款申请做完整尽调，给出风险评级、建议额度和尽调结论\n"
    "- 分项查看财报解析、工商核验、舆情扫描、反欺诈检测、额度测算\n"
    "- 查询企业的贷款申请、财务、股东、涉诉、担保、关联方等数据\n\n"
    "请告诉我企业名称或编号、贷款申请编号，例如："
    "「对某企业的贷款申请做尽调」「这家企业近三年的资产负债率怎么样」。"
)
_DD_BUSINESS_INTENT = (
    r"[A-Za-z]{1,4}-?\d{2,}"
    r"|企业|公司|集团|客户|申请|贷款|借款|授信|额度|放款|拒贷|评级|风险|尽调|调查"
    r"|担保|抵押|逾期|涉诉|诉讼|被执行|失信|限高|舆情|财报|财务|营收|收入|利润|负债"
    r"|资产|现金流|应收|股东|关联|法人|法定代表人|工商|征信|欺诈|报告"
)

_DD_TABLES = (
    "loan_application",
    "enterprise_basic",
    "enterprise_shareholder",
    "enterprise_finance",
    "enterprise_lawsuit",
    "enterprise_public_opinion",
    "enterprise_related",
    "enterprise_guarantee",
    "enterprise_risk",
    "schema_relationships",
)

SCENARIOS: dict[str, Scenario] = {
    "enterprise_dd": Scenario(
        scenario_id="enterprise_dd",
        system_prompt=ENTERPRISE_DD_SYSTEM,
        allowed_tools=_DD_TOOLS,
        entity_keys=("applicationId", "enterpriseId", "enterpriseName", "customerName"),
        # @why 主控正常只调用 run_dd_agents；单环节工具（rate_risk 等）虽不再声明给主控，但注册表仍会执行
        #      模型直接点名的已注册工具，所以针对它们的高风险规则保留作兜底，不是死代码
        confirmation_rules=(
            ConfirmationRule(
                tool_name="rate_risk", field="riskLevel", values=frozenset({"高风险"}),
                reason="评分卡风险评级为高风险，需业务人员确认"),
            ConfirmationRule(
                tool_name="calc_credit_limit", field="riskLevel", values=frozenset({"高风险"}),
                reason="额度测算对应高风险，需业务人员确认"),
            ConfirmationRule(
                tool_name="build_dd_report", field="riskLevel", values=frozenset({"高风险"}),
                reason="尽调报告风险评级为高风险，需业务人员确认"),
            ConfirmationRule(
                tool_name=dd_graph.TOOL_NAME, field="riskLevel", values=frozenset({"高风险"}),
                reason="评级授信 Agent 给出高风险，需业务人员确认"),
            ConfirmationRule(
                tool_name=dd_graph.TOOL_NAME, field="needsManualReview", values=frozenset({True}),
                reason="有角色 Agent 降级或失败、评分卡缺少主要依据或额度无法测算，需人工复核"),
        ),
        conclusion_pattern=r"风险评级|建议额度|尽调结论",
        require_evidence=True,
        guide_message=_DD_GUIDE_MESSAGE,
        business_intent_pattern=_DD_BUSINESS_INTENT,
        sql_tables=_DD_TABLES,
        build_masker=build_masker,
        terminal_tools=(dd_graph.TOOL_NAME,),
        answer_check=_check_dd_answer,
        max_answer_rewrites=_AGENTS.max_rewrites,
        max_total_tokens=_AGENTS.max_total_tokens,
        thinking=_AGENTS.controller_thinking,
    ),
}

DEFAULT_SCENARIO_ID = "enterprise_dd"
