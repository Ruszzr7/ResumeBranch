import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

test('main conversation reset is explicit and preserves resume business data', () => {
  assert.ok(appSource.includes('aria-label="重新开始"'))
  assert.ok(appSource.includes('重置当前对话上下文'))
  assert.ok(appSource.includes('将清空当前主对话的消息和上下文，但不会影响简历、JD、排版及版本记录。'))
  assert.ok(appSource.includes('`/tasks/${currentTaskId.value}/contexts/${context.id}/reset`'))
  assert.ok(appSource.includes("context.context_type === 'main' && context.session_id === activeContextId"))
  assert.ok(appSource.includes('main-context-reset-modal'))
  assert.ok(appSource.includes('isLoading || isResponding || isSwitchingContext || isResettingMainContext'))
  assert.ok(appSource.includes('localOnly: true'))
})
