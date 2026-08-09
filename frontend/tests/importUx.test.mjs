import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

test('resume import does not trigger an unsolicited LLM reply', () => {
  const start = appSource.indexOf('async function parseAndSaveResume')
  const end = appSource.indexOf('async function confirmResumeImport', start)
  assert.ok(start >= 0 && end > start)
  const importFlow = appSource.slice(start, end)
  assert.equal(importFlow.includes('first_message_from_resume'), false)
  assert.equal(importFlow.includes("fetch('/api/chat'"), false)
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
