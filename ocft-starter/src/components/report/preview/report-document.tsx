import type { ReactNode } from 'react'
import { Markdown } from '@/components/markdown'
import type { RunDetail } from '@/lib/types'
import { businessNarrative } from './report-business'
import { BarChart, DimensionChart, EmptyData, EventChart } from './report-charts'
import { amount, dict, isPointsScorecard, number, ratio, rows, strings, text, type Dict, type ReportData } from './report-data'

const CHAPTERS = [
  ['summary', '决策摘要'], ['overview', '企业概况'], ['finance', '财务分析 · 趋势'], ['quality', '财务分析 · 回款'],
  ['risk', '风险提示'], ['credit', '额度建议'], ['conditions', '风控条件'],
] as const
type ChapterId = typeof CHAPTERS[number][0]

const HEADS: Record<ChapterId, [string, string]> = {
  summary: ['', ''], overview: ['01 / Corporate profile', '主体、控制关系与关联担保，均取自本次核验快照'],
  finance: ['02 / Financial analysis', '数据来自本次财务测算快照'], quality: ['02 / Cash flow & operating efficiency', '使用工具指标定义，口径见表下说明'],
  risk: ['03 / Risk findings', '截至申请日的库内事件，不代表实时外部检索结果'], credit: ['04 / Credit proposal', '等级、金额及步骤引用本次工具结果'],
  conditions: ['05 / Conditions & review', '工具条件与模型建议分列，不伪造待办与审批记录'],
}

