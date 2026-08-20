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
const chatMessageSource = normalizeNewlines(readFileSync(new URL('../src/components/ChatMessage.vue', import.meta.url), 'utf8'))
const resumePreviewSource = normalizeNewlines(readFileSync(new URL('../src/components/ResumePreview.vue', import.meta.url), 'utf8'))

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

test('conversation persistence excludes empty streaming assistant placeholders', () => {
  assert.ok(appSource.includes('message.streaming !== true'))
  assert.ok(appSource.includes("message.role === 'assistant'"))
  assert.ok(appSource.includes("!String(message.content ?? '').trim()"))
})

test('layout advice uses the concise analysis prompt', () => {
  assert.ok(appSource.includes('根据当前简历数据与快照，检查当前简历存在的排版问题，按对简历影响程度从高到低编号列出可执行建议。'))
  assert.equal(appSource.includes('不要把默认状态、已符合规则、赞扬或无操作建议列为问题'), false)
})

test('visual analysis receives the same browser pagination style as export', () => {
  assert.ok(resumePreviewSource.includes("'render-style-updated'"))
  assert.ok(resumePreviewSource.includes('pageBreakBefore: pageBreakBefore.value'))
  assert.ok(appSource.includes('@render-style-updated="handleRenderStyleUpdated"'))
  assert.ok(appSource.includes("formData.append('render_style', JSON.stringify(activeRenderStyle.value))"))
})

test('closed task lifecycle records render as grey non-open cards', () => {
  assert.ok(chatMessageSource.includes("context-event-card--closed"))
  assert.ok(chatMessageSource.includes("isContextClosed ? '已关闭' : '打开'"))
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
  assert.ok(appSource.includes("label: '直接修改'"))
  assert.ok(appSource.includes('directEdit: true'))
  assert.ok(appSource.includes('/direct-replace-preview'))
  assert.ok(appSource.includes('也可以直接修改简历内容和排版'))
})

test('assistant actions follow the resume improvement workflow', () => {
  const start = appSource.indexOf('const assistantActions = [')
  const end = appSource.indexOf('\n]', start)
  const actions = appSource.slice(start, end)
  const labels = ['直接修改', '全面诊断', '排版建议', '深度打磨', '对照 JD']
  const positions = labels.map(label => actions.indexOf(`label: '${label}'`))
  assert.ok(positions.every(position => position >= 0))
  assert.deepEqual([...positions].sort((a, b) => a - b), positions)
})

test('mission commands only send their initial prompt when a context is newly created', () => {
  const start = appSource.indexOf('async function startMissionContext')
  const end = appSource.indexOf('function runWorkflowAction', start)
  const missionFlow = appSource.slice(start, end)
  assert.ok(missionFlow.includes('const resumed = Boolean(data.resumed)'))
  assert.ok(missionFlow.includes('if (!resumed) invalidateMainConversation()'))
  assert.ok(missionFlow.includes('if (mission.resumed) return'))
})

test('editing dialogs keep the resume preview visible and require an explicit close action', () => {
  assert.ok(appSource.includes('class="workspace-modal-mask preview-visible-modal-mask"'))
  assert.ok(appSource.includes('class="resume-dialog-overlay preview-visible-resume-overlay"'))
  assert.ok(appSource.includes('.preview-visible-modal-mask'))
  assert.ok(appSource.includes('width: min(400px, 100%)'))
  assert.ok(appSource.includes('grid-template-columns: minmax(0, 1fr)'))
  assert.ok(appSource.includes('.preview-visible-resume-overlay .resume-dialog'))
  assert.ok(appSource.includes('width: 100%'))
  assert.equal(appSource.includes('showDirectEditDialog" class="workspace-modal-mask" @click.self'), false)
  assert.equal(resumePreviewSource.includes('showSectionOrderDialog" class="success-dialog-overlay section-order-overlay" @click.self'), false)
})

test('single-change confirmation uses concise accept and reject labels', () => {
  assert.ok(chatMessageSource.includes("changes.length > 1 ? '全部接受' : '接受'"))
  assert.ok(chatMessageSource.includes("changes.length > 1 ? '全部拒绝' : '拒绝'"))
})

test('undo keeps the originating conversation session in scope through persistence', () => {
  const start = appSource.indexOf('async function handleUndoClick')
  const end = appSource.indexOf('// 检测哪个模块发生了变化', start)
  const undoFlow = appSource.slice(start, end)
  assert.ok(undoFlow.includes('const targetSessionId = sessionId.value'))
  assert.ok(undoFlow.includes('const targetState = ensureContextUiState(targetSessionId)'))
  assert.ok(undoFlow.includes('session_id: targetSessionId'))
  assert.ok(undoFlow.includes('conversationMessagesForSave(targetState.messages)'))
})

test('resume setting dialogs share one mutually exclusive group and surface color', () => {
  assert.ok(appSource.includes("const RESUME_SETTINGS_DIALOG_EVENT = 'resume-settings-dialog-open'"))
  assert.ok(appSource.includes("activateResumeSettingsDialog('direct-edit')"))
  assert.ok(appSource.includes("activateResumeSettingsDialog('resume-edit')"))
  assert.ok(resumePreviewSource.includes("activateResumeSettingsDialog('section-order')"))
  assert.ok(resumePreviewSource.includes("activateResumeSettingsDialog('font-size')"))
  assert.ok(appSource.includes('background: #25262c'))
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
