/**
 * 把 Agent 回复原文导出为 PDF / Word。
 * 内容与对话里展示的答案一致，不在前端重算结论；敏感字段做导出脱敏。
 */

const CREDIT_CODE = /[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}/g
const ID_CARD = /(?<![0-9A-Za-z])[1-9]\d{16}[\dXx](?![0-9A-Za-z])/g
const FONT = '"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif'

const PAGE_W = 794
const PAGE_H = 1123
const MARGIN = 40
const BOTTOM = 36
const SCALE = 2

export interface TextBlock {
  kind: 'title' | 'heading' | 'body' | 'note'
  text: string
}

export interface TableBlock {
  kind: 'table'
  headers: string[]
  rows: string[][]
}

export type ReportBlock = TextBlock | TableBlock

/** 导出文本里的信用代码、证件号，以及实控人/股东姓名。 */
export function maskExportText(value: string): string {
  return value
    .replace(CREDIT_CODE, (token) => maskToken(token, 4, 4))
    .replace(ID_CARD, (token) => maskToken(token, 3, 4))
    .replace(/实控人\S+?(?=与)/g, '实控人***')
    .replace(/第一大股东\S+?(?=不一致)/g, '第一大股东***')
}

function maskToken(value: string, head: number, tail: number): string {
  if (value.length <= head + tail) return '*'.repeat(Math.max(value.length, 4))
  return value.slice(0, head) + '*'.repeat(value.length - head - tail) + value.slice(-tail)
}

function plainInline(value: string): string {
  return maskExportText(
    value
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/^#{1,4}\s+/, '')
      .trim(),
  )
}

function splitRow(line: string): string[] {
  return line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => plainInline(cell))
}

/**
 * 没有 `#` 的章节标题行：可带「一、」「1.」前缀，但整行只能是章节名。
 * @why 不能带冒号后缀：报告正文要求写「风险评级：<档位>」「额度建议：…」，那是正文不是标题。
 */
const SECTION_TITLE =
  /^(?:(?:\d+[.、]|[一二三四五六七八九十]+[、.])\s*)?(企业概况|近三年财务分析|财务分析|风险评级|反欺诈检测|风险提示|建议授信额度|额度建议|风控条件)[：:]?$/
const REPORT_SECTIONS = ['企业概况', '财务分析', '风险提示', '额度建议', '风控条件']
const REPORT_TITLE = '企业智能信贷尽调报告'
const ENTITY_REPORT_TITLE = '企业主体尽调报告'

/** 报告首行标题：贷款口径与企业口径各自固定，导出时都只保留一个文档标题。 */
function isReportTitle(text: string): boolean {
  return text === REPORT_TITLE || text === ENTITY_REPORT_TITLE
}

