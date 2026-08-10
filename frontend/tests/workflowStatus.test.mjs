import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

test('workflow status localizes internal focus paths', () => {
  assert.ok(appSource.includes("'basics.target_position': '目标岗位'"))
  assert.ok(appSource.includes('聚焦：{{ workflowFocusLabel }}'))
  assert.equal(appSource.includes('聚焦：{{ workflowState.focus_section }}'), false)
  assert.ok(appSource.includes("? '简历内容' : focus"))
})

test('workflow status describes user-grounded additions without claiming external verification', () => {
  assert.ok(appSource.includes('已确认 {{ workflowState.fact_count || 0 }} 条补充信息'))
  assert.equal(appSource.includes('已核实 {{ workflowState.fact_count || 0 }} 条事实'), false)
})

test('completed workflow status remains visible for two seconds after a live command', () => {
  assert.ok(appSource.includes('function updateWorkflowState(nextState'))
  assert.ok(appSource.includes('workflowCompletedVisible.value = Boolean(completed && showCompletedBriefly)'))
  assert.ok(appSource.includes('}, 2000)'))
  assert.ok(appSource.includes("updateWorkflowState(data.state || null, { showCompletedBriefly: true })"))
  assert.ok(appSource.includes('updateWorkflowState(data.state || null)'))
})
