import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const previewSource = readFileSync(new URL('../src/components/ResumePreview.vue', import.meta.url), 'utf8')

test('preview resolves the same font and physical spacing tokens as exports', () => {
  assert.ok(previewSource.includes('resolveLayoutTokens(layout.value'))
  assert.ok(previewSource.includes('fontFamily: layoutTokens.value.fontFamilyCss'))
  assert.ok(previewSource.includes("'--name-font-size': `${layoutTokens.value.nameFontSizePt}pt`"))
  assert.ok(previewSource.includes("'--meta-font-weight': layoutTokens.value.metaFontWeight"))
  assert.ok(previewSource.includes("'--entry-title-font-weight': layoutTokens.value.entryTitleFontWeight"))
  assert.ok(previewSource.includes('font-size: var(--name-font-size)'))
  assert.ok(previewSource.includes('font-weight: var(--name-font-weight)'))
  assert.ok(previewSource.includes('font-weight: var(--entry-title-font-weight)'))
  assert.ok(previewSource.includes('font-weight: var(--meta-font-weight)'))
  assert.ok(previewSource.includes('font-size: var(--section-title-font-size)'))
  assert.ok(previewSource.includes('font-size: var(--body-font-size)'))
  assert.ok(previewSource.includes("'--module-margin': `${layoutTokens.value.moduleSpacingPt}pt`"))
  assert.ok(previewSource.includes('margin-bottom: var(--paragraph-spacing)'))
})

test('work and project details share semantic block rendering', () => {
  assert.ok(previewSource.includes('projectContentBlocks(entry.item).length'))
  assert.ok(previewSource.includes("block.type === 'numbered_list'"))
  assert.ok(previewSource.includes('project-block-label'))
})

test('preview pagination uses a small safety margin consistent with PDF export', () => {
  assert.equal(previewSource.includes('pageContentHeight - 120'), false)
  assert.equal(previewSource.includes('pageContentHeight - 150'), false)
  assert.ok(previewSource.includes('pageContentHeight - 8'))
})

test('layout menu opens a dedicated bidirectional manual ordering dialog', () => {
  assert.ok(previewSource.includes('调整模块顺序'))
  assert.ok(previewSource.includes('showSectionOrderDialog'))
  assert.ok(previewSource.includes('dragOverSection($event, section)'))
  assert.ok(previewSource.includes('拖动和箭头均支持双向调整'))
  assert.equal(previewSource.includes('根据 JD 推荐排序'), false)
})

test('section ordering uses a compact left-side dialog so the PDF stays visible', () => {
  assert.ok(previewSource.includes('width: calc((100vw - 156px) * 0.39)'))
  assert.ok(previewSource.includes('justify-content: flex-end'))
  assert.ok(previewSource.includes('width: min(340px, calc(100vw - 40px))'))
  assert.ok(previewSource.includes('background: rgba(7, 8, 11, 0.16)'))
})

test('section names are larger without enlarging the drag and arrow controls', () => {
  assert.ok(previewSource.includes('class="section-order-name"'))
  assert.ok(previewSource.includes('.section-order-name {'))
  assert.ok(previewSource.includes('font-size: 0.82rem'))
})

test('empty resume action remains visible on the dark preview background', () => {
  assert.ok(previewSource.includes('.no-data .jd-upload-btn'))
  assert.ok(previewSource.includes('color: #e4edff'))
  assert.ok(previewSource.includes('background: rgba(95, 143, 242, 0.2)'))
})

test('numbered generic items suppress the redundant outer bullet', () => {
  assert.ok(previewSource.includes('hasNativeListMarker'))
  assert.ok(previewSource.includes("'has-native-marker': hasNativeListMarker(item)"))
  assert.ok(previewSource.includes('.generic-list-item.has-native-marker::before'))
})

test('imported source can be viewed read-only without replacing the structured resume', () => {
  assert.ok(previewSource.includes('hasSourceDocument'))
  assert.ok(previewSource.includes("fetch(`/tasks/${props.taskId}/source-document`"))
  assert.ok(previewSource.includes('class="source-document-viewer"'))
  assert.ok(previewSource.includes('sourceDocumentIsPdf'))
  assert.ok(previewSource.includes("showSourceDocument ? '当前版' : '原版'"))
  assert.ok(previewSource.includes('只读原版，不会随当前简历修改'))
  assert.equal(previewSource.includes('downloadSourceDocument'), false)
})

