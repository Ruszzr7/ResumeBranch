<script setup>
import { ref, computed, onMounted, watch, nextTick, onUnmounted } from 'vue'
import { labels } from '../utils/labels.js'
import { formatInlineHtml, isFullyBoldInlineText, plainInlineText } from '../utils/inlineFormatting.js'
import { buildAuthorizationHeaders } from '../config/appMode.js'
import {
  DEFAULT_LAYOUT_CONFIG,
  FONT_SIZE_LABELS,
  FONT_SIZE_LIMITS,
  formatCompactAcademicMetric,
  normalizeLayoutConfig,
  resolveContentBlockFlow,
  resolveEducationColumnWidths,
  resolveLayoutTokens,
  resolvePhotoHeightMm,
  sectionTitle,
  sectionOrder,
  isSectionHidden
} from '../utils/layoutConfig.js'

const props = defineProps({
  data: {
    type: Object,
    required: false,
    default: () => null
  },
  // 高亮模块 - 值为: 'basics', 'education', 'work_experience', 'project_experience', 'others', 'self_evaluation'
  highlightedModule: {
    type: String,
    required: false,
    default: ''
  },
  // JD数据（新增）
  jdData: {
    type: Object,
    required: false,
    default: null
  },
  // 是否为移动端视图（由父组件传入）
  isMobileView: {
    type: Boolean,
    required: false,
    default: false
  },
  // 语言：'zh' | 'en'
  lang: {
    type: String,
    required: false,
    default: 'zh'
  },
  translationBusy: {
    type: Boolean,
    required: false,
    default: false
  },
  layoutConfig: {
    type: Object,
    required: false,
    default: () => ({})
  },
  taskId: {
    type: String,
    required: false,
    default: ''
  },
  sourcePageCount: {
    type: Number,
    required: false,
    default: 1
  },
  hasSourceDocument: {
    type: Boolean,
    required: false,
    default: false
  }
})

// 获取当前语言的标签
const t = computed(() => labels[props.lang] || labels.zh)
const localSectionOrder = ref(normalizeLayoutConfig(props.layoutConfig).global.sectionOrder)
const showSectionSettingsDialog = ref(false)
const isSavingSectionSettings = ref(false)
const sectionSettingsError = ref('')
const sectionSettingsDraft = ref(normalizeLayoutConfig(props.layoutConfig))
const layout = computed(() => {
  const source = showSectionSettingsDialog.value ? sectionSettingsDraft.value : props.layoutConfig
  const value = normalizeLayoutConfig(source)
  value.global.sectionOrder = [...localSectionOrder.value]
  return value
})
const moduleLayout = name => layout.value[name] || {}
const hiddenSection = name => isSectionHidden(layout.value, name)
const displayTitle = (name, fallback) => {
  const override = layout.value.global?.titleOverrides?.[name]?.[props.lang]
  if (override !== undefined) return override
  return Number(props.data?.formatting_version || 0) >= 2 ? `**${fallback}**` : sectionTitle(layout.value, name, props.lang, fallback)
}
const displayTitleText = (name, fallback) => plainInlineText(displayTitle(name, fallback))
const moduleTitleStyle = name => moduleLayout(name).titleStyle || layout.value.global.titleStyle
const moduleOrder = name => {
  const moduleTokens = layoutTokens.value?.modules?.[name] || {}
  const config = moduleLayout(name)
  return {
    order: sectionOrder(layout.value, name),
    textAlign: config.titleAlignment || undefined,
    '--item-spacing': `${moduleTokens.itemSpacingPt ?? layoutTokens.value?.itemSpacingPt ?? 0}pt`,
    '--paragraph-spacing': `${moduleTokens.paragraphSpacingPt ?? layoutTokens.value?.paragraphSpacingPt ?? 0}pt`,
    '--content-block-spacing': `${moduleTokens.contentBlockSpacingPt ?? layoutTokens.value?.contentBlockSpacingPt ?? 0}pt`,
    '--module-indent': `${moduleTokens.indentPt ?? 0}pt`
  }
}
const hiddenBasicField = field => moduleLayout('basics').hiddenFields?.includes(field)
const workSections = computed(() => {
  const make = (id, fallback) => ({ id, title: displayTitle(id, fallback), entries: workEntries(id) })
  if (layout.value.global.splitWorkExperience) {
    return [
      make('work_experience', props.lang === 'en' ? 'Work Experience' : '工作经历'),
      make('internship_experience', props.lang === 'en' ? 'Internship Experience' : '实习经历')
    ].filter(section => !hiddenSection(section) && section.entries.length)
  }
  return hiddenSection('work_experience')
    ? []
    : [make('work_experience', t.value.workExperience)].filter(section => section.entries.length)
})
const workTypePrefix = sectionId => sectionId === 'internship_experience' ? 'internship' : 'work'
const visibleOtherFields = computed(() => (moduleLayout('others').fieldOrder || [])
  .filter(field => field !== 'skills'
    && !moduleLayout('others').hiddenFields?.includes(field)
    && !moduleLayout('others').hiddenComponents?.includes(field)
    && props.data?.others?.[field]?.length))
const otherFieldLabel = field => {
  const custom = props.data?.others?.field_labels
  if (custom && Object.prototype.hasOwnProperty.call(custom, field)) return String(custom[field] ?? '').trim()
  return ({ skills: t.value.skills, certificates: t.value.certificates, languages: t.value.language }[field] || field)
}
const otherFieldValue = (field, values) => {
  const label = otherFieldLabel(field)
  const joined = (values || []).join(otherSeparator.value)
  return label ? `${label}：${joined}` : joined
}
const otherSeparator = computed(() => moduleLayout('others').separator === 'dot' ? ' · ' : ' | ')
const sectionMergedIntoEducation = section => Boolean(props.data?.education?.length)
  && layout.value.global.sectionPlacements?.[section] === 'education'
const mergedEducationGroups = computed(() => {
  const sections = [
    { id: 'research_interests', fallback: t.value.researchInterests, values: props.data?.research_interests || [] },
    { id: 'honors', fallback: t.value.honors, values: props.data?.honors || [] },
    { id: 'publications', fallback: props.lang === 'en' ? 'Publications' : '论文', values: props.data?.publications || [] },
    {
      id: 'others',
      fallback: props.lang === 'en' ? 'Certificates & Languages' : '证书与语言',
      values: visibleOtherFields.value.flatMap(field => {
        const label = otherFieldLabel(field)
        return (props.data?.others?.[field] || []).map(value => label ? `${label}：${value}` : value)
      })
    }
  ]
  return sections
    .filter(section => sectionMergedIntoEducation(section.id) && !hiddenSection(section.id) && section.values.length)
    .sort((left, right) => sectionOrder(layout.value, left.id) - sectionOrder(layout.value, right.id))
})
const educationSupplementValues = computed(() => {
  const manual = (props.data?.education_supplement || [])
    .map(value => String(value || '').trim())
    .filter(Boolean)
  return [
    ...mergedEducationGroups.value.flatMap(section => section.values),
    ...manual
  ]
})
const educationSupplementStyle = computed(() => moduleLayout('education').supplementListStyle || 'bullet')
function educationSupplementMarker(value, index) {
  if (educationSupplementStyle.value === 'numbered') return `(${index + 1})`
  return educationSupplementStyle.value === 'bullet' ? '•' : ''
}
function educationSupplementClasses(value, extra = '') {
  return [
    'generic-list-item',
    `list-style-${educationSupplementStyle.value}`,
    extra,
    { 'marker-bold': isFullyBoldText(value) }
  ]
}
const selfEvaluationValues = computed(() => {
  const values = (props.data?.self_evaluation || [])
    .map(value => String(value || '').trim())
    .filter(Boolean)
  return values.length && moduleLayout('self_evaluation').preset === 'compact' ? [values.join(' ')] : values
})

const showSourceDocument = ref(false)
const sourceDocumentLoading = ref(false)
const sourceDocumentError = ref('')
const sourceDocumentUrl = ref('')
const sourceDocumentMime = ref('')
const sourceDocumentName = ref('原版简历')
const sourceDocumentIsPdf = computed(() => sourceDocumentMime.value === 'application/pdf')

function releaseSourceDocumentUrl() {
  if (sourceDocumentUrl.value) URL.revokeObjectURL(sourceDocumentUrl.value)
  sourceDocumentUrl.value = ''
}

function closeSourceDocument() {
  showSourceDocument.value = false
  sourceDocumentLoading.value = false
  sourceDocumentError.value = ''
  releaseSourceDocumentUrl()
}

async function toggleSourceDocument() {
  if (showSourceDocument.value) {
    closeSourceDocument()
    return
  }
  if (!props.taskId || !props.hasSourceDocument) return
  closeToolbarMenu()
  showSourceDocument.value = true
  sourceDocumentLoading.value = true
  sourceDocumentError.value = ''
  try {
    const response = await fetch(`/tasks/${props.taskId}/source-document`, {
      headers: buildAuthorizationHeaders()
    })
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}))
      throw new Error(detail.detail || '原版简历加载失败')
    }
    const blob = await response.blob()
    releaseSourceDocumentUrl()
    sourceDocumentUrl.value = URL.createObjectURL(blob)
    sourceDocumentMime.value = blob.type || response.headers.get('Content-Type')?.split(';')[0] || ''
    const encodedName = response.headers.get('X-Source-Filename')
    if (encodedName) {
      try { sourceDocumentName.value = decodeURIComponent(encodedName) } catch { sourceDocumentName.value = encodedName }
    }
  } catch (error) {
    sourceDocumentError.value = error.message || '原版简历加载失败'
  } finally {
    sourceDocumentLoading.value = false
  }
}

function retrySourceDocument() {
  closeSourceDocument()
  toggleSourceDocument()
}

function academicMetrics(item) {
  const metrics = []
  const hidden = moduleLayout('education').hiddenMetrics || []
  if (item?.gpa && !hidden.includes('gpa')) {
    metrics.push(`${t.value.gpa}：${item.gpa}${item.gpa_scale ? `/${item.gpa_scale}` : ''}`)
  }
  if (item?.ranking && !hidden.includes('ranking')) {
    metrics.push(`${t.value.ranking}：${item.ranking}`)
  }
  return metrics
}

function projectContentBlocks(item, experienceKind = 'project') {
  if (Array.isArray(item?.content_blocks) && item.content_blocks.length) {
    return item.content_blocks.filter(block => resolveContentBlockFlow(block).visible)
  }
  const details = Array.isArray(item?.details) ? item.details.filter(Boolean) : []
  if (!details.length) return []
  if (experienceKind === 'work') {
    return [{ type: 'bullet_list', semantic_role: 'generic', label: '', label_bold: true, text: '', items: details }]
  }
  const blocks = []
  let duties = null
  const extras = []
  for (const raw of details) {
    const text = String(raw || '').trim()
    const intro = text.match(/^(项目简介|项目背景|项目概述|项目说明)\s*[：:]\s*(.*)$/)
    const duty = text.match(/^(项目职责|主要职责|个人职责|负责内容)\s*[：:]?\s*(.*)$/)
    if (intro) {
      blocks.push({ type: 'paragraph', semantic_role: 'introduction', label: intro[1], label_bold: true, text: intro[2], items: [] })
    } else if (duty) {
      duties = { type: 'numbered_list', semantic_role: 'responsibilities', label: duty[1], label_bold: true, text: '', items: [] }
      if (duty[2]) duties.items.push(duty[2].replace(/^\s*[（(]?\d+[）).、]\s*/, ''))
      blocks.push(duties)
    } else if (duties || /^\s*[（(]?\d+[）).、]/.test(text)) {
      if (!duties) {
        duties = { type: 'numbered_list', semantic_role: 'responsibilities', label: '项目职责', label_bold: true, text: '', items: [] }
        blocks.push(duties)
      }
      duties.items.push(text.replace(/^\s*[（(]?\d+[）).、]\s*/, ''))
    } else if (text) {
      extras.push(text)
    }
  }
  if (extras.length) blocks.push({ type: 'bullet_list', semantic_role: 'generic', label: '', label_bold: true, text: '', items: extras })
  return blocks.filter(block => block.text || block.items?.length)
}

function workPosition(item, moduleId = 'work_experience') {
  const jobTitle = String(item?.job_title || '').trim()
  const jobType = String(item?.job_type || '').trim()
  return [
    jobTitle,
    jobType && moduleLayout(moduleId).showJobType ? `(${jobType})` : ''
  ].filter(Boolean).join(' ')
}

function nativeListMarkerParts(value) {
  const text = String(value || '')
  const match = text.match(/^\s*([（(]?\d{1,2}[）).、．]|[一二三四五六七八九十]+[、.．])\s*(.*)$/s)
  return match ? { marker: match[1], content: match[2] } : null
}

function compactAcademicMetric(item) {
  const hidden = moduleLayout('education').hiddenMetrics || []
  return formatCompactAcademicMetric(item, hidden)
}

function visibleComponentRows(moduleId, excluded = []) {
  const hidden = new Set([...(moduleLayout(moduleId).hiddenComponents || []), ...excluded])
  return (moduleLayout(moduleId).componentRows || []).map(row => ({
    cells: (row.cells || []).map(cell => ({
      ...cell,
      components: (cell.components || []).filter(component => !hidden.has(component))
    })).filter(cell => cell.components.length)
  })).filter(row => row.cells.length)
}

function componentRowStyle(row, moduleId) {
  const isCompactEducationHeader = moduleId === 'education'
    && moduleLayout('education').preset === 'compact'
    && row.cells.length === 3
    && row.cells[0]?.components?.includes('school')
    && row.cells[1]?.components?.some(component => ['degree', 'major', 'metrics'].includes(component))
    && row.cells[2]?.components?.includes('date')
  const width = cell => cell.width === 'content' ? 'max-content' : 'minmax(0, 1fr)'
  return {
    gridTemplateColumns: isCompactEducationHeader
      ? 'var(--education-compact-side-column) var(--education-middle-column) var(--education-compact-side-column)'
      : row.cells.map(width).join(' '),
    gap: isCompactEducationHeader ? 0 : '0.3em',
    marginBottom: `${layoutTokens.value.modules?.[moduleId]?.rowSpacingPt || 0}pt`
  }
}

function componentCellStyle(cell) {
  return {
    display: cell.flow === 'stacked' ? 'flex' : 'flex',
    flexDirection: cell.flow === 'stacked' ? 'column' : 'row',
    flexWrap: 'wrap',
    justifyContent: cell.alignment === 'right' ? 'flex-end' : (cell.alignment === 'center' ? 'center' : 'flex-start'),
    textAlign: cell.alignment,
    minWidth: 0
  }
}

function educationComponentText(item, component) {
  if (component === 'school') return item?.school_name || '学校未填写'
  if (component === 'school_tags') return (item?.school_tags || []).join(' · ')
  if (component === 'degree') return item?.degree || ''
  if (component === 'major') return item?.major || ''
  if (component === 'metrics') {
    return moduleLayout('education').preset === 'compact'
      ? compactAcademicMetric(item)
      : academicMetrics(item).join(' · ')
  }
  if (component === 'date') return `${item?.date_range?.[0] || ''} - ${item?.date_range?.[1] || '至今'}`
  return ''
}

function workComponentText(item, component, moduleId) {
  if (component === 'organization') return item?.company_name || '公司未填写'
  if (component === 'position') return item?.job_title || ''
  if (component === 'job_type') return moduleLayout(moduleId).showJobType && item?.job_type ? `(${item.job_type})` : ''
  if (component === 'date') return `${item?.date_range?.[0] || ''} - ${item?.date_range?.[1] || '至今'}`
  return ''
}

function projectComponentText(item, component) {
  if (component === 'project_name') return item?.project_name || item?.name || '项目未填写'
  if (component === 'role') return moduleLayout('project_experience').showRole ? (item?.role || '') : ''
  if (component === 'date') return moduleLayout('project_experience').showDate ? `${item?.date_range?.[0] || ''} - ${item?.date_range?.[1] || '至今'}` : ''
  return ''
}

function basicsComponentText(component) {
  const basics = props.data?.basics || {}
  if (component === 'name') return basics.name || '姓名未填写'
  if (component === 'target_position' && !hiddenBasicField('target_position') && basics.target_position) {
    const label = `${t.value.targetPosition}：`
    return `${isFullyBoldInlineText(basics.target_position) ? `**${label}**` : label}${basics.target_position}`
  }
  if (component === 'personal_meta') return [
    !hiddenBasicField('gender') ? basics.gender : '',
    !hiddenBasicField('birth_date') && basics.birth_date ? basics.birth_date : ''
  ].filter(Boolean).join(' | ')
  if (component === 'contact') return [
    !hiddenBasicField('phone') ? basics.phone : '',
    !hiddenBasicField('email') ? basics.email : ''
  ].filter(Boolean).join(' | ')
  if (component === 'additional_fields' && !hiddenBasicField('additional_fields')) {
    return (basics.additional_fields || [])
      .filter(field => field?.label || field?.value)
      .map(field => field?.label && field?.value ? `${field.label}：${field.value}` : (field?.label || field?.value))
      .join(' | ')
  }
  return ''
}

function moduleListContent(value) {
  return nativeListMarkerParts(value)?.content || String(value || '')
}

function isFullyBoldText(value) {
  return isFullyBoldInlineText(moduleListContent(value).trim())
}

function moduleListStyle(moduleId) {
  return moduleLayout(moduleId).listStyle || 'bullet'
}

function moduleListMarker(moduleId, value, index) {
  const style = moduleListStyle(moduleId)
  if (style === 'numbered') return `(${index + 1})`
  return style === 'bullet' ? '•' : ''
}

function moduleListClasses(moduleId, value, extra = '') {
  return [
    'generic-list-item',
    `list-style-${moduleListStyle(moduleId)}`,
    extra,
    { 'marker-bold': isFullyBoldText(value) }
  ]
}

function othersComponentText(component) {
  const values = props.data?.others?.[component] || []
  if (!values.length) return ''
  return otherFieldValue(component, values)
}

function visibleOtherComponentRows() {
  return visibleComponentRows('others').map(row => ({
    cells: row.cells.map(cell => ({
      ...cell,
      components: cell.components.filter(component => othersComponentText(component))
    })).filter(cell => cell.components.length)
  })).filter(row => row.cells.length)
}

const emit = defineEmits(['open-jd-dialog', 'open-resume-edit', 'open-resume-import', 'toggle-lang', 'use-layout-prompt', 'layout-updated'])

const SECTION_LABELS = {
  education: '教育经历', skills: '专业技能', research_interests: '研究方向', honors: '主要荣誉',
  publications: '论文',
  work_experience: '工作经历', internship_experience: '实习经历', project_experience: '项目经历',
  custom_sections: '自定义栏目', others: '证书与语言', self_evaluation: '自我评价'
}
const isEducationChildSection = section => section !== 'education' && sectionMergedIntoEducation(section)
const hasResumeListContent = value => Array.isArray(value) && value.some(item => String(item || '').trim())
const sectionHasContent = section => {
  const data = props.data || {}
  if (section === 'education') return Array.isArray(data.education) && data.education.length > 0
  if (section === 'skills') return hasResumeListContent(data.others?.skills)
  if (section === 'research_interests') return hasResumeListContent(data.research_interests)
  if (section === 'honors') return hasResumeListContent(data.honors)
  if (section === 'publications') return hasResumeListContent(data.publications)
  if (section === 'work_experience') {
    const entries = data.work_experience || []
    return layout.value.global.splitWorkExperience
      ? entries.some(item => !/实习|intern/i.test(String(item?.job_type || '')))
      : entries.length > 0
  }
  if (section === 'internship_experience') {
    return layout.value.global.splitWorkExperience
      && (data.work_experience || []).some(item => /实习|intern/i.test(String(item?.job_type || '')))
  }
  if (section === 'project_experience') return hasResumeListContent(data.project_experience || data.projects)
  if (section === 'custom_sections') {
    return (data.custom_sections || []).some(item => String(item?.title || '').trim() && hasResumeListContent(item?.items))
  }
  if (section === 'others') return visibleOtherFields.value.length > 0
  if (section === 'self_evaluation') return hasResumeListContent(data.self_evaluation)
  return false
}
const reorderableTopSections = computed(() => localSectionOrder.value
  .filter(section => SECTION_LABELS[section] && sectionHasContent(section) && !hiddenSection(section) && !isEducationChildSection(section)))
const reorderableEducationChildren = computed(() => localSectionOrder.value
  .filter(section => SECTION_LABELS[section] && sectionHasContent(section) && !hiddenSection(section) && isEducationChildSection(section)))
const reorderableSections = computed(() => reorderableTopSections.value.flatMap(section => (
  section === 'education' ? [section, ...reorderableEducationChildren.value] : [section]
)))
const draggedSection = ref('')
const isSavingSectionOrder = ref(false)
const showSectionOrderDialog = ref(false)
const sectionOrderChangedByDrag = ref(false)
const sectionOrderSnapshot = ref([])
const sectionOrderError = ref('')
const listSettingSections = ['skills', 'research_interests', 'honors', 'publications', 'custom_sections', 'self_evaluation']
const mergeSettingSections = ['research_interests', 'honors', 'publications', 'others']
const LIST_STYLE_LABELS = { paragraph: '无标记', bullet: '分点', numbered: '编号' }

