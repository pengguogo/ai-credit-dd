import assert from 'node:assert/strict'
import test from 'node:test'
import { reportData } from '../src/components/report/preview/report-data.ts'
import { businessNarrative, approvalLabel, generationLabel } from '../src/components/report/preview/report-business.ts'
const evidence = (id, calc, snapshot, table = 'loan_application', keys = {}) => ({ evidenceId: id, sourceType: calc ? 'calculation' : 'db_query', sourceRef: { table, keys, ...(calc ? { calc } : {}) }, snapshot, dataVersion: 2, createdAt: '2026-01-01T00:00:00Z', contentHash: 'hash' })

test('生成完成与待确认均不代表贷款审批，未知审批不推断', () => {
  assert.equal(generationLabel('needs_confirmation'), '已生成 · 待业务确认')
  assert.equal(generationLabel('succeeded'), '已生成')
  assert.equal(generationLabel('failed'), '生成失败')
  assert.equal(approvalLabel('pending'), '待处理')
  assert.equal(approvalLabel('approved'), '已审批通过')
  assert.equal(approvalLabel(undefined), '未取得审批状态')
  assert.equal(approvalLabel('new-state'), '未取得审批状态')
})
test('业务措辞转换保留数字与阈值，不把未预警改成预警', () => {
  assert.equal(businessNarrative('期间费用率 12.5%，连续三年 flag 为预警；指标 flag 为空。'), '期间费用率 12.5%，连续三年触发预警；未触发该指标预警。')
  assert.equal(businessNarrative('needsManualReview 为 false；阈值 40%。'), '未发现评级资料缺口，仍须按业务流程复核；阈值 40%。')
  assert.equal(businessNarrative('needsManualReview=true'), '存在评级资料缺口，需人工补充核实')
})
test('证据链接与审批只使用本次报告同申请/企业，保留最新匹配计算', () => {
  const records = [
    evidence('loan', null, { applicationId: 'A', enterpriseId: 'E', status: 'pending' }),
    evidence('foreign-loan', null, { applicationId: 'B', enterpriseId: 'E', status: 'approved' }),
    evidence('old', 'calc_credit_limit', { applicationId: 'A', enterpriseId: 'E', applyAmount: 100 }),
    evidence('finance', 'analyze_financials', { enterpriseId: 'E', years: [] }),
    evidence('new', 'calc_credit_limit', { applicationId: 'A', enterpriseId: 'E', applyAmount: 120 }),
    evidence('foreign', 'calc_credit_limit', { applicationId: 'B', enterpriseId: 'E', applyAmount: 999 }),
    evidence('report', 'build_dd_report', { applicationId: 'A', enterpriseId: 'E', sections: {} }),
  ]
  const result = reportData(records)
  assert.equal(result.credit.applyAmount, 120)
  assert.equal(result.loanSnapshot.status, 'pending')
  assert.equal(result.evidenceSources.calc_credit_limit.evidenceId, 'new')
  assert.equal(result.evidenceSources.analyze_financials.evidenceId, 'finance')
  assert.ok(!Object.values(result.evidenceSources).some(e => ['foreign', 'old'].includes(e.evidenceId)))
})
test('缺少唯一对象或可定位证据时不伪造关联', () => {
  const result = reportData([evidence('a', 'rate_risk', { enterpriseId: 'E1' }), evidence('b', 'rate_risk', { enterpriseId: 'E2' })])
  assert.equal(result.ambiguous, true)
  assert.deepEqual(result.evidenceSources, {})
  assert.deepEqual(result.loanSnapshot, {})
})

test('过期取数日的计算证据不与本次报告混用，引用条件支持来源主键', () => {
  const result = reportData([
    evidence('matching', 'rate_risk', { enterpriseId: 'E', applicationId: 'A', asOf: '2026-01-01', score: 30 }),
    evidence('other-date', 'rate_risk', { enterpriseId: 'E', applicationId: 'A', asOf: '2026-02-01', score: 90 }),
    evidence('keys', 'calc_credit_limit', { applyAmount: 120 }, 'loan_application', { applicationId: 'A' }),
    evidence('report', 'build_dd_report', { applicationId: 'A', enterpriseId: 'E', asOf: '2026-01-01', sections: {} }),
  ])
  assert.equal(result.evidenceSources.rate_risk.evidenceId, 'matching')
  assert.equal(result.evidenceSources.calc_credit_limit.evidenceId, 'keys')
})
