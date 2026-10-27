import assert from 'node:assert/strict'
import test from 'node:test'
import { diligenceProgress } from '../src/lib/dd-progress.ts'

const roles = ['business', 'finance', 'opinion', 'fraud', 'rating', 'report']
const plan = { type: 'plan_ready' }
const finished = (role, status = 'ok') => ({ type: 'role_finished', role, status })

test('主控计划就绪推进首段，报告生成与输出合并为最后一段', () => {
  const events = []
  assert.equal(diligenceProgress(events, 'running', '').completed, 0)
  events.push({ type: 'run_started' })
  assert.equal(diligenceProgress(events, 'running', '').stages[0].state, 'running')
  events.push(plan)
  assert.equal(diligenceProgress(events, 'running', '').completed, 1)
  for (const [index, role] of roles.entries()) {
    events.push(finished(role))
    assert.equal(diligenceProgress(events, 'running', '').completed, Math.min(index + 2, 6))
  }
  assert.equal(diligenceProgress(events, 'succeeded', '').completed, 6)
  const progress = diligenceProgress(events, 'succeeded', '实际报告')
  assert.equal(progress.completed, 7)
  assert.deepEqual(progress.stages.map(stage => stage.label), ['主控', '工商', '财报', '舆情', '反欺诈', '评级授信', '生成报告'])
  assert.equal(diligenceProgress(events, 'needs_confirmation', '待业务确认报告').completed, 7)
})

test('重复事件不重复累计，重跑和失败会撤回旧节点完成状态', () => {
  const events = [finished('business'), finished('business'), finished('finance', 'failed')]
  assert.equal(diligenceProgress(events, 'running', '').completed, 1)
  events.push({ type: 'role_started', role: 'business' })
  assert.equal(diligenceProgress(events, 'running', '').completed, 0)
  events.push(finished('business', 'degraded'))
  assert.equal(diligenceProgress(events, 'failed', '错误说明').completed, 0)
})

test('追问未执行的角色保持未完成，错误和澄清不能当作报告输出', () => {
  for (const status of ['failed', 'blocked', 'insufficient_evidence', 'needs_clarification']) {
    assert.equal(diligenceProgress([plan, ...roles.map(role => finished(role))], status, '错误说明').completed, 6)
  }
  const progress = diligenceProgress([finished('report')], 'succeeded', '追问结果')
  assert.equal(progress.completed, 1)
  assert.equal(progress.stages.length, 7)
})


test('工商财报舆情并行，任意完成顺序只更新实际完成节点', () => {
  const orders = [
    ['business', 'finance', 'opinion'], ['business', 'opinion', 'finance'],
    ['finance', 'business', 'opinion'], ['finance', 'opinion', 'business'],
    ['opinion', 'business', 'finance'], ['opinion', 'finance', 'business'],
  ]
  for (const order of orders) {
    const events = [plan, ...order.map(role => ({ type: 'role_started', role }))]
    const completed = new Set()
    for (const role of order) {
      events.push(finished(role))
      completed.add(role)
      const progress = diligenceProgress(events, 'running', '')
      assert.equal(progress.completed, 1 + completed.size)
      for (const parallelRole of order) {
        assert.equal(progress.stages.find(stage => stage.id === parallelRole).state,
          completed.has(parallelRole) ? 'ok' : 'running')
      }
    }
  }
})