function editableSectionPlacement(section) {
  return sectionSettingsDraft.value.global.sectionPlacements[section] === 'education'
    ? 'education'
    : 'standalone'
}

function setEditableSectionPlacement(section, value) {
  if (value === 'education') sectionSettingsDraft.value.global.sectionPlacements[section] = 'education'
  else delete sectionSettingsDraft.value.global.sectionPlacements[section]
}

function openSectionSettingsDialog() {
  if (isSavingSectionOrder.value || isSavingFontSizes.value) return
  closeSectionOrderDialog()
  closeFontSizeDialog()
  sectionSettingsDraft.value = normalizeLayoutConfig(layout.value)
  sectionSettingsError.value = ''
  closeToolbarMenu()
  showSectionSettingsDialog.value = true
}

function closeSectionSettingsDialog() {
  if (isSavingSectionSettings.value) return
  sectionSettingsDraft.value = normalizeLayoutConfig(props.layoutConfig)
  showSectionSettingsDialog.value = false
  sectionSettingsError.value = ''
}

function resetSectionSettings() {
  const defaults = normalizeLayoutConfig(DEFAULT_LAYOUT_CONFIG)
  sectionSettingsDraft.value.global.sectionPlacements = {}
  for (const section of listSettingSections) {
    sectionSettingsDraft.value[section].listStyle = defaults[section].listStyle
  }
  sectionSettingsDraft.value.education.supplementListStyle = defaults.education.supplementListStyle
}

async function applySectionSettings() {
  if (!props.taskId || isSavingSectionSettings.value) return
  isSavingSectionSettings.value = true
  sectionSettingsError.value = ''
  try {
    const candidate = normalizeLayoutConfig(sectionSettingsDraft.value)
    const response = await fetch(`/tasks/${props.taskId}/layout`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...buildAuthorizationHeaders() },
      body: JSON.stringify({ layout_config: candidate })
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || '保存栏目设置失败')
    emit('layout-updated', normalizeLayoutConfig(payload.layout_config || candidate))
    showSectionSettingsDialog.value = false
  } catch (error) {
    sectionSettingsError.value = error.message || '保存栏目设置失败'
  } finally {
    isSavingSectionSettings.value = false
  }
}

async function persistSectionOrder() {
  if (!props.taskId || isSavingSectionOrder.value) return false
  isSavingSectionOrder.value = true
  sectionOrderError.value = ''
  const candidate = normalizeLayoutConfig(layout.value)
  candidate.global.sectionOrder = [...localSectionOrder.value]
  try {
    const response = await fetch(`/tasks/${props.taskId}/layout`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...buildAuthorizationHeaders() },
      body: JSON.stringify({ layout_config: candidate })
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '保存模块顺序失败')
    localSectionOrder.value = [...normalizeLayoutConfig(data.layout_config).global.sectionOrder]
    emit('layout-updated', data.layout_config)
    sectionOrderSnapshot.value = []
    return true
  } catch (error) {
    localSectionOrder.value = sectionOrderSnapshot.value.length
      ? [...sectionOrderSnapshot.value]
      : [...normalizeLayoutConfig(props.layoutConfig).global.sectionOrder]
    sectionOrderError.value = error.message || '保存模块顺序失败'
    console.error(error)
    return false
  } finally {
    isSavingSectionOrder.value = false
  }
}

function moveSection(section, direction) {
  if (isSavingSectionOrder.value) return
  const visible = isEducationChildSection(section) ? reorderableEducationChildren.value : reorderableTopSections.value
  const visibleIndex = visible.indexOf(section)
  const targetSection = visible[visibleIndex + direction]
  if (visibleIndex < 0 || !targetSection) return
  const order = [...localSectionOrder.value]
  const sourceIndex = order.indexOf(section)
  order.splice(sourceIndex, 1)
  const insertionIndex = order.indexOf(targetSection) + (direction > 0 ? 1 : 0)
  order.splice(insertionIndex, 0, section)
  localSectionOrder.value = order
}

function openSectionOrderDialog() {
  if (isSavingFontSizes.value || isSavingSectionSettings.value) return
  closeFontSizeDialog()
  closeSectionSettingsDialog()
  closeToolbarMenu()
  sectionOrderSnapshot.value = [...normalizeLayoutConfig(props.layoutConfig).global.sectionOrder]
  localSectionOrder.value = [...sectionOrderSnapshot.value]
  sectionOrderError.value = ''
  showSectionOrderDialog.value = true
}

function closeSectionOrderDialog() {
  if (isSavingSectionOrder.value) return
  if (sectionOrderSnapshot.value.length) localSectionOrder.value = [...sectionOrderSnapshot.value]
  sectionOrderSnapshot.value = []
  sectionOrderError.value = ''
  draggedSection.value = ''
  sectionOrderChangedByDrag.value = false
  showSectionOrderDialog.value = false
}

async function applySectionOrder() {
  if (await persistSectionOrder()) showSectionOrderDialog.value = false
}

function startSectionDrag(section, event) {
  if (isSavingSectionOrder.value) return
  draggedSection.value = section
  sectionOrderChangedByDrag.value = false
  if (event?.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', section)
  }
}

function dragOverSection(event, targetSection) {
  event.preventDefault()
  const source = draggedSection.value
  if (!source || source === targetSection || isSavingSectionOrder.value) return
  if (isEducationChildSection(source) !== isEducationChildSection(targetSection)) return
  const row = event.currentTarget
  const insertAfter = event.clientY > row.getBoundingClientRect().top + row.offsetHeight / 2
  const order = [...localSectionOrder.value].filter(section => section !== source)
  const targetIndex = order.indexOf(targetSection)
  order.splice(targetIndex < 0 ? order.length : targetIndex + (insertAfter ? 1 : 0), 0, source)
  if (order.join('|') !== localSectionOrder.value.join('|')) {
    localSectionOrder.value = order
    sectionOrderChangedByDrag.value = true
  }
  const list = row.closest('.section-order-list')
  if (list) {
    const bounds = list.getBoundingClientRect()
    if (event.clientY < bounds.top + 36) list.scrollTop -= 18
    if (event.clientY > bounds.bottom - 36) list.scrollTop += 18
  }
}

function finishSectionDrag() {
  draggedSection.value = ''
  sectionOrderChangedByDrag.value = false
}

function canMoveSection(section, direction) {
  if (isSavingSectionOrder.value) return false
  const visible = isEducationChildSection(section) ? reorderableEducationChildren.value : reorderableTopSections.value
  const index = visible.indexOf(section)
  return index >= 0 && index + direction >= 0 && index + direction < visible.length
}

function resetSectionOrder() {
  if (isSavingSectionOrder.value) return
  const defaultOrder = normalizeLayoutConfig(DEFAULT_LAYOUT_CONFIG).global.sectionOrder
  const currentOrder = localSectionOrder.value
  localSectionOrder.value = [
    ...defaultOrder.filter(section => currentOrder.includes(section)),
    ...currentOrder.filter(section => !defaultOrder.includes(section))
  ]
}

// ========== 样式控制变量 ==========
const DEFAULT_STYLE = {
  marginVertical: DEFAULT_LAYOUT_CONFIG.global.marginVertical,
  marginHorizontal: DEFAULT_LAYOUT_CONFIG.global.marginHorizontal,
  moduleMargin: DEFAULT_LAYOUT_CONFIG.global.moduleMargin,
  lineHeight: DEFAULT_LAYOUT_CONFIG.global.lineHeight,
  fontSize: DEFAULT_LAYOUT_CONFIG.global.fontSize
}
const marginVertical = ref(DEFAULT_STYLE.marginVertical)
const marginHorizontal = ref(DEFAULT_STYLE.marginHorizontal)
const moduleMargin = ref(DEFAULT_STYLE.moduleMargin)
const lineHeight = ref(DEFAULT_STYLE.lineHeight)
const fontSize = ref(DEFAULT_STYLE.fontSize)
const fontSizes = ref({ ...DEFAULT_LAYOUT_CONFIG.typography.fontSizes })
const fontSizeDraft = ref({ ...DEFAULT_LAYOUT_CONFIG.typography.fontSizes })
const showFontSizeDialog = ref(false)
const isSavingFontSizes = ref(false)
const fontSizeSaveError = ref('')
const overflowBeyondPageLimit = ref(false)
const pageBreakBefore = ref('')
const spacingSnapshot = ref(null)

function layoutStorageKey() {
  return props.taskId ? `resume-layout:${props.taskId}` : ''
}

function loadLayoutSettings() {
  const global = layout.value.global
  marginVertical.value = Number(global.marginVertical ?? DEFAULT_STYLE.marginVertical)
  marginHorizontal.value = Number(global.marginHorizontal ?? DEFAULT_STYLE.marginHorizontal)
  moduleMargin.value = Number(global.moduleMargin ?? DEFAULT_STYLE.moduleMargin)
  lineHeight.value = Number(global.lineHeight ?? DEFAULT_STYLE.lineHeight)
  fontSize.value = Number(global.fontSize ?? DEFAULT_STYLE.fontSize)
  fontSizes.value = { ...layout.value.typography.fontSizes }
}

async function migrateLegacyLayoutSettings() {
  const key = layoutStorageKey()
  if (!key) return
  const raw = localStorage.getItem(key)
  if (!raw) return
  try {
    const legacy = JSON.parse(raw)
    const serverGlobal = layout.value.global
    const isServerDefault = ['marginVertical', 'marginHorizontal', 'moduleMargin', 'lineHeight', 'fontSize']
      .every(field => Number(serverGlobal[field]) === Number(DEFAULT_STYLE[field]))
    if (isServerDefault) {
      const candidate = normalizeLayoutConfig(layout.value)
      for (const field of ['marginVertical', 'marginHorizontal', 'moduleMargin', 'lineHeight', 'fontSize']) {
        if (Number.isFinite(Number(legacy[field]))) candidate.global[field] = Number(legacy[field])
      }
      const response = await fetch(`/tasks/${props.taskId}/layout`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...buildAuthorizationHeaders() },
        body: JSON.stringify({ layout_config: candidate })
      })
      if (response.ok) {
        marginVertical.value = candidate.global.marginVertical
        marginHorizontal.value = candidate.global.marginHorizontal
        moduleMargin.value = candidate.global.moduleMargin
        lineHeight.value = candidate.global.lineHeight
        fontSize.value = candidate.global.fontSize
      }
    }
    localStorage.removeItem(key)
  } catch (error) {
    console.warn('迁移旧排版设置失败:', error)
  }
}

let layoutSaveTimer = null
let syncingLayoutProps = false
function saveLayoutSettings() {
  if (!props.taskId || syncingLayoutProps || activeToolbarMenu.value === 'layout') return
  clearTimeout(layoutSaveTimer)
  layoutSaveTimer = setTimeout(async () => {
    const candidate = normalizeLayoutConfig(layout.value)
    Object.assign(candidate.global, {
      marginVertical: marginVertical.value,
      marginHorizontal: marginHorizontal.value,
      moduleMargin: moduleMargin.value,
      lineHeight: lineHeight.value,
      fontSize: fontSize.value
    })
    candidate.typography.fontSizes = { ...fontSizes.value, body: fontSize.value }
    try {
      await fetch(`/tasks/${props.taskId}/layout`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...buildAuthorizationHeaders() },
        body: JSON.stringify({ layout_config: candidate })
      })
    } catch (error) {
      console.error('保存排版设置失败:', error)
    }
  }, 350)
}

const fontSizeRoles = ['name', 'meta', 'sectionTitle', 'entryTitle', 'label', 'body']
const openFontSizeRole = ref('')
const activeFontSizes = computed(() => showFontSizeDialog.value ? fontSizeDraft.value : fontSizes.value)
const fontSizeOptions = role => {
  const [minimum, maximum] = FONT_SIZE_LIMITS[role]
  const values = []
  for (let value = minimum; value <= maximum + 0.001; value += 0.5) values.push(value)
  return values
}

function contentBlockLabel(block, placement) {
  const flow = resolveContentBlockFlow(block)
  return flow.labelPlacement === placement ? flow.label : ''
}

function contentBlockLabelBold(block, placement) {
  const flow = resolveContentBlockFlow(block)
  return flow.labelPlacement === placement && flow.labelBold
}

function contentBlockClasses(block) {
  const flow = resolveContentBlockFlow(block)
  return [`block-${flow.type}`, { 'has-semantic-label': flow.labelMarker === 'bullet' }]
}

function openFontSizeDialog() {
  if (isSavingSectionOrder.value || isSavingSectionSettings.value) return
  closeSectionOrderDialog()
  closeSectionSettingsDialog()
  fontSizeDraft.value = { ...fontSizes.value }
  fontSizeSaveError.value = ''
  closeToolbarMenu()
  showFontSizeDialog.value = true
  openFontSizeRole.value = ''
}

function closeFontSizeDialog() {
  if (isSavingFontSizes.value) return
  fontSizeDraft.value = { ...fontSizes.value }
  showFontSizeDialog.value = false
  fontSizeSaveError.value = ''
  openFontSizeRole.value = ''
}

function toggleFontSizeRole(role) {
  openFontSizeRole.value = openFontSizeRole.value === role ? '' : role
}

function selectFontSize(role, size) {
  fontSizeDraft.value[role] = size
  openFontSizeRole.value = ''
}

function resetFontSizeDraft() {
  fontSizeDraft.value = { ...DEFAULT_LAYOUT_CONFIG.typography.fontSizes }
}

async function applyFontSizeSettings() {
  if (!props.taskId || isSavingFontSizes.value) return
  isSavingFontSizes.value = true
  fontSizeSaveError.value = ''
  const candidate = normalizeLayoutConfig(layout.value)
  candidate.typography.fontSizes = { ...fontSizeDraft.value }
  candidate.global.fontSize = Number(fontSizeDraft.value.body)
  try {
    const response = await fetch(`/tasks/${props.taskId}/layout`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...buildAuthorizationHeaders() },
      body: JSON.stringify({ layout_config: candidate })
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || '保存字号设置失败')
    const saved = normalizeLayoutConfig(payload.layout_config || candidate)
    fontSizes.value = { ...saved.typography.fontSizes }
    fontSize.value = saved.global.fontSize
    emit('layout-updated', saved)
    showFontSizeDialog.value = false
  } catch (error) {
    fontSizeSaveError.value = error.message || '保存字号设置失败'
  } finally {
    isSavingFontSizes.value = false
  }
}

function resetSpacingDraft() {
  marginVertical.value = DEFAULT_STYLE.marginVertical
  marginHorizontal.value = DEFAULT_STYLE.marginHorizontal
  moduleMargin.value = DEFAULT_STYLE.moduleMargin
  lineHeight.value = DEFAULT_STYLE.lineHeight
}

function confirmSpacingSettings() {
  spacingSnapshot.value = null
  activeToolbarMenu.value = null
  saveLayoutSettings()
}

const activeToolbarMenu = ref(null)
function toggleToolbarMenu(menu, event) {
  event?.stopPropagation()
  if (activeToolbarMenu.value === menu) {
    closeToolbarMenu()
    return
  }
  closeToolbarMenu()
  if (menu === 'layout') {
    spacingSnapshot.value = {
      marginVertical: marginVertical.value,
      marginHorizontal: marginHorizontal.value,
      moduleMargin: moduleMargin.value,
      lineHeight: lineHeight.value
    }
  }
  activeToolbarMenu.value = menu
}

function closeToolbarMenu() {
  if (activeToolbarMenu.value === 'layout' && spacingSnapshot.value) {
    marginVertical.value = spacingSnapshot.value.marginVertical
    marginHorizontal.value = spacingSnapshot.value.marginHorizontal
    moduleMargin.value = spacingSnapshot.value.moduleMargin
    lineHeight.value = spacingSnapshot.value.lineHeight
  }
  spacingSnapshot.value = null
  activeToolbarMenu.value = null
}

function toggleLanguage() {
  if (props.translationBusy) return
  emit('toggle-lang', props.lang === 'zh' ? 'en' : 'zh')
}

function openEditTarget(target) {
  closeToolbarMenu()
  if (target === 'resume') emit('open-resume-edit')
  else if (target === 'import') emit('open-resume-import')
  else emit('open-jd-dialog')
}

function handleToolbarOutsideClick(event) {
  if (!event.target.closest('.compact-toolbar-group')) {
    closeToolbarMenu()
  }
}

// A4尺寸（像素，96dpi）
const CSS_PX_PER_INCH = 96
const MM_PER_INCH = 25.4
const MM_TO_PX = CSS_PX_PER_INCH / MM_PER_INCH
const PAGE_WIDTH = 210 * MM_TO_PX
const PAGE_HEIGHT = 297 * MM_TO_PX

// 计算边距的像素值
const marginTopPx = computed(() => marginVertical.value * MM_TO_PX)
const marginBottomPx = computed(() => marginVertical.value * MM_TO_PX)
const marginLeftPx = computed(() => marginHorizontal.value * MM_TO_PX)
const marginRightPx = computed(() => marginHorizontal.value * MM_TO_PX)

// 预览、PDF 和 DOCX 都从同一排版协议解析物理尺寸；这里不再单独
// 使用 rem 推导模块/段落间距。
const renderLayout = computed(() => {
  const value = normalizeLayoutConfig(layout.value)
  value.typography.fontSizes = { ...activeFontSizes.value }
  value.global.fontSize = Number(activeFontSizes.value.body)
  return value
})
const layoutTokens = computed(() => resolveLayoutTokens(renderLayout.value, {
  fontSize: Number(activeFontSizes.value.body),
  lineHeight: lineHeight.value,
  moduleMargin: moduleMargin.value,
  marginTop: marginVertical.value,
  marginBottom: marginVertical.value,
  marginLeft: marginHorizontal.value,
  marginRight: marginHorizontal.value
}))
const educationColumnWidths = computed(() => {
  const items = props.data?.education || []
  return resolveEducationColumnWidths(layoutTokens.value, {
    schools: items.map(item => String(item?.school_name || '')),
    dates: items.map(item => (item?.date_range || []).slice(0, 2).filter(Boolean).join(' - ')),
    degreeMajors: items.map(item => [item?.degree, item?.major].filter(Boolean).join(' · ')),
    compactMetrics: items.map(compactAcademicMetric)
  })
})
const photoAspectRatio = ref(21 / 26)
let photoAspectRequest = 0
function refreshPhotoAspectRatio() {
  const explicit = Number(props.data?.basics?.photo_aspect_ratio)
  if (Number.isFinite(explicit) && explicit >= 0.2 && explicit <= 3) {
    photoAspectRatio.value = explicit
    return
  }
  const source = props.data?.basics?.photo
  if (!source || typeof Image === 'undefined') {
    photoAspectRatio.value = 21 / 26
    return
  }
  const request = ++photoAspectRequest
  const image = new Image()
  image.onload = () => {
    if (request !== photoAspectRequest || !image.naturalWidth || !image.naturalHeight) return
    photoAspectRatio.value = Math.min(3, Math.max(0.2, image.naturalWidth / image.naturalHeight))
  }
  image.onerror = () => {
    if (request === photoAspectRequest) photoAspectRatio.value = 21 / 26
  }
  image.src = source
}
const photoRenderHeightMm = computed(() => resolvePhotoHeightMm(props.data || {}, renderLayout.value, layoutTokens.value))
const pageStyles = computed(() => ({
  fontFamily: layoutTokens.value.fontFamilyCss,
  fontSize: `${layoutTokens.value.fontSizePt}pt`,
  fontWeight: layoutTokens.value.bodyFontWeight,
  letterSpacing: `${layoutTokens.value.letterSpacingPt}pt`,
  fontKerning: 'none',
  fontVariantLigatures: 'none',
  fontSynthesis: 'none',
  lineHeight: layoutTokens.value.lineHeight,
  '--body-font-size': `${layoutTokens.value.bodyFontSizePt}pt`,
  '--meta-font-size': `${layoutTokens.value.metaFontSizePt}pt`,
  '--entry-title-font-size': `${layoutTokens.value.entryTitleFontSizePt}pt`,
  '--section-title-font-size': `${layoutTokens.value.sectionTitleFontSizePt}pt`,
  '--name-font-size': `${layoutTokens.value.nameFontSizePt}pt`,
  '--label-font-size': `${layoutTokens.value.labelFontSizePt}pt`,
  '--body-font-weight': layoutTokens.value.bodyFontWeight,
  '--meta-font-weight': layoutTokens.value.metaFontWeight,
  '--entry-title-font-weight': layoutTokens.value.entryTitleFontWeight,
  '--manual-title-font-weight': Number(props.data?.formatting_version || 0) >= 1 ? 400 : layoutTokens.value.entryTitleFontWeight,
  '--manual-name-font-weight': Number(props.data?.formatting_version || 0) >= 1 ? 400 : layoutTokens.value.nameFontWeight,
  '--section-title-font-weight': Number(props.data?.formatting_version || 0) >= 2 ? 400 : layoutTokens.value.sectionTitleFontWeight,
  '--name-font-weight': Number(props.data?.formatting_version || 0) >= 1 ? 400 : layoutTokens.value.nameFontWeight,
  '--label-font-weight': layoutTokens.value.labelFontWeight,
  '--manual-field-font-weight': Number(props.data?.formatting_version || 0) < 3 ? layoutTokens.value.labelFontWeight : layoutTokens.value.bodyFontWeight,
  '--line-height': layoutTokens.value.lineHeight,
  '--module-margin': `${layoutTokens.value.moduleSpacingPt}pt`,
  '--header-name-after': `${layoutTokens.value.headerNameAfterPt}pt`,
  '--section-title-after': `${layoutTokens.value.sectionTitleAfterPt}pt`,
  '--section-title-border-gap': `${layoutTokens.value.sectionTitleBorderGapPt}pt`,
  '--item-spacing': `${layoutTokens.value.itemSpacingPt}pt`,
  '--paragraph-spacing': `${layoutTokens.value.paragraphSpacingPt}pt`,
  '--content-block-spacing': `${layoutTokens.value.contentBlockSpacingPt}pt`,
  '--content-label-spacing': `${layoutTokens.value.contentLabelSpacingPt}pt`,
  '--numbered-item-spacing': `${layoutTokens.value.numberedItemSpacingPt}pt`,
  '--list-text-indent': `${layoutTokens.value.listTextIndentPt}pt`,
  '--module-indent': '0pt',
  '--list-marker-gap': `${layoutTokens.value.listMarkerGapPt}pt`,
  '--education-side-column': `${layoutTokens.value.educationSideColumnMm}mm`,
  '--education-compact-side-column': `${educationColumnWidths.value.sideMm}mm`,
  '--education-middle-column': `${educationColumnWidths.value.middleMm}mm`,
  '--photo-width': `${photoRenderHeightMm.value * photoAspectRatio.value}mm`,
  '--photo-height': `${photoRenderHeightMm.value}mm`
}))

