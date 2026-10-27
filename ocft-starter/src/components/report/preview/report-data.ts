import type { Evidence } from '@/lib/types'

export type Dict = Record<string, unknown>
export const dict = (value: unknown): Dict => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Dict : {}
export const rows = (value: unknown): Dict[] => Array.isArray(value) ? value.filter((v) => v !== null && typeof v === 'object' && !Array.isArray(v)) as Dict[] : []
export const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
export const number = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null
export function text(value: unknown): string {
  if (value === null || value === undefined || value === '') return '暂无数据'
  if (typeof value === 'boolean') return value ? '是' : '否'
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '暂无数据'
}
/** 维度快照是否为点数制（新版）；旧版为 0–100 分加权重。 */
export const isPointsScorecard = (dimensions: Dict[]) => dimensions.some((d) => number(d.points) !== null)
export const amount = (value: unknown): string => number(value) === null ? (typeof value === 'string' && value ? value : text(value)) : (value as number).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
export const ratio = (value: unknown): string => number(value) === null ? '暂无数据' : `${((value as number) * 100).toFixed(2)}%`

/** 只取当前 run 的落库快照；不重新查企业最新值，也不重新测算或调用模型。 */
export function reportData(evidence: Evidence[]) {
  const calculated = evidence.filter((e) => typeof e.sourceRef.calc === 'string' && Object.keys(dict(e.snapshot)).length)
  const report = dict(calculated.slice().reverse().find((e) => e.sourceRef.calc === 'build_dd_report')?.snapshot)
  const enterpriseIds = new Set(calculated.map((e) => dict(e.snapshot).enterpriseId).filter(Boolean))
  const applicationIds = new Set(calculated.map((e) => dict(e.snapshot).applicationId).filter(Boolean))
  const enterpriseId = report.enterpriseId ?? (enterpriseIds.size === 1 ? [...enterpriseIds][0] : undefined)
  const applicationId = report.applicationId ?? (applicationIds.size === 1 ? [...applicationIds][0] : undefined)
  const ambiguous = enterpriseIds.size > 1 && !report.enterpriseId || applicationIds.size > 1 && !report.applicationId
  const evidenceSources: Record<string, Evidence> = {}
  const get = (calc: string): Dict => {
    if (ambiguous) return {}
    const match = calculated.slice().reverse().find((e) => {
      if (e.sourceRef.calc !== calc) return false
      const snapshot = dict(e.snapshot)
      const keys = dict(e.sourceRef.keys)
      const eid = snapshot.enterpriseId ?? keys.enterpriseId
      const aid = snapshot.applicationId ?? keys.applicationId
      const identified = Boolean((enterpriseId && eid === enterpriseId) || (applicationId && aid === applicationId))
      const asOf = snapshot.asOf
      return identified && (!eid || !enterpriseId || eid === enterpriseId) && (!aid || !applicationId || aid === applicationId)
        && (!asOf || !report.asOf || asOf === report.asOf)
    })
    if (match) evidenceSources[calc] = match
    return dict(match?.snapshot)
  }
  const loanEvidence = ambiguous || !applicationId ? undefined : evidence.slice().reverse().find((e) =>
    e.sourceRef.table === 'loan_application' && !e.sourceRef.calc
    && dict(e.snapshot).applicationId === applicationId
    && (!dict(e.snapshot).enterpriseId || dict(e.snapshot).enterpriseId === enterpriseId))
  const sections = dict(report.sections)
  const finance = get('analyze_financials')
  const credit = get('calc_credit_limit')
  const rating = get('rate_risk')
  // 企业名称取自本次实体识别的查询快照（经输出合规后的值），不另行查库。
  const basic = evidence.map((e) => dict(e.snapshot)).find((s) => s.enterpriseId === enterpriseId && typeof s.enterpriseName === 'string')
  const sources = [...new Set(calculated.map((e) => String(e.sourceRef.calc)))]
  // 口径随本次 build_dd_report 快照落库：enterprise 有建议授信额度、无申请贷款额度。
  const scope = report.scope === 'enterprise' ? 'enterprise' : 'loan'
  return {
    report, enterpriseId, applicationId, ambiguous, sources, scope, evidenceSources,
    loanSnapshot: dict(loanEvidence?.snapshot), loanEvidence,
    enterpriseName: ambiguous ? undefined : basic?.enterpriseName,
    business: get('verify_business_info'),
    overview: dict(sections.overview),
    finance: Object.keys(finance).length ? finance : dict(sections.financialAnalysis),
    opinion: get('scan_public_opinion'),
    fraud: get('detect_fraud_signals'),
    rating: Object.keys(rating).length ? rating : dict(sections.riskAlerts),
    credit: Object.keys(credit).length ? credit : dict(sections.creditSuggestion),
    conditions: strings(credit.conditions ?? dict(sections.riskConditions).conditions),
  }
}

export type ReportData = ReturnType<typeof reportData>

/**
 * 姓名脱敏：保留姓氏，其余字符替换为全角＊（陈建国 → 陈＊＊）。
 * @why 半角 ** 会被模型正文的 Markdown 渲染识别为加粗标记而被吞掉，显示成只剩姓氏。
 */
export const maskPersonName = (name: string): string => name.length <= 1 ? '＊' : name[0] + '＊'.repeat(name.length - 1)

/**
 * 本次快照里出现的自然人姓名（实控人、第一大股东），按长度降序便于整词替换。
 * @why 题目合规要求界面展示与导出文件中的敏感字段脱敏；后端发布前会还原名称，
 *      预览页作为导出载体在前端统一遮蔽，避免模型正文以任意句式写出全名。
 */
export function personNames(data: ReportData): string[] {
  // 后端证据接口若已把姓名字段遮成 ****，这里取不到原名，交由后端口径处理。
  const names = [data.business.actualController, data.business.topShareholder]
    .filter((v): v is string => typeof v === 'string' && v.trim().length >= 2 && !v.includes('*'))
    .map((v) => v.trim())
  return [...new Set(names)].sort((a, b) => b.length - a.length)
}

/** 把文本中出现的已知人员姓名整体替换为脱敏形式。 */
export function maskPersons(value: string, names: string[]): string {
  return names.reduce((out, name) => out.split(name).join(maskPersonName(name)), value)
}

/** 递归遮蔽对象里所有字符串中的人员姓名，键名与数值不变。 */
function maskDeep<T>(value: T, names: string[]): T {
  if (typeof value === 'string') return maskPersons(value, names) as T
  if (Array.isArray(value)) return value.map((v) => maskDeep(v, names)) as T
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value as Dict).map(([k, v]) => [k, maskDeep(v, names)])) as T
  }
  return value
}

/** 报告数据与模型正文统一做姓名脱敏；在渲染前调用，组件内无需逐处处理。 */
export function maskReport<R extends { answer: string | null }>(run: R, data: ReportData): { run: R; data: ReportData } {
  const names = personNames(data)
  if (!names.length) return { run, data }
  return { run: { ...run, answer: run.answer == null ? run.answer : maskPersons(run.answer, names) }, data: maskDeep(data, names) }
}
