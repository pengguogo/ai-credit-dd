/**
 * 尽调维度：把完整「主控 Agent 调度」拆成单角色页，便于查看单步工具结果；
 * 末步「尽调报告」汇总结构化五部分并可导出。
 *
 * 交互：选维度菜单 → 选贷款申请 → 分析本步 → 结构化展示本步工具结果。
 * 依赖说明见 docs/40-specs/enterprise-dd/五步依赖与单步核对.md
 */

export type ReportDimSlug =
  | 'finance'
  | 'business'
  | 'opinion'
  | 'fraud'
  | 'credit-risk'
  | 'report'

/** 计算依赖：本步内部会用到的前序结果（不必先打开前序页，服务端同进程重算）。 */
export interface ReportDimDependency {
  slug: ReportDimSlug
  label: string
  /** 本步如何用到该前置 */
  how: string
  /** false = 菜单叙事在前，但本步规则不读 */
  used: boolean
}

export interface ReportDim {
  slug: ReportDimSlug
  label: string
  step: number
  tools: string[]
  blurb: string
  /** 英雄区短句：一眼抓住本步价值 */
  hero: string
  /** 视觉主题：驱动渐变与强调色（仍落在品牌橙 / 科技青体系内） */
  theme: 'amber' | 'teal' | 'sky' | 'rose' | 'orange'
  /** 本步是否强制需要申请编号才能出完整结果 */
  needsApplication: boolean
  /** 计算依赖（展示用；与 dd_calc 一致） */
  dependsOn: ReportDimDependency[]
}

export const REPORT_DIMS: ReportDim[] = [
  {
    slug: 'finance',
    label: '财报解析',
    step: 1,
    tools: ['analyze_financials'],
    blurb: '单独查看财报解析 Agent：近三年科目、比率、勾稽与增长；有申请时按申请日截年。',
    hero: '三年科目、勾稽与增长一眼对齐，比率异常即时标出。',
    theme: 'sky',
    needsApplication: false,
    dependsOn: [],
  },
  {
    slug: 'business',
    label: '工商核验',
    step: 2,
    tools: ['verify_business_info'],
    blurb: '单独查看工商核验 Agent：经营状态、实缴、关联担保与 findings。',
    hero: '核验主体身份与关联网络，把异常 finding 摊开看清。',
    theme: 'teal',
    needsApplication: false,
    dependsOn: [],
  },
  {
    slug: 'opinion',
    label: '舆情扫描',
    step: 3,
    tools: ['scan_public_opinion'],
    blurb: '单独查看舆情扫描 Agent：事件列表、标签、健康分与涉诉。',
    hero: '舆情与涉诉合流成健康分，风险标签先于正文出现。',
    theme: 'amber',
    needsApplication: false,
    dependsOn: [],
  },
  {
    slug: 'fraud',
    label: '反欺诈检测',
    step: 4,
    tools: ['detect_fraud_signals'],
    blurb: '单独查看反欺诈检测 Agent：规则读取财报增长与工商侧关联/担保圈；舆情不参与本步。',
    hero: '规则引擎逐条点亮命中，财报与工商侧信号交叉验证。',
    theme: 'rose',
    needsApplication: false,
    // 与 detect_fraud / detect_fraud_signals 一致：内部先 analyze_financials；F06 读关联企业
    dependsOn: [
      {
        slug: 'finance',
        label: '财报解析',
        how: '内部即时重算科目与增长 → 规则 F01–F05',
        used: true,
      },
      {
        slug: 'business',
        label: '工商核验',
        how: '关联企业数与担保圈 → 规则 F06',
        used: true,
      },
      {
        slug: 'opinion',
        label: '舆情扫描',
        how: '本步规则不读舆情；进入「额度测算」评级才用健康分',
        used: false,
      },
    ],
  },
  {
    slug: 'credit-risk',
    label: '额度测算',
    step: 5,
    tools: ['rate_risk', 'calc_credit_limit'],
    blurb: '单独查看评级与额度测算：内部重跑前四步中间结果再算档位与额度。',
    hero: '评分卡落地风险档位，建议额度与风控条件一并给出。',
    theme: 'orange',
    needsApplication: false,
    dependsOn: [
      { slug: 'finance', label: '财报解析', how: '指标 flag、勾稽与能力口径', used: true },
      { slug: 'business', label: '工商核验', how: 'findings / 实缴等进稳定性维度', used: true },
      { slug: 'opinion', label: '舆情扫描', how: '健康分进司法舆情维度', used: true },
      { slug: 'fraud', label: '反欺诈检测', how: '命中数进欺诈维度与否决', used: true },
    ],
  },
  {
    slug: 'report',
    label: '尽调报告',
    step: 6,
    tools: ['build_dd_report'],
    blurb: '汇总五部分结构化报告（概况 / 财务 / 风险 / 额度 / 风控），可导出 JSON。',
    hero: '一次汇总同源计算结论，导出可核对的结构化尽调报告。',
    theme: 'orange',
    needsApplication: true,
    dependsOn: [
      { slug: 'finance', label: '财报解析', how: '三年科目与增长进财务分析章', used: true },
      { slug: 'business', label: '工商核验', how: '概况 findings 与主体状态', used: true },
      { slug: 'opinion', label: '舆情扫描', how: '标签进风险提示', used: true },
      { slug: 'fraud', label: '反欺诈检测', how: '命中规则进风险提示', used: true },
      { slug: 'credit-risk', label: '额度测算', how: '评级、额度与风控条件', used: true },
    ],
  },
]

export function dimBySlug(slug: string | undefined): ReportDim {
  return REPORT_DIMS.find((d) => d.slug === slug) ?? REPORT_DIMS[0]
}

export type ReportContext = {
  enterpriseId: string
  applicationId: string
}

export function readReportContext(search = typeof window !== 'undefined' ? window.location.search : ''): ReportContext {
  const q = new URLSearchParams(search)
  return {
    enterpriseId: (q.get('enterpriseId') ?? '').trim(),
    applicationId: (q.get('applicationId') ?? '').trim(),
  }
}

export function reportPath(slug = REPORT_DIMS[0].slug, ctx?: Partial<ReportContext>): string {
  const base = `/report/${slug}`
  const enterpriseId = ctx?.enterpriseId?.trim() ?? ''
  const params = new URLSearchParams()
  if (enterpriseId) params.set('enterpriseId', enterpriseId)
  const applicationId = ctx?.applicationId?.trim() ?? ''
  if (applicationId) params.set('applicationId', applicationId)
  const qs = params.toString()
  return qs ? `${base}?${qs}` : base
}

/** 切换维度时保留当前 URL 中的贷款申请与企业。 */
export function reportHref(slug: ReportDim['slug'], search?: string): string {
  const context = readReportContext(search)
  return reportPath(slug, context)
}
