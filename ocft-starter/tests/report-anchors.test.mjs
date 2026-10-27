import assert from 'node:assert/strict'
import test from 'node:test'
import { bindAnchorScroll } from '../src/components/report/preview/report-anchors.ts'

test('点击依据在原报告内展开并定位，不导航到父页面', () => {
  let click
  let prevented = false
  let scrolled = false
  const detail = { tagName: 'DETAILS', open: false, parentElement: null, scrollIntoView() { scrolled = true } }
  const doc = { addEventListener(name, handler) { assert.equal(name, 'click'); click = handler }, getElementById(id) { assert.equal(id, 'evidence-test'); return detail } }
  bindAnchorScroll(doc)
  click({ target: { closest() { return { getAttribute() { return '#evidence-test' } } } }, preventDefault() { prevented = true } })
  assert.equal(prevented, true)
  assert.equal(detail.open, true)
  assert.equal(scrolled, true)
})
