import { amount, dict, isPointsScorecard, number, rows, text, type Dict } from './report-data'

export function EmptyData({ children = '本次报告未提供该项结构化数据' }: { children?: string }) {
  return <p className="empty-data">{children}</p>
}

type Series = { key: string; label: string; color: string }

/** 年度分组柱状图（参考样式）：纵轴从 0 开始，缺失年份不画柱、不当成 0。 */
export function BarChart({ years, series, unit }: { years: Dict[]; series: Series[]; unit: string }) {
  const ordered = years.filter((y) => number(y.year) !== null).sort((a, b) => Number(a.year) - Number(b.year))
  const values = ordered.flatMap((y) => series.map((s) => number(dict(y.subjects)[s.key])).filter((v): v is number => v !== null))
  if (!ordered.length || !values.length) return <EmptyData />
  const min = Math.min(0, ...values), max = Math.max(0, ...values) * 1.14
  const span = max - min || 1
  const y = (v: number) => 165 - (v - min) / span * 135
  const slot = 560 / ordered.length
  const barWidth = series.length > 1 ? 38 : 78
  const label = series.map((s) => s.label).join('与')
  // 多系列图柱窄，单位只放在图例里；单系列图把单位标在柱顶数值后。
  return <>
    {series.length > 1 ? <div className="legend">{series.map((s, i) => <span key={s.key}><i className={i ? 'dot orange' : 'dot'} />{s.label}</span>)}<span>单位：{unit} · 纵轴从0开始</span></div> : null}
    <svg viewBox="0 0 660 207" role="img" aria-label={`${label}年度对照，单位${unit}`}>
      <title>{`${label}年度对照，单位${unit}`}</title>
      {[0, 1, 2, 3].map((i) => { const v = min + span * i / 3; return <g key={i}><path d={`M65 ${y(v)}H625`} stroke="#dce2e9" /><text x="55" y={y(v) + 4} textAnchor="end">{amount(Math.round(v))}</text></g> })}
      {ordered.map((year, i) => {
        const center = 65 + slot * (i + 0.5)
        const start = center - barWidth * series.length / 2 - (series.length - 1) * 3.5
        return <g key={i}>
          {series.map((s, j) => {
            const v = number(dict(year.subjects)[s.key])
            if (v === null) return null
            const x = start + j * (barWidth + 7)
            const top = Math.min(y(v), y(0))
            return <g key={s.key}>
              <rect x={x} y={top} width={barWidth} height={Math.abs(y(0) - y(v))} fill={j ? '#b56924' : '#245d8c'}><title>{`${text(year.year)}年 · ${s.label}：${amount(v)}${unit}`}</title></rect>
              <text x={x + barWidth / 2} y={top - 8} textAnchor="middle">{amount(v)}{series.length === 1 && unit !== '暂无数据' ? unit : ''}</text>
            </g>
          })}
          <text x={center} y="189" textAnchor="middle">{text(year.year)}</text>
        </g>
      })}
    </svg>
  </>
}

/** 单条事件贡献分折线；横轴按实际日期间隔，节点链接到明细行。 */
export function EventChart({ opinion }: { opinion: Dict }) {
  const events = rows(opinion.events).map((e, i) => ({ index: i, eventDate: e.eventDate, eventType: e.eventType, date: typeof e.eventDate === 'string' ? Date.parse(e.eventDate) : NaN, point: number(e.points) }))
    .filter((e) => Number.isFinite(e.date) && e.point !== null).sort((a, b) => a.date - b.date)
  if (!events.length) return <EmptyData>本次报告没有可绘制的带日期事件数据</EmptyData>
  const start = events[0].date, end = events.at(-1)!.date, span = end - start || 1
  const low = Math.min(0, ...events.map((e) => e.point!)), high = Math.max(0, ...events.map((e) => e.point!))
  const scale = high - low || 1
  const x = (date: number) => events.length === 1 ? 345 : 85 + (date - start) / span * 520
  const y = (value: number) => 205 - (value - low) / scale * 170
  const ticks = [0, 1, 2, 3, 4].map((i) => low + scale * i / 4)
  return <svg id="event-risk-line" viewBox="0 0 660 280" role="img" aria-label="按事件实际日期排列的单条事件风险贡献分折线图，非企业历史风险趋势">
    <title>事件日期与单条事件风险贡献分，分值来自舆情诉讼工具</title>
    {ticks.map((v, i) => <g key={i}><path d={`M65 ${y(v)}H625`} stroke="#dce2e9" strokeDasharray="3 4" /><text x="52" y={y(v) + 4} textAnchor="end">{v > 0 ? '+' : ''}{amount(Math.round(v * 10) / 10)}</text></g>)}
    {low < 0 ? <path d={`M65 ${y(0)}H625`} stroke="#9aafbf" /> : null}
    <text x="65" y="16">风险贡献 / 分（正值加风险、负值减风险）</text>
    <polyline points={events.map((e) => `${x(e.date)},${y(e.point!)}`).join(' ')} fill="none" stroke="#245d8c" strokeWidth="2" />
    {events.map((e, i) => <a key={i} href={`#event-${e.index + 1}`}>
      <circle cx={x(e.date)} cy={y(e.point!)} r="5" fill={e.point! > 0 ? '#b56924' : '#245d8c'}><title>{`${text(e.eventDate)} · ${text(e.eventType)}：${amount(e.point)}分`}</title></circle>
      <text x={x(e.date)} y={y(e.point!) - 11} textAnchor="middle">{String(e.index + 1).padStart(2, '0')}</text>
      <text x={x(e.date)} y="232" textAnchor="middle">{text(e.eventDate)}</text>
    </a>)}
  </svg>
}

// 旧版评分卡（4518e84 之前）的维度键，快照里只有英文键，没有中文 name。
const LEGACY_DIMENSIONS: Record<string, string> = { financial: '财务能力', solvency: '偿债能力', stability: '经营稳定性', judicial: '司法舆情', fraud: '反欺诈' }

/**
 * 评级维度：新版按 points / maxPoints 画条（点数越高风险越大）；
 * 旧版快照按 0–100 分画条并标注权重。两种口径都只展示快照原值，不互相换算。
 */
export function DimensionChart({ dimensions }: { dimensions: Dict[] }) {
  if (!dimensions.length) return <EmptyData />
  const points = isPointsScorecard(dimensions)
  return <div>{dimensions.map((d, i) => {
    const label = typeof d.name === 'string' && d.name ? d.name : LEGACY_DIMENSIONS[String(d.dimension)] ?? text(d.dimension)
    let width = 0, value = '—', sub = ''
    if (points) {
      const p = number(d.points), max = number(d.maxPoints)
      if (p !== null && max) width = p / max * 100
      if (p !== null) value = `${amount(p)} / ${amount(max)}`
    } else {
      const score = number(d.score), weight = number(d.weight)
      if (score !== null) { width = score; value = amount(score) }
      if (weight !== null) sub = `权重 ${Math.round(weight * 100)}%`
    }
    return <div className="dimension" key={i}>
      <span>{label}{sub ? <small className="dimension-sub">{sub}</small> : null}</span>
      <div className="track"><div className="fill" style={{ width: `${Math.max(0, Math.min(100, width))}%` }} /></div>
      <b>{value}</b>
    </div>
  })}</div>
}
