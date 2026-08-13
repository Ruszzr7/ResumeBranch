import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const previewSource = readFileSync(new URL('../src/components/ResumePreview.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const templateManagerSource = readFileSync(new URL('../src/components/TemplateManager.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')

test('desktop workspace heading and resume toolbar share the compact row height', () => {
  assert.ok(appSource.includes('.chat-panel-header {\n  height: 54px;\n  min-height: 54px;'))
  assert.ok(previewSource.includes('.resume-toolbar {\n  height: 54px;\n  min-height: 54px;'))
  assert.ok(appSource.includes('padding: 0.45rem 0.9rem'))
  assert.ok(previewSource.includes('padding: 0.35rem 0.65rem'))
})

test('preview and editor line flow share the content-block placement contract', () => {
  assert.ok(previewSource.includes('resolveContentBlockFlow'))
  assert.ok(previewSource.includes("contentBlockLabel(block, 'inline')"))
  assert.ok(previewSource.includes("contentBlockLabel(block, 'separate')"))
})

test('body copy is justified while semantic label weight follows saved data', () => {
  assert.ok(previewSource.includes('contentBlockLabelBold'))
  assert.ok(previewSource.includes("'is-bold': contentBlockLabelBold(block, 'inline')"))
  assert.ok(previewSource.includes('text-align: justify'))
  assert.ok(previewSource.includes('text-justify: inter-ideograph'))
})

test('preview resolves the same font and physical spacing tokens as exports', () => {
  assert.ok(previewSource.includes('resolveLayoutTokens(renderLayout.value'))
  assert.ok(previewSource.includes('fontFamily: layoutTokens.value.fontFamilyCss'))
  assert.ok(previewSource.includes("'--name-font-size': `${layoutTokens.value.nameFontSizePt}pt`"))
  assert.ok(previewSource.includes("'--label-font-size': `${layoutTokens.value.labelFontSizePt}pt`"))
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
  assert.ok(previewSource.includes('const MM_TO_PX = CSS_PX_PER_INCH / MM_PER_INCH'))
  assert.ok(previewSource.includes('const PAGE_WIDTH = 210 * MM_TO_PX'))
  assert.ok(previewSource.includes('const PAGE_HEIGHT = 297 * MM_TO_PX'))
  assert.ok(previewSource.includes('letterSpacing: `${layoutTokens.value.letterSpacingPt}pt`'))
  assert.ok(previewSource.includes("fontKerning: 'none'"))
  assert.ok(previewSource.includes("fontVariantLigatures: 'none'"))
  assert.ok(previewSource.includes("fontSynthesis: 'none'"))
  assert.ok(previewSource.includes('width: 210mm;'))
})

test('semantic font sizes use a half-point modal with live preview and page-limit guard', () => {
  assert.ok(previewSource.includes('设置各部分字号'))
  assert.ok(previewSource.includes('class="layout-guide-btn font-size-open-btn"'))
  assert.ok(previewSource.includes('调整文字大小'))
  assert.equal(previewSource.includes('font-size-slider-track'), false)
  assert.ok(previewSource.includes('FONT_SIZE_LIMITS'))
  assert.equal(previewSource.includes('bodyFontSizeProgress'), false)
  assert.ok(previewSource.includes('value += 0.5'))
  assert.ok(previewSource.includes('fontSizeDraft[role]'))
  assert.ok(previewSource.includes('activeFontSizes'))
  assert.ok(previewSource.includes('isSavingFontSizes || overflowBeyondPageLimit'))
  assert.ok(previewSource.includes('点击应用后才保存'))
})

test('resume fields render the escaped bold-only protocol', () => {
  assert.ok(previewSource.includes("import { formatInlineHtml } from '../utils/inlineFormatting.js'"))
  assert.ok(previewSource.includes('return formatInlineHtml(text)'))
  assert.equal(previewSource.includes(".replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')"), false)
})

test('work and project details share semantic block rendering', () => {
  assert.ok(previewSource.includes("projectContentBlocks(entry.item, 'work').length"))
  assert.ok(previewSource.includes('projectContentBlocks(item).length'))
  assert.ok(previewSource.includes("block.type === 'numbered_list'"))
  assert.ok(previewSource.includes('project-block-label'))
})

test('preview pagination measures shared spacing and uses a strict page boundary', () => {
  assert.ok(previewSource.includes('child.getBoundingClientRect().height + marginTop + marginBottom'))
  assert.ok(previewSource.includes('Number.parseFloat(computed.marginTop)'))
  assert.ok(previewSource.includes('Number.parseFloat(computed.marginBottom)'))
  assert.ok(previewSource.includes('pageContentHeight - 8'))
  assert.ok(previewSource.includes('pageContentHeight + 1'))
  assert.ok(previewSource.includes('pageContentHeight - 12'))
  assert.equal(previewSource.includes('pageContentHeight + 50'), false)
})

test('legacy work details remain body content regardless of their wording', () => {
  assert.ok(previewSource.includes("function projectContentBlocks(item, experienceKind = 'project')"))
  assert.ok(previewSource.includes("if (experienceKind === 'work')"))
  assert.ok(previewSource.includes("projectContentBlocks(entry.item, 'work')"))
  assert.ok(previewSource.includes("projectContentBlocks(item, 'work')"))
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
  assert.ok(previewSource.includes("'skill-list-item', { 'has-native-marker': hasNativeListMarker(item) }"))
  assert.ok(previewSource.includes('.generic-list-item.skill-list-item.has-native-marker {'))
  assert.ok(previewSource.includes('grid-template-columns: var(--list-text-indent) minmax(0, 1fr);'))
  assert.ok(previewSource.includes('class="native-list-marker"'))
  assert.ok(previewSource.includes('class="native-list-content"'))
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

test('template manager keeps custom templates before default and the create card last', () => {
  assert.ok(previewSource.includes('class="compact-toolbar-btn template-toolbar-btn"'))
  assert.equal(previewSource.includes('查看可用排版预设'), false)
  assert.ok(templateManagerSource.includes('const displayedTemplates = computed(() => [...templates.value, defaultTemplate])'))
  assert.ok(templateManagerSource.indexOf('v-for="template in displayedTemplates"') < templateManagerSource.indexOf('class="template-card create-card"'))
  assert.ok(templateManagerSource.includes("template.id === activeTemplateId ? '当前模板' : '应用模板'"))
  assert.ok(templateManagerSource.includes(": '模板管理'"))
  assert.ok(templateManagerSource.includes('class="template-action-row"'))
  assert.ok(templateManagerSource.includes('overflow-x: auto'))
  assert.equal(templateManagerSource.includes('李靖华'), false)
})

test('source document header stays compact and relies on the toolbar for returning', () => {
  assert.ok(previewSource.includes('min-height: 34px'))
  assert.ok(previewSource.includes('padding: 6px 12px'))
  assert.equal(previewSource.includes('class="source-document-actions"'), false)
})

test('single-page preview does not render a redundant 1 / 1 footer', () => {
  assert.ok(previewSource.includes('v-if="pageCount > 1" class="page-footer"'))
})

test('one-line education uses symmetric outer columns and a left-aligned middle frame', () => {
  assert.ok(previewSource.includes("'--education-side-column': `${layoutTokens.value.educationSideColumnMm}mm`"))
  assert.ok(previewSource.includes("'--education-compact-side-column': `${educationColumnWidths.value.sideMm}mm`"))
  assert.ok(previewSource.includes("'--education-middle-column': `${educationColumnWidths.value.middleMm}mm`"))
  assert.ok(previewSource.includes('grid-template-columns: var(--education-compact-side-column) var(--education-middle-column) var(--education-compact-side-column)'))
  assert.ok(previewSource.includes('grid-template-columns: var(--education-side-column) minmax(0, 1fr) var(--education-side-column)'))
  assert.ok(previewSource.includes('class="education-middle-column"'))
  assert.ok(previewSource.includes('compactAcademicMetric(item)'))
  assert.ok(previewSource.includes('compactEducationMiddle(item)'))
  assert.ok(previewSource.includes('formatCompactAcademicMetric(item, hidden, t.value.averageScore)'))
  assert.ok(previewSource.includes("filter(Boolean).join(' · ')"))
  assert.ok(previewSource.includes('text-align: left'))
  assert.ok(previewSource.includes('margin-right: 0'))
  assert.ok(previewSource.includes('position: static'))
  assert.equal(previewSource.includes('right: 6mm'), false)
})

test('semantic labels and their numbered responsibilities preserve nested indentation', () => {
  assert.ok(previewSource.includes("'--list-text-indent': `${layoutTokens.value.listTextIndentPt}pt`"))
  assert.ok(previewSource.includes("'--list-marker-gap': `${layoutTokens.value.listMarkerGapPt}pt`"))
  assert.ok(previewSource.includes('padding-left: var(--list-text-indent)'))
  assert.ok(previewSource.includes('width: calc(var(--list-text-indent) - var(--list-marker-gap))'))
  assert.ok(previewSource.includes('.project-content-block.has-semantic-label > .project-numbered-list'))
  assert.ok(previewSource.includes('margin-left: var(--list-text-indent)'))
  assert.ok(previewSource.includes(".list-item::before {\n  content: '•';\n  position: absolute;\n  left: 0;\n  width: calc(var(--list-text-indent) - var(--list-marker-gap));\n  text-align: center;"))
})

test('preview applies shared module spacing before every section title', () => {
  assert.ok(previewSource.includes('margin-top: var(--module-margin)'))
  assert.ok(previewSource.includes('margin-bottom: var(--section-title-after)'))
  assert.ok(previewSource.includes('padding-bottom: var(--section-title-border-gap)'))
})

test('narrow resume toolbar uses the dark workspace palette', () => {
  assert.ok(previewSource.includes('background: rgba(30, 31, 36, 0.98)'))
  assert.ok(previewSource.includes('color: #e4e6ed'))
})

test('retired toolbar implementations do not shadow the compact toolbar', () => {
  for (const selector of [
    '.toolbar-controls',
    '.zoom-controls',
    '.style-panel-mobile',
    '.mobile-toolbar-row'
  ]) {
    assert.equal(previewSource.includes(selector), false)
  }
})

test('all viewport widths render the same compact toolbar and narrow screens keep it above the preview', () => {
  assert.equal(previewSource.includes('<template v-if="isMobile">'), false)
  assert.ok(previewSource.includes('所有窗口宽度共用同一套操作'))
  assert.ok(previewSource.includes("showSourceDocument ? '当前版' : '原版'"))
  assert.ok(previewSource.includes('<span>排版</span>'))
  assert.ok(previewSource.includes('<span>编辑</span>'))
  assert.ok(previewSource.includes("position: sticky;\n    top: 0;\n    bottom: auto;"))
})

test('resume toolbar actions follow the requested visual and keyboard order', () => {
  const toolbarStart = previewSource.indexOf('<div class="shared-toolbar-actions">')
  const toolbarEnd = previewSource.indexOf('</div>\n      </div>\n    </div>', toolbarStart)
  const toolbarMarkup = previewSource.slice(toolbarStart, toolbarEnd)
  const orderedMarkers = [
    'aria-label="打开页面缩放"',
    'aria-label="打开模板管理"',
    'aria-label="打开内容编辑菜单"',
    'aria-label="打开排版设置"',
    'class="compact-toolbar-btn language-btn"',
    'v-if="hasSourceDocument"',
    '@click="exportPDF"',
    '@click="exportWord"'
  ]
  const positions = orderedMarkers.map(marker => toolbarMarkup.indexOf(marker))
  assert.ok(positions.every(position => position >= 0))
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right))
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

test('custom templates use compact sample content and explicit naming workflows', () => {
  assert.ok(templateManagerSource.includes('示例大学'))
  assert.ok(templateManagerSource.includes('智能简历助手'))
  assert.ok(templateManagerSource.includes("openNameDialog('copy', template)"))
  assert.ok(templateManagerSource.includes('新模板名称'))
  assert.ok(templateManagerSource.includes('localStorage.setItem(STORAGE_KEY'))
})

test('zoom stepper reports the live percentage instead of a fixed label', () => {
  assert.ok(previewSource.includes('aria-label="恢复百分之百">{{ zoomPercentage }}%</button>'))
  assert.ok(previewSource.includes('manualZoom.value = Math.min(1, Math.max(0.4, currentRatio + delta))'))
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
