import { createServer } from 'vite'
import { resolve } from 'node:path'
import test from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
test('报告精简后保留七章与业务正文，移除状态卡和证据附录且无失效链接', async () => {
  const root = resolve(import.meta.dirname, '..')
  const server = await createServer({ root, server: { middlewareMode: true }, appType: 'custom' })
  try {
    const { ReportDocument } = await server.ssrLoadModule('/src/components/report/preview/report-document.tsx')
    const { reportData } = await server.ssrLoadModule('/src/components/report/preview/report-data.ts')
    const records = [{ evidenceId:'calc-test', sourceRef: {calc:'calc_credit_limit',keys:{applicationId:'A'},table:'loan_application'},snapshot:{applicationId:'A',enterpriseId:'E',applyAmount:100,suggestedCreditAmount:'80',unit:'万元'},dataVersion:1,createdAt:'2026-01-01T00:00:00Z',contentHash:'test'}]
    const html = renderToStaticMarkup(createElement(ReportDocument,{run:{status:'needs_confirmation',model:'test',answer:'## 财务分析\n指标 flag 为空。'},data:reportData(records)}))
    const ids = new Set([...html.matchAll(/id="([^"]+)"/g)].map(m=>m[1]))
    const missing = [...html.matchAll(/href="#([^"]+)"/g)].map(m=>m[1]).filter(id=>!ids.has(id))
    if(missing.length) throw Error('dead anchors:' + missing)
    if(!html.includes('未触发该指标预警')) throw Error('missing business text')
    if(/outcome-grid|报告依据与生成时快照|href="#evidence-|报告产出状态|<h3>贷款审批<\/h3>/.test(html)) throw Error('removed report sections remain')
    if((html.match(/class="sheet"/g) ?? []).length !== 7) throw Error('report chapters changed')
  } finally { await server.close() }
})
