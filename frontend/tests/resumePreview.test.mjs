import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const previewSource = readFileSync(new URL('../src/components/ResumePreview.vue', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
const layoutConfigSource = readFileSync(new URL('../src/utils/layoutConfig.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n')
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
  assert.ok(previewSource.includes('.module-component.component-school { font-size: var(--entry-title-font-size); font-weight: var(--manual-title-font-weight); }'))
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

test('local exports stay in the project folder while hosted exports download in the browser', () => {
  assert.ok(previewSource.includes("response.headers.get('X-Local-Export-Saved') === 'true'"))
  assert.ok(previewSource.includes('await response.arrayBuffer()'))
  assert.ok(previewSource.includes('const documentBlob = await response.blob()'))
  assert.ok(previewSource.includes("fetch('/local/exports/open'"))
  assert.ok(previewSource.includes('打开导出文件夹'))
  assert.ok(previewSource.includes('class="compact-toolbar-btn export-folder-btn"'))
  assert.ok(previewSource.includes("v-if=\"localMode\""))
})

test('semantic font sizes use a half-point modal with live preview and page-limit guard', () => {
  assert.ok(previewSource.includes('<h3 id="font-size-title">文字大小</h3>'))
  assert.ok(previewSource.includes(':aria-label="`文字大小，当前正文字号 ${fontSizes.body}pt`"'))
  assert.ok(previewSource.includes("const fontSizeRoles = ['name', 'meta', 'sectionTitle', 'entryTitle', 'label', 'body']"))
  assert.equal(previewSource.includes('font-size-slider-track'), false)
  assert.ok(previewSource.includes('FONT_SIZE_LIMITS'))
  assert.equal(previewSource.includes('bodyFontSizeProgress'), false)
  assert.ok(previewSource.includes('value += 0.5'))
  assert.ok(previewSource.includes('fontSizeDraft[role]'))
  assert.ok(previewSource.includes('activeFontSizes'))
  assert.ok(previewSource.includes('isSavingFontSizes || overflowBeyondPageLimit'))
  assert.ok(previewSource.includes('点击应用后才保存'))
  assert.equal(previewSource.includes('class="settings-dialog-action" :disabled="isSavingFontSizes" @click="closeFontSizeDialog">取消</button>'), false)
  assert.ok(previewSource.includes('height: 144px'))
  assert.ok(previewSource.includes('overflow-y: auto'))
  assert.ok(layoutConfigSource.includes("meta: '用户信息'"))
  assert.ok(layoutConfigSource.includes("label: '字段标签'"))
})

test('resume fields render the escaped bold-only protocol', () => {
  assert.ok(previewSource.includes("joinInlineWithInheritedSeparator as joinInlineFields"))
  assert.ok(previewSource.includes("formatInlineHtml, isFullyBoldInlineText"))
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

test('work and project previews use only canonical content blocks', () => {
  assert.ok(previewSource.includes("function projectContentBlocks(item, experienceKind = 'project')"))
  assert.ok(previewSource.includes('normalizeContentBlocks(item?.content_blocks, { experienceKind })'))
  assert.equal(previewSource.includes('normalizeContentBlocks(item?.content_blocks, item?.details'), false)
  assert.ok(previewSource.includes("projectContentBlocks(entry.item, 'work')"))
  assert.ok(previewSource.includes("projectContentBlocks(item, 'work')"))
})

test('layout menu opens a dedicated bidirectional manual ordering dialog', () => {
  assert.ok(previewSource.includes('<h3 id="section-order-title">模块顺序</h3>'))
  assert.ok(previewSource.includes('showSectionOrderDialog'))
  assert.ok(previewSource.includes('dragOverSection($event, section)'))
  assert.ok(previewSource.includes('@click="resetSectionOrder">恢复默认</button>'))
  assert.equal(previewSource.includes('根据 JD 推荐排序'), false)
  assert.ok(previewSource.includes('@click="applySectionOrder"'))
  assert.ok(previewSource.includes('@click="closeSectionOrderDialog"'))
  assert.equal(previewSource.includes('localSectionOrder.value = order\n  persistSectionOrder()'), false)
})

test('module ordering only exposes visible modules with content', () => {
  assert.ok(previewSource.includes('const sectionHasContent = section =>'))
  assert.ok(previewSource.includes("return fallback ? displayTitleText(section, fallback) : ''"))
  assert.ok(previewSource.includes(".filter(section => sectionLabel(section) && sectionHasContent(section) && !hiddenSection(section) && !isEducationChildSection(section))"))
  for (const section of ['honors', 'publications', 'research_interests', 'skills', 'work_experience', 'project_experience', 'custom_sections', 'others', 'self_evaluation']) {
    assert.ok(previewSource.includes(`${section}:`), `missing module label: ${section}`)
  }
  assert.ok(previewSource.includes(".filter(section => sectionLabel(section) && sectionHasContent(section) && !hiddenSection(section) && isEducationChildSection(section))"))
  assert.ok(previewSource.includes('customSectionModuleId(sectionIndex)'))
  assert.ok(previewSource.includes('expandSectionOrderForData(props.layoutConfig, props.data)'))
})

test('direct edit scopes follow current content and current module titles', () => {
  assert.ok(appSource.includes('const directEditScopeOptions = computed(() => {'))
  assert.ok(appSource.includes("sectionTitle(layout, section, currentLang.value, fallback)"))
  assert.ok(appSource.includes("const options = [{ value: 'all', label: '整份简历' }]"))
  assert.ok(appSource.includes("add('education', title('education', '教育经历'), [data.education, data.education_supplement])"))
  assert.ok(appSource.includes("add('skills', title('skills', '专业技能'), data.others?.skills)"))
  assert.ok(appSource.includes('value: `custom_sections:${index}`'))
  assert.ok(appSource.includes('if (hasMeaningfulResumeContent(content)) options.push({ value, label })'))
})

test('font size order and section dialogs are mutually exclusive', () => {
  assert.ok(previewSource.includes('closeSectionOrderDialog()\n  closeFontSizeDialog()'))
  assert.ok(previewSource.includes('closeFontSizeDialog()\n  closeSectionSettingsDialog()'))
  assert.ok(previewSource.includes('closeSectionOrderDialog()\n  closeSectionSettingsDialog()'))
  assert.ok(previewSource.includes('top: 6px;\n  right: 6px;'))
})

test('section ordering uses a compact left-side dialog so the PDF stays visible', () => {
  assert.ok(previewSource.includes('width: calc((100vw - 156px) * 0.39)'))
  assert.ok(previewSource.includes('justify-content: flex-end'))
  assert.ok(previewSource.includes('width: min(340px, calc(100vw - 40px))'))
  assert.ok(previewSource.includes('background: rgba(7, 8, 11, 0.16)'))
  assert.ok(previewSource.includes('.font-size-overlay,\n.spacing-overlay {\n  right: auto;\n  left: 156px;'))
  assert.ok(previewSource.includes('.settings-dialog-action {\n  width: 76px;\n  min-width: 76px;\n  height: 34px;'))
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

test('selected list style replaces imported markers and marker weight follows content', () => {
  assert.ok(previewSource.includes('function moduleListContent(value)'))
  assert.ok(previewSource.includes("{ 'marker-bold': isFullyBoldText(value) }"))
  assert.ok(previewSource.includes('.generic-list-item.marker-bold::before'))
  assert.ok(previewSource.includes('content: attr(data-marker);'))
  assert.ok(previewSource.includes("content: '(' counter(project-duty) ')';"))
  assert.ok(previewSource.includes('v-html="formatText(moduleListContent(item))"'))
  assert.equal(previewSource.includes('has-native-marker'), false)
  assert.equal(previewSource.includes('native-list-marker'), false)
})

test('certificate and language values follow their section heading during pagination', () => {
  assert.ok(previewSource.includes("<div v-if=\"isItemVisible({index: getItemIndex('others-title', 0)}, page - 1)\" class=\"cert-lang-line\""))
})

test('certificate and language component rows remain separate lines', () => {
  assert.ok(previewSource.includes("function visibleOtherComponentRows()"))
  assert.ok(previewSource.includes("component-${component}"))
  assert.ok(layoutConfigSource.includes("components: ['certificates'], flow: 'stacked'"))
  assert.ok(layoutConfigSource.includes("components: ['languages'], flow: 'stacked'"))
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
  assert.ok(previewSource.includes("moduleListStyle('self_evaluation') === 'paragraph'"))
})

test('retired custom-template entry and duplicate toolbar column settings are absent', () => {
  assert.equal(previewSource.includes('aria-label="打开模板管理"'), false)
  assert.equal(previewSource.includes('/layout-templates'), false)
  assert.equal(previewSource.includes('>栏目设置</button>'), false)
  assert.equal(previewSource.includes('修改当前简历的栏目名称、段落标记，或将相关栏目并入教育经历。'), false)
  assert.ok(appSource.includes('RESUME_LIST_STYLE_OPTIONS'))
  assert.ok(appSource.includes('setResumeEditPlacement'))
  assert.ok(appSource.includes('并入教育经历后将不显示模块标题'))
})

test('column settings are compact, explicit, and preview every draft selection', () => {
  assert.ok(previewSource.includes('<h4>分点形式</h4>'))
  assert.equal(previewSource.includes('<h4>段落开头</h4>'), false)
  assert.ok(previewSource.includes('function editableSectionPlacement(section)'))
  assert.ok(previewSource.includes('<option value="standalone">独立栏目</option>'))
  assert.ok(previewSource.includes(':value="editableSectionPlacement(section)"'))
  assert.ok(previewSource.includes('v-model="sectionSettingsDraft[section].listStyle"'))
  assert.ok(previewSource.includes('v-model="sectionSettingsDraft.education.supplementListStyle"'))
  assert.ok(previewSource.includes('height: min(480px, calc(100vh - 96px))'))
  assert.ok(previewSource.includes('box-sizing: border-box'))
})

test('edit-content selectors sit beside their titles without visible setting labels', () => {
  assert.ok(appSource.includes('class="module-title-setting-row"'))
  assert.ok(appSource.includes('class="module-title-setting-controls"'))
  assert.ok(appSource.includes('grid-template-columns: minmax(220px, 33.333%) auto;'))
  assert.equal(appSource.includes('<label>内容形式</label>'), false)
  assert.equal(appSource.includes('<label>栏目位置</label>'), false)
  assert.ok(previewSource.includes("values.join('\\n')"))
})

test('resume content selectors keep their native dropdown arrows visible', () => {
  assert.ok(appSource.includes('.resume-dialog .module-title-setting-row > select'))
  assert.ok(appSource.includes('-webkit-appearance: menulist !important;'))
  assert.ok(appSource.includes('appearance: auto !important;'))
  assert.ok(appSource.includes('background-image: none !important;'))
})

test('education supplement reuses the same title-row select styling', () => {
  assert.ok(appSource.includes('<div class="education-supplement-editor">'))
  assert.equal(appSource.includes('<div class="field-group full-width education-supplement-editor">'), false)
  assert.ok(appSource.includes('<div class="module-title-setting-row module-title-setting-row-label">'))
})

test('custom section list style belongs to each section content editor', () => {
  assert.ok(appSource.includes('v-model="section._listStyle"'))
  assert.ok(appSource.includes('aria-label="自定义栏目内容分点形式"'))
  assert.ok(appSource.includes('list_style: normalizeResumeListStyle(section._listStyle || section.list_style)'))
  assert.ok(previewSource.includes('function customSectionListStyle(custom)'))
  assert.ok(previewSource.includes('customSectionListValues(custom)'))
})

test('paragraph content preserves authored line boundaries in the preview', () => {
  assert.ok(previewSource.includes("const paragraphText = value => String(value ?? '').replace(/\\r\\n?/g, '\\n')"))
  assert.ok(previewSource.includes('formatText(paragraphText(block.text))'))
  assert.ok(previewSource.includes('white-space: pre-wrap'))
})

test('closing live-preview settings restores saved values', () => {
  assert.ok(previewSource.includes('fontSizeDraft.value = { ...fontSizes.value }'))
  assert.ok(previewSource.includes('sectionSettingsDraft.value = normalizeLayoutConfig(props.layoutConfig)'))
  assert.ok(previewSource.includes('localSectionOrder.value = [...sectionOrderSnapshot.value]'))
})

test('birth date and merged education headings use body semantics', () => {
  assert.ok(previewSource.includes("!hiddenBasicField('birth_date') && basics.birth_date ? basics.birth_date : ''"))
  assert.equal(previewSource.includes('`${t.value.birthDate}：${basics.birth_date}`'), false)
  assert.ok(previewSource.includes('educationSupplementValues'))
  assert.ok(previewSource.includes('教育经历补充'))
  assert.ok(previewSource.includes('const educationSupplementStyle = computed'))
})

test('all basic information components use pipe separators', () => {
  assert.ok(previewSource.includes(".personal-info .module-component-cell.flow-inline .module-component + .module-component::before { content: ' | '; }"))
  assert.equal(previewSource.includes('contactLayout'), false)
  assert.equal(previewSource.includes("`${t.value.birthDate}：${basics.birth_date}`"), false)
})

test('target position label follows the content bold state', () => {
  assert.ok(previewSource.includes('isFullyBoldInlineText(basics.target_position) ? `**${label}**` : label'))
  assert.equal(previewSource.includes('.module-component.component-target_position { font-weight: var(--manual-title-font-weight); }'), false)
  assert.ok(previewSource.includes("'is-bold': isFullyBoldInlineText(data.basics.target_position)"))
})

test('merged education children use their saved order and cannot leave education', () => {
  assert.ok(previewSource.includes('.sort((left, right) => sectionOrder(layout.value, left.id) - sectionOrder(layout.value, right.id))'))
  assert.ok(previewSource.includes('const reorderableEducationChildren = computed'))
  assert.ok(previewSource.includes("section === 'education' ? [section, ...reorderableEducationChildren.value] : [section]"))
  assert.ok(previewSource.includes('isEducationChildSection(source) !== isEducationChildSection(targetSection)'))
  assert.ok(previewSource.includes(':disabled="!canMoveSection(section, -1)"'))
  assert.ok(previewSource.includes('section-order-dialog-row.education-child-row'))
  assert.ok(previewSource.includes('margin-left: 24px'))
})

test('edit content follows the default module order and saves live-editable titles and pending tags', () => {
  const markers = [
    '>基本信息</h4>',
    'v-model="resumeModuleTitles.education"',
    'v-model="resumeModuleTitles.honors"',
    'v-model="resumeModuleTitles.publications"',
    'v-model="resumeModuleTitles.research_interests"',
    'v-model="resumeModuleTitles.skills"',
    'v-model="resumeModuleTitles.work_experience"',
    'v-model="resumeModuleTitles.project_experience"',
    'class="module-title-inline-label">自定义项目</span>',
    'v-model="resumeModuleTitles.others"',
    'v-model="resumeModuleTitles.self_evaluation"'
  ]
  const positions = markers.map(marker => appSource.indexOf(marker))
  assert.ok(positions.every(position => position >= 0))
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right))
  assert.ok(appSource.includes('@update:modelValue="previewResumeModuleTitles"'))
  assert.ok(appSource.includes('candidate.global.titleOverrides[section]'))
  assert.ok(appSource.includes('addResumeSkill()\n    addResumeCert()\n    addResumeLang()'))
  assert.ok(appSource.includes('dataToSave.publications = multilineToArray(publicationsText.value)'))
})

test('source document header stays compact and relies on the toolbar for returning', () => {
  assert.ok(previewSource.includes('min-height: 34px'))
  assert.ok(previewSource.includes('padding: 6px 12px'))
  assert.equal(previewSource.includes('class="source-document-actions"'), false)
})

test('single-page preview does not render a redundant 1 / 1 footer', () => {
  assert.ok(previewSource.includes('v-if="pageCount > 1" class="page-footer"'))
})

test('education uses the normalized current component rows and symmetric widths', () => {
  assert.ok(previewSource.includes("'--education-compact-side-column': `${educationColumnWidths.value.sideMm}mm`"))
  assert.ok(previewSource.includes("'--education-middle-column': `${educationColumnWidths.value.middleMm}mm`"))
  assert.ok(previewSource.includes('grid-template-columns: var(--education-compact-side-column) var(--education-middle-column) var(--education-compact-side-column)'))
  assert.ok(previewSource.includes("visibleComponentRows('education', ['theses'])"))
  assert.ok(previewSource.includes('componentRowStyle(row, \'education\')'))
  assert.ok(previewSource.includes('componentCellStyle(cell)'))
  assert.ok(previewSource.includes('educationComponentText(item, component)'))
  assert.ok(previewSource.includes('formatCompactAcademicMetric(item, hidden)'))
  assert.ok(previewSource.includes("joinInlineWithInheritedSeparator(item?.school_tags, ' · ')"))
  assert.ok(previewSource.includes('text-align: center'))
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
  assert.ok(previewSource.includes('margin-left: calc(var(--module-indent) + var(--list-text-indent))'))
  assert.ok(previewSource.includes(".list-item::before {\n  content: '•';\n  position: absolute;\n  left: 0;\n  width: calc(var(--list-text-indent) - var(--list-marker-gap));\n  text-align: center;"))
})

test('field labels and semantic content labels use their requested typography roles', () => {
  assert.ok(previewSource.includes('.module-component.component-school_tags,'))
  assert.ok(previewSource.includes('.module-component.component-job_type { font-size: var(--label-font-size); font-weight: var(--manual-field-font-weight); }'))
  assert.ok(previewSource.includes('.project-block-label { margin-bottom: var(--content-label-spacing); font-size: var(--body-font-size);'))
})

test('preview applies shared module spacing before every section title', () => {
  assert.ok(previewSource.includes('margin-top: var(--module-margin)'))
  assert.ok(previewSource.includes('margin-bottom: var(--section-title-after)'))
  assert.ok(previewSource.includes('padding-bottom: var(--section-title-border-gap)'))
})

test('zero module indent does not fall back to the global list indent', () => {
  assert.match(previewSource, /'--module-indent': `\$\{moduleTokens\.indentPt \?\? 0\}pt`/)
  assert.match(previewSource, /margin-left: calc\(var\(--module-indent\) \+ var\(--list-text-indent\)\)/)
  assert.doesNotMatch(previewSource, /'--list-text-indent': `\$\{moduleTokens\.indentPt/)
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

test('work headings use configurable component rows and right-aligned date cells', () => {
  assert.ok(previewSource.includes("visibleComponentRows(section.id, ['content'])"))
  assert.ok(previewSource.includes('workComponentText(entry.item, component, section.id)'))
  assert.ok(previewSource.includes("cell.alignment === 'right' ? 'flex-end'"))
  assert.ok(previewSource.includes("cell.width === 'content' ? 'max-content' : 'minmax(0, 1fr)'"))
  assert.ok(previewSource.includes('text-align: right'))
})

test('empty work and project dates stay hidden and separators require both sides bold', () => {
  assert.ok(previewSource.includes('function dateRangeText(item)'))
  assert.ok(previewSource.includes("return joinInlineWithInheritedSeparator(values, ' - ')"))
  assert.equal(previewSource.includes("|| '至今'"), false)
  assert.ok(previewSource.includes("'component-explicit-bold': componentIsFullyBold(workComponentText(entry.item, component, section.id))"))
  assert.ok(previewSource.includes("'component-explicit-bold': componentIsFullyBold(projectComponentText(item, component))"))
  assert.ok(previewSource.includes('.component-explicit-bold + .module-component.component-explicit-bold::before'))
})

test('zoom stepper reports the live percentage instead of a fixed label', () => {
  assert.ok(previewSource.includes('aria-label="恢复百分之百">{{ zoomPercentage }}%</button>'))
  assert.ok(previewSource.includes('manualZoom.value = Math.min(1, Math.max(0.4, currentRatio + delta))'))
})

test('spacing settings preview as a draft and only reset the four spacing values', () => {
  assert.ok(previewSource.includes('class="success-dialog-overlay spacing-overlay"'))
  assert.ok(previewSource.includes('<h3 id="spacing-title">间距</h3>'))
  assert.ok(previewSource.includes('@click="openSpacingDialog"'))
  assert.ok(previewSource.includes('@click="resetSpacingDraft">恢复默认</button>'))
  assert.ok(previewSource.includes('@click="confirmSpacingSettings">应用</button>'))
  assert.ok(previewSource.includes('点击应用后才保存'))
  assert.ok(previewSource.includes('syncingLayoutProps || showSpacingDialog.value'))
  assert.ok(previewSource.includes("activateResumeSettingsDialog('spacing')"))
  const resetStart = previewSource.indexOf('function resetSpacingDraft')
  const confirmStart = previewSource.indexOf('function confirmSpacingSettings', resetStart)
  const resetBody = previewSource.slice(resetStart, confirmStart)
  for (const field of ['marginVertical', 'marginHorizontal', 'moduleMargin', 'lineHeight']) assert.ok(resetBody.includes(`${field}.value =`))
  assert.equal(resetBody.includes('fontSizes.value ='), false)
  assert.equal(previewSource.includes('恢复默认排版'), false)
  assert.ok(previewSource.includes('v-model.number="moduleMargin" min="0.1" max="1" step="0.1"'))
  assert.ok(previewSource.includes('v-model.number="lineHeight" min="1" max="1.8" step="0.05"'))
  assert.equal(previewSource.includes('<div class="layout-settings-heading">文字大小</div>'), false)
  assert.equal(previewSource.includes('<div class="layout-settings-heading">模块顺序</div>'), false)
})
