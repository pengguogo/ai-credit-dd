/** 左侧点企业编号时，按输入框现状生成填入文案（气泡与实际填入一致）。 */

/** 企业主体尽调：含建议授信额度，不含申请贷款额度（与贷款申请口径区分）。 */
export const DEFAULT_ENTERPRISE_QUESTION =
  '对企业E001 进行尽调并生成尽调报告'

/** 把文案里的「企业 Exxx / 对企业Exxx」换成新企业编号；没有该片段时用默认尽调问句。 */
export function withEnterpriseId(template: string, enterpriseId: string): string {
  const id = enterpriseId.trim()
  if (!id) return template
  if (/企业\s*E\d+/i.test(template)) {
    return template.replace(/(企业\s*)E\d+/gi, `$1${id}`)
  }
  return DEFAULT_ENTERPRISE_QUESTION.replace(/E001/i, id)
}

/**
 * 输入框有内容且含「企业 Exxx」→ 只替换企业编号；
 * 输入框为空 → 用默认尽调问句并换成当前企业；
 * 其它情况 → 落到默认尽调问句（已换企业）。
 */
export function applyEnterpriseToQuestion(
  input: string,
  enterpriseId: string,
  emptyExample: string = DEFAULT_ENTERPRISE_QUESTION,
): string {
  const id = enterpriseId.trim()
  if (!id) return input
  const trimmed = input.trim()
  if (!trimmed) {
    return withEnterpriseId(emptyExample, id)
  }
  if (/企业\s*E\d+/i.test(trimmed)) {
    return trimmed.replace(/(企业\s*)E\d+/gi, `$1${id}`)
  }
  return withEnterpriseId(emptyExample, id)
}