const pagePaddingStyle = computed(() => ({
  paddingTop: `${marginTopPx.value}px`,
  paddingBottom: `${marginBottomPx.value}px`,
  paddingLeft: `${marginLeftPx.value}px`,
  paddingRight: `${marginRightPx.value}px`
}))

// ========== 分页相关 ==========
const pageCount = ref(1)
const scale = ref(1)
const fitWidthScale = ref(1)
const zoomMode = ref('width') // width | page | manual
const manualZoom = ref(1)
const observer = ref(null)
const containerRef = ref(null)
const contentRef = ref(null)
const pageRanges = ref([])
const overflowStartIndex = ref(null)
const preferredSourcePages = computed(() => Number(props.sourcePageCount || 1) >= 2 ? 2 : 1)

function buildSemanticUnits(elementHeights, capacity) {
  const items = allItems.value
  const groups = []
  for (let index = 0; index < items.length;) {
    const groupId = items[index].groupId
    let end = index + 1
    while (end < items.length && items[end].groupId === groupId) end++
    const height = elementHeights.slice(index, end).reduce((sum, item) => sum + item.height, 0)
    groups.push({ start: index, end, height, breakKey: items[index].breakKey || '' })
    index = end
  }

  return groups.flatMap(group => {
    if (group.height <= capacity || group.end - group.start <= 1) return [group]
    const firstItem = items[group.start]
    const keepCount = firstItem?.isSectionTitle ? Math.min(2, group.end - group.start) : 1
    const units = []
    const keptEnd = group.start + keepCount
    units.push({
      start: group.start,
      end: keptEnd,
      height: elementHeights.slice(group.start, keptEnd).reduce((sum, item) => sum + item.height, 0),
      breakKey: group.breakKey
    })
    for (let index = keptEnd; index < group.end; index++) {
      units.push({
        start: index,
        end: index + 1,
        height: elementHeights[index].height,
        breakKey: group.breakKey
      })
    }
    return units
  })
}

function paginateSemanticUnits(units, capacity) {
  if (!units.length) return []
  const ranges = []
  let start = units[0].start
  let end = start
  let height = 0
  for (const unit of units) {
    if (height > 0 && height + unit.height > capacity) {
      ranges.push({ start, end })
      start = unit.start
      height = 0
    }
    end = unit.end
    height += unit.height
  }
  ranges.push({ start, end })
  return ranges
}

function balanceOriginalTwoPageResume(units, ranges) {
  if (preferredSourcePages.value !== 2 || ranges.length !== 1 || units.length < 2) return ranges
  const totalHeight = units.reduce((sum, unit) => sum + unit.height, 0)
  let runningHeight = 0
  let bestIndex = 1
  let bestDistance = Number.POSITIVE_INFINITY
  for (let index = 1; index < units.length; index++) {
    runningHeight += units[index - 1].height
    const distance = Math.abs(totalHeight / 2 - runningHeight)
    if (distance < bestDistance) {
      bestDistance = distance
      bestIndex = index
    }
  }
  return [
    { start: units[0].start, end: units[bestIndex - 1].end },
    { start: units[bestIndex].start, end: units[units.length - 1].end }
  ]
}

function applyAutomaticPagination(elementHeights, capacity) {
  const units = buildSemanticUnits(elementHeights, capacity)
  const naturalRanges = paginateSemanticUnits(units, capacity)
  const ranges = balanceOriginalTwoPageResume(units, naturalRanges)
  overflowBeyondPageLimit.value = ranges.length > 2
  overflowStartIndex.value = ranges.length > 2 ? ranges[2].start : null
  const visibleRanges = ranges.slice(0, 2)
  pageRanges.value = visibleRanges
  pageCount.value = Math.max(1, visibleRanges.length)
  const secondPageItem = visibleRanges.length > 1 ? allItems.value[visibleRanges[1].start] : null
  pageBreakBefore.value = secondPageItem?.breakKey || ''
}

const isInternship = item => /实习|intern/i.test(String(item?.job_type || ''))
const workEntries = section => (props.data?.work_experience || [])
  .map((item, dataIndex) => ({ item, dataIndex }))
  .filter(({ item }) => {
    if (!layout.value.global.splitWorkExperience) return section === 'work_experience'
    return section === 'internship_experience' ? isInternship(item) : !isInternship(item)
  })

// 扁平化的所有可分页项目，顺序由 layout_config 控制。
const allItems = computed(() => {
  if (!props.data) return []
  const items = []
  const push = item => items.push({ ...item, index: items.length, visible: true })
  if (props.data.basics) push({ type: 'basics', groupId: 'basics', breakKey: '' })

  for (const section of layout.value.global.sectionOrder) {
    if (hiddenSection(section)) continue
    if (section === 'education' && props.data.education?.length) {
      push({ type: 'education-title', groupId: 'education:0', breakKey: 'education:0', isSectionTitle: true })
      props.data.education.forEach((edu, i) => {
        push({ type: 'education-item', dataIndex: i, groupId: `education:${i}`, breakKey: `education:${i}` })
        if (moduleLayout('education').thesisDisplay !== 'hidden' && !moduleLayout('education').hiddenComponents?.includes('theses')) {
          ;(edu.theses || []).forEach((_, tIdx) => push({ type: 'thesis-item', dataIndex: `${i}-${tIdx}`, groupId: `education:${i}`, breakKey: `education:${i}` }))
        }
      })
      educationSupplementValues.value.forEach((_, i) => {
        push({ type: 'education-supplement-item', dataIndex: i, groupId: 'education-supplement', breakKey: 'education-supplement' })
      })
    }
    if (section === 'skills' && props.data.others?.skills?.length) {
      push({ type: 'skills-title', groupId: 'skills', breakKey: 'skills', isSectionTitle: true })
      props.data.others.skills.forEach((_, i) => push({ type: 'skills-item', dataIndex: i, groupId: 'skills', breakKey: 'skills' }))
    }
    if (section === 'research_interests' && !sectionMergedIntoEducation(section) && props.data.research_interests?.length) {
      push({ type: 'research-title', groupId: 'research_interests', breakKey: 'research_interests', isSectionTitle: true })
      props.data.research_interests.forEach((_, i) => push({ type: 'research-item', dataIndex: i, groupId: 'research_interests', breakKey: 'research_interests' }))
    }
    if (section === 'honors' && !sectionMergedIntoEducation(section) && props.data.honors?.length) {
      push({ type: 'honors-title', groupId: 'honors', breakKey: 'honors', isSectionTitle: true })
      props.data.honors.forEach((_, i) => push({ type: 'honors-item', dataIndex: i, groupId: 'honors', breakKey: 'honors' }))
    }
    if (section === 'publications' && !sectionMergedIntoEducation(section) && props.data.publications?.length) {
      push({ type: 'publications-title', groupId: 'publications', breakKey: 'publications', isSectionTitle: true })
      props.data.publications.forEach((_, i) => push({ type: 'publications-item', dataIndex: i, groupId: 'publications', breakKey: 'publications' }))
    }
    if ((section === 'work_experience' || section === 'internship_experience')) {
      const entries = workEntries(section)
      if (entries.length) {
        const prefix = section === 'internship_experience' ? 'internship' : 'work'
        push({ type: `${prefix}-title`, groupId: `${section}:${entries[0].dataIndex}`, breakKey: `${section}:${entries[0].dataIndex}`, isSectionTitle: true })
        entries.forEach(({ item, dataIndex }) => {
          push({ type: `${prefix}-item`, dataIndex, groupId: `${section}:${dataIndex}`, breakKey: `${section}:${dataIndex}` })
          if (projectContentBlocks(item, 'work').length) push({ type: `${prefix}-details`, dataIndex, groupId: `${section}:${dataIndex}`, breakKey: `${section}:${dataIndex}` })
        })
      }
    }
    if (section === 'project_experience') {
      const projects = props.data.project_experience || props.data.projects || []
      if (projects.length) {
        push({ type: 'projects-title', groupId: 'project_experience:0', breakKey: 'project_experience:0', isSectionTitle: true })
        projects.forEach((proj, i) => {
          push({ type: 'project-item', dataIndex: i, groupId: `project_experience:${i}`, breakKey: `project_experience:${i}` })
          if (projectContentBlocks(proj).length) push({ type: 'project-details', dataIndex: i, groupId: `project_experience:${i}`, breakKey: `project_experience:${i}` })
        })
      }
    }
    if (section === 'custom_sections' && props.data.custom_sections?.length) {
      props.data.custom_sections.forEach((custom, sectionIndex) => {
        if (!custom?.title || !custom?.items?.length) return
        push({ type: 'custom-title', dataIndex: sectionIndex, groupId: `custom_sections:${sectionIndex}`, breakKey: `custom_sections:${sectionIndex}`, isSectionTitle: true })
        custom.items.forEach((_, itemIndex) => push({ type: 'custom-item', dataIndex: `${sectionIndex}-${itemIndex}`, groupId: `custom_sections:${sectionIndex}`, breakKey: `custom_sections:${sectionIndex}` }))
      })
    }
    if (section === 'others' && !sectionMergedIntoEducation(section) && props.data.others) {
      const visibleFields = visibleOtherFields.value
      if (visibleFields.length) {
        push({ type: 'others-title', groupId: 'others', breakKey: 'others', isSectionTitle: true })
        push({ type: 'others-content', groupId: 'others', breakKey: 'others' })
      }
    }
    if (section === 'self_evaluation' && props.data.self_evaluation?.length) {
      push({ type: 'self-eval-title', groupId: 'self_evaluation', breakKey: 'self_evaluation', isSectionTitle: true })
      const values = moduleLayout('self_evaluation').preset === 'compact' ? [props.data.self_evaluation.join(' ')] : props.data.self_evaluation
      values.forEach((_, i) => push({ type: 'self-eval-item', dataIndex: i, groupId: 'self_evaluation', breakKey: 'self_evaluation' }))
    }
  }
  return items
})

const overflowItemLabel = computed(() => {
  const item = overflowStartIndex.value == null ? null : allItems.value[overflowStartIndex.value]
  if (!item) return '后续内容'
  const labelsByType = {
    'education-title': '教育经历', 'education-item': '教育经历', 'thesis-item': '论文',
    'education-supplement-item': '教育经历补充',
    'skills-title': '专业技能', 'skills-item': '专业技能',
    'research-title': '研究方向', 'research-item': '研究方向',
    'honors-title': '主要荣誉', 'honors-item': '主要荣誉', 'others-content': '证书与语言',
    'work-title': '工作经历', 'work-item': '工作经历', 'work-details': '工作经历详情',
    'projects-title': '项目经历', 'project-item': '项目经历', 'project-details': '项目经历详情',
    'custom-title': '其他原始栏目', 'custom-item': '其他原始栏目',
    'others-title': '其他信息', 'skill-line': '技能', 'cert-line': '证书', 'lang-line': '语言',
    'self-eval-title': '自我评价', 'self-eval-item': '自我评价'
  }
  const suffix = Number.isInteger(item.dataIndex) ? `第 ${item.dataIndex + 1} 项` : ''
  return `${labelsByType[item.type] || '后续内容'}${suffix}`
})

// 页面容器样式
const pageStyle = computed(() => ({
  width: `${PAGE_WIDTH}px`,
  height: `${PAGE_HEIGHT}px`
}))

// 预览区域容器样式
const pagesContainerStyle = computed(() => ({
  transform: `scale(${scale.value})`,
  transformOrigin: 'top left',
  width: `${PAGE_WIDTH}px`,
  position: 'absolute',
  top: '0',
  left: '0'
}))

const pagesViewportStyle = computed(() => {
  const unscaledHeight = pageCount.value * PAGE_HEIGHT + Math.max(0, pageCount.value - 1) * 20
  return {
    width: `${PAGE_WIDTH * scale.value}px`,
    height: `${unscaledHeight * scale.value}px`
  }
})

const zoomPercentage = computed(() => {
  if (!fitWidthScale.value) return 100
  return Math.round((scale.value / fitWidthScale.value) * 100)
})

// ========== 精细分页算法 ==========
const calculatePagination = async () => {
  // 等待字体完全加载（带超时）
  try {
    const fontsPromise = document.fonts.ready
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error('fonts timeout')), 500)
    )
    await Promise.race([fontsPromise, timeoutPromise])
  } catch (e) {
    await new Promise(resolve => setTimeout(resolve, 100))
  }

  await nextTick()
  await nextTick()

  if (!props.data || !contentRef.value) {
    pageRanges.value = []
    pageCount.value = 1
    return
  }

  const container = contentRef.value
  const topMargin = marginTopPx.value
  const bottomMargin = marginBottomPx.value
  const pageContentHeight = PAGE_HEIGHT - topMargin - bottomMargin

  // 只获取直接子元素中的 pageable-item
  const children = Array.from(container.children)
    .map((element, domIndex) => ({ element, domIndex }))
    .filter(({ element }) => element.classList.contains('pageable-item'))
    .sort((left, right) => {
      const leftOrder = Number.parseInt(getComputedStyle(left.element).order || '0', 10)
      const rightOrder = Number.parseInt(getComputedStyle(right.element).order || '0', 10)
      return leftOrder - rightOrder || left.domIndex - right.domIndex
    })
    .map(({ element }) => element)

  if (children.length === 0) {
    pageCount.value = 1
    return
  }

  // 使用完整外部高度参与分页。offsetHeight 不包含 margin，会漏算模块
  // 标题段前距、段后距和条目间距，导致实际两页被误判为一页。
  const elementHeights = children.map((child, idx) => {
    const computed = getComputedStyle(child)
    const marginTop = Number.parseFloat(computed.marginTop) || 0
    const marginBottom = Number.parseFloat(computed.marginBottom) || 0
    return {
      idx,
      height: child.getBoundingClientRect().height + marginTop + marginBottom
    }
  })

  // 仅保留极小的像素级安全余量。旧的 120px 固定预留会把后端可正常
  // 导出为一页的简历错误地拆成两页，造成预览与 PDF 不一致。
  applyAutomaticPagination(elementHeights, pageContentHeight - 8)

  // 验证：测量实际渲染的页面高度，如果溢出则调整
  await nextTick()
  await nextTick()

  const verifyAndFixPagination = async () => {
    const pageContents = document.querySelectorAll('.page-content')
    if (pageContents.length === 0) return

    const adjusted = Array.from(pageContents).some(el => el.scrollHeight > pageContentHeight + 1)
    if (adjusted) applyAutomaticPagination(elementHeights, pageContentHeight - 12)
  }

  // 延迟验证，确保DOM已完全渲染
  setTimeout(verifyAndFixPagination, 200)
}

// ========== 监听变化 ==========
watch([() => props.data, () => props.sourcePageCount, renderLayout, marginVertical, marginHorizontal, moduleMargin, lineHeight, fontSize, fontSizes, fontSizeDraft, showFontSizeDialog],
  () => {
    // 增加延迟时间，确保字体变化后浏览器有足够时间重新渲染
    if (window.requestAnimationFrame) {
      window.requestAnimationFrame(() => {
        setTimeout(calculatePagination, 300)  // 增加延迟
      })
    } else {
      setTimeout(calculatePagination, 300)
    }
  }, { deep: true })

watch([marginVertical, marginHorizontal, moduleMargin, lineHeight, fontSize], saveLayoutSettings)
watch(() => props.layoutConfig, () => {
  syncingLayoutProps = true
  localSectionOrder.value = [...normalizeLayoutConfig(props.layoutConfig).global.sectionOrder]
  loadLayoutSettings()
  nextTick(() => { syncingLayoutProps = false })
}, { deep: true, immediate: true })
watch(() => props.taskId, () => {
  closeSourceDocument()
  loadLayoutSettings()
  calculatePagination()
})
watch(() => props.hasSourceDocument, value => {
  if (!value) closeSourceDocument()
})
watch(() => [props.data?.basics?.photo, props.data?.basics?.photo_aspect_ratio], refreshPhotoAspectRatio, { immediate: true })

// ========== 高亮模块滚动 ==========
watch(() => props.highlightedModule, async (newModule) => {
  if (newModule && props.data) {
    await nextTick()
    // 延迟执行滚动，确保DOM已完全渲染
    setTimeout(() => {
      // 在可见的 pages-wrapper 中查找对应模块
      const pagesWrapper = document.querySelector('.pages-wrapper')
      if (pagesWrapper) {
        // 根据模块类型查找对应的section标题
        const sectionTitle = pagesWrapper.querySelector(`[data-module="${newModule}"]`)
        if (sectionTitle) {
          sectionTitle.scrollIntoView({ behavior: 'smooth', block: 'center' })
        } else {
          // 如果没找到，尝试在 preview-content 中查找
          const previewContent = document.querySelector('.preview-content')
          if (previewContent) {
            const element = previewContent.querySelector(`[data-module="${newModule}"]`)
            if (element) {
              element.scrollIntoView({ behavior: 'smooth', block: 'center' })
            }
          }
        }
      }
    }, 200)
  }
})

// 调试方法：在控制台调用 testHighlight('education') 测试高亮效果
window.testHighlight = (moduleName) => {
  const previewContent = document.querySelector('.preview-content')
  if (previewContent) {
    const element = previewContent.querySelector(`[data-module="${moduleName}"]`)
    if (element) {
      // 添加高亮类测试动画
      element.classList.add('title-highlight')
      // 测试滚动
      element.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }
}

// 测试动画的独立方法
window.testAnimation = (moduleName) => {
  const element = document.querySelector(`[data-module="${moduleName}"]`)
  if (element) {
    element.classList.add('title-highlight')
    setTimeout(() => {
      element.classList.remove('title-highlight')
    }, 3000)
  }
}

// ========== 缩放计算 ==========
const calculateScale = () => {
  const container = containerRef.value || document.querySelector('.preview-content')
  if (!container) return

  const availableWidth = container.clientWidth - 40
  const widthScale = Math.min(1, Math.max(0.3, availableWidth / PAGE_WIDTH))
  fitWidthScale.value = widthScale

  let newScale = widthScale
  if (zoomMode.value === 'page') {
    const availableHeight = container.clientHeight - 40
    newScale = Math.min(widthScale, Math.max(0.3, availableHeight / PAGE_HEIGHT))
  } else if (zoomMode.value === 'manual') {
    newScale = widthScale * manualZoom.value
  }

  if (Math.abs(newScale - scale.value) > 0.01) {
    scale.value = newScale
  }
}

const setZoomMode = (mode, event) => {
  zoomMode.value = mode
  if (mode === 'width') manualZoom.value = 1
  calculateScale()
  event?.currentTarget?.blur()
}

const adjustZoom = (delta, event) => {
  const currentRatio = fitWidthScale.value
    ? scale.value / fitWidthScale.value
    : manualZoom.value
  manualZoom.value = Math.min(1, Math.max(0.4, currentRatio + delta))
  zoomMode.value = 'manual'
  calculateScale()
  event?.currentTarget?.blur()
}

// ========== 工具栏控制 ==========
// ========== 格式化文本 ==========
const formatText = (text) => {
  if (typeof text !== 'string') return text
  return formatInlineHtml(text)
}

// ========== 导出PDF（调用后端API，使用WeasyPrint生成矢量PDF）============
const showSuccessDialog = ref(false)
const exportError = ref('')
const isExportingPDF = ref(false)
const isExportingDOCX = ref(false)
const lastExportFormat = ref('PDF')

const exportDocument = async (format) => {
  if (!props.data) return

  if (overflowBeyondPageLimit.value) {
    exportError.value = '当前内容超出两页，请精简内容或调整排版后再导出。'
    return
  }

  const isPDF = format === 'pdf'
  if (isPDF) isExportingPDF.value = true
  else isExportingDOCX.value = true
  try {
    // 构建样式参数
    const style = {
      marginTop: marginVertical.value,
      marginBottom: marginVertical.value,
      marginLeft: marginHorizontal.value,
      marginRight: marginHorizontal.value,
      moduleMargin: moduleMargin.value,
      lineHeight: lineHeight.value,
      fontSize: fontSize.value,
      pageMode: 'auto',
      sourcePageCount: Number(props.sourcePageCount || 1),
      pageBreakBefore: pageBreakBefore.value
    }

    // 调用后端API
    const response = await fetch(isPDF ? '/export_pdf' : '/export_docx', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...buildAuthorizationHeaders(),
        ...(props.taskId ? { 'X-Task-ID': props.taskId } : {})
      },
      body: JSON.stringify({
        resume_data: props.data,
        style: style,
        layout_config: renderLayout.value,
        lang: props.lang
      })
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => null)
      throw new Error(errorData?.detail || errorData || `${isPDF ? 'PDF' : 'Word'}生成失败`)
    }

    // 获取PDF二进制数据
    const documentBlob = await response.blob()

    // 创建下载链接
    const url = window.URL.createObjectURL(documentBlob)
    const a = document.createElement('a')
    a.href = url
    const rawName = plainInlineText(props.data.basics?.name || '').replace(/[\\/:*?"<>|\r\n]+/g, '_').trim()
    a.download = `resume_${rawName || '简历'}.${isPDF ? 'pdf' : 'docx'}`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)

    // 显示成功提示弹窗
    lastExportFormat.value = isPDF ? 'PDF' : 'Word'
    showSuccessDialog.value = true

  } catch (error) {
    console.error('简历导出错误:', error)
    exportError.value = error.message || '简历导出失败，请确认后端服务正常运行后重试。'
  } finally {
    if (isPDF) isExportingPDF.value = false
    else isExportingDOCX.value = false
  }
}

