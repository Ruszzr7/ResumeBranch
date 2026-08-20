import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

test('standalone mission windows do not render the legacy workflow status bar', () => {
  assert.equal(appSource.includes('<div v-if="workflowVisible" class="workflow-status"'), false)
  assert.equal(appSource.includes('已确认 {{ workflowState.fact_count || 0 }} 条补充信息'), false)
})

test('completed workflow status remains visible for two seconds after a live command', () => {
  assert.ok(appSource.includes('function updateWorkflowState(nextState'))
  assert.ok(appSource.includes('targetState.workflowCompletedVisible = Boolean(completed && showCompletedBriefly)'))
  assert.ok(appSource.includes('}, 2000)'))
  assert.ok(appSource.includes("updateWorkflowState(data.state || null, { showCompletedBriefly: true }, requestState)"))
  assert.ok(appSource.includes('updateWorkflowState(data.state || null, {}, targetState)'))
})