/** 是否完整尽调报告：五个章节标题至少出现四个（单项追问的回答不按报告命名）。 */
export function isFullReport(answer: string): boolean {
  const headings = answer.split(/\r?\n/)
    .map((line) => line.trim().replace(/^#{1,4}\s+/, '').replace(/^(?:\d+[.、]|[一二三四五六七八九十]+[、.])\s*/, ''))
  return REPORT_SECTIONS.filter((s) => headings.includes(s)).length >= 4
}

/** 用户提示是否在要求生成完整尽调/尽职报告（预览报告按钮只在此类问询下展示）。 */
export function isReportGenerationQuestion(question: string): boolean {
  const q = question.replace(/\s+/g, '')
  if (!q) return false
  return /生成(完整)?(尽调|尽职(调查)?)报告|出具(完整)?(尽调|尽职(调查)?)报告|输出完整尽调报告|写(一份|一篇)?(尽调|尽职(调查)?)报告/.test(q)
}

/** 把 Agent 答案拆成导出块，尽量保留标题 / 表格 / 段落结构。 */
export function answerBlocks(answer: string, question?: string): ReportBlock[] {
  const blocks: ReportBlock[] = [
    // 标题按报告口径取名：企业口径报告不写「智能信贷」
    { kind: 'title', text: answer.includes(ENTITY_REPORT_TITLE) ? ENTITY_REPORT_TITLE : (isFullReport(answer) ? REPORT_TITLE : '企业信贷尽调问答') },
  ]
  if (question?.trim()) {
    blocks.push({ kind: 'note', text: `问询：${maskExportText(question.trim())}` })
  }
  const lines = answer.replace(/\r\n/g, '\n').split('\n')
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i += 1
      continue
    }
    if (line.trim().startsWith('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const headers = splitRow(line)
      const rows: string[][] = []
      i += 2
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        rows.push(splitRow(lines[i]))
        i += 1
      }
      blocks.push({ kind: 'table', headers, rows })
      continue
    }
    const mdHeading = /^(#{1,4})\s+(.*)$/.exec(line)
    if (mdHeading) {
      // 尽调报告 Skill 的回复以同名标题开头，导出已有文档标题，不重复
      if (!isReportTitle(plainInline(mdHeading[2]))) {
        blocks.push({ kind: 'heading', text: plainInline(mdHeading[2]) })
      }
      i += 1
      continue
    }
    const section = SECTION_TITLE.exec(line.trim())
    if (section) {
      blocks.push({ kind: 'heading', text: plainInline(line) })
      i += 1
      continue
    }
    const bullet = /^\s*(?:[-*•▸]|\d+[.)、])\s+(.*)$/.exec(line)
    blocks.push({
      kind: 'body',
      text: bullet ? `• ${plainInline(bullet[1])}` : plainInline(line),
    })
    i += 1
  }
  if (blocks.length <= (question?.trim() ? 2 : 1)) {
    blocks.push({ kind: 'note', text: '本次回复没有可导出的正文' })
  }
  return blocks
}

function exportBaseName(question: string, answer: string, runId: string | null): string {
  const hit = `${question}\n${answer}`.match(/\b(?:LA|E)\d{3}\b/)
  const raw = hit?.[0] || runId || 'report'
  const prefix = isFullReport(answer) ? '尽调报告' : '尽调问答'
  return `${prefix}_${raw.replace(/[^\w.-]+/g, '_') || 'report'}`
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function concat(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.length, 0)
  const out = new Uint8Array(total)
  let offset = 0
  for (const part of parts) {
    out.set(part, offset)
    offset += part.length
  }
  return out
}

