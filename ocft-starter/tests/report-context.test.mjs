import assert from 'node:assert/strict'
import test from 'node:test'
import { readReportContext, reportHref, reportPath } from '../src/lib/report-dims.ts'

test('同企业的不同贷款在维度跳转中保持独立', () => {
  for (const applicationId of ['SYNTHETIC-A', 'SYNTHETIC-B']) {
    const source = reportPath('business', { enterpriseId: 'borrower', applicationId })
    const next = reportHref('report', source.slice(source.indexOf('?')))
    assert.equal(next.split('?')[0], '/report/report')
    assert.deepEqual(readReportContext(next.slice(next.indexOf('?'))), {
      enterpriseId: 'borrower', applicationId,
    })
  }
})

test('仅有贷款编号时保留编号，查询字符安全往返', () => {
  const applicationId = 'loan / & ?'
  const path = reportPath('finance', { applicationId })
  assert.deepEqual(readReportContext(path.slice(path.indexOf('?'))), {
    enterpriseId: '', applicationId,
  })
  assert.equal(reportHref('report', ''), '/report/report')
})
