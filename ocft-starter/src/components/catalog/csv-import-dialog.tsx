/**
 * 按表 CSV 增量导入：只接受当前表对应文件名 → POST /api/agent/data/imports。
 */
import { FileSpreadsheetIcon, UploadIcon, XIcon } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { ApiError, CsvImportError, api, type CsvImportReport } from '@/lib/api'

export function CsvImportDialog({ actorId, allowedFileName, onImported }: {
  actorId: string
  /** 当前表允许的唯一 CSV 文件名 */
  allowedFileName: string
  onImported: () => void
}) {
  const titleId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [pending, setPending] = useState(false)
  const [report, setReport] = useState<CsvImportReport | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, pending])

  const badName = Boolean(file && file.name !== allowedFileName)
  const canSubmit = Boolean(file) && !badName && !pending

  const submit = async () => {
    if (!file || !canSubmit) return
    setPending(true)
    setReport(null)
    setError('')
    try {
      const result = await api.importCsvFiles(actorId, [file])
      setReport(result)
      setFile(null)
      if (result.added > 0) onImported()
    } catch (exc) {
      if (exc instanceof CsvImportError) setReport(exc.report)
      else setError(exc instanceof ApiError ? exc.message : '导入失败')
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <Button type="button" variant="outline" size="sm" title={`导入 ${allowedFileName}`}
        onClick={() => {
          setFile(null)
          setReport(null)
          setError('')
          setOpen(true)
        }}>
        <UploadIcon />导入
      </Button>
      {open && createPortal(
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 py-16"
          onMouseDown={() => { if (!pending) setOpen(false) }}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="surface-panel-solid flex max-h-[min(40rem,calc(100vh-8rem))] w-full max-w-lg flex-col overflow-hidden rounded-xl"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="border-b px-4 py-3">
              <h2 id={titleId} className="text-base font-medium">导入本表数据</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                仅接受 <span className="font-mono">{allowedFileName}</span>。新记录插入，完全相同跳过，同键不同内容整次拒绝。
              </p>
            </div>
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
              <input
                ref={inputRef}
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                aria-label="选择 CSV 文件"
                onChange={(e) => {
                  const next = e.target.files?.[0] ?? null
                  setFile(next)
                  setReport(null)
                  setError('')
                  e.target.value = ''
                }}
              />
              <Button type="button" variant="outline" size="sm" disabled={pending}
                onClick={() => inputRef.current?.click()}>
                <FileSpreadsheetIcon />选择文件
              </Button>
              {file && (
                <div className="flex items-center justify-between gap-2 rounded-md border px-2 py-1 text-xs">
                  <span className={badName ? 'text-destructive' : undefined}>
                    {file.name}{badName && `（须为 ${allowedFileName}）`}
                  </span>
                  <Button type="button" variant="ghost" size="icon-sm" aria-label="移除"
                    disabled={pending} onClick={() => setFile(null)}>
                    <XIcon />
                  </Button>
                </div>
              )}
              {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              {report && <ImportReport report={report} />}
            </div>
            <div className="flex justify-end gap-2 border-t px-4 py-3">
              <Button type="button" variant="outline" size="sm" disabled={pending} onClick={() => setOpen(false)}>
                关闭
              </Button>
              <Button type="button" size="sm" disabled={!canSubmit} onClick={() => void submit()}>
                {pending ? <Spinner /> : <UploadIcon />}开始导入
              </Button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}

function ImportReport({ report }: { report: CsvImportReport }) {
  const ok = report.status === 'imported'
  return (
    <section aria-label="导入结果" role="status" className="space-y-2 rounded-lg border p-3 text-xs">
      <p className={ok ? 'font-medium text-success' : 'font-medium text-destructive'}>
        {ok
          ? `导入成功：新增 ${report.added} 条，跳过重复 ${report.skipped} 条`
          : '校验未通过，本次未写入任何数据'}
      </p>
      <p className="text-muted-foreground">导入编号 {report.importId}</p>
      {report.errors.length > 0 && (
        <ul className="max-h-48 space-y-1 overflow-y-auto">
          {report.errors.map((e, i) => (
            <li key={i} className="rounded-md bg-destructive/5 px-2 py-1">
              {e.fileName}{e.row != null && ` 第 ${e.row} 行`}{e.field && ` · ${e.field}`}：{e.message}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