/** 把每页 JPEG 装进一页 A4 PDF。 */
export function imagesToPdf(pages: { jpeg: Uint8Array; width: number; height: number }[]): Uint8Array {
  if (pages.length === 0) throw new Error('没有可导出的页面')
  const text = new TextEncoder()
  const chunks: Uint8Array[] = [text.encode('%PDF-1.4\n')]
  let cursor = chunks[0].length
  const offsets = [0]

  function add(body: Uint8Array) {
    const number = offsets.length
    offsets.push(cursor)
    const head = text.encode(`${number} 0 obj\n`)
    const tail = text.encode('\nendobj\n')
    chunks.push(head, body, tail)
    cursor += head.length + body.length + tail.length
  }

  const kids = pages.map((_, index) => `${3 + index * 3} 0 R`).join(' ')
  add(text.encode('<< /Type /Catalog /Pages 2 0 R >>'))
  add(text.encode(`<< /Type /Pages /Count ${pages.length} /Kids [${kids}] >>`))
  pages.forEach((page, index) => {
    const pageId = 3 + index * 3
    const content = text.encode(`q\n595.28 0 0 841.89 0 0 cm\n/Im${index} Do\nQ`)
    add(text.encode(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Contents ${pageId + 1} 0 R /Resources << /XObject << /Im${index} ${pageId + 2} 0 R >> >> >>`,
    ))
    add(concat([
      text.encode(`<< /Length ${content.length} >>\nstream\n`),
      content,
      text.encode('\nendstream'),
    ]))
    add(concat([
      text.encode(`<< /Type /XObject /Subtype /Image /Width ${page.width} /Height ${page.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${page.jpeg.length} >>\nstream\n`),
      page.jpeg,
      text.encode('\nendstream'),
    ]))
  })

  const xrefAt = cursor
  const lines = ['xref', `0 ${offsets.length}`, '0000000000 65535 f ']
  for (let index = 1; index < offsets.length; index += 1) {
    lines.push(`${String(offsets[index]).padStart(10, '0')} 00000 n `)
  }
  lines.push(`trailer`, `<< /Size ${offsets.length} /Root 1 0 R >>`, 'startxref', String(xrefAt), '%%EOF')
  chunks.push(text.encode(`${lines.join('\n')}\n`))
  return concat(chunks)
}

function wrap(ctx: CanvasRenderingContext2D, value: string, width: number): string[] {
  const lines: string[] = []
  let current = ''
  for (const char of value) {
    const next = current + char
    if (current && ctx.measureText(next).width > width) {
      lines.push(current)
      current = char
    } else {
      current = next
    }
  }
  lines.push(current || ' ')
  return lines
}

function blockGap(block: ReportBlock): number {
  if (block.kind === 'heading') return 16
  if (block.kind === 'title') return 8
  return 6
}

interface Page {
  canvas: HTMLCanvasElement
  ctx: CanvasRenderingContext2D
  y: number
}

function newPage(): Page {
  const canvas = document.createElement('canvas')
  canvas.width = PAGE_W * SCALE
  canvas.height = PAGE_H * SCALE
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('当前浏览器不能生成 PDF')
  ctx.scale(SCALE, SCALE)
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, PAGE_W, PAGE_H)
  ctx.fillStyle = '#1f2933'
  ctx.textBaseline = 'top'
  return { canvas, ctx, y: MARGIN }
}

function paintFooter(page: Page, index: number) {
  page.ctx.fillStyle = '#6b7280'
  page.ctx.font = `11px ${FONT}`
  page.ctx.fillText(`第 ${index + 1} 页`, MARGIN, PAGE_H - 24)
  page.ctx.fillStyle = '#1f2933'
}

function textHeight(ctx: CanvasRenderingContext2D, block: TextBlock): number {
  const size = block.kind === 'title' ? 20 : block.kind === 'heading' ? 14 : block.kind === 'note' ? 12 : 13
  ctx.font = `${block.kind === 'title' || block.kind === 'heading' ? 600 : 400} ${size}px ${FONT}`
  return wrap(ctx, block.text, PAGE_W - MARGIN * 2).length * (size + 6)
}

function drawText(page: Page, block: TextBlock) {
  const size = block.kind === 'title' ? 20 : block.kind === 'heading' ? 14 : block.kind === 'note' ? 12 : 13
  page.ctx.font = `${block.kind === 'title' || block.kind === 'heading' ? 600 : 400} ${size}px ${FONT}`
  page.ctx.fillStyle = block.kind === 'note' ? '#6b7280' : '#1f2933'
  for (const line of wrap(page.ctx, block.text, PAGE_W - MARGIN * 2)) {
    page.ctx.fillText(line, MARGIN, page.y)
    page.y += size + 6
  }
  page.ctx.fillStyle = '#1f2933'
}

function columnWidth(count: number): number {
  return (PAGE_W - MARGIN * 2) / Math.max(count, 1)
}

function rowHeight(ctx: CanvasRenderingContext2D, cells: string[], width: number): number {
  ctx.font = `11px ${FONT}`
  const lines = cells.map((cell) => wrap(ctx, cell, width - 8).length)
  return Math.max(...lines, 1) * 16 + 8
}

function drawRow(ctx: CanvasRenderingContext2D, cells: string[], y: number, width: number, header: boolean): number {
  const height = rowHeight(ctx, cells, width)
  ctx.font = `${header ? 600 : 400} 11px ${FONT}`
  ctx.fillStyle = header ? '#f3f4f6' : '#ffffff'
  ctx.fillRect(MARGIN, y, PAGE_W - MARGIN * 2, height)
  ctx.strokeStyle = '#e5e7eb'
  ctx.strokeRect(MARGIN, y, PAGE_W - MARGIN * 2, height)
  ctx.fillStyle = '#1f2933'
  cells.forEach((cell, index) => {
    const left = MARGIN + index * width
    ctx.strokeRect(left, y, width, height)
    let lineY = y + 4
    for (const line of wrap(ctx, cell, width - 8)) {
      ctx.fillText(line, left + 4, lineY)
      lineY += 16
    }
  })
  return height
}

async function canvasJpeg(canvas: HTMLCanvasElement): Promise<Uint8Array> {
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92))
  if (!blob) throw new Error('导出页面失败')
  return new Uint8Array(await blob.arrayBuffer())
}

async function renderPages(blocks: ReportBlock[]): Promise<{ jpeg: Uint8Array; width: number; height: number }[]> {
  const pages: Page[] = []
  let page = newPage()
  pages.push(page)
  const limit = PAGE_H - BOTTOM

  function breakPage() {
    paintFooter(page, pages.length - 1)
    page = newPage()
    pages.push(page)
  }

  for (const block of blocks) {
    if (block.kind === 'table') {
      const width = columnWidth(block.headers.length)
      const headerHeight = rowHeight(page.ctx, block.headers, width)
      const body = block.rows.length ? block.rows : [block.headers.map(() => '—')]
      for (const [rowIndex, row] of body.entries()) {
        const height = rowHeight(page.ctx, row, width)
        const needed = height + (rowIndex === 0 || page.y + height > limit ? headerHeight : 0)
        if (page.y + needed > limit) breakPage()
        if (rowIndex === 0 || page.y === MARGIN) page.y += drawRow(page.ctx, block.headers, page.y, width, true)
        page.y += drawRow(page.ctx, row, page.y, width, false)
      }
      page.y += 8
      continue
    }
    const height = textHeight(page.ctx, block) + blockGap(block)
    if (page.y + height > limit) breakPage()
    page.y += block.kind === 'heading' ? 14 : block.kind === 'title' ? 0 : 4
    drawText(page, block)
  }
  paintFooter(page, pages.length - 1)
  const images = []
  for (const item of pages) {
    images.push({ jpeg: await canvasJpeg(item.canvas), width: item.canvas.width, height: item.canvas.height })
  }
  return images
}

export async function downloadAnswerPdf(
  answer: string,
  options: { question?: string; runId?: string | null } = {},
): Promise<void> {
  const pdf = imagesToPdf(await renderPages(answerBlocks(answer, options.question)))
  const name = exportBaseName(options.question ?? '', answer, options.runId ?? null)
  const buffer = pdf.buffer.slice(pdf.byteOffset, pdf.byteOffset + pdf.byteLength) as ArrayBuffer
  triggerDownload(new Blob([buffer], { type: 'application/pdf' }), `${name}.pdf`)
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function wordText(value: string): string {
  const escaped = escapeXml(value)
  if (/^\s|\s$/.test(value)) return `<w:t xml:space="preserve">${escaped}</w:t>`
  return `<w:t>${escaped}</w:t>`
}

function wordParagraph(text: string, style: 'Title' | 'Heading1' | 'Normal'): string {
  const size = style === 'Title' ? 32 : style === 'Heading1' ? 24 : 21
  const bold = style === 'Title' || style === 'Heading1' ? '<w:b/>' : ''
  const color = style === 'Normal' ? '' : '<w:color w:val="1F2933"/>'
  return (
    `<w:p>`
    + `<w:pPr><w:pStyle w:val="${style}"/>`
    + (style === 'Normal' ? '' : '<w:spacing w:before="200" w:after="120"/>')
    + `</w:pPr>`
    + `<w:r><w:rPr>${bold}<w:sz w:val="${size}"/><w:szCs w:val="${size}"/>${color}</w:rPr>${wordText(text)}</w:r>`
    + `</w:p>`
  )
}

function wordTable(headers: string[], rows: string[][]): string {
  const cols = Math.max(headers.length, ...rows.map((row) => row.length), 1)
  const width = Math.floor(9000 / cols)
  const grid = `<w:tblGrid>${Array.from({ length: cols }, () => `<w:gridCol w:w="${width}"/>`).join('')}</w:tblGrid>`
  const cell = (value: string, header: boolean) => (
    `<w:tc><w:tcPr><w:tcW w:w="${width}" w:type="dxa"/>`
    + (header ? '<w:shd w:val="clear" w:fill="F3F4F6"/>' : '')
    + `</w:tcPr><w:p><w:r><w:rPr>${header ? '<w:b/>' : ''}<w:sz w:val="18"/></w:rPr>${wordText(value || '—')}</w:r></w:p></w:tc>`
  )
  const rowXml = (cells: string[], header: boolean) => {
    const padded = Array.from({ length: cols }, (_, index) => cells[index] ?? '')
    return `<w:tr>${padded.map((value) => cell(value, header)).join('')}</w:tr>`
  }
  const body = rows.length ? rows : [headers.map(() => '—')]
  return (
    `<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/>`
    + `<w:tblBorders>`
    + `<w:top w:val="single" w:sz="4" w:color="E5E7EB"/>`
    + `<w:left w:val="single" w:sz="4" w:color="E5E7EB"/>`
    + `<w:bottom w:val="single" w:sz="4" w:color="E5E7EB"/>`
    + `<w:right w:val="single" w:sz="4" w:color="E5E7EB"/>`
    + `<w:insideH w:val="single" w:sz="4" w:color="E5E7EB"/>`
    + `<w:insideV w:val="single" w:sz="4" w:color="E5E7EB"/>`
    + `</w:tblBorders></w:tblPr>${grid}${rowXml(headers, true)}${body.map((row) => rowXml(row, false)).join('')}</w:tbl>`
  )
}

function documentXml(blocks: ReportBlock[]): string {
  const parts: string[] = []
  for (const block of blocks) {
    if (block.kind === 'table') {
      parts.push(wordTable(block.headers, block.rows))
      continue
    }
    const style = block.kind === 'title' ? 'Title' : block.kind === 'heading' ? 'Heading1' : 'Normal'
    parts.push(wordParagraph(block.text, style))
  }
  return (
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`
    + `<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">`
    + `<w:body>${parts.join('')}`
    + `<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>`
    + `</w:body></w:document>`
  )
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let i = 0; i < 256; i += 1) {
    let c = i
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[i] = c
  }
  return table
})()

function crc32(data: Uint8Array): number {
  let c = 0xffffffff
  for (const byte of data) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

function u16(value: number): Uint8Array {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff])
}

function u32(value: number): Uint8Array {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff])
}

