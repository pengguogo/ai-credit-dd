/**
 * srcDoc 文档的基准地址是父页面 URL，`#id` 链接会让 iframe 整页导航到预览页本身；
 * 沙箱禁止脚本，导航后只剩空白。这里由父页面接管页内锚点，改为在报告内滚动定位。
 */
export function bindAnchorScroll(doc: Document | null | undefined) {
  if (!doc) return
  doc.addEventListener('click', (event) => {
    const link = (event.target as Element | null)?.closest?.('a')
    const href = link?.getAttribute('href') ?? ''
    if (!href.startsWith('#')) return
    event.preventDefault()
    const target = doc.getElementById(decodeURIComponent(href.slice(1)))
    if (!target) return
    let ancestor: Element | null = target
    while (ancestor) {
      if (ancestor.tagName === 'DETAILS') (ancestor as HTMLDetailsElement).open = true
      ancestor = ancestor.parentElement
    }
    target.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

