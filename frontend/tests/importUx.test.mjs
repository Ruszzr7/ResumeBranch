import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const normalizeNewlines = (source) => source.replace(/\r\n?/g, '\n')
const appSource = normalizeNewlines(readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8'))
const viteSource = normalizeNewlines(readFileSync(new URL('../vite.config.js', import.meta.url), 'utf8'))
const logoSource = normalizeNewlines(readFileSync(new URL('../src/components/BrandLogo.vue', import.meta.url), 'utf8'))
const indexSource = normalizeNewlines(readFileSync(new URL('../index.html', import.meta.url), 'utf8'))
const iconSource = normalizeNewlines(readFileSync(new URL('../public/icon.svg', import.meta.url), 'utf8'))
const faviconSource = normalizeNewlines(readFileSync(new URL('../public/favicon.svg', import.meta.url), 'utf8'))

test('ResumeBranch uses the restored branch logo and adaptive favicon', () => {
  assert.ok(logoSource.includes('/icon.svg?v=5'))
  assert.equal(logoSource.includes('filter: grayscale'), false)
  assert.ok(logoSource.includes('font-size: 1.25rem'))
  assert.ok(logoSource.includes('width: 22px'))
  assert.ok(indexSource.includes('/favicon.svg?v=5'))
  assert.ok(iconSource.includes('#4D9CFF'))
  assert.ok(iconSource.includes('<circle cx="18" cy="57" r="3.75" stroke="#EEF1F5"/>'))
  assert.ok(faviconSource.includes('<circle class="paper" cx="18" cy="57" r="3.75"/>'))
  assert.ok(faviconSource.includes('prefers-color-scheme: dark'))
  assert.ok(appSource.includes('height: calc(100vh - 52px)'))
  assert.ok(appSource.includes('height: 52px;\n  min-height: 52px;'))
})

test('resume import does not trigger an unsolicited LLM reply', () => {
  const start = appSource.indexOf('async function parseAndSaveResume')
  const end = appSource.indexOf('async function confirmResumeImport', start)
  assert.ok(start >= 0 && end > start)
  const importFlow = appSource.slice(start, end)
  assert.equal(importFlow.includes('first_message_from_resume'), false)
  assert.equal(importFlow.includes("fetch('/api/chat'"), false)
})

test('all resume upload entry points share the same draft parser and confirmation helpers', () => {
  const requestStart = appSource.indexOf('async function requestResumeImport')
  const requestEnd = appSource.indexOf('// 解析并保存简历', requestStart)
  const requestHelper = appSource.slice(requestStart, requestEnd)
  assert.ok(requestStart >= 0 && requestEnd > requestStart)
  assert.ok(requestHelper.includes("fetch('/api/resume/parse_and_save'"))
  assert.ok(requestHelper.includes("formData.append('draft_only', 'true')"))

  const confirmStart = appSource.indexOf('async function confirmResumeImportDraft')
  const confirmEnd = appSource.indexOf('// 解析并保存简历', confirmStart)
  const confirmHelper = appSource.slice(confirmStart, confirmEnd)
  assert.ok(confirmHelper.includes("fetch('/api/resume/confirm_import'"))
  assert.ok(confirmHelper.includes('getAuthHeaders(taskId)'))

  const taskStart = appSource.indexOf('async function confirmCreateProjectTask')
  const taskEnd = appSource.indexOf('async function deleteProjectTask', taskStart)
  const taskFlow = appSource.slice(taskStart, taskEnd)
  assert.ok(taskFlow.includes('requestResumeImport(taskImportFile.value, task.id)'))
  assert.ok(taskFlow.includes('confirmResumeImportDraft(importData, task.id)'))
  assert.equal(taskFlow.includes("fetch('/api/resume/parse_and_save'"), false)
})

test('import confirmation stays concise and hides parser diagnostics', () => {
  assert.equal(appSource.includes('source_fingerprint'), false)
  assert.equal(appSource.includes('parser_transport'), false)
  assert.equal(appSource.includes('校验码'), false)
  assert.ok(appSource.includes('上传清晰原图'))
})

test('local welcome includes diagnosis, interview and JD entry points', () => {
  assert.ok(appSource.includes('检查简历中的不足'))
  assert.ok(appSource.includes('进行深度打磨'))
  assert.ok(appSource.includes('结合 JD 分析匹配度'))
  assert.ok(appSource.includes('自行上传清晰原图'))
})

test('assistant actions use clear, professional wording', () => {
  assert.ok(appSource.includes("label: '深度打磨'"))
  assert.ok(appSource.includes("label: '排版建议'"))
  assert.ok(appSource.includes('本轮只分析，不修改简历'))
  assert.equal(appSource.includes("label: '开始拷打'"), false)
  assert.equal(appSource.includes("label: '优化排版'"), false)
  assert.ok(appSource.includes("label: '修改简历'"))
  assert.ok(appSource.includes('prefillOnly: true'))
  assert.ok(appSource.includes('也可以直接修改简历内容和排版'))
})

test('assistant actions follow the resume improvement workflow', () => {
  const start = appSource.indexOf('const assistantActions = [')
  const end = appSource.indexOf('\n]', start)
  const actions = appSource.slice(start, end)
  const labels = ['修改简历', '排版建议', '全面诊断', '深度打磨', '对照 JD']
  const positions = labels.map(label => actions.indexOf(`label: '${label}'`))
  assert.ok(positions.every(position => position >= 0))
  assert.deepEqual([...positions].sort((a, b) => a - b), positions)
})

test('resume translation uses a dedicated endpoint and reusable cache', () => {
  assert.ok(appSource.includes("fetch('/translate_resume'"))
  assert.ok(appSource.includes("fetch('/restore_resume_translation'"))
  assert.ok(appSource.includes('TRANSLATION_CACHE_PREFIX'))
  assert.ok(appSource.includes('loadCachedTranslation(sourceData)'))
  assert.equal(appSource.includes('const TRANSLATE_MESSAGE'), false)
  assert.equal(appSource.includes('pendingTranslationConfirmId'), false)
  assert.ok(viteSource.includes("'/translate_resume'"))
  assert.ok(viteSource.includes("'/restore_resume_translation'"))
})

test('resume edit shortcut guides a concrete request without spending an LLM call', () => {
  const start = appSource.indexOf('function runAssistantAction(action)')
  const end = appSource.indexOf('function runWorkflowAction(action)', start)
  const actionFlow = appSource.slice(start, end)
  const prefillBranch = actionFlow.indexOf('if (action.prefillOnly)')
  const earlyReturn = actionFlow.indexOf('return', prefillBranch)
  const sendCall = actionFlow.indexOf('sendMessage()', prefillBranch)
  assert.ok(start >= 0 && end > start)
  assert.ok(prefillBranch >= 0 && earlyReturn > prefillBranch)
  assert.ok(sendCall > earlyReturn)
  assert.ok(actionFlow.includes('修改需求模板已填入输入框'))
})

test('start import opens the native file chooser before showing the upload review', () => {
  assert.ok(appSource.includes('function selectResumeFileFromStart()'))
  assert.ok(appSource.includes('startResumeFileInput.value?.click()'))
  assert.ok(appSource.includes('@click="selectResumeFileFromStart"'))
  assert.ok(appSource.includes('const selectedFromStart = showStartDialog.value'))
})

test('start choices share a neutral default and blue hover state', () => {
  assert.equal(appSource.includes('@click="selectResumeFileFromStart" class="option-item primary"'), false)
  assert.ok(appSource.includes('.start-modal .option-item:hover'))
  assert.ok(appSource.includes('.start-modal .modal-close-btn.light:hover'))
})

test('re-import dialog stays on the current workspace without a redundant back button', () => {
  const start = appSource.indexOf('<!-- 简历上传弹窗 -->')
  const end = appSource.indexOf('<!-- 顶部导航栏（全屏宽度） -->', start)
  const uploadDialog = appSource.slice(start, end)
  assert.ok(start >= 0 && end > start)
  assert.ok(uploadDialog.includes('<h2>导入简历</h2>'))
  assert.equal(uploadDialog.includes('backToStartDialog'), false)
  assert.equal(uploadDialog.includes('class="modal-back"'), false)
})

test('re-import dialog can be closed without selecting a file', () => {
  const start = appSource.indexOf('<!-- 简历上传弹窗 -->')
  const end = appSource.indexOf('<!-- 顶部导航栏（全屏宽度） -->', start)
  const uploadDialog = appSource.slice(start, end)
  assert.ok(uploadDialog.includes('aria-label="关闭导入简历"'))
  assert.ok(uploadDialog.includes('@click="closeUploadDialog"'))
})

test('task sidebar shows one aligned version name without a redundant JD subtitle', () => {
  const start = appSource.indexOf('<aside class="task-sidebar">')
  const end = appSource.indexOf('<div class="main-content">', start)
  const sidebar = appSource.slice(start, end)
  assert.ok(start >= 0 && end > start)
  assert.equal(sidebar.includes('JD 定制版'), false)
  assert.equal(sidebar.includes('task.target_position'), false)
  assert.ok(sidebar.includes('class="task-action-trigger"'))
  assert.ok(sidebar.includes('class="task-action-menu"'))
  assert.ok(appSource.includes('.task-row {\n  position: relative;\n  display: flex;\n  align-items: center;'))
  assert.ok(appSource.includes('gap: .25rem;\n  margin-bottom: .2rem;'))
})
