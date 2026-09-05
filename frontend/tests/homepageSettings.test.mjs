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
  assert.ok(openFlow.includes('abortSettingsOperations()'))
  assert.ok(openFlow.includes('resetSettingsUi()'))
  assert.ok(openFlow.includes('++settingsDialogGeneration'))
})

test('chat and parser queries keep independent modal state', () => {
  assert.ok(homepageSource.includes('settingsUi = ref({ chat: createSettingsUiState(), parser: createSettingsUiState() })'))
  assert.ok(homepageSource.includes('const role = settingsRole.value'))
  assert.ok(homepageSource.includes('const ui = settingsUi.value[role]'))
  assert.ok(homepageSource.includes('settingsAbortControllers[role].models = controller'))
  assert.ok(homepageSource.includes('settingsAbortControllers[role].test = controller'))
})

test('closing settings aborts active model and capability requests', () => {
  const start = homepageSource.indexOf('function closeSettings()')
  const end = homepageSource.indexOf('function settingsPayload', start)
  const closeFlow = homepageSource.slice(start, end)
  assert.ok(closeFlow.includes('abortSettingsOperations()'))
  assert.ok(closeFlow.includes('resetSettingsUi()'))
  assert.equal(closeFlow.includes('isTestingSettings.value'), false)
  assert.equal(closeFlow.includes('isLoadingModels.value'), false)
})

test('chat capability test is named for project conversation behavior', () => {
  assert.ok(homepageSource.includes("'测试对话能力'"))
  assert.ok(homepageSource.includes("tool_calling: '工具调用'"))
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