const exportPDF = () => exportDocument('pdf')
const exportWord = () => exportDocument('docx')

// ========== 生命周期 ==========
onMounted(async () => {
  loadLayoutSettings()
  await migrateLegacyLayoutSettings()
  await nextTick()
  setTimeout(async () => {
    await calculatePagination()
    calculateScale()
  }, 100)

  observer.value = new ResizeObserver(() => {
    clearTimeout(window.scaleTimeout)
    window.scaleTimeout = setTimeout(async () => {
      await calculatePagination()
      calculateScale()
    }, 100)
  })

  const container = document.querySelector('.preview-content')
  if (container) observer.value.observe(container)
  // 也监听隐藏内容的变化（字体变化会影响高度）
  if (contentRef.value) observer.value.observe(contentRef.value)
  observer.value.observe(document.body)
  window.addEventListener('resize', calculateScale)
  document.addEventListener('click', handleToolbarOutsideClick)
})

onUnmounted(() => {
  closeSourceDocument()
  observer.value?.disconnect()
  window.removeEventListener('resize', calculateScale)
  document.removeEventListener('click', handleToolbarOutsideClick)
  clearTimeout(window.scaleTimeout)
})

// ========== 分页工具函数 ==========
const isItemVisible = (item, pageIndex) => {
  if (!pageRanges.value.length) return true
  const range = pageRanges.value[pageIndex]
  return range && item.index >= range.start && item.index < range.end
}

const getItemIndex = (type, dataIndex) => {
  const items = allItems.value
  if (!items.length) return 0

  const singleTypes = ['basics', 'education-title', 'skills-title', 'research-title', 'honors-title', 'work-title', 'projects-title', 'others-title', 'self-eval-title']
  if (singleTypes.includes(type)) {
    const found = items.find(item => item.type === type)
    return found ? found.index : 0
  }

  // 处理 cert-line、lang-line 和 skill-line（无 dataIndex 的特殊类型）
  if (type === 'cert-line' || type === 'lang-line' || type === 'skill-line') {
    const found = items.find(item => item.type === type)
    return found ? found.index : items.length
  }

  // 处理带 dataIndex 的类型
  const found = items.find(item => {
    if (item.type !== type) return false
    return item.dataIndex === dataIndex
  })
  return found ? found.index : 0
}
</script>

