/**
 * 轻量 Markdown 渲染：标题、段落、列表、表格、粗体、行内代码。
 * @why 模型答案带 Markdown；这里只生成 React 元素、不用 innerHTML，模型输出无法注入 HTML/脚本。
 *      不引入第三方解析库，覆盖审批意见书用到的语法即可。
 */
import type { ReactNode } from 'react'

function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = []
  const pattern = /(\*\*([^*]+)\*\*|`([^`]+)`)/g
  let last = 0
  let i = 0
  for (const m of text.matchAll(pattern)) {
    if (m.index > last) out.push(text.slice(last, m.index))
    if (m[2] !== undefined) out.push(<strong key={`${keyBase}-b${i}`} className="font-semibold text-foreground">{m[2]}</strong>)
    else out.push(<code key={`${keyBase}-c${i}`} className="rounded bg-muted px-1 font-mono text-[0.85em]">{m[3]}</code>)
    last = m.index + m[0].length
    i += 1
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

const BULLET = /^\s*(?:[-*•▸]|\d+[.)、])\s+/
const ORDERED = /^\s*\d+[.)、]\s+/
// 纯数字单元格（含千分位、百分号、区间、单位）右对齐，便于逐年对比
const NUMERIC = /^[-+−]?[\d,]+(?:\.\d+)?(?:\s*[-–][\d,]+(?:\.\d+)?)?\s*(?:%|万元|分|次|天|个月)?$/

function splitRow(line: string): string[] {
  return line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
}

/**
 * variant=report：对话框中的完整尽调报告。章节标题加编号色块，表格表头加深、数值列等宽，
 * 段首「标签：」加粗；普通问答仍用默认样式。
 */
export function Markdown({ text, variant = 'default' }: { text: string; variant?: 'default' | 'report' }) {
  const report = variant === 'report'
  let section = 0
  const lines = String(text ?? '').replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const key = `blk-${i}`
    if (!line.trim()) {
      i += 1
      continue
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line)
    if (heading) {
      // 层级分明：报告标题 / 章节 / 小节，各自字号与分隔线不同
      const level = heading[1].length
      const content = inline(heading[2], key)
      if (report && level === 1) {
        // 报告标题在外层卡片头部展示，正文里不再重复
      } else if (report && level === 2) {
        section += 1
        blocks.push(
          <h3 key={key} className="mt-6 flex items-center gap-2.5 border-b border-border pb-2 text-[15px] font-semibold text-foreground first:mt-0">
            <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-brand text-xs font-bold text-white tabular-nums">{String(section).padStart(2, '0')}</span>
            {content}
          </h3>,
        )
      } else if (report) {
        blocks.push(<h4 key={key} className="mt-4 flex items-center gap-2 text-sm font-semibold text-foreground before:h-3.5 before:w-1 before:rounded-full before:bg-brand/60">{content}</h4>)
      } else if (level === 1) {
        blocks.push(<h2 key={key} className="border-b-2 border-primary pb-2 text-lg font-bold tracking-wide text-foreground">{content}</h2>)
      } else if (level === 2) {
        blocks.push(<h3 key={key} className="mt-5 border-l-4 border-primary bg-muted/60 px-3 py-1.5 text-base font-semibold text-foreground">{content}</h3>)
      } else {
        blocks.push(<h4 key={key} className="mt-3 border-b pb-1 text-sm font-semibold text-foreground">{content}</h4>)
      }
      i += 1
      continue
    }
    if (line.trim().startsWith('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const header = splitRow(line)
      const rows: string[][] = []
      i += 2
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        rows.push(splitRow(lines[i]))
        i += 1
      }
      blocks.push(
        <div key={key} className={report ? 'overflow-x-auto rounded-lg border border-border bg-card shadow-xs' : 'overflow-x-auto rounded border'}>
          <table className="w-full border-collapse text-xs">
            <thead className={report ? 'bg-slate-700 text-white dark:bg-slate-800' : 'bg-muted'}>
              <tr>{header.map((h, j) => <th key={j} scope="col" className={`border-b px-2.5 py-1.5 text-left font-semibold ${report ? 'border-slate-600 py-2 font-medium tracking-wide' : ''}`}>{inline(h, `${key}-h${j}`)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri} className={report ? 'border-b border-border/70 last:border-0 even:bg-muted/25 hover:bg-brand-soft/60' : 'border-b last:border-0 even:bg-muted/30'}>
                  {r.map((c, ci) => (
                    <td key={ci} className={`px-2.5 py-1.5 align-top ${report && ci === 0 ? 'font-medium text-foreground' : ''} ${NUMERIC.test(c) && !(report && header.length <= 2) ? 'text-right tabular-nums whitespace-nowrap' : ''}`}>
                      {inline(c, `${key}-${ri}-${ci}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }
    if (BULLET.test(line)) {
      const ordered = ORDERED.test(line)
      const items: string[] = []
      while (i < lines.length && BULLET.test(lines[i])) {
        items.push(lines[i].replace(BULLET, ''))
        i += 1
      }
      const List = ordered ? 'ol' : 'ul'
      blocks.push(
        <List key={key} className={`${ordered ? 'list-decimal' : 'list-disc'} space-y-0.5 pl-5 ${report ? 'space-y-1 marker:text-brand' : ''}`}>
          {items.map((it, j) => <li key={j}>{inline(it, `${key}-${j}`)}</li>)}
        </List>,
      )
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !BULLET.test(lines[i]) && !/^#{1,4}\s/.test(lines[i])
      && !lines[i].trim().startsWith('|')) {
      para.push(lines[i])
      i += 1
    }
    // 无表头分隔符的管道行按普通文本展示，保证解析游标前进。
    if (para.length === 0) {
      para.push(lines[i])
      i += 1
    }
    // 报告里「尽调结论：」「摘要判断：」这类以粗体标签开头的段落，做成浅色提示条
    const callout = report && /^\*\*[^*]{2,12}(?:\*\*[：:]|[：:][^*]*\*\*)/.test(para[0] ?? '')
    blocks.push(
      <p key={key} className={callout ? 'rounded-md border-l-[3px] border-brand bg-brand-soft/70 px-3 py-2 text-foreground' : undefined}>
        {para.flatMap((p, j) => (j ? [<br key={`${key}-br${j}`} />, ...inline(p, `${key}-${j}`)] : inline(p, `${key}-${j}`)))}
      </p>,
    )
  }
  return <div className={report ? 'space-y-2.5 text-sm leading-relaxed text-foreground/90' : 'space-y-2 text-sm leading-relaxed'}>{blocks}</div>
}
