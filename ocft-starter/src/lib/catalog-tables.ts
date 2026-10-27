/** 业务目录 kind，以及数据列表页的业务表。 */

export type CatalogKind =
  | 'enterprises'
  | 'applications'
  | 'shareholders'
  | 'finances'
  | 'public_opinions'
  | 'lawsuits'
  | 'related'
  | 'guarantees'
  | 'risks'
  | 'schema_relationships'

export interface ListTableItem {
  kind: CatalogKind
  label: string
  table: string
  /** 对应 CSV 文件名；尽调维度无导入 */
  csvFile?: string
  /** 是否支持单行增删改 */
  writable: boolean
}

/** 企业档案菜单：只读尽调维度（放首位）+ 企业信息 + 8 张可写业务表。 */
export const LIST_TABLES: ListTableItem[] = [
  { kind: 'schema_relationships', label: '尽调维度', table: 'schema_relationships', writable: false },
  { kind: 'enterprises', label: '企业信息', table: 'enterprise_basic', csvFile: 'enterprise_basic.csv', writable: true },
  { kind: 'applications', label: '贷款申请', table: 'loan_application', csvFile: 'loan_application.csv', writable: true },
  { kind: 'shareholders', label: '股东信息', table: 'enterprise_shareholder', csvFile: 'enterprise_shareholder.csv', writable: true },
  { kind: 'finances', label: '财务数据', table: 'enterprise_finance', csvFile: 'enterprise_finance.csv', writable: true },
  { kind: 'public_opinions', label: '舆情事件', table: 'enterprise_public_opinion', csvFile: 'enterprise_public_opinion.csv', writable: true },
  { kind: 'lawsuits', label: '涉诉案件', table: 'enterprise_lawsuit', csvFile: 'enterprise_lawsuit.csv', writable: true },
  { kind: 'related', label: '关联企业', table: 'enterprise_related', csvFile: 'enterprise_related.csv', writable: true },
  { kind: 'guarantees', label: '对外担保', table: 'enterprise_guarantee', csvFile: 'enterprise_guarantee.csv', writable: true },
  { kind: 'risks', label: '风险汇总', table: 'enterprise_risk', csvFile: 'enterprise_risk.csv', writable: true },
]

/** 单行表单字段：与写接口 camelCase 一致（风险汇总不含外部评级列）。 */
export type FieldOption = { value: string; label: string }

export type FieldDef = {
  key: string
  label: string
  /** text 默认；auto 新建时只读自动生成；enterprise 企业编号下拉；date / select 见控件 */
  type?: 'text' | 'number' | 'date' | 'select' | 'auto' | 'enterprise'
  options?: FieldOption[]
}

export const LOAN_STATUS_OPTIONS: FieldOption[] = [
  { value: 'pending', label: '待处理' },
  { value: 'pending_review', label: '待审核' },
  { value: 'approved', label: '审核通过' },
  { value: 'rejected', label: '审核不通过' },
]

export const LOAN_GUARANTEE_OPTIONS: FieldOption[] = [
  { value: '抵押担保', label: '抵押担保' },
  { value: '信用担保', label: '信用担保' },
  { value: '保证担保', label: '保证担保' },
]

export const LOAN_TERM_OPTIONS: FieldOption[] = [
  { value: '12', label: '12 个月' },
  { value: '18', label: '18 个月' },
  { value: '24', label: '24 个月' },
  { value: '36', label: '36 个月' },
  { value: '60', label: '60 个月' },
]

/** 按已有编号生成下一个唯一审批号（LA001 → LA011…）；无匹配时从 LA001 起。 */
export function nextApplicationId(existing: Iterable<string>, floor = 0): string {
  let max = Math.max(0, floor)
  for (const raw of existing) {
    const m = /^LA(\d+)$/i.exec(String(raw).trim())
    if (m) max = Math.max(max, Number(m[1]))
  }
  return `LA${String(max + 1).padStart(3, '0')}`
}

