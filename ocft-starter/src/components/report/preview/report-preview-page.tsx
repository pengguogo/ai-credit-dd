import { useEffect, useMemo, useRef, useState } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { BootSplash } from '@/components/auth/boot-splash'
import { api } from '@/lib/api'
import type { Evidence, RunDetail } from '@/lib/types'
import { bindAnchorScroll } from './report-anchors'
import { ReportDocument } from './report-document'
import { maskReport, reportData } from './report-data'
import templateStyles from './report-template.css?raw'

type Result = { run: RunDetail; evidence: Evidence[] }

/** 独立报告页面；刷新后按 runId 重新读取快照，不依赖智能尽调页内存或临时 Blob URL。 */
export function ReportPreviewPage({ actorId, runId }: { actorId: string; runId: string }) {
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [frameReady, setFrameReady] = useState(false)
  const [printError, setPrintError] = useState('')
  const frame = useRef<HTMLIFrameElement>(null)
  useEffect(() => {
    let active = true
    Promise.all([api.getRun(actorId, runId), api.getEvidence(actorId, runId)])
      .then(([run, evidence]) => {
        if (!active) return
        if (!['succeeded', 'needs_confirmation'].includes(run.status) || !run.answer?.trim()) {
          setError('该次运行尚无可预览的报告，请返回「智能尽调」查看执行状态。')
          return
        }
        setResult({ run, evidence })
      })
      .catch((exc: unknown) => { if (active) setError(exc instanceof Error ? exc.message : '报告加载失败') })
    return () => { active = false }
  }, [actorId, runId, attempt])

  const html = useMemo(() => {
    if (!result) return ''
    // 姓名在渲染前统一脱敏（结构化字段与模型正文同口径）。
    const masked = maskReport(result.run, reportData(result.evidence))
    // React 自动转义全部业务字段与模型正文；模板不执行模型输出的 HTML 或脚本。
    return '<!DOCTYPE html>' + renderToStaticMarkup(<html lang="zh-CN"><head>
      <meta charSet="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
      <meta httpEquiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'" />
      <title>{masked.data.scope === 'enterprise' ? '企业主体尽调报告' : '企业信贷尽调报告'}</title><style>{templateStyles}</style>
    </head><body><ReportDocument run={masked.run} data={masked.data} /></body></html>)
  }, [result])

  // 与主站登录恢复一致：加载中全屏 BootSplash，不露出预览顶栏。
  if (!result && !error) {
    return <div className="h-dvh"><BootSplash /></div>
  }

  return <section style={{ height: '100dvh', display: 'flex', flexDirection: 'column', background: '#e9edf2', color: '#172b44' }}>
    <header style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 16, padding: '14px 24px', background: '#172b44', color: '#fff' }}>
      <strong style={{ marginRight: 'auto' }}>企业信贷尽调报告 · 预览</strong>
      <a href="/" style={{ color: '#fff', fontSize: 13 }}>返回智能尽调</a>
      <button type="button" disabled={!frameReady || !result} onClick={() => {
        try {
          frame.current?.contentWindow?.focus()
          frame.current?.contentWindow?.print()
          setPrintError('')
        } catch { setPrintError('无法打开打印窗口，请检查浏览器设置后重试。') }
      }} style={{ borderRadius: 5, padding: '7px 16px', background: '#fff', color: '#172b44', cursor: frameReady ? 'pointer' : 'wait', opacity: frameReady ? 1 : 0.6 }}>打印 / 另存为 PDF</button>
    </header>
    {printError ? <p role="alert" style={{ padding: 12 }}>{printError}</p> : null}
    {error ? <div role="alert" style={{ margin: '60px auto', padding: 28, maxWidth: 600, background: '#fff', borderRadius: 8 }}>
      <h1 style={{ fontSize: 22, marginBottom: 12 }}>报告暂时无法预览</h1><p>{error}</p>
      <button type="button" onClick={() => { setError(''); setResult(null); setFrameReady(false); setAttempt((n) => n + 1) }} style={{ marginTop: 16, cursor: 'pointer' }}>重新加载</button>
    </div> : <iframe ref={frame} title="企业信贷尽调报告正文" srcDoc={html} sandbox="allow-same-origin allow-modals" onLoad={() => {
      bindAnchorScroll(frame.current?.contentDocument)
      setFrameReady(true)
    }} style={{ flex: 1, width: '100%', border: 0, minHeight: 0 }} />}
  </section>
}
