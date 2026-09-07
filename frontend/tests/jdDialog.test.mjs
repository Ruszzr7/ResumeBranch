import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

test('JD editor keeps legacy form controls on the dark dialog surface', () => {
  assert.ok(appSource.includes('.jd-dialog .back-btn'))
  assert.ok(appSource.includes('.jd-dialog .tags-input'))
  assert.ok(appSource.includes('.jd-dialog .tags-input .tag-input'))
  assert.ok(appSource.includes('background: rgba(255, 255, 255, 0.035)'))
})

test('saved JD can be explicitly cleared after an inline confirmation', () => {
  assert.ok(appSource.includes('>清除 JD</button>'))
  assert.ok(appSource.includes('确定清除当前 JD？此操作不可撤销。'))
  const start = appSource.indexOf('async function clearJD()')
  const end = appSource.indexOf('// 添加技能标签', start)
  const clearFlow = appSource.slice(start, end)
  assert.ok(clearFlow.includes("fetch('/save_jd'"))
  assert.ok(clearFlow.includes('jd_data: {}'))
  assert.ok(clearFlow.includes('jdData.value = null'))
})