test('empty compact self evaluation never creates a heading-only section', () => {
  assert.ok(previewSource.includes('.map(value => String(value || \'\').trim())'))
  assert.ok(previewSource.includes('.filter(Boolean)'))
  assert.ok(previewSource.includes('values.length && moduleLayout(\'self_evaluation\').preset === \'compact\''))
})

test('template chooser uses the preview itself for zoom and one centered apply action', () => {
  assert.equal(previewSource.includes('class="template-secondary-btn"'), false)
  assert.ok(previewSource.includes('.template-card-actions { display: flex; justify-content: center; }'))
  assert.ok(previewSource.includes('.template-card-actions button { min-width: 132px;'))
  assert.ok(previewSource.includes('max-height: calc(100vh - 32px)'))
})

test('source document header stays compact and relies on the toolbar for returning', () => {
  assert.ok(previewSource.includes('min-height: 34px'))
  assert.ok(previewSource.includes('padding: 6px 12px'))
  assert.equal(previewSource.includes('class="source-document-actions"'), false)
})

test('single-page preview does not render a redundant 1 / 1 footer', () => {
  assert.ok(previewSource.includes('v-if="pageCount > 1" class="page-footer"'))
})

test('one-line education dates stay in the normal four-column flow', () => {
  assert.ok(previewSource.includes('flex: 1 1 0'))
  assert.ok(previewSource.includes('flex: 0 0 36mm'))
  assert.ok(previewSource.includes('margin-right: 2mm'))
  assert.ok(previewSource.includes('position: static'))
  assert.equal(previewSource.includes('right: 6mm'), false)
})

test('narrow resume toolbar uses the dark workspace palette', () => {
  assert.ok(previewSource.includes('background: rgba(30, 31, 36, 0.98)'))
  assert.ok(previewSource.includes('color: #eceef4'))
  assert.ok(previewSource.includes('color: #ffffff'))
})

test('all viewport widths render the same compact toolbar and narrow screens keep it above the preview', () => {
  assert.equal(previewSource.includes('<template v-if="isMobile">'), false)
  assert.ok(previewSource.includes('所有窗口宽度共用同一套操作'))
  assert.ok(previewSource.includes("showSourceDocument ? '当前版' : '原版'"))
  assert.ok(previewSource.includes('<span>排版</span>'))
  assert.ok(previewSource.includes('<span>编辑</span>'))
  assert.ok(previewSource.includes("position: sticky;\n    top: 0;\n    bottom: auto;"))
})

test('every toolbar popover is centered under its trigger button', () => {
  const popoverStart = previewSource.indexOf('.compact-popover {')
  const popoverEnd = previewSource.indexOf('}', popoverStart)
  const popoverCss = previewSource.slice(popoverStart, popoverEnd)
  assert.ok(popoverCss.includes('left: 50%'))
  assert.ok(popoverCss.includes('right: auto'))
  assert.ok(popoverCss.includes('transform: translateX(-50%)'))
})

test('work headings stay inline and right-positioned dates use a two-column grid', () => {
  assert.ok(previewSource.includes('class="work-main"'))
  assert.ok(previewSource.includes('workPosition(entry.item)'))
  assert.ok(previewSource.includes('.work-main .position::before'))
  assert.ok(previewSource.includes('.project-item.date-right .project-header'))
  assert.ok(previewSource.includes('grid-template-columns: minmax(0, 1fr) auto'))
  assert.ok(previewSource.includes('text-align: right'))
})

test('enlarged template is centered with viewport breathing room', () => {
  assert.ok(previewSource.includes('max-height: calc(100vh - 64px)'))
  assert.ok(previewSource.includes('transform: translateY(12px)'))
})

test('restoring default layout requires explicit confirmation', () => {
  assert.ok(previewSource.includes('@click="requestResetStyleSettings"'))
  assert.ok(previewSource.includes('恢复默认排版？'))
  assert.ok(previewSource.includes('确认恢复'))
  assert.ok(previewSource.includes('@click="resetStyleSettings"'))
  const requestStart = previewSource.indexOf('function requestResetStyleSettings')
  const requestEnd = previewSource.indexOf('function resetStyleSettings', requestStart)
  assert.equal(previewSource.slice(requestStart, requestEnd).includes('marginVertical.value ='), false)
})
