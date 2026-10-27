/** 业务展示文案；不推导授信结论，不修改已存报告或证据。 */
export function generationLabel(status: string): string {
  if (status === 'succeeded') return '已生成'
  if (status === 'needs_confirmation') return '已生成 · 待业务确认'
  if (status === 'failed') return '生成失败'
  return '尚未生成'
}

export function approvalLabel(status: unknown): string {
  const labels: Record<string, string> = {
    pending: '待处理', pending_review: '待审批', approved: '已审批通过', rejected: '已审批驳回',
  }
  return typeof status === 'string' && Object.hasOwn(labels, status) ? labels[status] : '未取得审批状态'
}

/** 只兼容已知技术措辞；事实数字和原始快照保持原样。 */
export function businessNarrative(value: string): string {
  return value
    .replace(/needsManualReview\s*(?:为|[:：=])\s*[`*]*(true|false)[`*]*/gi, (_, flag: string) => flag.toLowerCase() === 'true'
      ? '存在评级资料缺口，需人工补充核实' : '未发现评级资料缺口，仍须按业务流程复核')
    .replace(/(?:指标\s*)?flag\s*(?:为|是)?\s*空(?:值)?/gi, '未触发该指标预警')
    .replace(/\s*flag\s*(?:为|是)\s*预警/gi, '触发预警')
    .replace(/\bneedsManualReview\b/g, '评级资料复核要求')
    .replace(/\bflag\b/gi, '预警标记')
}