<template>
  <div class="resume-wrapper">
    <!-- 工具栏 - 始终显示 -->
    <div class="resume-toolbar-wrapper">
      <div class="resume-toolbar">
        <!-- 所有窗口宽度共用同一套操作，窄屏只通过响应式布局调整位置。 -->
        <div class="shared-toolbar-actions">
          <div class="compact-toolbar-cluster">
          <div class="compact-toolbar-group">
            <button
              class="compact-toolbar-btn"
              :class="{ active: activeToolbarMenu === 'zoom' }"
              :aria-expanded="activeToolbarMenu === 'zoom'"
              aria-label="打开页面缩放"
              @click="toggleToolbarMenu('zoom', $event)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3m18 0v3a2 2 0 0 1-2 2h-3"/>
              </svg>
              <span>{{ zoomPercentage }}%</span>
            </button>
            <div v-if="activeToolbarMenu === 'zoom'" class="compact-popover zoom-popover" @click.stop>
              <div class="compact-popover-title">页面缩放</div>
              <div class="zoom-mode-grid">
                <button :class="{ active: zoomMode === 'width' }" @click="setZoomMode('width', $event)">适宽</button>
                <button :class="{ active: zoomMode === 'page' }" @click="setZoomMode('page', $event)">整页</button>
              </div>
              <div class="compact-zoom-stepper">
                <button @click="adjustZoom(-0.1, $event)" :disabled="zoomPercentage <= 40" aria-label="缩小">−</button>
                <button @click="manualZoom = 1; setZoomMode('manual', $event)" aria-label="恢复百分之百">{{ zoomPercentage }}%</button>
                <button @click="adjustZoom(0.1, $event)" :disabled="zoomPercentage >= 100" aria-label="放大">＋</button>
              </div>
            </div>
          </div>

          <div class="compact-toolbar-group edit-toolbar-group">
            <button
              class="compact-toolbar-btn"
              :class="{ active: activeToolbarMenu === 'edit' }"
              :aria-expanded="activeToolbarMenu === 'edit'"
              aria-label="打开内容编辑菜单"
              @click="toggleToolbarMenu('edit', $event)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <path d="M12 20h9"/>
                <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L8 18l-4 1 1-4Z"/>
              </svg>
              <span>编辑</span>
            </button>
            <div v-if="activeToolbarMenu === 'edit'" class="compact-popover edit-popover" @click.stop>
              <div class="compact-popover-title">编辑简历</div>
              <button class="compact-menu-item" @click="openEditTarget('resume')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/>
                  <path d="M14 2v6h6M8 13h8M8 17h5"/>
                </svg>
                <span><strong>编辑内容</strong><small>修改个人信息与经历</small></span>
              </button>
              <button class="compact-menu-item" @click="openEditTarget('import')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                  <path d="M12 3v12M7 8l5-5 5 5"/>
                  <path d="M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"/>
                </svg>
                <span><strong>重新导入简历</strong><small>解析草稿确认后替换当前内容</small></span>
              </button>
              <button class="compact-menu-item" @click="openEditTarget('jd')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                  <rect x="3" y="7" width="18" height="13" rx="2"/>
                  <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18"/>
                </svg>
                <span><strong>目标岗位 JD</strong><small>{{ jdData ? '查看或修改岗位信息' : '添加岗位信息' }}</small></span>
              </button>
            </div>
          </div>

          <div class="compact-toolbar-group">
            <button
              class="compact-toolbar-btn"
              :class="{ active: activeToolbarMenu === 'layout' }"
              :aria-expanded="activeToolbarMenu === 'layout'"
              aria-label="打开排版设置"
              @click="toggleToolbarMenu('layout', $event)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <rect x="4" y="3" width="16" height="18" rx="2"/>
                <path d="M8 7h8M8 11h8M8 15h5"/>
              </svg>
              <span>排版</span>
            </button>
            <div v-if="activeToolbarMenu === 'layout'" class="compact-popover layout-popover" @click.stop>
              <div class="compact-popover-title">排版设置</div>
              <section class="layout-settings-section layout-spacing-section">
                <div class="layout-settings-heading">间距</div>
                <div class="auto-page-hint">页数自动识别，最多两页</div>
                <label class="compact-control">
                  <span>上下页边距 <strong>{{ marginVertical }}mm</strong></span>
                  <input type="range" v-model.number="marginVertical" min="3" max="12" step="0.25" class="slider">
                </label>
                <label class="compact-control">
                  <span>左右页边距 <strong>{{ marginHorizontal }}mm</strong></span>
                  <input type="range" v-model.number="marginHorizontal" min="3" max="12" step="0.25" class="slider">
                </label>
                <label class="compact-control">
                  <span>模块间距 <strong>{{ moduleMargin }}rem</strong></span>
                  <input type="range" v-model.number="moduleMargin" min="0.1" max="1" step="0.1" class="slider">
                </label>
                <label class="compact-control">
                  <span>行间距 <strong>{{ lineHeight }}</strong></span>
                  <input type="range" v-model.number="lineHeight" min="1" max="1.8" step="0.05" class="slider">
                </label>
                <div class="layout-spacing-actions">
                  <button type="button" @click="resetSpacingDraft">恢复默认</button>
                  <button type="button" class="primary" @click="confirmSpacingSettings">确认</button>
                </div>
              </section>
              <button type="button" class="layout-guide-btn font-size-open-btn" aria-haspopup="dialog" :aria-label="`文字大小，当前正文字号 ${fontSizes.body}pt`" @click="openFontSizeDialog">文字大小</button>
              <button class="layout-guide-btn section-order-open-btn" @click="openSectionOrderDialog">模块顺序</button>
              <button class="layout-guide-btn section-settings-open-btn" @click="openSectionSettingsDialog">栏目设置</button>
            </div>
          </div>

          <button class="compact-toolbar-btn language-btn" :disabled="translationBusy" @click="toggleLanguage" :aria-label="translationBusy ? '正在翻译简历' : `切换为${lang === 'zh' ? '英文' : '中文'}简历`">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <circle cx="12" cy="12" r="9"/>
              <path d="M3 12h18M12 3c2.2 2.5 3.3 5.5 3.3 9S14.2 18.5 12 21c-2.2-2.5-3.3-5.5-3.3-9S9.8 5.5 12 3"/>
            </svg>
            <span>{{ translationBusy ? '翻译中…' : (lang === 'zh' ? '中 / EN' : 'EN / 中') }}</span>
          </button>

          <button
            v-if="hasSourceDocument"
            class="compact-toolbar-btn"
            :class="{ active: showSourceDocument }"
            :aria-label="showSourceDocument ? '返回当前简历' : '查看导入的原版简历'"
            @click="toggleSourceDocument"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <path d="M8 13h8M8 17h5"/>
            </svg>
            <span>{{ showSourceDocument ? '当前版' : '原版' }}</span>
          </button>
          </div>

          <button class="export-btn compact-export-btn" @click="exportPDF" :disabled="isExportingPDF || !data">
            <span v-if="isExportingPDF" class="spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M12 3v12M7 10l5 5 5-5"/>
              <path d="M5 21h14"/>
            </svg>
            <span>{{ isExportingPDF ? '导出中...' : '导出 PDF' }}</span>
          </button>
          <button class="export-btn compact-export-btn word-export-btn" @click="exportWord" :disabled="isExportingDOCX || !data">
            <span v-if="isExportingDOCX" class="spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M6 3h9l3 3v15H6z"/><path d="M15 3v4h4M9 11l2 6 2-4 2 4 2-6"/>
            </svg>
            <span>{{ isExportingDOCX ? '导出中...' : '导出 Word' }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 有简历数据时显示预览 -->
    <section v-if="showSourceDocument" class="source-document-viewer" aria-label="原版简历预览">
      <header class="source-document-header">
        <strong>{{ sourceDocumentName }}</strong>
        <span>只读原版，不会随当前简历修改</span>
      </header>
      <div v-if="sourceDocumentLoading" class="source-document-status">正在加载原版简历…</div>
      <div v-else-if="sourceDocumentError" class="source-document-status source-document-error">
        <p>{{ sourceDocumentError }}</p>
        <button type="button" @click="retrySourceDocument">重试</button>
      </div>
      <iframe v-else-if="sourceDocumentIsPdf && sourceDocumentUrl" class="source-document-frame" :src="sourceDocumentUrl" title="原版 PDF 简历"></iframe>
      <div v-else-if="sourceDocumentUrl" class="source-document-image-scroll">
        <img :src="sourceDocumentUrl" :alt="sourceDocumentName">
      </div>
    </section>

    <template v-else-if="data">
      <!-- 预览内容区域 -->
      <div class="preview-content" ref="containerRef">
      <!-- 隐藏的完整内容（用于测量） -->
      <div ref="contentRef" class="content-source" :style="[pageStyles, pagePaddingStyle]">
      <!-- 个人信息 -->
      <div v-if="data.basics" class="pageable-item personal-info" :class="[`basics-${moduleLayout('basics').preset}`, `contact-${moduleLayout('basics').contactLayout}`, { 'module-highlight': highlightedModule === 'basics', 'has-photo': data.basics.photo && !hiddenBasicField('photo') }]" data-module="basics">
        <div class="module-component-rows basics-component-rows">
          <div v-for="(row, rowIndex) in visibleComponentRows('basics')" :key="rowIndex" class="module-component-row" :style="componentRowStyle(row, 'basics')">
            <div v-for="(cell, cellIndex) in row.cells" :key="cellIndex" class="module-component-cell" :class="`flow-${cell.flow}`" :style="componentCellStyle(cell)">
              <template v-for="component in cell.components" :key="component">
                <img v-if="component === 'photo' && data.basics.photo && !hiddenBasicField('photo')" :src="data.basics.photo" class="profile-photo component-photo" alt="证件照">
                <span v-else-if="basicsComponentText(component)" class="module-component" :class="[`component-${component}`, { name: component === 'name' }]" v-html="formatText(basicsComponentText(component))"></span>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- {{ t.education }} -->
      <template v-if="data.education && data.education.length && !hiddenSection('education')">
        <h2 class="pageable-item section-title" :class="[`title-${moduleTitleStyle('education')}`, { 'title-highlight': highlightedModule === 'education' }]" :style="moduleOrder('education')" data-module="education" v-html="formatText(displayTitle('education', t.education))"></h2>
        <div v-for="(item, idx) in data.education" :key="idx" class="pageable-item education-item" :class="`preset-${moduleLayout('education').preset}`" :style="moduleOrder('education')">
          <div class="module-component-rows">
            <div v-for="(row, rowIndex) in visibleComponentRows('education', ['theses'])" :key="rowIndex" class="module-component-row" :style="componentRowStyle(row, 'education')">
              <div v-for="(cell, cellIndex) in row.cells" :key="cellIndex" class="module-component-cell" :class="`flow-${cell.flow}`" :style="componentCellStyle(cell)">
                <span v-for="component in cell.components" v-show="educationComponentText(item, component)" :key="component" class="module-component" :class="[`component-${component}`, { school: component === 'school', 'graduation-date': component === 'date' }]" v-html="formatText(educationComponentText(item, component))"></span>
              </div>
            </div>
          </div>
        </div>
        <template v-if="data.education">
          <template v-for="(item, idx) in data.education">
            <template v-if="item.theses?.length && moduleLayout('education').thesisDisplay !== 'hidden' && !moduleLayout('education').hiddenComponents?.includes('theses')">
                <div v-for="(thesis, tIdx) in item.theses" :key="'thesis-'+idx+'-'+tIdx" class="pageable-item thesis-item" :style="moduleOrder('education')">
                <h4 class="subfield-title">{{ t.thesis }}</h4>
                <div class="thesis-title" v-html="formatText(thesis.title)"></div>
                  <ul v-if="thesis.details?.length && moduleLayout('education').thesisDisplay === 'expanded'" class="list-items">
                  <li v-for="(detail, dIdx) in thesis.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
                </ul>
              </div>
            </template>
          </template>
        </template>
      </template>

      <template v-if="data.education?.length && educationSupplementValues.length">
        <div v-for="(item, idx) in educationSupplementValues" :key="`source-education-supplement-${idx}`" :class="['pageable-item', ...educationSupplementClasses(item)]" :data-marker="educationSupplementMarker(item, idx)" :style="moduleOrder('education')" v-html="formatText(moduleListContent(item))"></div>
      </template>

      <template v-if="data.others?.skills?.length && !hiddenSection('skills')">
        <h2 class="pageable-item section-title" :class="`title-${moduleTitleStyle('skills')}`" :style="moduleOrder('skills')" data-module="skills" v-html="formatText(displayTitle('skills', t.skillsSection))"></h2>
        <div v-for="(item, idx) in data.others.skills" :key="`source-skill-${idx}`" :class="['pageable-item', ...moduleListClasses('skills', item, 'skill-list-item')]" :data-marker="moduleListMarker('skills', item, idx)" :style="moduleOrder('skills')" v-html="formatText(moduleListContent(item))"></div>
      </template>

      <template v-if="data.research_interests?.length && !hiddenSection('research_interests') && !sectionMergedIntoEducation('research_interests')">
        <h2 class="pageable-item section-title" :class="`title-${moduleTitleStyle('research_interests')}`" :style="moduleOrder('research_interests')" data-module="research_interests" v-html="formatText(displayTitle('research_interests', t.researchInterests))"></h2>
        <div v-for="(item, idx) in data.research_interests" :key="`source-research-${idx}`" :class="['pageable-item', ...moduleListClasses('research_interests', item)]" :data-marker="moduleListMarker('research_interests', item, idx)" :style="moduleOrder('research_interests')" v-html="formatText(moduleListContent(item))"></div>
      </template>

      <template v-if="data.honors?.length && !hiddenSection('honors') && !sectionMergedIntoEducation('honors')">
        <h2 class="pageable-item section-title" :class="`title-${moduleTitleStyle('honors')}`" :style="moduleOrder('honors')" data-module="honors" v-html="formatText(displayTitle('honors', t.honors))"></h2>
        <div v-for="(item, idx) in data.honors" :key="`source-honor-${idx}`" :class="['pageable-item', ...moduleListClasses('honors', item)]" :data-marker="moduleListMarker('honors', item, idx)" :style="moduleOrder('honors')" v-html="formatText(moduleListContent(item))"></div>
      </template>

      <!-- {{ t.workExperience }} -->
      <template v-for="section in workSections" :key="`source-${section.id}`">
        <h2 class="pageable-item section-title" :class="[`title-${moduleTitleStyle(section.id)}`, { 'title-highlight': highlightedModule === 'work_experience' }]" :style="moduleOrder(section.id)" :data-module="section.id" v-html="formatText(section.title)"></h2>
        <template v-for="entry in section.entries" :key="`source-${section.id}-${entry.dataIndex}`">
          <div class="pageable-item work-item" :class="[`preset-${moduleLayout(section.id).preset}`, `date-${moduleLayout(section.id).datePosition}`]" :style="moduleOrder(section.id)">
            <div class="module-component-rows">
              <div v-for="(row, rowIndex) in visibleComponentRows(section.id, ['content'])" :key="rowIndex" class="module-component-row" :style="componentRowStyle(row, section.id)">
                <div v-for="(cell, cellIndex) in row.cells" :key="cellIndex" class="module-component-cell" :class="`flow-${cell.flow}`" :style="componentCellStyle(cell)">
                  <span v-for="component in cell.components" v-show="workComponentText(entry.item, component, section.id)" :key="component" class="module-component" :class="[`component-${component}`, { company: component === 'organization', 'work-period': component === 'date' }]" v-html="formatText(workComponentText(entry.item, component, section.id))"></span>
                </div>
              </div>
            </div>
          </div>
          <div v-if="projectContentBlocks(entry.item, 'work').length" class="pageable-item work-details" :class="`details-${moduleLayout(section.id).detailsStyle}`" :style="moduleOrder(section.id)">
            <div v-for="(block, bIdx) in projectContentBlocks(entry.item, 'work')" :key="bIdx" class="project-content-block" :class="contentBlockClasses(block)">
              <p v-if="block.type === 'paragraph'" class="project-paragraph"><span v-if="contentBlockLabel(block, 'inline')" class="project-inline-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'inline') }" v-html="`${formatText(contentBlockLabel(block, 'inline'))}：`"></span><span v-html="formatText(block.text)"></span></p>
              <template v-else>
                <div v-if="contentBlockLabel(block, 'separate')" class="project-block-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'separate') }" v-html="`${formatText(contentBlockLabel(block, 'separate'))}：`"></div>
                <ol v-if="block.type === 'numbered_list'" class="project-numbered-list">
                  <li v-for="(detail, dIdx) in block.items" :key="dIdx" :class="{ 'marker-bold': isFullyBoldText(detail) }" v-html="formatText(detail)"></li>
                </ol>
                <ul v-else class="list-items">
                  <li v-for="(detail, dIdx) in block.items" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
                </ul>
              </template>
            </div>
          </div>
        </template>
      </template>

      <!-- {{ t.projectExperience }} -->
      <template v-if="(data.project_experience || data.projects) && (data.project_experience || data.projects).length && !hiddenSection('project_experience')">
        <h2 class="pageable-item section-title" :class="[`title-${moduleTitleStyle('project_experience')}`, { 'title-highlight': highlightedModule === 'project_experience' }]" :style="moduleOrder('project_experience')" data-module="project_experience" v-html="formatText(displayTitle('project_experience', t.projectExperience))"></h2>
        <template v-for="(item, idx) in (data.project_experience || data.projects)" :key="'source-project-'+idx">
          <div class="pageable-item project-item" :class="[`preset-${moduleLayout('project_experience').preset}`, `date-${moduleLayout('project_experience').datePosition}`]" :style="moduleOrder('project_experience')">
            <div class="module-component-rows">
              <div v-for="(row, rowIndex) in visibleComponentRows('project_experience', ['content'])" :key="rowIndex" class="module-component-row" :style="componentRowStyle(row, 'project_experience')">
                <div v-for="(cell, cellIndex) in row.cells" :key="cellIndex" class="module-component-cell" :class="`flow-${cell.flow}`" :style="componentCellStyle(cell)">
                  <span v-for="component in cell.components" v-show="projectComponentText(item, component)" :key="component" class="module-component" :class="[`component-${component}`, { 'project-name': component === 'project_name', 'project-period': component === 'date' }]" v-html="formatText(projectComponentText(item, component))"></span>
                </div>
              </div>
            </div>
          </div>
          <div v-if="projectContentBlocks(item).length" class="pageable-item project-details" :style="moduleOrder('project_experience')">
            <div v-for="(block, blockIndex) in projectContentBlocks(item)" :key="blockIndex" class="project-content-block" :class="contentBlockClasses(block)">
              <p v-if="block.type === 'paragraph'" class="project-paragraph"><span v-if="contentBlockLabel(block, 'inline')" class="project-inline-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'inline') }" v-html="`${formatText(contentBlockLabel(block, 'inline'))}：`"></span><span v-html="formatText(block.text)"></span></p>
              <template v-else>
                <div v-if="contentBlockLabel(block, 'separate')" class="project-block-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'separate') }" v-html="`${formatText(contentBlockLabel(block, 'separate'))}：`"></div>
                <ol v-if="block.type === 'numbered_list'" class="project-numbered-list">
                  <li v-for="(detail, dIdx) in block.items" :key="dIdx" :class="{ 'marker-bold': isFullyBoldText(detail) }" v-html="formatText(detail)"></li>
                </ol>
                <ul v-else class="list-items">
                  <li v-for="(detail, dIdx) in block.items" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
                </ul>
              </template>
            </div>
          </div>
        </template>
      </template>

      <template v-if="data.custom_sections?.length && !hiddenSection('custom_sections')">
        <template v-for="(custom, sectionIndex) in data.custom_sections" :key="`source-custom-${sectionIndex}`">
          <h2 v-if="custom.title && custom.items?.length" class="pageable-item section-title" :class="`title-${moduleTitleStyle('custom_sections')}`" :style="moduleOrder('custom_sections')" data-module="custom_sections" v-html="formatText(custom.title)"></h2>
          <div v-for="(item, itemIndex) in (custom.items || [])" :key="`source-custom-${sectionIndex}-${itemIndex}`" :class="['pageable-item', ...moduleListClasses('custom_sections', item)]" :data-marker="moduleListMarker('custom_sections', item, itemIndex)" :style="moduleOrder('custom_sections')" v-html="formatText(moduleListContent(item))"></div>
        </template>
      </template>

      <!-- 其他 -->
      <template v-if="data.others && visibleOtherFields.length && !hiddenSection('others') && !sectionMergedIntoEducation('others')">
        <h2 class="pageable-item section-title" :class="[`title-${moduleTitleStyle('others')}`, { 'title-highlight': highlightedModule === 'others' }]" :style="moduleOrder('others')" data-module="others" v-html="formatText(displayTitle('others', props.lang === 'en' ? 'Certificates & Languages' : '证书与语言'))"></h2>
        <div class="pageable-item cert-lang-line" :class="`others-${moduleLayout('others').preset}`" :style="moduleOrder('others')">
          <div class="module-component-rows">
            <div v-for="(row, rowIndex) in visibleOtherComponentRows()" :key="rowIndex" class="module-component-row" :style="componentRowStyle(row, 'others')">
              <div v-for="(cell, cellIndex) in row.cells" :key="cellIndex" class="module-component-cell" :class="`flow-${cell.flow}`" :style="componentCellStyle(cell)">
                <span v-for="component in cell.components" :key="component" class="module-component" :class="`component-${component}`" v-html="formatText(othersComponentText(component))"></span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-if="data.publications?.length && !hiddenSection('publications') && !sectionMergedIntoEducation('publications')">
        <h2 class="pageable-item section-title" :class="`title-${moduleTitleStyle('publications')}`" :style="moduleOrder('publications')" data-module="publications" v-html="formatText(displayTitle('publications', lang === 'en' ? 'Publications' : '论文'))"></h2>
        <div v-for="(item, idx) in data.publications" :key="`source-publication-${idx}`" :class="['pageable-item', ...moduleListClasses('publications', item)]" :data-marker="moduleListMarker('publications', item, idx)" :style="moduleOrder('publications')" v-html="formatText(moduleListContent(item))"></div>
      </template>

      <!-- {{ t.selfEvaluation }} -->
      <template v-if="selfEvaluationValues.length && !hiddenSection('self_evaluation')">
        <h2 class="pageable-item section-title" :class="[`title-${moduleTitleStyle('self_evaluation')}`, { 'title-highlight': highlightedModule === 'self_evaluation' }]" :style="moduleOrder('self_evaluation')" data-module="self_evaluation" v-html="formatText(displayTitle('self_evaluation', t.selfEvaluation))"></h2>
        <!-- 每条{{ t.selfEvaluation }}独立分页 -->
        <template v-for="(item, idx) in selfEvaluationValues">
          <div v-if="item" :key="'self-eval-'+idx" class="pageable-item self-eval-item" :class="moduleListClasses('self_evaluation', item)" :data-marker="moduleListMarker('self_evaluation', item, idx)" :style="moduleOrder('self_evaluation')">
            <span v-html="formatText(moduleListContent(item))"></span>
          </div>
        </template>
      </template>
    </div>

    <!-- 打印专用容器 - 连续内容流，让浏览器自动分页 -->
    <div class="print-container" :style="[pageStyles, pagePaddingStyle]" v-if="data && data.work_experience">
      <!-- 个人信息 -->
      <div class="personal-info" :class="{ 'has-photo': data.basics?.photo }">
        <div v-if="data.basics?.photo" class="photo-container">
          <img :src="data.basics.photo" class="profile-photo" alt="证件照" />
        </div>
        <h1 class="name" v-html="formatText(data.basics?.name || '姓名未填写')"></h1>
        <div class="contact-info">
          <span v-if="data.basics?.gender" v-html="formatText(data.basics.gender)"></span>
          <span v-if="data.basics?.birth_date" class="separator">|</span>
          <span v-if="data.basics?.birth_date" v-html="formatText(data.basics.birth_date)"></span>
          <span v-if="data.basics?.gender || data.basics?.birth_date || data.basics?.phone" class="separator">|</span>
          <span v-if="data.basics?.phone" v-html="formatText(data.basics.phone)"></span>
          <span v-if="(data.basics?.gender || data.basics?.phone) && data.basics?.email" class="separator">|</span>
          <span v-if="data.basics?.email" v-html="formatText(data.basics.email)"></span>
          <template v-for="(field, fieldIndex) in (data.basics?.additional_fields || [])" :key="`print-basic-extra-${fieldIndex}`">
            <span v-if="field?.label || field?.value" class="separator">|</span>
            <span v-if="field?.label || field?.value" v-html="formatText(field?.label && field?.value ? `${field.label}：${field.value}` : (field?.label || field?.value))"></span>
          </template>
        </div>
        <div v-if="data.basics?.target_position" class="target-position">
          <span class="inline-label" :class="{ 'is-bold': isFullyBoldInlineText(data.basics.target_position) }">{{ t.targetPosition }}：</span><span v-html="formatText(data.basics.target_position)"></span>
        </div>
      </div>

      <!-- {{ t.education }} -->
      <template v-if="data.education && data.education.length">
        <h2 class="section-title" v-html="formatText(displayTitle('education', t.education))"></h2>
        <div v-for="(item, idx) in data.education" :key="idx" class="education-item">
          <div class="education-header">
            <div class="school-info">
              <span class="school" v-html="formatText(item.school_name || '学校未填写')"></span>
              <div v-if="item.school_tags?.length" class="school-tags">
                <span v-for="(tag, tIdx) in item.school_tags" :key="tIdx" class="school-tag" v-html="formatText(tag)"></span>
              </div>
            </div>
            <span class="graduation-date" v-html="formatText(`${item.date_range?.[0] || ''} - ${item.date_range?.[1] || '至今'}`)"></span>
          </div>
          <div class="degree-major" v-html="formatText(`${item.degree || ''} ${item.major || ''}`)"></div>
          <div v-if="academicMetrics(item).length" class="academic-metrics">
            <span v-for="metric in academicMetrics(item)" :key="metric" v-html="formatText(metric)"></span>
          </div>
          <!-- 论文 -->
          <template v-if="item.theses?.length">
            <div v-for="(thesis, tIdx) in item.theses" :key="'thesis-'+idx+'-'+tIdx" class="thesis-item">
              <h4 class="subfield-title">{{ t.thesis }}</h4>
              <div class="thesis-title" v-html="formatText(thesis.title)"></div>
              <ul v-if="thesis.details?.length" class="list-items">
                <li v-for="(detail, dIdx) in thesis.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
              </ul>
            </div>
          </template>
        </div>
      </template>

      <template v-if="data.others?.skills?.length">
        <h2 class="section-title" v-html="formatText(displayTitle('skills', t.skillsSection))"></h2>
        <div v-for="(item, idx) in data.others.skills" :key="`print-skill-${idx}`" :class="moduleListClasses('skills', item, 'skill-list-item')" :data-marker="moduleListMarker('skills', item, idx)" v-html="formatText(moduleListContent(item))"></div>
      </template>

      <template v-if="data.research_interests?.length">
        <h2 class="section-title" v-html="formatText(displayTitle('research_interests', t.researchInterests))"></h2>
        <div v-for="(item, idx) in data.research_interests" :key="`print-research-${idx}`" :class="moduleListClasses('research_interests', item)" :data-marker="moduleListMarker('research_interests', item, idx)" v-html="formatText(moduleListContent(item))"></div>
      </template>

      <template v-if="data.honors?.length">
        <h2 class="section-title" v-html="formatText(displayTitle('honors', t.honors))"></h2>
        <div v-for="(item, idx) in data.honors" :key="`print-honor-${idx}`" :class="moduleListClasses('honors', item)" :data-marker="moduleListMarker('honors', item, idx)" v-html="formatText(moduleListContent(item))"></div>
      </template>

      <!-- {{ t.workExperience }} -->
      <template v-if="data.work_experience && data.work_experience.length">
        <h2 class="section-title" v-html="formatText(displayTitle('work_experience', t.workExperience))"></h2>
        <div v-for="(item, idx) in data.work_experience" :key="idx" class="work-item">
          <div class="work-header">
            <div class="work-main">
              <div class="company" v-html="formatText(item.company_name || '公司未填写')"></div>
              <div v-if="workPosition(item)" class="position" v-html="formatText(workPosition(item))"></div>
            </div>
            <span class="work-period" v-html="formatText(`${item.date_range?.[0] || ''} - ${item.date_range?.[1] || '至今'}`)"></span>
          </div>
            <div v-for="(block, bIdx) in projectContentBlocks(item, 'work')" :key="bIdx" class="project-content-block" :class="contentBlockClasses(block)">
            <p v-if="block.type === 'paragraph'" class="project-paragraph"><span v-if="contentBlockLabel(block, 'inline')" class="project-inline-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'inline') }" v-html="`${formatText(contentBlockLabel(block, 'inline'))}：`"></span><span v-html="formatText(block.text)"></span></p>
            <template v-else>
              <div v-if="contentBlockLabel(block, 'separate')" class="project-block-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'separate') }" v-html="`${formatText(contentBlockLabel(block, 'separate'))}：`"></div>
              <ol v-if="block.type === 'numbered_list'" class="project-numbered-list">
                <li v-for="(detail, dIdx) in block.items" :key="dIdx" :class="{ 'marker-bold': isFullyBoldText(detail) }" v-html="formatText(detail)"></li>
              </ol>
              <ul v-else class="list-items">
                <li v-for="(detail, dIdx) in block.items" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
              </ul>
            </template>
          </div>
        </div>
      </template>

      <!-- {{ t.projectExperience }} -->
      <template v-if="(data.project_experience || data.projects) && (data.project_experience || data.projects).length">
        <h2 class="section-title" v-html="formatText(displayTitle('project_experience', t.projectExperience))"></h2>
        <div v-for="(item, idx) in (data.project_experience || data.projects)" :key="idx" class="project-item">
          <div class="project-header">
            <div class="project-name" v-html="formatText(item.project_name || item.name || '项目未填写')"></div>
            <div v-if="item.role || item.date_range?.length || item.start_date || item.end_date" class="project-role">
              <span v-if="item.date_range?.length" v-html="formatText(`${item.role ? `${item.role} | ` : ''}${item.date_range[0]} - ${item.date_range[1] || '至今'}`)"></span>
              <span v-else-if="item.start_date || item.end_date" v-html="formatText(`${item.role ? `${item.role} | ` : ''}${item.start_date || ''} - ${item.end_date || '至今'}`)"></span>
              <span v-else-if="item.role" v-html="formatText(item.role)"></span>
            </div>
          </div>
            <div v-for="(block, blockIndex) in projectContentBlocks(item)" :key="blockIndex" class="project-content-block" :class="contentBlockClasses(block)">
            <p v-if="block.type === 'paragraph'" class="project-paragraph"><span v-if="contentBlockLabel(block, 'inline')" class="project-inline-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'inline') }" v-html="`${formatText(contentBlockLabel(block, 'inline'))}：`"></span><span v-html="formatText(block.text)"></span></p>
            <template v-else>
              <div v-if="contentBlockLabel(block, 'separate')" class="project-block-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'separate') }" v-html="`${formatText(contentBlockLabel(block, 'separate'))}：`"></div>
              <ol v-if="block.type === 'numbered_list'" class="project-numbered-list"><li v-for="(detail, dIdx) in block.items" :key="dIdx" :class="{ 'marker-bold': isFullyBoldText(detail) }" v-html="formatText(detail)"></li></ol>
              <ul v-else class="list-items"><li v-for="(detail, dIdx) in block.items" :key="dIdx" class="list-item" v-html="formatText(detail)"></li></ul>
            </template>
          </div>
        </div>
      </template>

      <template v-for="(custom, sectionIndex) in (data.custom_sections || [])" :key="`print-custom-${sectionIndex}`">
        <template v-if="custom.title && custom.items?.length">
          <h2 class="section-title" v-html="formatText(custom.title)"></h2>
          <div v-for="(item, itemIndex) in custom.items" :key="`print-custom-${sectionIndex}-${itemIndex}`" :class="moduleListClasses('custom_sections', item)" :data-marker="moduleListMarker('custom_sections', item, itemIndex)" v-html="formatText(moduleListContent(item))"></div>
        </template>
      </template>

      <!-- 其他 -->
      <template v-if="data.others && (data.others.certificates?.length || data.others.languages?.length)">
        <h2 class="section-title" v-html="formatText(displayTitle('others', props.lang === 'en' ? 'Certificates & Languages' : '证书与语言'))"></h2>
        <div v-if="data.others.certificates?.length" class="cert-lang-line">
          <span class="cert-lang-label">{{ t.certificates }}：</span>
          <template v-for="(cert, cIdx) in data.others.certificates" :key="'cert-'+cIdx">
            <span v-html="formatText(cert)"></span><span v-if="cIdx < data.others.certificates.length - 1" class="cert-lang-separator"> | </span>
          </template>
        </div>
        <div v-if="data.others.languages?.length" class="cert-lang-line">
          <span class="cert-lang-label">{{ t.language }}：</span>
          <template v-for="(lang, lIdx) in data.others.languages" :key="'lang-'+lIdx">
            <span v-html="formatText(lang)"></span><span v-if="lIdx < data.others.languages.length - 1" class="cert-lang-separator"> | </span>
          </template>
        </div>
      </template>

      <!-- {{ t.selfEvaluation }} -->
      <template v-if="data.self_evaluation && data.self_evaluation.length">
        <h2 class="section-title" v-html="formatText(displayTitle('self_evaluation', t.selfEvaluation))"></h2>
        <template v-for="(item, idx) in data.self_evaluation">
          <div v-if="item" :key="'self-eval-'+idx" class="self-eval-item" v-html="formatText(item)"></div>
        </template>
      </template>
    </div>

    <!-- 分页预览 -->
    <div class="pages-scale-shell" :style="pagesViewportStyle">
    <div class="pages-wrapper" :style="pagesContainerStyle">
      <div v-for="page in pageCount" :key="page" class="a4-page" :style="pageStyle">
        <div class="page-inner" :style="pagePaddingStyle">
          <div class="page-content" :style="pageStyles">
            <!-- 个人信息 -->
            <div v-if="data.basics && isItemVisible({index: getItemIndex('basics', 0)}, page - 1)" class="personal-info" :class="[`basics-${moduleLayout('basics').preset}`, `contact-${moduleLayout('basics').contactLayout}`, { 'module-highlight': highlightedModule === 'basics', 'has-photo': data.basics.photo && !hiddenBasicField('photo') }]" data-module="basics">
              <div class="module-component-rows basics-component-rows">
                <div v-for="(row, rowIndex) in visibleComponentRows('basics')" :key="rowIndex" class="module-component-row" :style="componentRowStyle(row, 'basics')">
                  <div v-for="(cell, cellIndex) in row.cells" :key="cellIndex" class="module-component-cell" :class="`flow-${cell.flow}`" :style="componentCellStyle(cell)">
                    <template v-for="component in cell.components" :key="component">
                      <img v-if="component === 'photo' && data.basics.photo && !hiddenBasicField('photo')" :src="data.basics.photo" class="profile-photo component-photo" alt="证件照">
                      <span v-else-if="basicsComponentText(component)" class="module-component" :class="[`component-${component}`, { name: component === 'name' }]" v-html="formatText(basicsComponentText(component))"></span>
                    </template>
                  </div>
                </div>
              </div>
            </div>

            <!-- {{ t.education }} -->
            <template v-if="data.education && data.education.length && !hiddenSection('education')">
              <h2 v-if="isItemVisible({index: getItemIndex('education-title', 0)}, page - 1)" class="section-title" :class="[`title-${moduleTitleStyle('education')}`, { 'title-highlight': highlightedModule === 'education' }]" :style="moduleOrder('education')" data-module="education" v-html="formatText(displayTitle('education', t.education))"></h2>
              <template v-for="(item, idx) in data.education">
                <div v-if="isItemVisible({index: getItemIndex('education-item', idx)}, page - 1)" :key="'edu-'+idx" class="education-item" :class="[`preset-${moduleLayout('education').preset}`, { 'content-highlight': highlightedModule === 'education' }]" :style="moduleOrder('education')">
                  <div class="module-component-rows">
                    <div v-for="(row, rowIndex) in visibleComponentRows('education', ['theses'])" :key="rowIndex" class="module-component-row" :style="componentRowStyle(row, 'education')">
                      <div v-for="(cell, cellIndex) in row.cells" :key="cellIndex" class="module-component-cell" :class="`flow-${cell.flow}`" :style="componentCellStyle(cell)">
                        <span v-for="component in cell.components" v-show="educationComponentText(item, component)" :key="component" class="module-component" :class="[`component-${component}`, { school: component === 'school', 'graduation-date': component === 'date' }]" v-html="formatText(educationComponentText(item, component))"></span>
                      </div>
                    </div>
                  </div>
                </div>
                <!-- 论文（独立分页项） -->
                <template v-if="item.theses?.length && moduleLayout('education').thesisDisplay !== 'hidden' && !moduleLayout('education').hiddenComponents?.includes('theses')">
                  <template v-for="(thesis, tIdx) in item.theses">
                    <div v-if="isItemVisible({index: getItemIndex('thesis-item', `${idx}-${tIdx}`)}, page - 1)" :key="'thesis-'+idx+'-'+tIdx" class="thesis-item" :style="moduleOrder('education')">
                      <h4 class="subfield-title">{{ t.thesis }}</h4>
                      <div class="thesis-title" v-html="formatText(thesis.title)"></div>
                      <ul v-if="thesis.details?.length && moduleLayout('education').thesisDisplay === 'expanded'" class="list-items">
                        <li v-for="(detail, dIdx) in thesis.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
                      </ul>
                    </div>
                  </template>
                </template>
              </template>
            </template>

            <template v-if="data.education?.length && educationSupplementValues.length">
              <div v-for="(item, idx) in educationSupplementValues" v-show="isItemVisible({index: getItemIndex('education-supplement-item', idx)}, page - 1)" :key="`page-${page}-education-supplement-${idx}`" :class="educationSupplementClasses(item)" :data-marker="educationSupplementMarker(item, idx)" :style="moduleOrder('education')" v-html="formatText(moduleListContent(item))"></div>
            </template>

            <template v-if="data.others?.skills?.length && !hiddenSection('skills')">
              <h2 v-if="isItemVisible({index: getItemIndex('skills-title', 0)}, page - 1)" class="section-title" :class="`title-${moduleTitleStyle('skills')}`" :style="moduleOrder('skills')" data-module="skills" v-html="formatText(displayTitle('skills', t.skillsSection))"></h2>
              <div v-for="(item, idx) in data.others.skills" v-show="isItemVisible({index: getItemIndex('skills-item', idx)}, page - 1)" :key="`page-${page}-skill-${idx}`" :class="moduleListClasses('skills', item, 'skill-list-item')" :data-marker="moduleListMarker('skills', item, idx)" :style="moduleOrder('skills')" v-html="formatText(moduleListContent(item))"></div>
            </template>

            <template v-if="data.research_interests?.length && !hiddenSection('research_interests') && !sectionMergedIntoEducation('research_interests')">
              <h2 v-if="isItemVisible({index: getItemIndex('research-title', 0)}, page - 1)" class="section-title" :class="`title-${moduleTitleStyle('research_interests')}`" :style="moduleOrder('research_interests')" data-module="research_interests" v-html="formatText(displayTitle('research_interests', t.researchInterests))"></h2>
              <div v-for="(item, idx) in data.research_interests" v-show="isItemVisible({index: getItemIndex('research-item', idx)}, page - 1)" :key="`page-${page}-research-${idx}`" :class="moduleListClasses('research_interests', item)" :data-marker="moduleListMarker('research_interests', item, idx)" :style="moduleOrder('research_interests')" v-html="formatText(moduleListContent(item))"></div>
            </template>

            <template v-if="data.honors?.length && !hiddenSection('honors') && !sectionMergedIntoEducation('honors')">
              <h2 v-if="isItemVisible({index: getItemIndex('honors-title', 0)}, page - 1)" class="section-title" :class="`title-${moduleTitleStyle('honors')}`" :style="moduleOrder('honors')" data-module="honors" v-html="formatText(displayTitle('honors', t.honors))"></h2>
              <div v-for="(item, idx) in data.honors" v-show="isItemVisible({index: getItemIndex('honors-item', idx)}, page - 1)" :key="`page-${page}-honor-${idx}`" :class="moduleListClasses('honors', item)" :data-marker="moduleListMarker('honors', item, idx)" :style="moduleOrder('honors')" v-html="formatText(moduleListContent(item))"></div>
            </template>

            <!-- {{ t.workExperience }} -->
            <template v-for="section in workSections" :key="`page-${page}-${section.id}`">
              <h2 v-if="isItemVisible({index: getItemIndex(`${workTypePrefix(section.id)}-title`, 0)}, page - 1)" class="section-title" :class="[`title-${moduleTitleStyle(section.id)}`, { 'title-highlight': highlightedModule === 'work_experience' }]" :style="moduleOrder(section.id)" :data-module="section.id" v-html="formatText(section.title)"></h2>
              <template v-for="entry in section.entries" :key="`${section.id}-${entry.dataIndex}`">
                <div v-if="isItemVisible({index: getItemIndex(`${workTypePrefix(section.id)}-item`, entry.dataIndex)}, page - 1)" class="work-item" :class="[`preset-${moduleLayout(section.id).preset}`, `date-${moduleLayout(section.id).datePosition}`, { 'content-highlight': highlightedModule === 'work_experience' }]" :style="moduleOrder(section.id)">
                  <div class="module-component-rows">
                    <div v-for="(row, rowIndex) in visibleComponentRows(section.id, ['content'])" :key="rowIndex" class="module-component-row" :style="componentRowStyle(row, section.id)">
                      <div v-for="(cell, cellIndex) in row.cells" :key="cellIndex" class="module-component-cell" :class="`flow-${cell.flow}`" :style="componentCellStyle(cell)">
                        <span v-for="component in cell.components" v-show="workComponentText(entry.item, component, section.id)" :key="component" class="module-component" :class="[`component-${component}`, { company: component === 'organization', 'work-period': component === 'date' }]" v-html="formatText(workComponentText(entry.item, component, section.id))"></span>
                      </div>
                    </div>
                  </div>
                </div>
                <!-- 工作详情（独立分页项） -->
                <div v-if="projectContentBlocks(entry.item, 'work').length && isItemVisible({index: getItemIndex(`${workTypePrefix(section.id)}-details`, entry.dataIndex)}, page - 1)" class="work-details" :class="`details-${moduleLayout(section.id).detailsStyle}`" :style="moduleOrder(section.id)">
                  <div v-for="(block, bIdx) in projectContentBlocks(entry.item, 'work')" :key="bIdx" class="project-content-block" :class="contentBlockClasses(block)">
                    <p v-if="block.type === 'paragraph'" class="project-paragraph"><span v-if="contentBlockLabel(block, 'inline')" class="project-inline-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'inline') }" v-html="`${formatText(contentBlockLabel(block, 'inline'))}：`"></span><span v-html="formatText(block.text)"></span></p>
                    <template v-else>
                      <div v-if="contentBlockLabel(block, 'separate')" class="project-block-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'separate') }" v-html="`${formatText(contentBlockLabel(block, 'separate'))}：`"></div>
                      <ol v-if="block.type === 'numbered_list'" class="project-numbered-list">
                        <li v-for="(detail, dIdx) in block.items" :key="dIdx" :class="{ 'marker-bold': isFullyBoldText(detail) }" v-html="formatText(detail)"></li>
                      </ol>
                      <ul v-else class="list-items">
                        <li v-for="(detail, dIdx) in block.items" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
                      </ul>
                    </template>
                  </div>
                </div>
              </template>
            </template>

            <!-- {{ t.projectExperience }} -->
            <template v-if="(data.project_experience || data.projects) && (data.project_experience || data.projects).length && !hiddenSection('project_experience')">
              <h2 v-if="isItemVisible({index: getItemIndex('projects-title', 0)}, page - 1)" class="section-title" :class="[`title-${moduleTitleStyle('project_experience')}`, { 'title-highlight': highlightedModule === 'project_experience' }]" :style="moduleOrder('project_experience')" data-module="project_experience" v-html="formatText(displayTitle('project_experience', t.projectExperience))"></h2>
              <template v-for="(item, idx) in (data.project_experience || data.projects)">
                <div v-if="isItemVisible({index: getItemIndex('project-item', idx)}, page - 1)" :key="'proj-'+idx" class="project-item" :class="[`preset-${moduleLayout('project_experience').preset}`, `date-${moduleLayout('project_experience').datePosition}`, { 'content-highlight': highlightedModule === 'project_experience' }]" :style="moduleOrder('project_experience')">
                  <div class="module-component-rows">
                    <div v-for="(row, rowIndex) in visibleComponentRows('project_experience', ['content'])" :key="rowIndex" class="module-component-row" :style="componentRowStyle(row, 'project_experience')">
                      <div v-for="(cell, cellIndex) in row.cells" :key="cellIndex" class="module-component-cell" :class="`flow-${cell.flow}`" :style="componentCellStyle(cell)">
                        <span v-for="component in cell.components" v-show="projectComponentText(item, component)" :key="component" class="module-component" :class="[`component-${component}`, { 'project-name': component === 'project_name', 'project-period': component === 'date' }]" v-html="formatText(projectComponentText(item, component))"></span>
                      </div>
                    </div>
                  </div>
                </div>
                <!-- 项目详情（独立分页项） -->
                <div v-if="projectContentBlocks(item).length && isItemVisible({index: getItemIndex('project-details', idx)}, page - 1)" :key="'proj-details-'+idx" class="project-details" :style="moduleOrder('project_experience')">
                  <div v-for="(block, blockIndex) in projectContentBlocks(item)" :key="blockIndex" class="project-content-block" :class="contentBlockClasses(block)">
                    <p v-if="block.type === 'paragraph'" class="project-paragraph"><span v-if="contentBlockLabel(block, 'inline')" class="project-inline-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'inline') }" v-html="`${formatText(contentBlockLabel(block, 'inline'))}：`"></span><span v-html="formatText(block.text)"></span></p>
                    <template v-else>
                      <div v-if="contentBlockLabel(block, 'separate')" class="project-block-label" :class="{ 'is-bold': contentBlockLabelBold(block, 'separate') }" v-html="`${formatText(contentBlockLabel(block, 'separate'))}：`"></div>
                      <ol v-if="block.type === 'numbered_list'" class="project-numbered-list">
                        <li v-for="(detail, dIdx) in block.items" :key="dIdx" :class="{ 'marker-bold': isFullyBoldText(detail) }" v-html="formatText(detail)"></li>
                      </ol>
                      <ul v-else class="list-items">
                        <li v-for="(detail, dIdx) in block.items" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
                      </ul>
                    </template>
                  </div>
                </div>
              </template>
            </template>

            <template v-if="data.custom_sections?.length && !hiddenSection('custom_sections')">
              <template v-for="(custom, sectionIndex) in data.custom_sections" :key="`page-${page}-custom-${sectionIndex}`">
                <h2 v-if="custom.title && custom.items?.length && isItemVisible({index: getItemIndex('custom-title', sectionIndex)}, page - 1)" class="section-title" :class="`title-${moduleTitleStyle('custom_sections')}`" :style="moduleOrder('custom_sections')" data-module="custom_sections" v-html="formatText(custom.title)"></h2>
                <div v-for="(item, itemIndex) in (custom.items || [])" v-show="isItemVisible({index: getItemIndex('custom-item', `${sectionIndex}-${itemIndex}`)}, page - 1)" :key="`page-${page}-custom-${sectionIndex}-${itemIndex}`" :class="moduleListClasses('custom_sections', item)" :data-marker="moduleListMarker('custom_sections', item, itemIndex)" :style="moduleOrder('custom_sections')" v-html="formatText(moduleListContent(item))"></div>
              </template>
            </template>

            <!-- 其他 -->
      <template v-if="data.others && visibleOtherFields.length && !hiddenSection('others') && !sectionMergedIntoEducation('others')">
              <h2 v-if="isItemVisible({index: getItemIndex('others-title', 0)}, page - 1)" class="section-title" :class="[`title-${moduleTitleStyle('others')}`, { 'title-highlight': highlightedModule === 'others' }]" :style="moduleOrder('others')" data-module="others" v-html="formatText(displayTitle('others', props.lang === 'en' ? 'Certificates & Languages' : '证书与语言'))"></h2>
              <!-- Keep the heading and its values on the same page.  The two
                   elements share one semantic pagination unit, so the value
                   visibility follows the heading index instead of being
                   independently rounded into the adjacent page. -->
              <div v-if="isItemVisible({index: getItemIndex('others-title', 0)}, page - 1)" class="cert-lang-line" :class="`others-${moduleLayout('others').preset}`" :style="moduleOrder('others')">
                <div class="module-component-rows">
                  <div v-for="(row, rowIndex) in visibleOtherComponentRows()" :key="rowIndex" class="module-component-row" :style="componentRowStyle(row, 'others')">
                    <div v-for="(cell, cellIndex) in row.cells" :key="cellIndex" class="module-component-cell" :class="`flow-${cell.flow}`" :style="componentCellStyle(cell)">
                      <span v-for="component in cell.components" :key="component" class="module-component" :class="`component-${component}`" v-html="formatText(othersComponentText(component))"></span>
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <template v-if="data.publications?.length && !hiddenSection('publications') && !sectionMergedIntoEducation('publications')">
              <h2 v-if="isItemVisible({index: getItemIndex('publications-title', 0)}, page - 1)" class="section-title" :class="`title-${moduleTitleStyle('publications')}`" :style="moduleOrder('publications')" data-module="publications" v-html="formatText(displayTitle('publications', lang === 'en' ? 'Publications' : '论文'))"></h2>
              <div v-for="(item, idx) in data.publications" v-show="isItemVisible({index: getItemIndex('publications-item', idx)}, page - 1)" :key="`page-${page}-publication-${idx}`" :class="moduleListClasses('publications', item)" :data-marker="moduleListMarker('publications', item, idx)" :style="moduleOrder('publications')" v-html="formatText(moduleListContent(item))"></div>
            </template>

            <!-- {{ t.selfEvaluation }} -->
            <template v-if="selfEvaluationValues.length && !hiddenSection('self_evaluation')">
              <h2 v-if="isItemVisible({index: getItemIndex('self-eval-title', 0)}, page - 1)" class="section-title" :class="[`title-${moduleTitleStyle('self_evaluation')}`, { 'title-highlight': highlightedModule === 'self_evaluation' }]" :style="moduleOrder('self_evaluation')" data-module="self_evaluation" v-html="formatText(displayTitle('self_evaluation', t.selfEvaluation))"></h2>
              <!-- 每条{{ t.selfEvaluation }}独立分页 -->
              <template v-for="(item, idx) in selfEvaluationValues">
                <div v-if="item && isItemVisible({index: getItemIndex('self-eval-item', idx)}, page - 1)" :key="'self-eval-'+idx" class="self-eval-item" :class="[...moduleListClasses('self_evaluation', item), { 'content-highlight': highlightedModule === 'self_evaluation' }]" :data-marker="moduleListMarker('self_evaluation', item, idx)" :style="moduleOrder('self_evaluation')">
                  <span v-html="formatText(moduleListContent(item))"></span>
                </div>
              </template>
            </template>
          </div>
        </div>
        <div v-if="pageCount > 1" class="page-footer">{{ page }} / {{ pageCount }}</div>
      </div>
    </div>
    </div>
    <div v-if="pageCount > 1" class="page-indicator">共 {{ pageCount }} 页</div>
    <div v-if="overflowBeyondPageLimit" class="page-overflow-warning" role="status">
      当前内容超出两页，未排入内容从“{{ overflowItemLabel }}”开始。请精简内容或调小字体、间距后再导出。
    </div>
    </div>
    </template>

    <!-- 无简历数据时显示提示 -->
    <div v-if="!data && !showSourceDocument" class="no-data">
      <p>暂无简历数据，请先编辑简历</p>
      <button class="jd-upload-btn" @click="emit('open-resume-edit')" title="编辑简历">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
        </svg>
        <span>编辑简历</span>
      </button>
    </div>
  </div>

  <div v-if="showSectionOrderDialog" class="success-dialog-overlay section-order-overlay" @click.self="closeSectionOrderDialog">
    <div class="section-order-dialog" role="dialog" aria-modal="true" aria-labelledby="section-order-title">
      <div class="layout-guide-header">
        <div>
          <h3 id="section-order-title">模块顺序</h3>
          <p>按住任意模块上下拖动，或使用箭头微调；点击确定后才保存。</p>
        </div>
        <button class="layout-guide-close" aria-label="关闭模块排序" :disabled="isSavingSectionOrder" @click="closeSectionOrderDialog">×</button>
      </div>
      <div class="section-order-list">
        <div
          v-for="section in reorderableSections"
          :key="section"
          class="section-order-row section-order-dialog-row"
          :class="{ dragging: draggedSection === section, 'education-child-row': isEducationChildSection(section) }"
          draggable="true"
          @dragstart="startSectionDrag(section, $event)"
          @dragover="dragOverSection($event, section)"
          @drop.prevent="finishSectionDrag"
          @dragend="finishSectionDrag"
        >
          <span class="drag-handle" aria-hidden="true">⋮⋮</span>
          <span class="section-order-name">{{ displayTitleText(section, SECTION_LABELS[section]) }}</span>
          <span class="section-order-actions">
            <button type="button" :disabled="!canMoveSection(section, -1)" :aria-label="`上移${SECTION_LABELS[section]}`" @click="moveSection(section, -1)">↑</button>
            <button type="button" :disabled="!canMoveSection(section, 1)" :aria-label="`下移${SECTION_LABELS[section]}`" @click="moveSection(section, 1)">↓</button>
          </span>
        </div>
      </div>
      <div v-if="sectionOrderError" class="font-size-error" role="alert">{{ sectionOrderError }}</div>
      <div class="section-order-dialog-footer">
        <button type="button" class="settings-dialog-action" :disabled="isSavingSectionOrder" @click="resetSectionOrder">恢复默认</button>
        <button type="button" class="settings-dialog-action primary" :disabled="isSavingSectionOrder" @click="applySectionOrder">{{ isSavingSectionOrder ? '保存中…' : '应用' }}</button>
      </div>
    </div>
  </div>

  <div v-if="showFontSizeDialog" class="success-dialog-overlay font-size-overlay" @click.self="closeFontSizeDialog">
    <div class="font-size-dialog" role="dialog" aria-modal="true" aria-labelledby="font-size-title">
      <div class="layout-guide-header">
        <div>
          <h3 id="font-size-title">文字大小</h3>
          <p>字号按半磅调整。修改会先显示在右侧预览，点击应用后才保存。</p>
        </div>
        <button class="layout-guide-close" aria-label="关闭字号设置" :disabled="isSavingFontSizes" @click="closeFontSizeDialog">×</button>
      </div>
      <div class="font-size-grid">
        <label v-for="role in fontSizeRoles" :key="role" class="font-size-field">
          <span>{{ FONT_SIZE_LABELS[role] }}</span>
          <span class="font-size-picker">
            <button type="button" class="font-size-picker-trigger" :aria-label="`${FONT_SIZE_LABELS[role]}字号`" :aria-expanded="openFontSizeRole === role" @click="toggleFontSizeRole(role)">{{ fontSizeDraft[role] }} pt <i>⌄</i></button>
            <span v-if="openFontSizeRole === role" class="font-size-options" role="listbox" :aria-label="`${FONT_SIZE_LABELS[role]}字号选项`">
              <button v-for="size in fontSizeOptions(role)" :key="size" type="button" role="option" :aria-selected="fontSizeDraft[role] === size" :class="{ selected: fontSizeDraft[role] === size }" @click="selectFontSize(role, size)">{{ size }} pt</button>
            </span>
          </span>
        </label>
      </div>
      <div v-if="overflowBeyondPageLimit" class="font-size-warning" role="status">当前字号会使内容超出两页，请调小字号后再应用。</div>
      <div v-if="fontSizeSaveError" class="font-size-error" role="alert">{{ fontSizeSaveError }}</div>
      <div class="font-size-actions">
        <button type="button" class="settings-dialog-action font-size-reset" :disabled="isSavingFontSizes" @click="resetFontSizeDraft">恢复默认</button>
        <span class="font-size-action-spacer"></span>
        <button type="button" class="settings-dialog-action primary font-size-apply" :disabled="isSavingFontSizes || overflowBeyondPageLimit" @click="applyFontSizeSettings">
          {{ isSavingFontSizes ? '保存中…' : '应用' }}
        </button>
      </div>
    </div>
  </div>

  <div v-if="showSectionSettingsDialog" class="success-dialog-overlay section-settings-overlay" @click.self="closeSectionSettingsDialog">
    <div class="section-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="section-settings-title">
      <div class="layout-guide-header">
        <div>
          <h3 id="section-settings-title">栏目设置</h3>
        </div>
        <button class="layout-guide-close" aria-label="关闭栏目设置" :disabled="isSavingSectionSettings" @click="closeSectionSettingsDialog">×</button>
      </div>
      <div class="section-settings-body">
        <section>
          <h4>分点形式</h4>
          <label v-for="section in listSettingSections" :key="`list-${section}`" class="section-setting-row">
            <span>{{ SECTION_LABELS[section] }}</span>
            <select v-model="sectionSettingsDraft[section].listStyle">
              <option v-for="(label, value) in LIST_STYLE_LABELS" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
          <label class="section-setting-row">
            <span>教育经历补充</span>
            <select v-model="sectionSettingsDraft.education.supplementListStyle">
              <option v-for="(label, value) in LIST_STYLE_LABELS" :key="value" :value="value">{{ label }}</option>
            </select>
          </label>
        </section>
        <section>
          <h4>栏目位置</h4>
          <label v-for="section in mergeSettingSections" :key="`placement-${section}`" class="section-setting-row">
            <span>{{ SECTION_LABELS[section] }}</span>
            <select :value="editableSectionPlacement(section)" @change="setEditableSectionPlacement(section, $event.target.value)">
              <option value="standalone">独立栏目</option>
              <option value="education">并入教育经历</option>
            </select>
          </label>
          <p class="section-settings-note">并入教育经历后将不显示模块标题</p>
        </section>
      </div>
      <div v-if="sectionSettingsError" class="font-size-error" role="alert">{{ sectionSettingsError }}</div>
      <div class="section-order-dialog-footer">
        <button type="button" class="settings-dialog-action" :disabled="isSavingSectionSettings" @click="resetSectionSettings">恢复默认</button>
        <button type="button" class="settings-dialog-action primary" :disabled="isSavingSectionSettings" @click="applySectionSettings">{{ isSavingSectionSettings ? '保存中…' : '应用' }}</button>
      </div>
    </div>
  </div>

  <div v-if="showSuccessDialog" class="success-dialog-overlay" @click.self="showSuccessDialog = false">
    <div class="success-dialog">
      <div class="success-icon">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h3>简历导出成功</h3>
      <p>{{ lastExportFormat }} 文件已成功下载。<br><br>{{ lastExportFormat === 'Word' ? 'DOCX 中的文字、段落和列表均可在 Word 或 WPS 中继续编辑。' : '网页预览与实际 PDF 文件在排版上可能有细微差异；可调整样式参数后重新导出。' }}</p>
      <button class="confirm-btn" @click="showSuccessDialog = false">我知道了</button>
    </div>
  </div>

  <div v-if="exportError" class="success-dialog-overlay" @click.self="exportError = ''">
    <div class="success-dialog error-dialog">
      <div class="success-icon error-icon">!</div>
      <h3>导出未完成</h3>
      <p>{{ exportError }}</p>
      <button class="confirm-btn" @click="exportError = ''">关闭</button>
    </div>
  </div>
</template>

<style scoped>
.resume-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
}
.source-document-viewer {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #18191e;
}
.source-document-header {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  min-height: 34px;
  padding: 6px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  color: #f3f4f7;
  background: #24262c;
}
.source-document-header strong {
  min-width: 0;
  max-width: 52%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}
