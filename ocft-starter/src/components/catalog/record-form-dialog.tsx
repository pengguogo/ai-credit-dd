/** 业务表单行新增 / 编辑。打开时由父级换 key 以重置表单。 */
import { useEffect, useId, useState } from 'react'
import { createPortal } from 'react-dom'

import { Button } from '@/components/ui/button'
import { DateField } from '@/components/ui/date-field'
import { Input } from '@/components/ui/input'
import { SelectField } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { SCENARIO_ID } from '@/data/scenario'
import { ApiError, api } from '@/lib/api'
import {
  LIST_TABLES,
  WRITE_FIELDS,
  nextApplicationId,
  type CatalogKind,
  type FieldDef,
  type FieldOption,
} from '@/lib/catalog-tables'

type WritableKind = Exclude<CatalogKind, 'schema_relationships'>

type EnterpriseOption = { value: string; label: string }

function todayIso(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function defaultForField(f: FieldDef, mode: 'create' | 'edit'): string {
  if (mode !== 'create') return ''
  if (f.key === 'applyDate' || f.type === 'date') return todayIso()
  if (f.key === 'status') return 'pending'
  if (f.key === 'guaranteeType') return f.options?.[0]?.value ?? ''
  if (f.key === 'loanTermMonths') return f.options?.[0]?.value ?? '12'
  return ''
}

function initialValues(
  kind: WritableKind,
  mode: 'create' | 'edit',
  initial: Record<string, string | number | null> | null,
): Record<string, string> {
  const next: Record<string, string> = {}
  for (const f of WRITE_FIELDS[kind]) {
    const raw = initial?.[f.key]
    if (raw != null && String(raw) !== '') {
      next[f.key] = String(raw)
    } else {
      next[f.key] = defaultForField(f, mode)
    }
  }
  return next
}

function dialogTitle(kind: WritableKind, mode: 'create' | 'edit'): string {
  const label = LIST_TABLES.find((t) => t.kind === kind)?.label ?? '记录'
  return mode === 'create' ? `新增${label}` : `编辑${label}`
}

function controlClass(mono = false): string {
  return mono ? 'mt-1 h-8 font-mono text-xs' : 'mt-1 h-8 text-xs'
}

export function RecordFormDialog({ actorId, kind, mode, initial, open, onClose, onSaved }: {
  actorId: string
  kind: WritableKind
  mode: 'create' | 'edit'
  initial: Record<string, string | number | null> | null
  open: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const titleId = useId()
  const fields = WRITE_FIELDS[kind]
  const needsEnterprise = fields.some((f) => f.type === 'enterprise')
  const needsAutoId = mode === 'create' && fields.some((f) => f.type === 'auto' && f.key === 'applicationId')

  const [values, setValues] = useState(() => initialValues(kind, mode, initial))
  const [enterprises, setEnterprises] = useState<EnterpriseOption[]>([])
  const [loadingMeta, setLoadingMeta] = useState(needsEnterprise || needsAutoId)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !pending) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, pending, onClose])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    const load = async () => {
      if (!needsEnterprise && !needsAutoId) {
        setLoadingMeta(false)
        return
      }
      setLoadingMeta(true)
      setError('')
      try {
        const [entRes, appRes] = await Promise.all([
          needsEnterprise
            ? api.catalog(actorId, SCENARIO_ID, '', 'enterprises')
            : Promise.resolve(null),
          needsAutoId
            ? api.catalog(actorId, SCENARIO_ID, '', 'applications')
            : Promise.resolve(null),
        ])
        if (cancelled) return
        if (entRes) {
          const opts: EnterpriseOption[] = entRes.rows
            .map((row) => {
              const id = String(row.enterpriseId ?? '').trim()
              if (!id) return null
              const name = String(row.enterpriseName ?? '').trim()
              return { value: id, label: name ? `${id} · ${name}` : id }
            })
            .filter((item): item is EnterpriseOption => item != null)
            .sort((a, b) => a.value.localeCompare(b.value, 'zh-CN'))
          setEnterprises(opts)
          setValues((prev) => {
            if (prev.enterpriseId || opts.length === 0) return prev
            return { ...prev, enterpriseId: opts[0].value }
          })
        }
        if (appRes) {
          const ids = appRes.rows.map((row) => String(row.applicationId ?? ''))
          // total 作下限：目录有截断时仍尽量避开已占用序号
          const nextId = nextApplicationId(ids, appRes.total)
          setValues((prev) => ({ ...prev, applicationId: nextId }))
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof ApiError ? exc.message : '加载表单选项失败')
        }
      } finally {
        if (!cancelled) setLoadingMeta(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [open, actorId, needsEnterprise, needsAutoId])

  if (!open) return null

  const setField = (key: string, value: string) => {
    setValues((v) => ({ ...v, [key]: value }))
  }

  const submit = async () => {
    setPending(true)
    setError('')
    const body: Record<string, string | number> = {}
    for (const f of fields) {
      const text = (values[f.key] ?? '').trim()
      if (text === '') {
        if (f.type === 'auto' || f.type === 'enterprise' || f.key === 'applyDate' || f.key === 'status') {
          setError(`请填写${f.label}`)
          setPending(false)
          return
        }
        continue
      }
      body[f.key] = f.type === 'number' || f.key === 'loanTermMonths' || f.key === 'applyAmount'
        ? Number(text)
        : text
    }
    try {
      if (mode === 'create') {
        await api.createCatalogRecord(actorId, SCENARIO_ID, kind, body)
      } else {
        const id = Number(initial?.id)
        if (!Number.isFinite(id)) throw new ApiError(400, 'invalid_args', '缺少记录 id')
        await api.updateCatalogRecord(actorId, SCENARIO_ID, kind, id, body)
      }
      onSaved()
      onClose()
    } catch (exc) {
      if (
        mode === 'create'
        && kind === 'applications'
        && exc instanceof ApiError
        && exc.errorCode === 'conflict'
      ) {
        // 编号冲突时再取一次已有列表，生成下一个唯一号后提示用户重试
        try {
          const appRes = await api.catalog(actorId, SCENARIO_ID, '', 'applications')
          const nextId = nextApplicationId(
            appRes.rows.map((row) => String(row.applicationId ?? '')),
            appRes.total,
          )
          setValues((prev) => ({ ...prev, applicationId: nextId }))
          setError(`贷款编号已占用，已更新为 ${nextId}，请再次保存`)
        } catch {
          setError(exc.message)
        }
      } else {
        setError(exc instanceof ApiError ? exc.message : '保存失败')
      }
    } finally {
      setPending(false)
    }
  }

  const renderControl = (f: FieldDef) => {
    const value = values[f.key] ?? ''
    const disabled = pending || loadingMeta
      || (f.type === 'auto')
      || (mode === 'edit' && (f.key === 'applicationId' || f.key === 'enterpriseId'
        || f.key === 'eventId' || f.key === 'caseId'))

    if (f.type === 'enterprise') {
      return (
        <SelectField
          className="mt-1"
          value={value}
          disabled={disabled || enterprises.length === 0}
          onValueChange={(next) => setField(f.key, next)}
          aria-label={f.label}
          mono
          placeholder={enterprises.length === 0 ? '暂无企业，请先新增企业信息' : '选择企业'}
          options={enterprises}
        />
      )
    }

    if (f.type === 'select' && f.options) {
      const options: FieldOption[] = [...f.options]
      if (value && !options.some((opt) => opt.value === value)) {
        options.unshift({ value, label: value })
      }
      return (
        <SelectField
          className="mt-1"
          value={value}
          disabled={disabled}
          onValueChange={(next) => setField(f.key, next)}
          aria-label={f.label}
          placeholder={`选择${f.label}`}
          options={options}
        />
      )
    }

    if (f.type === 'date') {
      return (
        <DateField
          className="mt-1"
          value={value}
          disabled={disabled}
          onValueChange={(next) => setField(f.key, next)}
          aria-label={f.label}
          placeholder={`选择${f.label}`}
        />
      )
    }

    if (f.type === 'number') {
      return (
        <Input
          type="text"
          inputMode="decimal"
          className={controlClass(true)}
          value={value}
          disabled={disabled}
          onChange={(e) => setField(f.key, e.target.value.replace(/[^\d.-]/g, ''))}
          aria-label={f.label}
        />
      )
    }

    return (
      <Input
        className={controlClass(f.type === 'auto' || f.key.endsWith('Id'))}
        value={value}
        disabled={disabled}
        readOnly={f.type === 'auto'}
        onChange={(e) => setField(f.key, e.target.value)}
        aria-label={f.label}
        title={f.type === 'auto' ? '系统自动生成，保证唯一' : undefined}
      />
    )
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 py-10"
      onMouseDown={() => { if (!pending) onClose() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="surface-panel-solid flex max-h-[min(44rem,calc(100vh-5rem))] w-full max-w-xl flex-col overflow-hidden rounded-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="border-b px-4 py-3">
          <h2 id={titleId} className="text-base font-medium">{dialogTitle(kind, mode)}</h2>
          {kind === 'applications' && mode === 'create' && (
            <p className="mt-0.5 text-xs text-muted-foreground">贷款编号自动生成；企业从已有名录选择</p>
          )}
        </div>
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3">
          {loadingMeta && (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Spinner className="size-3.5" />加载选项…
            </p>
          )}
          {fields.map((f) => (
            <label key={f.key} className="block text-xs">
              <span className="text-muted-foreground">
                {f.label}
                {f.type === 'auto' && mode === 'create' && (
                  <span className="ml-1 text-[10px] text-muted-foreground/80">自动生成</span>
                )}
              </span>
              {renderControl(f)}
            </label>
          ))}
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t px-4 py-3">
          <Button type="button" variant="outline" size="sm" disabled={pending} onClick={onClose}>取消</Button>
          <Button
            type="button"
            size="sm"
            disabled={pending || loadingMeta || (needsEnterprise && enterprises.length === 0)}
            onClick={() => void submit()}
          >
            {pending ? <Spinner /> : '保存'}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
