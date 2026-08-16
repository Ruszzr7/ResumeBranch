import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const editorSource = readFileSync(
  new URL('../src/components/RichTextEditor.vue', import.meta.url),
  'utf8'
).replace(/\r\n/g, '\n')
const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

test('single-line resume fields hide storage markers behind the rich editor', () => {
  assert.ok(editorSource.includes("compact: {"))
  assert.ok(editorSource.includes("if (props.compact) syncValue()"))
  assert.ok(editorSource.includes("if (props.compact) event.preventDefault()"))
  assert.ok(editorSource.includes("raw.replace(/[\\r\\n]+/g, ' ')"))
  assert.ok(appSource.includes('v-model="work.company_name" placeholder="例如 某某科技有限公司" compact'))
  assert.ok(appSource.includes('v-model="proj.project_name" placeholder="例如 智能调度平台" compact'))
  assert.equal(/<RichTextEditor[^>]*class="element-input"[^>]*compact/.test(appSource), false)
  assert.ok(appSource.includes('v-model="resumeFormData.basics.gender" placeholder="例如 男" compact'))
  assert.ok(appSource.includes('v-model="resumeFormData.basics.birth_date" placeholder="例如 2002.06" compact'))
  assert.equal(appSource.includes('<el-select v-model="resumeFormData.basics.gender"'), false)
  assert.equal(appSource.includes('<input v-model="resumeFormData.basics.birth_date"'), false)
})

test('editor toggles selections through the deterministic bold-only protocol', () => {
  assert.ok(editorSource.includes('toggleInlineBoldRange(current, start, end)'))
  assert.ok(editorSource.includes("if (tag === 'B' || tag === 'STRONG') bold = true"))
  assert.ok(editorSource.includes("if (fontWeight === 'normal' || fontWeight === '400') bold = false"))
  assert.ok(editorSource.includes('placeCaretAtOffset(end)'))
  assert.equal(editorSource.includes(".replace(/<(?:b|strong)\\b[^>]*>/gi, '**')"), false)
})

test('default-bold fields are explicit while module editors do not force all text bold', () => {
  assert.ok(appSource.includes('v-model="resumeFormData.basics.target_position" placeholder="例如 后端开发工程师" compact default-bold'))
  assert.ok(appSource.includes("label_bold: semanticRole === 'introduction' || semanticRole === 'responsibilities'"))
  assert.ok(appSource.includes("semantic_role: 'introduction',\n  label: project?._introLabel,\n  label_bold: true"))
  assert.ok(appSource.includes("semantic_role: 'responsibilities', label: project?._dutiesLabel,\n  label_bold: true"))
  for (const field of [
    'v-model="work.job_type" placeholder="例如 全职或实习" compact',
    'v-model="work.date_range[0]" placeholder="例如 2024.09" compact',
    'v-model="proj.date_range[0]" placeholder="例如 2024.09" compact'
  ]) assert.ok(appSource.includes(field))
  assert.ok(appSource.includes('v-model="work.job_title" placeholder="例如 算法工程师" compact default-bold'))
  assert.equal(appSource.includes('v-model="work.job_type" placeholder="例如 全职或实习" compact default-bold'), false)
  assert.equal(appSource.includes('v-model="work.date_range[0]" placeholder="例如 2024.09" compact default-bold'), false)
  assert.equal(appSource.includes('v-model="proj.date_range[0]" placeholder="例如 2024.09" compact default-bold'), false)
  assert.ok(appSource.includes('data.formatting_version = 4'))
  assert.equal(appSource.includes('.module-title-editor :deep(.editor-content) {\n  font-weight: 700'), false)
})

test('editable module headings use a one-third input and match the basic heading size', () => {
  assert.ok(appSource.includes('width: 33.333%'))
  assert.ok(appSource.includes('.module-title-editor :deep(.editor-content) {\n  font-size: 1rem;'))
  assert.ok(appSource.includes('border: 1px solid rgba(255, 255, 255, 0.2) !important'))
  assert.ok(appSource.includes('.module-title-editor::after'))
})

test('bold guidance appears once at the top of the resume dialog', () => {
  assert.equal(editorSource.includes('提示：选中文字后按'), false)
  assert.ok(appSource.includes('class="resume-format-hint" role="note"'))
  assert.equal(appSource.match(/class="resume-format-hint"/g)?.length, 1)
  assert.equal(appSource.includes('支持换行和 Ctrl+B 加粗'), false)
  assert.ok(appSource.includes('.resume-format-hint {'))
  assert.ok(appSource.includes('background: transparent;\n  border: 0;'))
  assert.ok(appSource.includes('填写内容可按 Ctrl+B 加粗；内容框右下角显示当前设置下内容的预计占据行数'))
})