/** 模型正文按二级标题拆到对应章节；未识别的标题并入风控条件页，原文不丢弃、不改写。 */
function splitAnswer(answer: string): Record<ChapterId, string> {
  const out: Record<ChapterId, string> = { summary: '', overview: '', finance: '', quality: '', risk: '', credit: '', conditions: '' }
  const route = (title: string): ChapterId | 'other' => /企业概况|主体/.test(title) ? 'overview' : /财务/.test(title) ? 'finance' : /风险提示|风险/.test(title) && !/风控/.test(title) ? 'risk'
    : /额度|授信建议/.test(title) ? 'credit' : /风控条件|条件/.test(title) ? 'conditions' : 'other'
  let current: ChapterId = 'summary'
  for (const line of answer.split('\n')) {
    if (/^#\s/.test(line)) continue
    const head = /^##\s+(.+)$/.exec(line)
    if (head) {
      const target = route(head[1])
      // 未识别章节保留原二级标题，接在风控条件后展示
      if (target === 'other') { current = 'conditions'; out.conditions += line + '\n'; continue }
      current = target; continue
    }
    out[current] += line + '\n'
  }
  return out
}

function ModelNote({ model, children }: { model: string; children: string }) {
  if (!children.trim()) return null
  return <div className="model-note report-text"><b>模型解读 · {model} · 建议不代表审批</b><Markdown text={businessNarrative(children)} /></div>
}

// 首页摘要里这三类小节单独成卡片；其余内容仍按模型解读原文展示。
const SUMMARY_CARDS: [RegExp, string][] = [[/支持因素/, 'ok'], [/重点关注|关注事项/, 'warn'], [/报告边界|分析边界/, 'scope']]

function SummaryNote({ model, text: body }: { model: string; text: string }) {
  const intro: string[] = []
  const cards: { title: string; tone: string; lines: string[] }[] = []
  let current: { title: string; tone: string; lines: string[] } | null = null
  for (const line of body.split('\n')) {
    const head = /^###\s+(.+)$/.exec(line)
    if (head) {
      const match = SUMMARY_CARDS.find(([pattern]) => pattern.test(head[1]))
      current = match ? { title: head[1].trim(), tone: match[1], lines: [] } : null
      if (current) { cards.push(current); continue }
    }
    if (current) current.lines.push(line)
    else intro.push(line)
  }
  return <>
    <ModelNote model={model}>{intro.join('\n')}</ModelNote>
    {cards.length ? <div className="summary-cards block">{cards.map((c, i) => <section className={`summary-card ${c.tone}`} key={i}>
      <h3>{c.title}</h3><div className="report-text"><Markdown text={businessNarrative(c.lines.join('\n'))} /></div>
    </section>)}</div> : null}
  </>
}

function Table({ headers, values, note }: { headers: string[]; values: ReactNode[][]; note?: string }) {
  if (!values.length) return <EmptyData />
  return <><div className="preview-table"><table><thead><tr>{headers.map((h, i) => <th key={i}>{h}</th>)}</tr></thead><tbody>{values.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody></table></div>{note ? <p className="table-note">{note}</p> : null}</>
}

function Facts({ items }: { items: [string, unknown][] }) {
  return <>{items.map(([label, value]) => <div className="keyline" key={label}><span>{label}</span><b>{text(value)}</b></div>)}</>
}

const yesNo = (value: unknown) => value === true ? '是' : value === false ? '否' : '暂无数据'
const pct1 = (value: unknown) => number(value) === null ? '暂无数据' : `${((value as number) * 100).toFixed(1)}%`

// 指标单位按工具字段名区分：比率转百分数，周转按次，天数按天，覆盖倍数按倍。
function metricValue(key: string, value: unknown): string {
  if (number(value) === null) return '暂无数据'
  const v = value as number
  if (/Days$/.test(key)) return `${v.toFixed(1)} 天`
  if (/Turnover$/.test(key)) return `${v.toFixed(2)} 次`
  if (/^ocfTo/.test(key)) return `${v.toFixed(2)} 倍`
  return pct1(v)
}
// 新版评分卡输出风险点数，旧版输出加权总分；按快照口径命名，不混用。
const scoreLabel = (data: ReportData) => isPointsScorecard(rows(data.rating.dimensions)) ? '风险点数' : '综合得分'
const flagText = (flag: unknown) => flag === 'warn' ? '关注' : flag === 'block' ? '风险' : '—'

function Overview({ data }: { data: ReportData }) {
  const b = data.business, o = data.overview
  const findings = rows(b.findings ?? o.findings)
  return <>
    <div className="grid2">
      <section className="panel soft"><h3>企业 {text(data.enterpriseId)}</h3><Facts items={[
        ['企业名称', data.enterpriseName], ['所属行业', o.industry], ['经营状态 / 成立日期', `${text(b.businessStatus ?? o.businessStatus)} / ${text(o.establishDate)}`],
        ['实缴比例', ratio(b.paidInRatio)],
      ]} /></section>
      <section className="panel"><h3>控制关系与关联担保</h3><Facts items={[
        ['实控人 / 第一大股东', `${text(b.actualController)} / ${text(b.topShareholder)}`], ['两者一致', yesNo(b.controllerMatchesTopShareholder)],
        ['关联企业 登记 / 明细', `${text(b.relatedEnterpriseCountDeclared)} / ${text(b.relatedEnterpriseCountActual)} 家`],
        ['担保圈企业 / 逾期担保', `${text(b.guaranteeCircleCount)} 家 / ${text(b.guaranteeOverdueCount)} 笔`],
      ]} /></section>
    </div>
    <section className="block"><div className="origin">工商核验结果</div><h3>工商核验发现</h3>
      {findings.length ? <Table headers={['项目', '关注程度', '核验结果']} values={findings.map((f) => [text(f.code), flagText(f.level), text(f.detail)])} /> : <p className="callout">本次核验未发现工具定义的工商异常项。此处不声称已联网查询工商或核验原件。</p>}
    </section>
  </>
}

const SUBJECTS: [string, string][] = [['revenue', '营业收入'], ['netProfit', '净利润'], ['operatingCashflow', '经营现金流'], ['totalAssets', '资产总额'], ['totalLiabilities', '负债总额'], ['ownersEquity', '所有者权益']]
function Finance({ data, years }: { data: ReportData; years: Dict[] }) {
  const unit = text(data.finance.unit), growth = dict(data.finance.growth)
  const ratioRows: [string, string][] = [['netMargin', '净利率'], ['assetLiabilityRatio', '资产负债率'], ['roe', '净资产收益率']]
  return <>
    <div className="origin">数据库事实＋工具计算</div>
    <h3>营业收入年度趋势 · {unit}</h3>
    <BarChart years={years} unit={unit} series={[{ key: 'revenue', label: '营业收入', color: '#245d8c' }]} />
    {years.length ? <Table headers={['科目 / 指标', ...years.map((y) => text(y.year))]} values={[
      // 金额科目在项目名后标注单位；单位缺失时不标，不臆造。
      ...SUBJECTS.map(([key, label]) => [unit === '暂无数据' ? label : `${label}（${unit}）`, ...years.map((y) => amount(dict(y.subjects)[key]))]),
      ...ratioRows.map(([key, label]) => [label, ...years.map((y) => pct1(dict(dict(y.metrics)[key]).value))]),
    ]} note="比率直接使用工具输出并转换为百分数，展示舍入至1位。" /> : <EmptyData />}
    <div className="grid3 block">{[['最近年度收入同比', growth.revenueYoy], ['最近年度净利润同比', growth.netProfitYoy], ['收入复合增长率', growth.revenueCagr]].map(([label, value]) =>
      <div className="panel" key={String(label)}><p className="small muted">{String(label)}</p><h2>{pct1(value)}</h2></div>)}</div>
  </>
}

const QUALITY: [string, string][] = [['receivableDays', '应收周转天数'], ['inventoryDays', '存货周转天数'], ['ocfToProfit', '经营现金流 / 净利润'], ['periodExpenseRatio', '期间费用率'], ['interestBearingRatio', '有息负债 / 总资产']]
function Quality({ data, years }: { data: ReportData; years: Dict[] }) {
  const unit = text(data.finance.unit)
  const latest = years.at(-1)
  const flagged = Object.entries(dict(latest?.metrics)).map(([key, m]): Dict & { key: string } => ({ ...dict(m), key })).filter((m) => m.flag === 'warn' || m.flag === 'block')
  return <>
    <BarChart years={years} unit={unit} series={[{ key: 'netProfit', label: '净利润', color: '#245d8c' }, { key: 'operatingCashflow', label: '经营现金流', color: '#b56924' }]} />
    {years.length ? <Table headers={['指标', ...years.map((y) => text(y.year)), '最新标记']} values={QUALITY.map(([key, label]) => [
      label, ...years.map((y) => metricValue(key, dict(dict(y.metrics)[key]).value)), flagText(dict(dict(latest?.metrics)[key]).flag),
    ])} /> : <EmptyData />}
    {flagged.length ? <div className="callout warn block"><strong>工具预警：{flagged.map((m) => text(m.name)).join('、')}</strong>
      {flagged.map((m) => `${text(m.name)} ${metricValue(m.key, m.value)}`).join('；')}。这是配置规则预警，不是法定红线。</div> : null}
    <section className="block"><h3>财报勾稽与审计意见</h3><Table headers={['年度', '审计意见', '资产负债勾稽', unit === '暂无数据' ? '差额' : `差额（${unit}）`]} values={years.map((y) => {
      const check = dict(y.balanceCheck)
      return [text(y.year), text(dict(y.subjects).auditOpinion), check.balanced === true ? '平衡' : check.balanced === false ? '不平衡' : '暂无数据', amount(check.gap)]
    })} note={data.finance.denominatorNote ? text(data.finance.denominatorNote) : undefined} /></section>
  </>
}

function Risk({ data }: { data: ReportData }) {
  // 按事件日期升序编号，时间线节点与明细行共用同一序号。
  const events = rows(data.opinion.events).sort((a, b) => String(a.eventDate).localeCompare(String(b.eventDate)))
  const fraudRules = rows(data.fraud.rules)
  const hits = fraudRules.filter((r) => r.hit === true).length
  return <>
    <div className="grid3">
      <div className="panel"><p className="small muted">未结被告金额</p><h2>{amount(data.opinion.openDefendantAmount)}<small> 万元</small></h2></div>
      <div className="panel"><p className="small muted">舆情司法风险分</p><h2>{amount(data.opinion.opinionRiskScore)}</h2><p className="table-note">健康分 {amount(data.opinion.healthScore)}；越高风险越大，非概率</p></div>
      <div className="panel"><p className="small muted">反欺诈命中</p><h2>{fraudRules.length ? `${hits} / ${fraudRules.length}` : '暂无数据'}</h2><p className="table-note">{strings(data.fraud.hitRuleIds).join('、') || '规则均未命中'}</p></div>
    </div>
    {strings(data.opinion.labels).length || strings(data.rating.vetoes).length ? <p className="block">{[...strings(data.opinion.labels), ...strings(data.rating.vetoes)].map((l, i) => <span className="tag warn" key={i} style={{ marginRight: 6 }}>{l}</span>)}</p> : null}
    <section className="block"><h3>关键风险事实与依据</h3>
      <Table headers={['事项', '本次核验事实']} values={[
        ['存量逾期', `逾期 ${text(dict(data.business.riskFacts).overdueCount)} 次 / ${amount(dict(data.business.riskFacts).overdueAmount)} 万元`],
        ['担保风险', `担保圈 ${text(data.business.guaranteeCircleCount)} 家；逾期担保 ${text(data.business.guaranteeOverdueCount)} 笔 / ${amount(data.business.guaranteeOverdueAmount)} 万元`],
        ['舆情与涉诉', `未结被告金额 ${amount(data.opinion.openDefendantAmount)} 万元`],
        ['反欺诈', fraudRules.length ? `命中 ${hits} / ${fraudRules.length} 项` : '暂无数据'],
      ]} />
    </section>
    <section className="block"><h3>事件时间线</h3><div className="timeline">
      <EventChart opinion={{ ...data.opinion, events }} />
      <p className="table-note">横轴按实际日期间隔绘制，点击节点定位明细。分值为单条事件计分，不是累计风险或违约概率；连线仅连接离散事件。</p>
      <Table headers={['事件 / 日期', '库内事项与来源', '贡献分']} values={events.map((e, i) => [
        <span key="date" id={`event-${i + 1}`}>{String(i + 1).padStart(2, '0')} / {text(e.eventDate)}</span>,
        <span key="body"><strong>{text(e.eventType)}</strong> · {text(e.sentiment)}<br />{text(e.eventContent)}<br /><span className="table-note">{text(e.eventId)} · 来源字段：{text(e.eventSource)}</span></span>,
        `${(number(e.points) ?? 0) > 0 ? '+' : ''}${amount(e.points)}`,
      ])} />
    </div></section>
    <section className="block"><h3>涉诉情况</h3><Table headers={['案号', '当前状态', '诉讼角色', '金额（万元）', '风险分值']} values={rows(data.opinion.lawsuits).map((e) => [text(e.caseId), text(e.caseStatus), text(e.litigationRole), amount(e.amount), amount(e.points)])} note="涉诉快照不含立案日期，未纳入时间线。" /></section>
  </>
}

function Credit({ data }: { data: ReportData }) {
  const c = data.credit, unit = text(c.unit)
  const steps = rows(c.steps)
  const entityScope = data.scope === 'enterprise'
  return <>
    <div className="callout"><strong>{text(data.rating.riskLevel ?? c.riskLevel)} · {scoreLabel(data)} {amount(data.rating.score)} · 建议授信额度 {text(c.suggestedCreditAmount ?? data.report.suggestedCreditAmount)} {unit}</strong>
      {entityScope
        ? <>利率方向 {text(c.rateDirection)}。一票否决：{strings(data.rating.vetoes).join('、') || '无'}。企业主体测算，不含申请贷款额度。测算建议，不是银行批准额度或正式报价。</>
        : <>申请贷款额度 {amount(c.applyAmount)} {unit}；期限 {text(c.termMonths)} 个月；担保方式 {text(c.guaranteeType)}；利率方向 {text(c.rateDirection)}。一票否决：{strings(data.rating.vetoes).join('、') || '无'}。测算建议，不是银行批准额度或正式报价。</>}
    </div>
    <section className="block"><h3>额度计算路径</h3>{steps.length ? <div className="steps">{steps.map((s, i) => <div className="step" key={i}>
      <span className="n">{i + 1}</span><div>{text(s.step)}<br /><small>{text(s.formula)}</small></div>
      <b>{Array.isArray(s.value) ? `命中 ${s.value.length} 项` : amount(s.value)}{number(s.value) !== null || /^\d+-\d+$/.test(String(s.value)) ? <small> {unit}</small> : null}</b>
    </div>)}</div> : <EmptyData />}
      <p className="table-note">取数年度 {text(c.financialYear)}；政策版本 {text(c.policyVersion)}。存量贷款 {amount(dict(c.exposures).existingLoanBalance)} 万元、对外担保 {amount(dict(c.exposures).externalGuaranteeAmount)} 万元。</p></section>
    <section className="block"><h3>评级维度 · {isPointsScorecard(rows(data.rating.dimensions)) ? '风险点数 / 上限' : '0—100 分'}</h3><DimensionChart dimensions={rows(data.rating.dimensions)} />
      <p className="table-note">{isPointsScorecard(rows(data.rating.dimensions))
        ? `${text(data.rating.scoreDirection)}；合计 ${amount(data.rating.score)} 点。点数不是违约概率。`
        : `本次快照为旧版评分卡（分数越高越好），加权总分 ${amount(data.rating.score)}。分数不是违约概率。`}</p></section>
  </>
}

function Conditions({ data }: { data: ReportData }) {
  const fraud = rows(data.fraud.rules)
  return <>
    <div className="origin">{data.scope === 'enterprise' ? '评级与风险核查条件' : '额度测算条件'}</div>
    {data.conditions.length ? data.conditions.map((c, i) => <div className="task" key={i}><div className="task-head"><strong>{String(i + 1).padStart(2, '0')}　{businessNarrative(c)}</strong><span className="tag">工具条件</span></div></div>) : <EmptyData>本次工具未输出风控条件</EmptyData>}
    <section className="block"><h3>反欺诈规则结果明细</h3><Table headers={['规则', '结果', '计算值', '配置阈值']} values={fraud.map((r) => [
      `${text(r.ruleId)} ${text(r.name)}`, r.hit === true ? '命中' : r.hit === false ? '未命中' : '暂无数据', amount(r.value), amount(r.threshold),
    ])} note="值为原始工具输出；单列阈值不代表完整规则，正式解释以规则配置为准。" /></section>
    <div className="callout block"><strong>复核与资料边界</strong>{data.rating.needsManualReview === true ? '存在评级资料缺口，需补充资料并人工核实。' : data.rating.needsManualReview === false ? '未发现评级资料缺口，仍须按业务流程复核。' : '本次未取得评级资料完整性结果，请人工核实。'}报告生成与尽调建议不代表贷款审批或放款。</div>
  </>
}

export function ReportDocument({ run, data }: { run: RunDetail; data: ReportData }) {
  const years = rows(data.finance.years).sort((a, b) => Number(a.year) - Number(b.year))
  const notes = splitAnswer(run.answer ?? '')
  const unit = text(data.credit.unit)
  const enterprise = text(data.enterpriseId), application = text(data.applicationId)
  const entityScope = data.scope === 'enterprise'
  // 两种口径都含额度页；企业口径只展示建议授信额度，不展示申请贷款额度。
  const chapters = CHAPTERS
  const footer = '本次运行快照＋工具计算＋模型解读 · 非正式审批报告'
  const body: Record<ChapterId, ReactNode> = {
    summary: <>
      <div className="eyebrow">Due diligence report / {enterprise}</div><div className="rule" />
      <h1>{entityScope ? '企业主体' : '企业智能信贷'}<br />尽职调查报告</h1>
      <p className="subtitle">{data.enterpriseName ? `${text(data.enterpriseName)} · ` : ''}企业 {enterprise}{entityScope ? ' · 企业主体尽调' : ` · 申请 ${application}`}</p>
      <p className="watermark">数据取自本次运行落库快照｜工具现算｜模型 {run.model} 解读｜生成于 {text(run.finishedAt ?? run.createdAt)}</p>
      {data.ambiguous ? <div className="callout warn block"><strong>对象不唯一</strong>本次运行涉及多个对象，无法唯一定位报告数据，结构化图表不合并展示。</div> : null}
      <div className="kpis">
        <div className="kpi"><label>系统计算评级</label><div className="value">{text(data.rating.riskLevel ?? data.report.riskLevel)}</div><div className="caption">{scoreLabel(data)} {amount(data.rating.score)}{data.rating.scoreDirection ? `，${text(data.rating.scoreDirection)}` : ''}</div></div>
        <div className="kpi"><label>建议授信额度</label><div className="value">{text(data.credit.suggestedCreditAmount ?? data.report.suggestedCreditAmount)}</div><div className="caption">单位：{unit} · 测算结果</div></div>
        {entityScope ? <>
          <div className="kpi"><label>财务基准年度</label><div className="value">{text(data.credit.financialYear ?? years.at(-1)?.year)} <small>年</small></div><div className="caption">最近完整年度</div></div>
        </> : <>
          <div className="kpi"><label>申请贷款额度</label><div className="value">{amount(data.credit.applyAmount)}</div><div className="caption">单位：{unit}</div></div>
          <div className="kpi"><label>建议期限</label><div className="value">{text(data.credit.termMonths)} <small>个月</small></div><div className="caption">利率方向：{text(data.credit.rateDirection)}</div></div>
          <div className="kpi"><label>财务基准年度</label><div className="value">{text(data.credit.financialYear ?? data.finance.latestYear)} <small>年</small></div><div className="caption">本次额度测算取数年度</div></div>
        </>}
      </div>
      <div className="callout"><strong>尽调结论</strong>{data.report.dueDiligenceConclusion ? text(data.report.dueDiligenceConclusion) : '本次未返回独立的结构化结论，见下方模型解读。'}</div>
      <SummaryNote model={run.model} text={notes.summary} />
      <div className="panel block small"><strong>时间与范围</strong><br />数据截止：{text(data.report.asOf ?? data.credit.asOf ?? data.finance.asOf)}；财务期间：{years.length ? `${text(years[0].year)}—${text(years.at(-1)!.year)}` : '暂无数据'}。<br />报告生成：{text(run.finishedAt ?? run.createdAt)}。数据截止日与生成时间不同，不代表实时经营情况。</div>
    </>,
    overview: <><Overview data={data} /><ModelNote model={run.model}>{notes.overview}</ModelNote></>,
    finance: <><Finance data={data} years={years} /><ModelNote model={run.model}>{notes.finance}</ModelNote></>,
    quality: <Quality data={data} years={years} />,
    risk: <><Risk data={data} /><ModelNote model={run.model}>{notes.risk}</ModelNote></>,
    credit: <><Credit data={data} /><ModelNote model={run.model}>{notes.credit}</ModelNote></>,
    conditions: <><Conditions data={data} /><ModelNote model={run.model}>{notes.conditions}</ModelNote></>,
  }
  return <div className="layout">
    <nav className="sidebar" aria-label="报告目录"><h3>报告目录 / CONTENTS</h3>{chapters.map(([id, title], i) => <a href={`#${id}`} key={id}>{String(i + 1).padStart(2, '0')}　{title}</a>)}
      <div className="note"><strong>数据范围</strong><br />仅本次运行的落库事实、工具计算和模型解读。</div></nav>
    <main className="pages">{chapters.map(([id, title], i) => <article id={id} className="sheet" key={id}>
      <div className="running"><strong>{entityScope ? '企业主体尽调' : '企业信贷尽调'}</strong><span>{entityScope ? enterprise : `${enterprise} / ${application}`}</span></div>
      <div className="pagebody">{i > 0 ? <div className="section-head"><div><div className="eyebrow">{HEADS[id][0]}</div><h2>{title}</h2><p className="subtitle">{HEADS[id][1]}</p></div><span className="number">{String(i + 1).padStart(2, '0')}</span></div> : null}{body[id]}</div>
      <div className="footer"><span>{footer}</span><span>{String(i + 1).padStart(2, '0')} / {String(chapters.length).padStart(2, '0')}</span></div>
    </article>)}</main>
  </div>
}