export const WRITE_FIELDS: Record<Exclude<CatalogKind, 'schema_relationships'>, FieldDef[]> = {
  enterprises: [
    { key: 'enterpriseId', label: '企业编号' },
    { key: 'enterpriseName', label: '企业名称' },
    { key: 'creditCode', label: '信用代码' },
    { key: 'legalPerson', label: '法人' },
    { key: 'legalPersonId', label: '法人证件号' },
    { key: 'registerCapital', label: '注册资本', type: 'number' },
    { key: 'registeredCapitalPaid', label: '实缴资本', type: 'number' },
    { key: 'establishDate', label: '成立日期', type: 'date' },
    { key: 'enterpriseType', label: '企业类型' },
    { key: 'industry', label: '行业' },
    { key: 'registerAddress', label: '注册地址' },
    { key: 'businessScope', label: '经营范围' },
    { key: 'employeeCount', label: '员工人数', type: 'number' },
    { key: 'relatedEnterpriseCount', label: '关联企业数', type: 'number' },
    { key: 'businessStatus', label: '经营状态' },
    { key: 'legalPersonDishonest', label: '法人失信' },
    { key: 'legalPersonConsumptionLimit', label: '法人限高' },
    { key: 'actualController', label: '实控人' },
  ],
  applications: [
    { key: 'applicationId', label: '贷款编号', type: 'auto' },
    { key: 'enterpriseId', label: '企业编号', type: 'enterprise' },
    { key: 'applyAmount', label: '申请额(万)', type: 'number' },
    { key: 'loanPurpose', label: '用途' },
    { key: 'loanTermMonths', label: '期限(月)', type: 'select', options: LOAN_TERM_OPTIONS },
    { key: 'applyDate', label: '申请日期', type: 'date' },
    { key: 'guaranteeType', label: '担保', type: 'select', options: LOAN_GUARANTEE_OPTIONS },
    { key: 'status', label: '状态', type: 'select', options: LOAN_STATUS_OPTIONS },
  ],
  shareholders: [
    { key: 'enterpriseId', label: '企业编号' },
    { key: 'shareholderName', label: '股东名称' },
    { key: 'shareholderType', label: '股东类型' },
    { key: 'shareholdingRatio', label: '持股比例', type: 'number' },
    { key: 'contributionAmount', label: '出资金额', type: 'number' },
    { key: 'contributionRatio', label: '出资比例', type: 'number' },
  ],
  finances: [
    { key: 'enterpriseId', label: '企业编号' },
    { key: 'year', label: '年份', type: 'number' },
    { key: 'revenue', label: '营收', type: 'number' },
    { key: 'netProfit', label: '净利润', type: 'number' },
    { key: 'totalAssets', label: '总资产', type: 'number' },
    { key: 'totalLiabilities', label: '总负债', type: 'number' },
    { key: 'operatingCashflow', label: '经营现金流', type: 'number' },
    { key: 'accountsReceivable', label: '应收账款', type: 'number' },
    { key: 'inventory', label: '存货', type: 'number' },
    { key: 'fixedAssets', label: '固定资产', type: 'number' },
    { key: 'shortTermLoan', label: '短期借款', type: 'number' },
    { key: 'longTermLoan', label: '长期借款', type: 'number' },
    { key: 'accountsPayable', label: '应付账款', type: 'number' },
    { key: 'otherReceivable', label: '其他应收', type: 'number' },
    { key: 'prepayment', label: '预付款', type: 'number' },
    { key: 'ownersEquity', label: '所有者权益', type: 'number' },
    { key: 'rdExpense', label: '研发费用', type: 'number' },
    { key: 'salesExpense', label: '销售费用', type: 'number' },
    { key: 'adminExpense', label: '管理费用', type: 'number' },
    { key: 'financeExpense', label: '财务费用', type: 'number' },
    { key: 'auditOpinion', label: '审计意见' },
  ],
  public_opinions: [
    { key: 'enterpriseId', label: '企业编号' },
    { key: 'eventId', label: '事件编号' },
    { key: 'eventDate', label: '事件日期' },
    { key: 'eventType', label: '事件类型' },
    { key: 'eventSource', label: '来源' },
    { key: 'eventContent', label: '内容' },
    { key: 'sentiment', label: '情感' },
    { key: 'impactLevel', label: '影响等级' },
  ],
  lawsuits: [
    { key: 'enterpriseId', label: '企业编号' },
    { key: 'caseId', label: '案件编号' },
    { key: 'caseNumber', label: '案号' },
    { key: 'caseType', label: '案件类型' },
    { key: 'cause', label: '案由' },
    { key: 'filingDate', label: '立案日期' },
    { key: 'caseStatus', label: '状态' },
    { key: 'litigationRole', label: '诉讼地位' },
    { key: 'amount', label: '金额', type: 'number' },
  ],
  related: [
    { key: 'enterpriseId', label: '企业编号' },
    { key: 'relatedEnterpriseName', label: '关联企业' },
    { key: 'relationType', label: '关系类型' },
    { key: 'shareholdingRatio', label: '持股比例', type: 'number' },
    { key: 'isGuaranteeCircle', label: '担保圈' },
  ],
  guarantees: [
    { key: 'enterpriseId', label: '企业编号' },
    { key: 'guaranteedParty', label: '被担保方' },
    { key: 'guaranteeAmount', label: '担保金额', type: 'number' },
    { key: 'guaranteeType', label: '担保类型' },
    { key: 'guaranteePeriod', label: '担保期限' },
    { key: 'isOverdue', label: '是否逾期' },
  ],
  risks: [
    { key: 'enterpriseId', label: '企业编号' },
    { key: 'existingLoanBalance', label: '存量贷款', type: 'number' },
    { key: 'overdueCount', label: '逾期次数', type: 'number' },
    { key: 'overdueAmount', label: '逾期金额', type: 'number' },
    { key: 'externalGuaranteeAmount', label: '对外担保', type: 'number' },
    { key: 'publicOpinionScore', label: '舆情评分', type: 'number' },
    { key: 'abnormalOperation', label: '经营异常' },
  ],
}
