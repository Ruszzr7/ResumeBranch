import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const homepageSource = readFileSync(new URL('../src/views/Homepage.vue', import.meta.url), 'utf8')

test('model discovery status is rendered before the API key field', () => {
  const modelStatus = homepageSource.indexOf('modelQueryStatus.message')
  const apiKey = homepageSource.indexOf('for="api-key"')
  assert.ok(modelStatus > 0)
  assert.ok(apiKey > modelStatus)
})

test('reopening API settings clears transient query and connection results', () => {
  const start = homepageSource.indexOf('async function openSettings()')
  const end = homepageSource.indexOf('function selectSettingsRole', start)
  const openFlow = homepageSource.slice(start, end)
  assert.ok(openFlow.includes("modelQueryStatus.value = { type: '', message: '' }"))
  assert.ok(openFlow.includes("settingsStatus.value = { type: '', message: '' }"))
  assert.ok(openFlow.includes('visibleSettingsChecks.value = {}'))
})

test('API settings uses a fixed viewport-aware height and scrollable body', () => {
  assert.ok(homepageSource.includes('height: min(760px, calc(100dvh - 40px))'))
  assert.ok(homepageSource.includes('.settings-modal > .modal-body'))
  assert.ok(homepageSource.includes('overflow-y: auto'))
})

test('modal inputs override browser autofill with the dark surface', () => {
  assert.ok(homepageSource.includes('.internal-modal .modal-body input:-webkit-autofill'))
  assert.ok(homepageSource.includes('box-shadow: 0 0 0 1000px #303138 inset'))
})

test('resume summaries strip storage-only bold markers before display', () => {
  assert.ok(homepageSource.includes("import { plainInlineText } from '../utils/inlineFormatting.js'"))
  assert.ok(homepageSource.includes('const plainSummaryText = value => plainInlineText'))
  assert.ok(homepageSource.includes('{{ plainSummaryText(project.candidate_name || \'姓名尚未填写\') }}'))
})
