/**
 * 将 build_dd_report 结构化结果整理为可导出文本 / JSON。
 * 数字与结论均来自工具返回，不在前端重算。
 */
import { downloadAnswerDocx } from '@/lib/answer-export'

type Dict = Record<string, unknown>

function isDict(value: unknown): value is Dict {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function text(value: unknown, fallback = '—'): string {
  if (value == null || value === '') return fallback
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

function listLines(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    if (isDict(item)) return text(item.detail ?? item.code ?? item.name ?? JSON.stringify(item))
    return text(item)
  }).filter(Boolean)
}

/** 把工具 JSON 转成与对话报告相近的章节正文，供 Word 导出。 */
export function ddReportToMarkdown(data: Dict): string {
  const sections = isDict(data.sections) ? data.sections : {}
  const overview = isDict(sections.overview) ? sections.overview : {}
  const finance = isDict(sections.financialAnalysis) ? sections.financialAnalysis : {}
  const risk = isDict(sections.riskAlerts) ? sections.riskAlerts : {}
  const credit = isDict(sections.creditSuggestion) ? sections.creditSuggestion : {}
  const conditions = isDict(sections.riskConditions) ? sections.riskConditions : {}
  // 企业口径报告没有额度章节：导出同样不写额度建议，避免把主体尽调导成贷款报告。
  const hasCredit = Object.keys(credit).length > 0

  const findings = listLines(overview.findings)
  const years = Array.isArray(finance.years) ? finance.years.filter(isDict) : []
  const yearLines = years.map((row) => {
    const year = text(row.year)
    const metrics = isDict(row.metrics) ? row.metrics : row
    return `- ${year}：${Object.entries(metrics)
      .filter(([key]) => key !== 'year' && key !== 'metrics')
      .slice(0, 8)
      .map(([key, value]) => {
        if (isDict(value) && 'value' in value) return `${key}=${text(value.value)}`
        return `${key}=${text(value)}`
      })
      .join('，')}`
  })

  const conditionLines = listLines(conditions.conditions)
  const assumptionLines = listLines(credit.assumptions)
  const vetoes = listLines(risk.vetoes)
  const fraudHits = listLines(risk.fraudHits)
  const opinionLabels = listLines(risk.opinionLabels)

  const parts = [
    '# 企业概况',
    `企业编号：${text(overview.enterpriseId ?? data.enterpriseId)}`,
    `行业：${text(overview.industry)}`,
    `经营状态：${text(overview.businessStatus)}`,
    `成立日期：${text(overview.establishDate)}`,
    findings.length ? `工商发现：\n${findings.map((line) => `- ${line}`).join('\n')}` : '工商发现：无',
    '',
    '# 财务分析',
    `单位：${text(finance.unit)}`,
    yearLines.length ? yearLines.join('\n') : '暂无分年财务摘要',
    '',
    '# 风险提示',
    `风险评级：${text(risk.riskLevel ?? data.riskLevel)}`,
    `评分：${text(risk.score)}`,
    `一票否决：${vetoes.length ? vetoes.join('、') : '无'}`,
    `反欺诈命中：${fraudHits.length ? fraudHits.join('、') : '无'}`,
    `舆情标签：${opinionLabels.length ? opinionLabels.join('、') : '无'}`,
    `需人工复核：${text(risk.needsManualReview)}`,
    ...(hasCredit ? [
      '',
      '# 额度建议',
      `建议额度：${text(credit.suggestedCreditAmount ?? data.suggestedCreditAmount)}${text(credit.unit, '')}`,
      `期限（月）：${text(credit.termMonths)}`,
      `利率方向：${text(credit.rateDirection)}`,
      `担保方式：${text(credit.guaranteeType)}`,
      assumptionLines.length ? `假设：\n${assumptionLines.map((line) => `- ${line}`).join('\n')}` : '',
    ] : []),
    '',
    '# 风控条件',
    conditionLines.length ? conditionLines.map((line) => `- ${line}`).join('\n') : '无附加条件',
    '',
    '## 尽调结论',
    text(data.dueDiligenceConclusion, '暂无结论摘要'),
  ]
  return parts.filter((line) => line !== undefined).join('\n')
}

export function downloadDdReportDocx(data: Dict): void {
  const answer = ddReportToMarkdown(data)
  const eid = text(data.enterpriseId, 'enterprise')
  const aid = text(data.applicationId, '')
  downloadAnswerDocx(answer, {
    question: aid ? `尽调报告 ${eid} / ${aid}` : `尽调报告 ${eid}`,
    runId: null,
  })
}

export function downloadDdReportJson(data: Dict): void {
  const eid = text(data.enterpriseId, 'enterprise')
  const aid = text(data.applicationId, 'report')
  const blob = new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `尽调报告-${eid}-${aid}.json`
  link.click()
  URL.revokeObjectURL(url)
}