/** 无压缩 ZIP（store），用于拼最小 DOCX，不引入第三方库。 */
function zipStore(files: Record<string, string>): Blob {
  const encoder = new TextEncoder()
  const locals: Uint8Array[] = []
  const centrals: Uint8Array[] = []
  let offset = 0
  for (const [name, content] of Object.entries(files)) {
    const nameBytes = encoder.encode(name)
    const data = encoder.encode(content)
    const crc = crc32(data)
    const local = concat([
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(nameBytes.length),
      u16(0),
      nameBytes,
      data,
    ])
    const central = concat([
      u32(0x02014b50),
      u16(20),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(nameBytes.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0),
      u32(offset),
      nameBytes,
    ])
    locals.push(local)
    centrals.push(central)
    offset += local.length
  }
  const centralDir = concat(centrals)
  const end = concat([
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(Object.keys(files).length),
    u16(Object.keys(files).length),
    u32(centralDir.length),
    u32(offset),
    u16(0),
  ])
  const bytes = concat([...locals, centralDir, end])
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
  return new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  })
}

export function downloadAnswerDocx(
  answer: string,
  options: { question?: string; runId?: string | null } = {},
): void {
  const blocks = answerBlocks(answer, options.question)
  const name = exportBaseName(options.question ?? '', answer, options.runId ?? null)
  const blob = zipStore({
    '[Content_Types].xml': (
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`
      + `<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">`
      + `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>`
      + `<Default Extension="xml" ContentType="application/xml"/>`
      + `<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>`
      + `</Types>`
    ),
    '_rels/.rels': (
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`
      + `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">`
      + `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>`
      + `</Relationships>`
    ),
    'word/document.xml': documentXml(blocks),
  })
  triggerDownload(blob, `${name}.docx`)
}