.source-document-header span {
  flex: 0 0 auto;
  color: #aeb3bf;
  font-size: 12px;
  white-space: nowrap;
}
.source-document-status button {
  border: 1px solid #505560;
  border-radius: 7px;
  min-width: 0;
  padding: 5px 9px;
  color: #e5e8ef;
  background: #33363e;
  font-size: 12px;
  line-height: 1.2;
  cursor: pointer;
}
.source-document-status {
  flex: 1;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
  color: #c9cdd5;
}
.source-document-status p { margin: 0; }
.source-document-error { color: #f0a7a7; }
.source-document-frame { flex: 1; width: 100%; min-height: 0; border: 0; background: #fff; }
.source-document-image-scroll { flex: 1; overflow: auto; padding: 20px; text-align: center; }
.source-document-image-scroll img { display: inline-block; max-width: 100%; height: auto; box-shadow: 0 8px 30px rgba(0,0,0,.35); }
/* 工具栏包装器 - 为sticky提供正确的定位上下文 */
.resume-toolbar-wrapper {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(31, 32, 37, 0.97);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  flex-shrink: 0;
}
.resume-toolbar {
  height: 54px;
  min-height: 54px;
  box-sizing: border-box;
  background: transparent;
  padding: 0.35rem 0.65rem;
  box-shadow: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.4rem;
  flex-shrink: 0;
  flex-wrap: nowrap;
  overflow: visible;
}
.slider {
  -webkit-appearance: none;
  width: 120px;
  height: 4px;
  border-radius: 0;
  background: #e0e0e0;
  outline: none;
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 0;
  background: #303030;
  cursor: pointer;
  border: none;
  box-shadow: none;
}
.slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 0;
  background: #303030;
  cursor: pointer;
  border: none;
  box-shadow: none;
}
.export-btn {
  background: #5f8ff2;
  color: #303030;
  border: 1px solid #303030;
  padding: 0.38rem 0.55rem;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.625rem;
  font-weight: 400;
  border-radius: 0;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 0.2rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  box-shadow: 2px 2px 0 #303030;
}
.export-btn:hover {
  background: #303030;
  color: #78a6ff;
  box-shadow: none;
  transform: translate(2px, 2px);
}
.export-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}
/* 语言切换 */
.lang-toggle {
  display: flex;
  border: 1px solid #303030;
}
.lang-toggle span {
  padding: 0.35rem 0.4rem;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.625rem;
  cursor: pointer;
  transition: all 0.2s ease;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.lang-toggle span:first-child {
  border-right: 1px solid #303030;
}
.lang-toggle span.active {
  background: #303030;
  color: #78a6ff;
}
.lang-toggle span:not(.active):hover {
  background: #f0f0f0;
}
/* JD上传按钮 */
.jd-upload-btn {
  background: transparent;
  color: #303030;
  border: 1px solid #303030;
  padding: 0.35rem 0.5rem;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.625rem;
  font-weight: 400;
  border-radius: 0;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 0.2rem;
  position: relative;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.jd-upload-btn:hover {
  background: rgba(95, 143, 242, 0.16);
  border-color: #303030;
}
/* 桌面端 Apple 风格合并工具栏 */
.compact-toolbar-group {
  position: relative;
  flex: 0 0 auto;
}

.shared-toolbar-actions { display: contents; }

.compact-toolbar-cluster {
  display: flex;
  align-items: center;
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: 0;
}

.compact-toolbar-cluster .compact-toolbar-btn {
  border-color: transparent;
  background: transparent;
  box-shadow: none;
}

.compact-toolbar-cluster .compact-toolbar-group + .compact-toolbar-group,
.compact-toolbar-cluster > .compact-toolbar-btn,
.compact-toolbar-cluster > .compact-toolbar-group + .compact-toolbar-btn,
.compact-toolbar-cluster > .compact-toolbar-btn + .compact-toolbar-group {
  border-left: 1px solid rgba(255, 255, 255, 0.065);
  border-top-left-radius: 0;
  border-bottom-left-radius: 0;
}

.compact-toolbar-btn {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.32rem;
  padding: 0.35rem 0.55rem;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 9px;
  color: #c9c9cf;
  background: rgba(255, 255, 255, 0.055);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
  cursor: pointer;
  white-space: nowrap;
  font-size: 0.68rem;
  font-weight: 500;
  transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}

.compact-toolbar-btn svg,
.compact-export-btn svg,
.compact-menu-item svg {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
}

.compact-toolbar-btn:hover,
.compact-toolbar-btn.active {
  color: #f5f5f7;
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.1);
}

.compact-toolbar-cluster .compact-toolbar-btn.active {
  border-color: transparent;
}

.compact-toolbar-btn:focus,
.compact-export-btn:focus,
.compact-menu-item:focus,
.compact-reset-btn:focus,
.compact-toolbar-btn:focus-visible,
.compact-export-btn:focus-visible,
.compact-menu-item:focus-visible,
.compact-reset-btn:focus-visible {
  outline: none;
  box-shadow: none;
}

.compact-popover {
  position: absolute;
  top: calc(100% + 9px);
  left: 50%;
  right: auto;
  transform: translateX(-50%);
  z-index: 10020;
  min-width: 220px;
  padding: 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  color: #f5f5f7;
  background: rgba(35, 36, 42, 0.98);
  box-shadow: 0 20px 55px rgba(0, 0, 0, 0.48);
  backdrop-filter: blur(26px);
  -webkit-backdrop-filter: blur(26px);
}

.layout-popover {
  width: 238px;
  max-height: calc(100vh - 110px);
  overflow-y: auto;
}

.layout-settings-section {
  margin-top: 9px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 9px;
}
.layout-settings-heading { color: #d9dce4; font-size: 0.7rem; font-weight: 600; }
.layout-spacing-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; margin-top: 12px; }
.layout-spacing-actions button {
  min-height: 30px;
  padding: 0 8px;
  border: 0;
  border-radius: 7px;
  color: #d8dbe3;
  background: rgba(255, 255, 255, 0.08);
  font-size: 0.68rem;
  cursor: pointer;
}
.layout-spacing-actions button.primary { color: #fff; background: #4d6fb8; }

.auto-page-hint {
  margin: 7px 0 10px;
  padding: 6px 8px;
  color: #9ea4b2;
  font-size: 12px;
  line-height: 1.4;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 8px;
}

.page-overflow-warning {
  width: min(560px, calc(100% - 24px));
  margin: 10px auto 0;
  padding: 9px 12px;
  color: #ffc1a8;
  font-size: 12px;
  line-height: 1.5;
  text-align: center;
  background: rgba(255, 126, 82, 0.1);
  border: 1px solid rgba(255, 144, 104, 0.22);
  border-radius: 9px;
}

.edit-popover {
  width: 240px;
}

.compact-popover-title {
  margin-bottom: 0.65rem;
  color: #f0f0f3;
  font-size: 0.72rem;
  font-weight: 500;
}

.zoom-mode-grid,
.compact-zoom-stepper {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.4rem;
}

.compact-zoom-stepper {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 0.45rem;
}

.zoom-mode-grid button,
.compact-zoom-stepper button,
.compact-reset-btn {
  min-height: 32px;
  padding: 0.3rem 0.45rem;
  border: 0;
  border-radius: 9px;
  color: #c7c7ce;
  background: rgba(255, 255, 255, 0.06);
  font-size: 0.68rem;
}

.zoom-mode-grid button:hover,
.zoom-mode-grid button.active,
.compact-zoom-stepper button:hover:not(:disabled),
.compact-reset-btn:hover {
  color: #f5f5f7;
  background: rgba(255, 255, 255, 0.11);
}

.layout-guide-btn {
  width: 100%;
  min-height: 30px;
  margin-top: 7px;
  border: 0;
  border-radius: 7px;
  color: #dce7ff;
  background: rgba(88, 132, 230, 0.12);
  font-size: 0.72rem;
  cursor: pointer;
}
.layout-guide-btn:hover { background: rgba(88, 132, 230, 0.2); }
.section-order-row {
  display: grid;
  grid-template-columns: 18px 1fr auto;
  align-items: center;
  min-height: 30px;
  margin-bottom: 3px;
  padding: 3px 5px;
  color: #e7e7eb;
  background: rgba(255, 255, 255, 0.045);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 6px;
  font-size: 0.7rem;
  cursor: grab;
}
.section-order-row.dragging { opacity: 0.5; }
.drag-handle { color: #858892; letter-spacing: -3px; }
.section-order-actions { display: flex; gap: 2px; }
.section-order-actions button {
  width: 24px;
  height: 22px;
  padding: 0;
  color: #dfe6f7;
  background: transparent;
  border: 0;
  cursor: pointer;
}
.section-order-actions button:hover:not(:disabled) { background: rgba(255, 255, 255, 0.1); }
.section-order-open-btn { margin-top: 7px; }

.compact-zoom-stepper button:disabled {
  opacity: 0.35;
  cursor: default;
}

.compact-control {
  display: grid;
  gap: 0.35rem;
  margin-top: 0.65rem;
}

.compact-control > span {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  color: #bdbdc5;
  font-size: 0.68rem;
}

.compact-control strong {
  color: #85858f;
  font-weight: 400;
}

.compact-control .slider {
  width: 100%;
  height: 3px;
  border-radius: 999px;
  background: #3b3c42;
}

.compact-control .slider::-webkit-slider-thumb {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: #e7eaf1;
}

.compact-control .slider::-moz-range-thumb {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: #e7eaf1;
}

.compact-menu-item {
  width: 100%;
  min-height: 46px;
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.5rem 0.55rem;
  border: 0;
  border-radius: 9px;
  color: #d7d7dc;
  background: transparent;
  text-align: left;
}

.compact-menu-item:hover {
  color: #f5f5f7;
  background: rgba(255, 255, 255, 0.075);
}

.compact-menu-item > span {
  display: grid;
  gap: 0.12rem;
}

.compact-menu-item strong {
  font-size: 0.69rem;
  font-weight: 500;
}

.compact-menu-item small {
  color: #85858f;
  font-size: 0.62rem;
}

.language-btn {
  flex: 0 0 auto;
}

.language-btn:disabled {
  min-width: 78px;
  color: #cbd5ea;
  cursor: wait;
  opacity: 0.78;
}

.compact-export-btn {
  min-height: 32px;
  padding: 0.35rem 0.7rem;
  border: 1px solid rgba(255, 255, 255, 0.7);
  border-radius: 9px;
  color: #0b0b0d;
  background: #f0f0f2;
  box-shadow: 0 5px 16px rgba(0, 0, 0, 0.2);
  font-size: 0.68rem;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
}

.compact-export-btn:hover {
  color: #0b0b0d;
  background: #ffffff;
  box-shadow: 0 7px 20px rgba(0, 0, 0, 0.28);
  transform: translateY(-1px);
}

.compact-export-btn:disabled {
  color: #0b0b0d;
  background: #a8a8ad;
  border-color: transparent;
  transform: none;
}
/* Spinner 转圈圈 */
.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(48, 48, 48, 0.3);
  border-radius: 0;
  border-top-color: #303030;
  animation: spin 0.8s linear infinite;
  margin-right: 6px;
  vertical-align: middle;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
/* 预览内容区域 - 处理滚动 */
.preview-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px;
  background:
    radial-gradient(circle at 50% 5%, rgba(91, 105, 145, 0.16), transparent 34%),
    #202126;
  width: 100%;
  box-sizing: border-box;
  overflow-y: auto;
  overflow-x: hidden;
  flex: 1;
  min-height: 0;
}
.content-source {
  /* 使用 opacity: 0 而非 visibility: hidden，确保可以准确测量高度 */
  position: fixed;
  left: 0;
  top: 0;
  opacity: 0;
  width: 210mm;
  box-sizing: border-box;
  background: white;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  color: #111;
}
.pages-wrapper {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.pages-scale-shell {
  position: relative;
  flex: 0 0 auto;
  align-self: center;
}

/* 打印容器默认隐藏，只在打印时显示 */
.print-container {
  display: none;
  color: #111;
}
.a4-page {
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  position: relative;
  box-sizing: border-box;
  flex-shrink: 0;
}
.a4-page::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  border: 1px solid #e0e0e0;
  pointer-events: none;
  z-index: 1;
}
.page-inner {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
}
.page-content {
  width: 100%;
  box-sizing: border-box;
  word-wrap: break-word;
  overflow-wrap: break-word;
  display: flex;
  flex-direction: column;
  color: #111;
}
.personal-info {
  text-align: center;
  position: relative;
  min-height: 0;
  margin-bottom: 0.35em;
}
.personal-info.basics-left-aligned { text-align: left; }
.personal-info.basics-left-aligned .contact-info { justify-content: flex-start; }
.personal-info.contact-stacked .contact-info { flex-direction: column; gap: 0.1em; }
.personal-info.contact-inline .contact-info > span + span::before {
  content: '|';
  margin-right: 0.5em;
  color: #333333;
}

.personal-info .name {
  font-size: var(--name-font-size);
  font-weight: var(--name-font-weight);
  margin: 0 0 var(--header-name-after) 0;
  color: #212529;
}

.contact-info {
  display: flex;
  justify-content: center;
  gap: 0.5em;
  flex-wrap: wrap;
  font-size: var(--meta-font-size);
  font-weight: var(--meta-font-weight);
  color: #333333;
}

.photo-container {
  position: absolute;
  top: 0;
  right: 0;
}

.profile-photo {
  width: 80px;
  height: 100px;
  object-fit: cover;
  border-radius: 0;
  border: 0;
}
.photo-container .profile-photo {
  width: var(--photo-width);
  height: var(--photo-height);
}

.target-position {
  font-size: var(--meta-font-size);
  color: #212529;
  font-weight: var(--meta-font-weight);
  margin-top: 0.25em;
}
.target-position .inline-label.is-bold { font-weight: var(--label-font-weight); }

.section-title {
  font-size: var(--section-title-font-size);
  font-weight: var(--section-title-font-weight);
  margin: 0 0 var(--module-margin, 0.5em) 0;
  color: #212529;
  padding-bottom: 0.25em;
  border-bottom: 1px solid #333;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.education-item,
.work-item,
.project-item {
  margin-bottom: var(--module-margin, 0.5em);
}
.education-header,
.work-header,
.project-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.5em;
}
.work-main {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 0.32em;
}
.work-main .company,
.project-header .project-name { min-width: 0; }
.work-main .position { flex: 0 1 auto; }
.work-main .position::before { content: '· '; }
.work-item.date-right .work-header,
.project-item.date-right .project-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline;
  column-gap: 0.65em;
}
.work-item.date-right .work-period,
.project-item.date-right .project-role {
  margin-left: 0;
  text-align: right;
  white-space: nowrap;
}
.school,
.company,
.project-name {
  font-size: var(--entry-title-font-size);
  font-weight: var(--manual-title-font-weight);
  color: #212529;
}
.school-info {
  display: flex;
  align-items: baseline;
  gap: 0.5em;
  flex-wrap: wrap;
}
.school-tags {
  display: inline-flex;
  gap: 0.375em;
  flex-wrap: nowrap;
  white-space: nowrap;
}
.school-tag {
  display: inline-block;
  padding: 0.125em 0.5em;
  background: #333;
  color: white;
  font-size: var(--label-font-size);
  border-radius: 4px;
  font-weight: 500;
}
.graduation-date,
.work-period {
  font-size: var(--meta-font-size);
  color: #95a5a6;
  white-space: nowrap;
  font-weight: var(--meta-font-weight);
}
.degree-major,
.position,
.project-role {
  font-size: var(--meta-font-size);
  color: #6c757d;
  font-weight: var(--meta-font-weight);
}
.school-tag.tag-outline { background: transparent; color: #333; border: 1px solid #333; }
.school-tag.tag-text { background: transparent; color: #333; padding: 0; border-radius: 0; }
.section-title.title-plain {
  border-bottom: 1px solid #333;
  padding-bottom: 0.2em;
  text-transform: none;
  letter-spacing: 0;
}
.education-item .education-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.15em 0.8em;
  align-items: start;
}
.education-item .school-info { grid-column: 1; grid-row: 1; }
.education-item .education-middle-column { grid-column: 1; grid-row: 2; }
.education-item .graduation-date { grid-column: 2; grid-row: 1; }
.education-item .school-info,
.education-item .education-middle-column,
.education-item .education-degree-column,
.education-item .education-metrics-column {
  min-width: 0;
  overflow-wrap: break-word;
  word-break: break-word;
}
.education-item.preset-compact .education-header {
  display: grid;
  width: 100%;
  grid-template-columns: var(--education-compact-side-column) var(--education-middle-column) var(--education-compact-side-column);
  column-gap: 0;
  align-items: baseline;
}
.module-component-rows { display: grid; width: 100%; }
.module-component-row { display: grid; width: 100%; align-items: baseline; }
.module-component-cell { gap: 0.3em; overflow-wrap: anywhere; }
.module-component-cell.flow-inline .module-component + .module-component::before { content: ' · '; white-space: pre; }
.personal-info .module-component-cell.flow-inline .module-component + .module-component::before { content: ' | '; }
.module-component-cell.flow-inline .component-position + .component-job_type::before { content: ' '; }
.module-component.component-school { font-size: var(--entry-title-font-size); font-weight: var(--manual-title-font-weight); }
.module-component.component-organization,
.module-component.component-project_name { font-size: var(--entry-title-font-size); font-weight: var(--manual-title-font-weight); }
.module-component.component-name { font-size: var(--name-font-size); font-weight: var(--manual-name-font-weight); }
.module-component.component-target_position,
.module-component.component-personal_meta,
.module-component.component-contact,
.module-component.component-additional_fields { font-size: var(--meta-font-size); font-weight: var(--meta-font-weight); color: #333; }
.personal-info .component-photo { position: absolute; top: 0; right: 0; flex: none; width: var(--photo-width); height: var(--photo-height); object-fit: cover; }
.module-component.component-school_tags,
.module-component.component-degree,
.module-component.component-major,
.module-component.component-metrics,
.module-component.component-date,
.module-component.component-position,
.module-component.component-job_type { font-size: var(--label-font-size); font-weight: var(--manual-field-font-weight); }
.education-item .module-component.component-school_tags,
.education-item .module-component.component-degree,
.education-item .module-component.component-major,
.education-item .module-component.component-metrics,
.education-item .module-component.component-date { font-weight: var(--body-font-weight); }
.module-component.component-role { font-size: var(--meta-font-size); font-weight: var(--meta-font-weight); }
.education-item.preset-three-column .education-header {
  display: grid;
  width: 100%;
  grid-template-columns: var(--education-side-column) minmax(0, 1fr) var(--education-side-column);
  column-gap: 0;
  align-items: baseline;
}
.education-item.preset-compact .school-info,
.education-item.preset-three-column .school-info,
.education-item.preset-compact .education-middle-column,
.education-item.preset-three-column .education-middle-column,
.education-item.preset-compact .education-degree-column,
.education-item.preset-three-column .education-degree-column,
.education-item.preset-compact .education-metrics-column,
.education-item.preset-three-column .education-metrics-column { min-width: 0; }
.education-item.preset-compact .school-info,
.education-item.preset-three-column .school-info { grid-column: 1; grid-row: 1; gap: 0.3em; }
.education-item.preset-compact .education-middle-column,
.education-item.preset-three-column .education-middle-column {
  grid-column: 2;
  grid-row: 1;
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  column-gap: var(--education-metric-gap);
  row-gap: 0;
  text-align: left;
}
.education-item.preset-compact .graduation-date,
.education-item.preset-three-column .graduation-date {
  grid-column: 3;
  grid-row: 1;
  position: static;
  width: auto;
  min-width: 0;
  margin-right: 0;
  text-align: right;
}
.education-item.preset-compact .academic-metrics,
.education-item.preset-three-column .academic-metrics { margin-top: 0; }
.academic-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25em 1em;
  margin-top: 0.125em;
  font-size: var(--meta-font-size);
  color: #222;
  font-weight: var(--meta-font-weight);
}
.list-items {
  list-style: none;
  padding: 0;
  margin: 0;
}
.list-item {
  position: relative;
  padding-left: var(--list-text-indent);
  margin-bottom: 0.25em;
  font-size: var(--body-font-size);
  line-height: var(--line-height, 1.6);
}
.list-item::before {
  content: '•';
  position: absolute;
  left: 0;
  width: calc(var(--list-text-indent) - var(--list-marker-gap));
  text-align: center;
  color: #333;
  font-weight: bold;
}
.generic-list-item {
  position: relative;
  padding-left: var(--module-indent);
  margin-bottom: 0.25em;
  font-size: var(--body-font-size);
  line-height: var(--line-height, 1.6);
}
.generic-list-item::before {
  content: attr(data-marker);
  position: absolute;
  left: var(--module-indent);
  width: 1.75em;
  text-align: right;
  color: #333;
  font-weight: 400;
}
.generic-list-item.marker-bold::before { font-weight: var(--label-font-weight); }
.generic-list-item.list-style-bullet { padding-left: calc(var(--module-indent) + 1.15em); }
.generic-list-item.list-style-bullet::before { width: 0.9em; text-align: center; }
.generic-list-item.list-style-numbered { padding-left: calc(var(--module-indent) + 2em); }
.generic-list-item.list-style-paragraph::before { content: none; }
.page-content .section-title,
.content-source .section-title,
.print-container .section-title {
  margin-top: var(--module-margin);
  margin-bottom: var(--section-title-after);
  padding-bottom: var(--section-title-border-gap);
  color: #111;
  font-weight: var(--section-title-font-weight);
}
.page-content .education-item,
.page-content .work-item,
.page-content .project-item,
.content-source .education-item,
.content-source .work-item,
.content-source .project-item { margin-bottom: var(--item-spacing); }
.page-content .degree-major,
.page-content .position,
.page-content .project-role,
.page-content .graduation-date,
.page-content .work-period,
.page-content .list-item,
.page-content .generic-list-item,
.content-source .degree-major,
.content-source .position,
.content-source .project-role,
.content-source .graduation-date,
.content-source .work-period,
.content-source .list-item,
.content-source .generic-list-item { color: #111; }
.page-content .list-item,
.content-source .list-item,
.content-source .list-item { margin-bottom: var(--paragraph-spacing); }
.page-content .generic-list-item,
.content-source .generic-list-item { margin-bottom: var(--item-spacing); }
.project-content-block { margin: 0 0 var(--content-block-spacing); font-size: var(--body-font-size); color: #111; }
.project-paragraph { margin: 0; }
.project-block-label { margin-bottom: var(--content-label-spacing); font-size: var(--body-font-size); font-weight: 400; }
.project-inline-label,
.cert-lang-label,
.subfield-title { font-size: var(--body-font-size); }
.project-inline-label.is-bold,
.project-block-label.is-bold { font-weight: var(--label-font-weight); }
.list-item,
.generic-list-item,
.project-paragraph,
.project-numbered-list > li,
.self-eval-item {
  text-align: justify;
  text-justify: inter-ideograph;
}
.project-numbered-list {
  list-style: none;
  margin: 0;
  padding: 0;
  counter-reset: project-duty;
}
.project-content-block.has-semantic-label > .project-numbered-list,
.project-content-block.has-semantic-label > .list-items {
  margin-left: calc(var(--module-indent) + var(--list-text-indent));
}
.project-content-block:not(.has-semantic-label) > .project-numbered-list,
.project-content-block:not(.has-semantic-label) > .list-items { margin-left: var(--module-indent); }
.project-numbered-list > li {
  position: relative;
  margin-bottom: var(--numbered-item-spacing);
  padding-left: var(--list-text-indent);
  counter-increment: project-duty;
}
.project-numbered-list > li::before {
  content: '(' counter(project-duty) ')';
  position: absolute;
  left: 0;
  width: calc(var(--list-text-indent) - var(--list-marker-gap));
  text-align: right;
  white-space: nowrap;
  font-weight: 400;
}
.project-numbered-list > li.marker-bold::before { font-weight: var(--label-font-weight); }
.project-content-block.has-semantic-label > .project-paragraph,
.project-content-block.has-semantic-label > .project-block-label {
  position: relative;
  padding-left: calc(var(--module-indent) + var(--list-text-indent));
}
.project-content-block.has-semantic-label > .project-paragraph::before,
.project-content-block.has-semantic-label > .project-block-label::before {
  content: '•';
  position: absolute;
  left: var(--module-indent);
  width: calc(var(--list-text-indent) - var(--list-marker-gap));
  text-align: center;
  font-weight: 700;
}
.details-paragraph .list-item { padding-left: 0; list-style: none; }
.details-paragraph .list-item::before { content: none; }
.work-item.date-inline .work-header,
.project-item.date-inline .project-header { justify-content: flex-start; }
.work-item.date-inline .work-period,
.project-item.date-inline .project-role { margin-left: 0.55em; }
.others-tags .other-value {
  display: inline-block;
  padding: 0.08em 0.45em;
  margin: 0.1em 0.2em 0.1em 0;
  border: 1px solid #9ca3af;
  border-radius: 999px;
}
.others-tags .cert-lang-separator { display: none; }
.others-stacked { display: flex; flex-direction: column; align-items: flex-start; }
.self-bullets { position: relative; padding-left: var(--list-text-indent); }
.self-bullets::before {
  content: '•';
  position: absolute;
  left: 0;
  width: calc(var(--list-text-indent) - var(--list-marker-gap));
  text-align: center;
  font-weight: 700;
}
.self-eval-item {
  font-size: var(--body-font-size);
  line-height: var(--line-height, 1.6);
  color: #212529;
}
.others-title {
  font-size: var(--body-font-size);
  font-weight: var(--label-font-weight);
  color: #212529;
  margin: 0 0 0.25em 0;
}
.skill-section,
.cert-section,
.lang-section {
  margin-bottom: var(--module-margin, 0.5em);
}
.skill-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5em;
}
.skill-item,
.cert-lang-line,
.inline-item {
  font-size: var(--body-font-size);
  color: #212529;
  word-wrap: break-word;
  overflow-wrap: break-word;
  max-width: 100%;
}
.cert-lang-label {
  font-weight: var(--label-font-weight);
  margin-right: 0.25em;
}
.cert-lang-separator {
  color: #333;
  margin: 0 0.25em;
}
.skills-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5em;
}
.thesis-item {
  margin-top: 0.25em;
}
.thesis-title {
  font-weight: var(--label-font-weight);
  font-size: var(--body-font-size);
}
.subfield-title {
  font-size: var(--meta-font-size);
  font-weight: var(--label-font-weight);
  color: #6c757d;
  margin-bottom: 0.25em;
  display: block;
}
.inline-list {
  display: inline;
}
.inline-item:not(:last-child)::after {
  content: '·';
  color: #333;
  font-weight: bold;
  margin-left: 0.5em;
  margin-right: 0.5em;
}
:deep(b) {
  font-weight: var(--label-font-weight);
}
.page-footer {
  position: absolute;
  bottom: 15px;
  right: 20px;
  font-size: 10pt;
  color: #6c757d;
}
/* PC端页面指示器 - 保持原来的定位方式 */
@media (min-width: 1200px) {
  .page-indicator {
    position: absolute;
    right: 20px;
    bottom: 30px;
    color: #6c757d;
    font-size: 12px;
  }
}
.no-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  color: #aeb3bf;
  font-size: 1.1rem;
  gap: 1rem;
}

.no-data .jd-upload-btn {
  margin-top: 0.5rem;
  border-color: rgba(132, 169, 255, 0.72);
  color: #e4edff;
  background: rgba(95, 143, 242, 0.2);
  box-shadow: 0 0 0 1px rgba(95, 143, 242, 0.08) inset;
}

.no-data .jd-upload-btn:hover {
  border-color: #8fb1ff;
  color: #fff;
  background: rgba(95, 143, 242, 0.32);
}

/* 成功提示弹窗 */
.success-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.3s ease;
}

