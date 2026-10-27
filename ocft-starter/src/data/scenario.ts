/**
 * 场景说明类静态内容（AGENTS.md：src/data/ 只放说明，不放业务数据与结论）。
 * 示例问题只是提问模板，答案全部由后端 Agent 实时取证生成。
 */
import { DEFAULT_ENTERPRISE_QUESTION } from '@/lib/enterprise-input'

export interface Suggestion {
  /** 这条示例要走到的工具；合规拦截没有对应工具。 */
  tool: string
  question: string
}

export interface ScenarioMeta {
  id: string
  name: string
  title: string
  description: string
  agentName: string
  emptyTitle: string
  emptyDescription: string
  placeholder: string
  sessionHint: string
  mainSuggestions: Suggestion[]
  edgeSuggestions: Suggestion[]
}

export const SCENARIO_ID = 'enterprise_dd'

export const SCENARIOS: ScenarioMeta[] = [
  {
    id: SCENARIO_ID,
    name: '企业尽调',
    title: '企业智能信贷尽调',
    description: '选择一笔贷款申请，系统完成财报解析、工商核验、舆情扫描、反欺诈检测、额度测算并生成五部分尽调报告。数字来自工具，可继续追问。',
    agentName: '尽调主控',
    emptyTitle: '从一笔贷款申请开始',
    emptyDescription: '点贷款编号：本笔贷款尽调（含申请额度与建议授信额度）。点企业编号：企业主体尽调（含建议授信额度，不含申请额度）。',
    placeholder: '例如：对企业E001 进行尽调并生成尽调报告（Enter 发送，Shift+Enter 换行）',
    sessionHint: '本会话会记住查到的申请和企业',
    // 对齐 question_public 的 question 列，并带上对应企业编号以便定位。不含参考答案。
    mainSuggestions: [
      { tool: 'build_dd_report', question: DEFAULT_ENTERPRISE_QUESTION },
      { tool: 'analyze_financials', question: '企业 E003：该企业的资产负债率是多少？是否存在偿债风险？' },
      { tool: 'detect_fraud_signals', question: '企业 E010：该企业是否存在财务异常或欺诈线索？' },
      { tool: 'calc_credit_limit', question: '企业 E009：请测算该企业的建议授信额度' },
      { tool: 'scan_public_opinion', question: '企业 E006：该企业的舆情和诉讼风险如何？' },
      { tool: 'analyze_financials', question: '企业 E002：分析该企业近三年成长性' },
      { tool: 'build_dd_report', question: '贷款申请 LA007：该企业适合发放本笔贷款吗？给出尽调结论' },
      { tool: 'analyze_financials', question: '企业 E004：该企业的营运能力如何？' },
      { tool: 'scan_public_opinion', question: '企业 E003：扫描该企业的舆情事件并评估影响' },
      { tool: 'verify_business_info', question: '企业 E010：核查该企业的关联企业和对外担保情况' },
    ],
    edgeSuggestions: [
      { tool: 'request_clarification', question: '帮我看看那家企业能不能贷款' },
      { tool: 'request_clarification', question: '评估贷款申请 LA999 的尽调结论' },
      { tool: '合规拦截', question: '怎么洗钱不被发现' },
    ],
  },
]

export function getScenario(id: string): ScenarioMeta {
  return SCENARIOS.find((item) => item.id === id) ?? SCENARIOS[0]
}

/** 业务数据列表点贷款编号：本笔贷款尽调（列申请额与建议额度）。 */
export function applicationQuestion(applicationId: string): string {
  return `对审批 ${applicationId} 进行尽调并生成尽调报告`
}

export function firstEnterpriseExample(_scenario?: ScenarioMeta): string {
  return DEFAULT_ENTERPRISE_QUESTION
}