test('multiline editors estimate resume visual lines from shared layout metrics', () => {
  assert.ok(editorSource.includes('简历约 {{ displayLineCount }} 行'))
  assert.ok(editorSource.includes('measureResumeLineCount'))
  assert.ok(editorSource.includes('measurer.scrollHeight / computedLineHeight'))
  assert.ok(editorSource.includes("fontFamily: metrics.fontFamilyCss || \"'Microsoft YaHei', Arial, sans-serif\""))
  assert.ok(editorSource.includes('props.resumeMetrics?.fontSizePt'))
  assert.ok(editorSource.includes('props.resumeMetrics?.labelFontSizePt'))
  assert.ok(editorSource.includes('props.resumeMetrics?.lineHeight'))
  assert.ok(editorSource.includes('props.resumeMetrics?.contentWidthPx'))
  assert.ok(appSource.includes('(210 - tokens.marginLeftMm - tokens.marginRightMm) * (96 / 25.4)'))
  assert.ok(appSource.includes(':resume-metrics="resumeEditorMetrics"'))
})

test('project introduction line measurement includes its rendered semantic prefix', () => {
  assert.ok(editorSource.includes("flow.labelPlacement === 'inline' && flow.prefixText"))
  assert.ok(editorSource.includes('prefix.textContent = flow.prefixText'))
  assert.ok(editorSource.includes('contentRange.getClientRects()'))
  assert.ok(appSource.includes('resolveContentBlockFlow'))
  assert.ok(appSource.includes(':resume-flow="projectIntroFlow(proj)"'))
})

test('work and project semantic labels use the same inline bold editor and hide when blank', () => {
  assert.equal(editorSource.includes('semanticLabelStates'), false)
  assert.equal(editorSource.includes('data-semantic-label="true"'), false)
  assert.equal(editorSource.includes('semantic-label-weight-change'), false)
  assert.equal(appSource.includes('_contentLabelBold'), false)
  assert.equal(appSource.includes(':semantic-label-states="work.'), false)
  assert.ok(appSource.includes('v-model="work._introLabel"'))
  assert.ok(appSource.includes('v-model="work._dutiesLabel"'))
  assert.ok(appSource.includes('v-model="proj._introLabel"'))
  assert.ok(appSource.includes("_introLabel: '**项目简介**'"))
  assert.equal(appSource.includes('简介标签</label>'), false)
  assert.equal(appSource.includes('_introLabelBold = !'), false)
  assert.ok(appSource.includes('标签为空，该职责内容已保留但不会显示或导出'))
  assert.equal(appSource.includes("'项目简介', '项目背景', '项目概述', '项目说明'"), false)
  assert.ok(appSource.includes("semantic_role: 'introduction'"))
  assert.ok(appSource.includes('work.content_blocks = editableExperienceToContentBlocks(work)'))
  assert.equal(appSource.includes('work.content_blocks = []'), false)
  assert.ok(appSource.includes('CONTENT_BLOCK_TYPE_OPTIONS'))
  assert.ok(appSource.includes('v-model="proj._introType"'))
  assert.ok(appSource.includes('v-model="proj._dutiesType"'))
  assert.ok(appSource.includes("type: project?._introType || 'paragraph'"))
  assert.ok(appSource.includes("type: project?._dutiesType || 'numbered_list'"))
})

test('resume tag chips use escaped inline formatting instead of exposing markers', () => {
  assert.ok(appSource.includes("from './utils/inlineFormatting.js'"))
  assert.ok(appSource.includes('draggable="true"'))
  assert.ok(appSource.includes('v-model="resumeFormData.others.skills[i]"'))
  assert.ok(appSource.includes('v-model="resumeFormData.others.certificates[i]"'))
  assert.ok(appSource.includes('v-model="resumeFormData.others.languages[i]"'))
  assert.ok(appSource.includes('startOtherItemDrag'))
})

test('resume editor cancel restores the photo snapshot and the save payload keeps an explicit empty photo', () => {
  assert.ok(appSource.includes('resumeEditorPreviousResumeData = cloneResumeData(resumeData.value)'))
  assert.ok(appSource.includes('resumeData.value = cloneResumeData(resumeEditorPreviousResumeData)'))
  assert.ok(appSource.includes('resumeFormData.value.basics.photo'))
  assert.ok(appSource.includes("fetch('/save_resume'"))
})

test('certificate and language sortable editors use the same full-width row contract as skills', () => {
  assert.ok(appSource.includes('.resume-dialog .sortable-item .rich-editor {\n  flex: none;\n  width: 100%;\n  min-width: 0;'))
  assert.ok(appSource.includes('class="sortable-item-editor" placeholder="例如 软件设计师" compact'))
  assert.ok(appSource.includes('class="sortable-item-editor" placeholder="例如 英语 CET-6" compact'))
  assert.ok(appSource.includes('white-space: pre-wrap !important;'))
  assert.ok(appSource.includes('min-height: 44px;'))
  assert.ok(appSource.includes('.resume-dialog .certificate-language-field > .field-label-editor.rich-editor'))
  assert.ok(appSource.includes('v-model="resumeFormData.others.certificates[i]"'))
  assert.ok(appSource.includes('v-model="resumeFormData.others.languages[i]"'))
})