.success-dialog {
  background: white;
  border-radius: var(--radius-lg);
  padding: 32px;
  max-width: 420px;
  width: 90%;
  text-align: center;
  box-shadow: var(--shadow-lg);
  animation: slideUp 0.3s ease;
}

.success-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 20px;
  background: #f0f9f0;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.success-icon svg {
  width: 32px;
  height: 32px;
  color: #22c55e;
}

.layout-guide-overlay { padding: 24px; background: rgba(7, 8, 11, 0.72); }
.font-size-overlay {
  right: auto;
  left: 156px;
  width: calc((100vw - 156px) * 0.39);
  justify-content: flex-end;
  padding: 24px 0 24px 16px;
  background: rgba(7, 8, 11, 0.16);
}
.inline-label { font-size: var(--label-font-size); }
.font-size-dialog {
  width: min(390px, calc(100vw - 40px));
  max-height: calc(100vh - 48px);
  padding: 18px;
  overflow: visible;
  border: 1px solid #454852;
  border-radius: 14px;
  color: #f5f6f8;
  background: #25262c;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
}
.font-size-dialog .layout-guide-header h3 { color: #fff; }
.font-size-dialog .layout-guide-header p { color: #b9bdc8; }
.font-size-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
  margin-top: 14px;
}
.font-size-field {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 72px;
  align-items: center;
  gap: 6px;
  padding: 8px 9px;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 9px;
  color: #e7e9ee;
  background: rgba(255, 255, 255, 0.035);
  font-size: 0.76rem;
}
.font-size-picker { position: relative; min-width: 0; }
.font-size-picker-trigger {
  width: 100%;
  height: 30px;
  padding: 0 7px;
  border: 0;
  border-radius: 6px;
  color: #f3f4f7;
  background: #30323a;
  font: inherit;
  cursor: pointer;
}
.font-size-picker-trigger i { margin-left: 3px; color: #9499a6; font-style: normal; }
.font-size-options {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 4;
  display: grid;
  width: 72px;
  height: 144px;
  padding: 4px;
  overflow-y: auto;
  background: #30323a;
  border-radius: 7px;
  box-shadow: 0 12px 28px rgba(0, 0, 0, .42);
}
.font-size-options button {
  min-height: 27px;
  padding: 0 5px;
  border: 0;
  border-radius: 5px;
  color: #dfe2e9;
  background: transparent;
  font-size: 0.72rem;
  cursor: pointer;
}
.font-size-options button:hover,
.font-size-options button.selected { color: #fff; background: #4b5363; }
.font-size-options::-webkit-scrollbar { width: 5px; }
.font-size-options::-webkit-scrollbar-thumb { background: #626977; border-radius: 999px; }
.font-size-options::-webkit-scrollbar-track { background: transparent; }
.font-size-warning,
.font-size-error {
  margin-top: 14px;
  padding: 9px 11px;
  border-radius: 8px;
  font-size: 0.78rem;
  line-height: 1.5;
}
.font-size-warning { color: #ffd8a8; background: rgba(180, 83, 9, 0.2); }
.font-size-error { color: #fecaca; background: rgba(185, 28, 28, 0.2); }
.font-size-actions {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 16px;
}
.font-size-action-spacer { flex: 1; }
.settings-dialog-action {
  width: 76px;
  min-width: 76px;
  height: 34px;
  padding: 0;
  border: 0;
  border-radius: 7px;
  color: #e8eaf0;
  background: #343740;
  font-size: 0.78rem;
  cursor: pointer;
}
.settings-dialog-action.primary { color: #fff; background: #4d6fb8; }
.font-size-actions .font-size-reset { color: #d2d6df; background: #343740; }
.font-size-actions button:disabled { opacity: 0.5; cursor: default; }
.section-order-overlay {
  right: auto;
  left: 156px;
  width: calc((100vw - 156px) * 0.39);
  justify-content: flex-end;
  padding: 24px 0 24px 16px;
  background: rgba(7, 8, 11, 0.16);
}
.section-order-dialog {
  width: min(340px, calc(100vw - 40px));
  max-height: min(680px, calc(100vh - 48px));
  padding: 18px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  color: #f4f5f8;
  background: #25262c;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
  display: flex;
  flex-direction: column;
}
.section-order-dialog .layout-guide-header h3 { color: #fff; }
.section-order-dialog .layout-guide-header p { color: #aeb1bb; }
.section-order-list {
  min-height: 180px;
  max-height: 410px;
  margin-top: 12px;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.section-order-dialog-row {
  min-height: 38px;
  margin-bottom: 5px;
  padding: 5px 8px;
  cursor: grab;
}
.section-order-name {
  font-size: 0.82rem;
  font-weight: 600;
}
.section-order-dialog-row:active { cursor: grabbing; }
.section-order-dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 16px;
}
.section-order-dialog-row.education-child-row {
  width: calc(100% - 24px);
  margin-left: 24px;
  box-sizing: border-box;
  background: rgba(255, 255, 255, 0.035);
}
.section-settings-overlay {
  right: auto;
  left: 156px;
  width: calc((100vw - 156px) * 0.39);
  justify-content: flex-end;
  padding: 24px 0 24px 16px;
  background: rgba(7, 8, 11, 0.16);
}
.section-settings-dialog {
  width: min(390px, calc(100vw - 40px));
  height: min(480px, calc(100vh - 96px));
  max-height: calc(100vh - 96px);
  box-sizing: border-box;
  padding: 18px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  color: #f4f5f8;
  background: #25262c;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
  display: flex;
  flex-direction: column;
}
.section-settings-dialog .layout-guide-header h3 { margin-bottom: 0; }
.section-settings-body { margin-top: 12px; min-height: 0; overflow-y: auto; }
.section-settings-body section + section { margin-top: 16px; }
.section-settings-body h4 { margin: 0 0 8px; color: #dfe2e9; font-size: 0.82rem; }
.section-setting-row {
  display: grid;
  grid-template-columns: minmax(92px, 0.8fr) minmax(0, 1.2fr);
  align-items: center;
  gap: 8px;
  margin-bottom: 7px;
  color: #cdd1da;
  font-size: 0.78rem;
}
.section-setting-row input,
.section-setting-row select {
  width: 85%;
  height: 34px;
  box-sizing: border-box;
  border: 0;
  border-radius: 7px;
  padding: 0 9px;
  color: #f3f4f7;
  background: #30323a;
  font: inherit;
}
.section-settings-note {
  margin: 2px 0 0;
  color: #aeb0b9;
  font-size: 0.78rem;
  line-height: 1.4;
}
@media (max-width: 820px) {
  .font-size-overlay {
    right: 0;
    left: 0;
    width: 100%;
    justify-content: center;
    padding: 16px;
    background: rgba(7, 8, 11, 0.62);
  }
  .font-size-dialog { width: min(390px, calc(100vw - 32px)); padding: 18px; overflow-y: auto; }
  .font-size-grid { grid-template-columns: 1fr; }
  .section-order-overlay,
  .section-settings-overlay {
    right: 0;
    left: 0;
    width: 100%;
    justify-content: center;
    padding: 16px;
    background: rgba(7, 8, 11, 0.62);
  }
  .section-order-dialog {
    width: min(340px, calc(100vw - 32px));
    max-height: calc(100vh - 32px);
  }
  .section-settings-dialog { width: min(390px, calc(100vw - 32px)); height: min(440px, calc(100vh - 48px)); max-height: calc(100vh - 48px); }
}
.font-size-dialog,
.section-order-dialog,
.section-settings-dialog { position: relative; }
.layout-guide-header { display: flex; justify-content: space-between; gap: 24px; padding-right: 38px; }
.layout-guide-header h3 { margin: 0 0 8px; font-size: 18px; }
.layout-guide-header p { margin: 0; color: #aeb3c0; font-size: 13px; line-height: 1.6; }
.layout-guide-close {
  position: absolute;
  top: 6px;
  right: 6px;
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 0;
  color: #d8dbe2;
  background: transparent;
  box-shadow: none;
  appearance: none;
  font-size: 24px;
  cursor: pointer;
}
.layout-guide-close:hover,
.layout-guide-close:focus-visible {
  color: #ffffff;
  background: transparent;
  outline: none;
  box-shadow: none;
}
.success-icon.error-icon {
  color: #b64d52;
  font-size: 28px;
  font-weight: 600;
  background: #fff0f0;
}

.success-dialog h3 {
  margin: 0 0 16px;
  font-size: 1.25rem;
  font-weight: 600;
  color: #212529;
}

.success-dialog p {
  margin: 0 0 24px;
  font-size: 0.95rem;
  color: #6c757d;
  line-height: 1.6;
}

.success-dialog .confirm-btn {
  background: #212529;
  color: white;
  border: none;
  padding: 12px 32px;
  border-radius: var(--radius-md);
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.success-dialog .confirm-btn:hover {
  background: #495057;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ========== 模块高亮动画 - AI风格蓝紫色炫光 ========== */

/* 模块高亮边框脉冲动画 */
.module-highlight {
  position: relative;
  animation: borderPulse 2s ease-in-out infinite;
}

@keyframes borderPulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(6, 182, 212, 0);
  }
  25% {
    box-shadow: 0 0 0 2px rgba(6, 182, 212, 0.3), 0 0 10px rgba(139, 92, 246, 0.2);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(6, 182, 212, 0.2), 0 0 20px rgba(139, 92, 246, 0.3);
  }
  75% {
    box-shadow: 0 0 0 2px rgba(6, 182, 212, 0.3), 0 0 10px rgba(139, 92, 246, 0.2);
  }
}

/* 标题文字炫光动画 */
.title-highlight {
  position: relative;
  background: linear-gradient(
    90deg,
    #212529 0%,
    #06b6d4 25%,
    #8b5cf6 50%,
    #06b6d4 75%,
    #212529 100%
  );
  background-size: 200% 100%;
  background-clip: text;
  -webkit-background-clip: text;
  color: transparent;
  animation: titleShimmer 2.5s ease-in-out infinite;
  display: inline-block;
}

@keyframes titleShimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}
</style>

<!-- 全局样式 - 用于动态添加的高亮类 -->
<style>
/* ========== 模块高亮动画 - 全局样式（用于动态添加的类） ========== */

/* 模块高亮边框脉冲动画 */
:global(.module-highlight) {
  position: relative;
  animation: borderPulseGlobal 2s ease-in-out infinite;
}

@keyframes borderPulseGlobal {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(6, 182, 212, 0);
  }
  25% {
    box-shadow: 0 0 0 2px rgba(6, 182, 212, 0.3), 0 0 10px rgba(139, 92, 246, 0.2);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(6, 182, 212, 0.2), 0 0 20px rgba(139, 92, 246, 0.3);
  }
  75% {
    box-shadow: 0 0 0 2px rgba(6, 182, 212, 0.3), 0 0 10px rgba(139, 92, 246, 0.2);
  }
}

/* 标题文字炫光动画 - 使用 :global() 配合父选择器提高优先级 */
:global(.resume-wrapper .title-highlight),
:global(.preview-content .title-highlight),
:global(.pages-wrapper .title-highlight) {
  background: linear-gradient(
    90deg,
    #212529 0%,
    #06b6d4 25%,
    #8b5cf6 50%,
    #06b6d4 75%,
    #212529 100%
  ) !important;
  background-size: 200% 100% !important;
  -webkit-background-clip: text !important;
  background-clip: text !important;
  color: transparent !important;
  animation: titleShimmerGlobal 2.5s ease-in-out infinite;
  display: inline-block !important;
  background-repeat: repeat-y !important;
}

@keyframes titleShimmerGlobal {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}

/* 内容项动画 - 淡入闪烁效果 */
:global(.resume-wrapper .content-highlight),
:global(.preview-content .content-highlight),
:global(.pages-wrapper .content-highlight) {
  animation: contentPulseGlobal 2s ease-in-out infinite;
  border-radius: 4px;
}

@keyframes contentPulseGlobal {
  0%, 100% {
    background-color: transparent;
  }
  25% {
    background-color: rgba(6, 182, 212, 0.1);
  }
  50% {
    background-color: rgba(139, 92, 246, 0.15);
  }
  75% {
    background-color: rgba(6, 182, 212, 0.1);
  }
}

/* ==================== 移动端适配（0-1200px统一使用移动端样式） ==================== */
@media (max-width: 1200px) {
  .resume-wrapper {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  /* 窄屏仍使用桌面端同一工具栏，并固定在预览上方。 */
  .resume-toolbar-wrapper {
    position: sticky;
    top: 0;
    bottom: auto;
    z-index: 999;
    background: rgba(30, 31, 36, 0.98);
    border-top: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.09);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.24);
  }

  .resume-toolbar {
    flex-wrap: wrap;
    height: auto;
    min-height: 52px;
    justify-content: flex-end;
    padding: 6px 8px;
    gap: 6px;
    overflow: visible;
  }

  .compact-toolbar-cluster {
    min-width: 0;
    max-width: 100%;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .compact-toolbar-btn,
  .compact-export-btn {
    min-height: 34px;
    color: #e4e6ed;
    border-color: rgba(255, 255, 255, 0.12);
  }

  .compact-popover {
    top: calc(100% + 8px);
    max-width: calc(100vw - 24px);
  }

  .jd-upload-btn {
    padding: 6px 12px;
    font-size: 11px;
  }

  .export-btn {
    padding: 6px 12px;
    font-size: 11px;
  }

  /* 预览内容区域适配 */
  .preview-content {
    padding: 8px;
    flex: 1;
    overflow-y: auto;
    height: auto;
    min-height: 0;
    box-sizing: border-box;
  }

  /* 移动端页面指示器 */
  .page-indicator {
    position: fixed;
    bottom: 80px;
    right: 12px;
    background: rgba(255, 255, 255, 0.95);
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 10px;
    line-height: 1;
    z-index: 1001;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
    white-space: nowrap;
  }

}
</style>
