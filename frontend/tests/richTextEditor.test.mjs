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
  assert.ok(appSource.includes('v-model="work.company_name" placeholder="请输入" compact'))
  assert.ok(appSource.includes('v-model="proj.project_name" placeholder="请输入" compact'))
  assert.equal(/<RichTextEditor[^>]*class="element-input"[^>]*compact/.test(appSource), false)
})

test('editor serializes both browser bold element forms into the bold-only protocol', () => {
  assert.ok(editorSource.includes(".replace(/<(?:b|strong)\\b[^>]*>/gi, '**')"))
  assert.ok(editorSource.includes(".replace(/<\\/(?:b|strong)>/gi, '**')"))
  assert.ok(editorSource.includes("document.execCommand('bold', false, null)"))
  assert.ok(editorSource.includes('selection.collapseToEnd()'))
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
  assert.ok(appSource.includes('v-html="formatInlineHtml(skill)"'))
  assert.ok(appSource.includes('v-html="formatInlineHtml(cert)"'))
  assert.ok(appSource.includes('v-html="formatInlineHtml(lang)"'))
})
