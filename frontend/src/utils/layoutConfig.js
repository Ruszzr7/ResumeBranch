import { normalizeContentBlock } from './resumeContract.js'
import { isFullyBoldInlineText, joinInlineWithInheritedSeparator, plainInlineText } from './inlineFormatting.js'

export const MODULE_COMPONENTS = Object.freeze({
  basics: ['name', 'target_position', 'personal_meta', 'contact', 'additional_fields', 'photo'],
  education: ['school', 'school_tags', 'degree', 'major', 'metrics', 'date', 'theses'],
  skills: ['items'], research_interests: ['items'], honors: ['items'], publications: ['items'],
  work_experience: ['organization', 'position', 'job_type', 'date', 'content'],
  project_experience: ['project_name', 'role', 'date', 'content'],
  custom_sections: ['items'], others: ['certificates', 'languages'], self_evaluation: ['items']
})

// Fixed physical clearance between the photo bottom and the first visible
// section divider.  The preview and PDF measurement paths use the same value;
// Word keeps its existing table-specific resolver.
export const PHOTO_BOTTOM_GAP_MM = 1.5

const REQUIRED_COMPONENTS = Object.freeze({
  basics: ['name'], education: ['school'], skills: ['items'], research_interests: ['items'], honors: ['items'], publications: ['items'],
  work_experience: ['organization', 'content'],
  project_experience: ['project_name', 'content'], custom_sections: ['items'], others: [], self_evaluation: ['items']
})

const LONG_TEXT_COMPONENTS = new Set([
  'education.theses', 'work_experience.content', 'project_experience.content',
  'skills.items', 'research_interests.items', 'honors.items', 'publications.items', 'custom_sections.items', 'self_evaluation.items'
])

export const DEFAULT_COMPONENT_ROWS = Object.freeze({
  basics: [
    { cells: [{ components: ['name'], flow: 'stacked', width: 'fill', alignment: 'left' }, { components: ['photo'], flow: 'stacked', width: 'content', alignment: 'right' }] },
    { cells: [{ components: ['target_position'], flow: 'stacked', width: 'fill', alignment: 'left' }] },
    { cells: [{ components: ['personal_meta', 'contact', 'additional_fields'], flow: 'inline', width: 'fill', alignment: 'left' }] }
  ],
  education: [
    { cells: [{ components: ['school', 'school_tags'], flow: 'inline', width: 'content', alignment: 'left' }, { components: ['degree', 'major', 'metrics'], flow: 'inline', width: 'fill', alignment: 'left' }, { components: ['date'], flow: 'inline', width: 'content', alignment: 'right' }] },
    { cells: [{ components: ['theses'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }
  ],
  work_experience: [
    { cells: [{ components: ['organization', 'position', 'job_type'], flow: 'inline', width: 'fill', alignment: 'left' }, { components: ['date'], flow: 'inline', width: 'content', alignment: 'right' }] },
    { cells: [{ components: ['content'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }
  ],
  project_experience: [
    { cells: [{ components: ['project_name', 'role'], flow: 'inline', width: 'fill', alignment: 'left' }, { components: ['date'], flow: 'inline', width: 'content', alignment: 'right' }] },
    { cells: [{ components: ['content'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }
  ],
  skills: [{ cells: [{ components: ['items'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }],
  research_interests: [{ cells: [{ components: ['items'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }],
  honors: [{ cells: [{ components: ['items'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }],
  publications: [{ cells: [{ components: ['items'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }],
  custom_sections: [{ cells: [{ components: ['items'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }],
  // Certificates and languages are separate semantic lines.  Each field still
  // joins its own entries with the configured separator, but the two labels
  // must never be rendered on the same line.
  others: [
    { cells: [{ components: ['certificates'], flow: 'stacked', width: 'fill', alignment: 'left' }] },
    { cells: [{ components: ['languages'], flow: 'stacked', width: 'fill', alignment: 'left' }] }
  ],
  self_evaluation: [{ cells: [{ components: ['items'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }]
})

const moduleContract = (moduleId, values = {}) => ({
  titleStyle: null, titleAlignment: null,
  paragraphSpacing: 0.09, itemSpacing: 0.22, contentBlockSpacing: 0.14, rowSpacing: 0,
  indentLevel: 0,
  hiddenComponents: [], componentRows: JSON.parse(JSON.stringify(DEFAULT_COMPONENT_ROWS[moduleId])), ...values
})

const LEGACY_V7_DEFAULT_SECTION_ORDER = [
  'education', 'skills', 'research_interests', 'honors', 'publications',
  'work_experience', 'project_experience', 'custom_sections', 'others', 'self_evaluation'
]

export const DEFAULT_LAYOUT_CONFIG = Object.freeze({
  version: 10,
  typography: {
    preset: 'microsoft-office',
    latinFont: 'Arial',
    eastAsiaFont: 'Microsoft YaHei',
    fallbackFonts: ['Noto Sans CJK SC', 'sans-serif'],
    fontSizes: { name: 14, sectionTitle: 11, entryTitle: 10, meta: 9, body: 9, label: 9 }
  },
  global: {
    density: 'compact', fontSize: 9, lineHeight: 1.25, moduleMargin: 0.5,
    marginVertical: 8.5, marginHorizontal: 9, titleStyle: 'underline',
    sectionOrder: ['education', 'honors', 'publications', 'research_interests', 'skills', 'work_experience', 'project_experience', 'custom_sections', 'others', 'self_evaluation'],
    hiddenSections: [], titleOverrides: {}, sectionPlacements: {}
  },
  basics: moduleContract('basics', {
    photoPosition: 'right',
    // Photo height is the only user-facing size control. Width is derived from
    // the imported image's aspect ratio at render time.
    photoHeightMm: 26, photoWidthMm: 21, hiddenFields: []
  }),
  education: moduleContract('education', { schoolTagStyle: 'text', hiddenMetrics: [], thesisDisplay: 'expanded', supplementListStyle: 'bullet' }),
  skills: moduleContract('skills', { listStyle: 'bullet' }),
  research_interests: moduleContract('research_interests', { listStyle: 'bullet' }),
  honors: moduleContract('honors', { listStyle: 'bullet' }),
  publications: moduleContract('publications', { listStyle: 'bullet' }),
  work_experience: moduleContract('work_experience', { detailsStyle: 'bullets', datePosition: 'right', showJobType: true }),
  project_experience: moduleContract('project_experience', { detailsStyle: 'bullets', datePosition: 'right', showRole: true, showDate: true }),
  custom_sections: moduleContract('custom_sections', { listStyle: 'bullet' }),
  others: moduleContract('others', { fieldOrder: ['skills', 'certificates', 'languages'], hiddenFields: [], separator: 'dot' }),
  self_evaluation: moduleContract('self_evaluation', { listStyle: 'paragraph' })
})

const clone = value => JSON.parse(JSON.stringify(value))

export const FONT_SIZE_LIMITS = Object.freeze({
  name: [12, 20],
  sectionTitle: [9, 16],
  entryTitle: [8.5, 14],
  meta: [8, 11.5],
  body: [8, 11.5],
  label: [8, 12]
})
export const FONT_SIZE_LABELS = Object.freeze({
  name: '姓名', sectionTitle: '模块标题', entryTitle: '条目标题',
  meta: '用户信息', body: '正文内容', label: '字段标签'
})
const semanticFontSizes = body => ({
  name: 14, sectionTitle: body + 2, entryTitle: body + 1,
  meta: body, body, label: body
})
const SECTION_IDS = new Set([
  'education', 'honors', 'publications', 'research_interests', 'skills', 'work_experience',
  'project_experience', 'custom_sections', 'others', 'self_evaluation'
])
const CUSTOM_SECTION_MODULE_RE = /^custom_sections:(\d+)$/

export const customSectionModuleId = index => `custom_sections:${Math.max(0, Number(index) || 0)}`

export function customSectionIndex(moduleId) {
  const match = CUSTOM_SECTION_MODULE_RE.exec(String(moduleId || ''))
  return match ? Number(match[1]) : null
}

export function isCustomSectionModule(moduleId) {
  return customSectionIndex(moduleId) !== null
}

const isValidSectionId = value => SECTION_IDS.has(value) || isCustomSectionModule(value)
const ENUMS = Object.freeze({
  'typography.preset': ['microsoft-office'],
  'global.density': ['compact', 'standard', 'comfortable'],
  'global.titleStyle': ['underline', 'plain'],
  'basics.photoPosition': ['right', 'hidden'],
  'education.schoolTagStyle': ['filled', 'outline', 'text', 'hidden'],
  'education.thesisDisplay': ['expanded', 'compact', 'hidden'],
  'education.supplementListStyle': ['paragraph', 'bullet', 'numbered'],
  'work_experience.detailsStyle': ['bullets', 'paragraph'],
  'work_experience.datePosition': ['right', 'inline'],
  'project_experience.detailsStyle': ['bullets', 'paragraph'],
  'project_experience.datePosition': ['right', 'inline'],
  'others.separator': ['pipe', 'dot'],
})
const ALLOWED_HIDDEN_FIELDS = Object.freeze({
  basics: new Set(['gender', 'birth_date', 'phone', 'email', 'target_position', 'photo', 'additional_fields']),
  education: new Set(['gpa', 'ranking']),
  others: new Set(['skills', 'certificates', 'languages'])
})

function mergeKnown(target, source, template) {
  if (!source || typeof source !== 'object') return
  for (const key of Object.keys(template)) {
    if (!(key in source)) continue
    if (template[key] && typeof template[key] === 'object' && !Array.isArray(template[key]) && source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
      mergeKnown(target[key], source[key], template[key])
    } else {
      target[key] = clone(source[key])
    }
  }
}

function legacyComponentRows(moduleId, config) {
  const rows = clone(DEFAULT_COMPONENT_ROWS[moduleId])
  if (moduleId === 'work_experience' && config.datePosition === 'inline') {
    rows[0] = { cells: [{ components: ['organization', 'position', 'job_type', 'date'], flow: 'inline', width: 'fill', alignment: 'left' }] }
  }
  if (moduleId === 'project_experience' && config.datePosition === 'inline') {
    rows[0] = { cells: [{ components: ['project_name', 'role', 'date'], flow: 'inline', width: 'fill', alignment: 'left' }] }
  }
  return rows
}

function normalizeComponentRows(moduleId, supplied, fallback, hidden) {
  const allowed = new Set(MODULE_COMPONENTS[moduleId])
  const seen = new Set()
  const rows = []
  const candidates = Array.isArray(supplied) ? supplied : []
  for (const rawRow of candidates.slice(0, 12)) {
    if (!rawRow || !Array.isArray(rawRow.cells)) continue
    const cells = []
    for (const rawCell of rawRow.cells.slice(0, 3)) {
      if (!rawCell || typeof rawCell !== 'object') continue
      let components = (Array.isArray(rawCell.components) ? rawCell.components : [])
        .filter(component => allowed.has(component) && !hidden.has(component) && !seen.has(component))
      if (!components.length) continue
      const containsLongText = components.some(component => LONG_TEXT_COMPONENTS.has(`${moduleId}.${component}`))
      let alignment
      let width
      let flow
      if (containsLongText) {
        components = components.filter(component => LONG_TEXT_COMPONENTS.has(`${moduleId}.${component}`))
        alignment = ['left', 'justify'].includes(rawCell.alignment) ? rawCell.alignment : 'justify'
        width = 'fill'
        flow = 'stacked'
      } else {
        alignment = ['left', 'center', 'right'].includes(rawCell.alignment) ? rawCell.alignment : 'left'
        width = ['content', 'fill', 'equal'].includes(rawCell.width) ? rawCell.width : 'fill'
        flow = ['inline', 'stacked'].includes(rawCell.flow) ? rawCell.flow : 'inline'
      }
      if (components.includes('photo')) {
        components = ['photo']; width = 'content'; flow = 'stacked'; alignment = 'right'
      }
      components.forEach(component => seen.add(component))
      cells.push({ components, flow, width, alignment })
    }
    if (cells.length) {
      const longCell = cells.find(cell => cell.components.some(component => LONG_TEXT_COMPONENTS.has(`${moduleId}.${component}`)))
      rows.push({ cells: longCell ? [longCell] : cells })
    }
  }
  const missing = MODULE_COMPONENTS[moduleId].filter(component => !seen.has(component) && !hidden.has(component))
  if (missing.length) {
    for (const fallbackRow of fallback) {
      const cells = fallbackRow.cells.map(cell => ({ ...clone(cell), components: cell.components.filter(component => missing.includes(component)) }))
        .filter(cell => cell.components.length)
      if (cells.length) rows.push({ cells })
    }
  }
  return rows.length ? rows : clone(fallback)
}

function normalizeOtherComponentRows(rows) {
  const cellByComponent = new Map()
  for (const row of rows || []) {
    for (const cell of row?.cells || []) {
      for (const component of cell.components || []) {
        if (!cellByComponent.has(component)) cellByComponent.set(component, cell)
      }
    }
  }
  return ['certificates', 'languages'].map(component => {
    const source = cellByComponent.get(component) || DEFAULT_COMPONENT_ROWS.others[component === 'certificates' ? 0 : 1].cells[0]
    return {
      cells: [{
        ...source,
        components: [component],
        flow: 'stacked',
        width: 'fill',
        alignment: 'left'
      }]
    }
  })
}

function normalizeModuleContracts(result, source, suppliedVersion, bounded) {
  for (const moduleId of Object.keys(MODULE_COMPONENTS)) {
    const module = result[moduleId]
    module.titleStyle = null
    module.titleAlignment = null
    module.paragraphSpacing = bounded(module.paragraphSpacing, 0, 1.5, 0.09)
    module.itemSpacing = bounded(module.itemSpacing, 0, 2, 0.22)
    module.contentBlockSpacing = bounded(module.contentBlockSpacing, 0, 2, 0.14)
    module.rowSpacing = bounded(module.rowSpacing, 0, 2, 0)
    module.indentLevel = Math.min(3, Math.max(0, Math.trunc(Number(module.indentLevel) || 0)))
    if (moduleId === 'education' && !['paragraph', 'bullet', 'numbered'].includes(module.supplementListStyle)) {
      module.supplementListStyle = DEFAULT_LAYOUT_CONFIG.education.supplementListStyle
    }
    const required = new Set(REQUIRED_COMPONENTS[moduleId])
    const hidden = new Set((Array.isArray(module.hiddenComponents) ? module.hiddenComponents : [])
      .filter(component => MODULE_COMPONENTS[moduleId].includes(component) && !required.has(component)))
    module.hiddenComponents = MODULE_COMPONENTS[moduleId].filter(component => hidden.has(component))
    const fallback = suppliedVersion < 7 ? legacyComponentRows(moduleId, module) : clone(DEFAULT_COMPONENT_ROWS[moduleId])
    const rawModule = source?.[moduleId] && typeof source[moduleId] === 'object' ? source[moduleId] : {}
    const rawRows = ['basics', 'education'].includes(moduleId)
      ? clone(DEFAULT_COMPONENT_ROWS[moduleId])
      : (suppliedVersion >= 7 ? rawModule.componentRows : fallback)
    module.componentRows = normalizeComponentRows(moduleId, rawRows, fallback, hidden)
    if (moduleId === 'others') module.componentRows = normalizeOtherComponentRows(module.componentRows)
  }
}

export function normalizeLayoutConfig(value = {}) {
  const suppliedVersion = Number(value?.version || 1)
  const result = clone(DEFAULT_LAYOUT_CONFIG)
  mergeKnown(result, value, DEFAULT_LAYOUT_CONFIG)
  result.version = DEFAULT_LAYOUT_CONFIG.version
  const suppliedGlobal = value?.global || {}
  if (suppliedVersion < 2 && ['fontSize', 'lineHeight', 'moduleMargin', 'marginVertical']
    .every((field, index) => Number(suppliedGlobal[field] ?? [11, 1.6, 1, 9][index]) === [11, 1.6, 1, 9][index])) {
    Object.assign(result.global, { density: 'compact', fontSize: 10.5, lineHeight: 1.32, moduleMargin: 0.45, marginVertical: 8 })
  }
  // v1-v3 used fontSize as a root CSS size while most resume text rendered at
  // 0.8em. v4 stores the actual body size and derives the hierarchy from it.
  if (suppliedVersion < 4) {
    const legacyFontSize = Number('fontSize' in suppliedGlobal ? result.global.fontSize : 10.5)
    result.global.fontSize = legacyFontSize === 10.5
      ? 9
      : Math.round(legacyFontSize * 0.8 * 2) / 2
    const legacyLineHeight = Number('lineHeight' in suppliedGlobal ? result.global.lineHeight : 1.32)
    const legacyModuleMargin = Number('moduleMargin' in suppliedGlobal ? result.global.moduleMargin : 0.45)
    if (legacyLineHeight === 1.32) result.global.lineHeight = 1.28
    if (legacyModuleMargin === 0.45) result.global.moduleMargin = 0.55
  }
  const boundedConfigNumber = (candidate, min, max, fallback) => {
    const number = Number(candidate)
    return Number.isFinite(number) ? Math.min(Math.max(number, min), max) : fallback
  }
  for (const [path, allowed] of Object.entries(ENUMS)) {
    const [section, key] = path.split('.')
    if (!allowed.includes(result[section][key])) result[section][key] = clone(DEFAULT_LAYOUT_CONFIG[section][key])
  }
  result.global.fontSize = Math.round(boundedConfigNumber(result.global.fontSize, 8, 11.5, 9) * 2) / 2
  // v6 restores the compact standard-density line rhythm used by the
  // established one-page export baseline. Explicit non-default values remain.
  if (suppliedVersion < 6 && result.global.density === 'standard' && Number(result.global.lineHeight) === 1.35) {
    result.global.lineHeight = 1.28
  }
  result.global.lineHeight = boundedConfigNumber(result.global.lineHeight, 1, 1.8, 1.25)
  result.global.moduleMargin = boundedConfigNumber(result.global.moduleMargin, 0.1, 1, 0.5)
  result.global.marginVertical = boundedConfigNumber(result.global.marginVertical, 3, 12, 9)
  result.global.marginHorizontal = boundedConfigNumber(result.global.marginHorizontal, 3, 12, 9)
  if (suppliedVersion < 8 && Array.isArray(result.global.sectionOrder)
      && result.global.sectionOrder.join('|') === LEGACY_V7_DEFAULT_SECTION_ORDER.join('|')) {
    result.global.sectionOrder = [...DEFAULT_LAYOUT_CONFIG.global.sectionOrder]
  }
  result.global.sectionOrder = [...new Set((Array.isArray(result.global.sectionOrder) ? result.global.sectionOrder : [])
    .filter(item => isValidSectionId(item)))]
  const insertAfter = (item, anchor) => {
    if (result.global.sectionOrder.includes(item)) return
    const index = result.global.sectionOrder.indexOf(anchor)
    result.global.sectionOrder.splice(index >= 0 ? index + 1 : result.global.sectionOrder.length, 0, item)
  }
  insertAfter('honors', 'education')
  insertAfter('publications', 'honors')
  insertAfter('research_interests', 'publications')
  insertAfter('skills', 'research_interests')
  const hasCustomSectionModules = result.global.sectionOrder.some(isCustomSectionModule)
  if (!hasCustomSectionModules) insertAfter('custom_sections', 'project_experience')
  for (const item of SECTION_IDS) {
    if (item === 'custom_sections' && hasCustomSectionModules) continue
    insertAfter(item)
  }
  result.global.hiddenSections = [...new Set(
    (Array.isArray(result.global.hiddenSections) ? result.global.hiddenSections : []).filter(item => isValidSectionId(item))
  )]
  const cleanTitles = {}
  const suppliedTitles = suppliedGlobal.titleOverrides ?? result.global.titleOverrides
  if (suppliedTitles && typeof suppliedTitles === 'object' && !Array.isArray(suppliedTitles)) {
    for (const [section, translations] of Object.entries(suppliedTitles)) {
      if (!SECTION_IDS.has(section) || !translations || typeof translations !== 'object' || Array.isArray(translations)) continue
      const clean = {}
      for (const language of ['zh', 'en']) {
        const text = String(translations[language] || '').trim().slice(0, 40)
        if (text) clean[language] = text
      }
      if (Object.keys(clean).length) cleanTitles[section] = clean
    }
  }
  result.global.titleOverrides = cleanTitles
  for (const [section, allowed] of Object.entries(ALLOWED_HIDDEN_FIELDS)) {
    const key = section === 'education' ? 'hiddenMetrics' : 'hiddenFields'
    result[section][key] = [...new Set(
      (Array.isArray(result[section][key]) ? result[section][key] : []).filter(item => allowed.has(item))
    )]
  }
  const suppliedBasics = value?.basics && typeof value.basics === 'object' ? value.basics : {}
  result.basics.photoWidthMm = boundedConfigNumber(result.basics.photoWidthMm, 15, 30, 21)
  result.basics.photoHeightMm = boundedConfigNumber(
    Object.prototype.hasOwnProperty.call(suppliedBasics, 'photoHeightMm')
      ? result.basics.photoHeightMm
      : result.basics.photoWidthMm * 26 / 21,
    18, 45, 26
  )
  if (result.basics.photoPosition === 'hidden' && !result.basics.hiddenFields.includes('photo')) result.basics.hiddenFields.push('photo')
  if (result.basics.hiddenFields.includes('photo')) result.basics.photoPosition = 'hidden'
  result.others.fieldOrder = (Array.isArray(result.others.fieldOrder) ? result.others.fieldOrder : [])
    .filter(item => ALLOWED_HIDDEN_FIELDS.others.has(item))
  for (const item of ['skills', 'certificates', 'languages']) {
    if (!result.others.fieldOrder.includes(item)) result.others.fieldOrder.push(item)
  }
  result.work_experience.showJobType = Boolean(result.work_experience.showJobType)
  result.project_experience.showRole = Boolean(result.project_experience.showRole)
  result.project_experience.showDate = Boolean(result.project_experience.showDate)
  const suppliedFontSizes = value?.typography?.fontSizes
  if (suppliedVersion < 5 || !suppliedFontSizes || typeof suppliedFontSizes !== 'object' || Array.isArray(suppliedFontSizes)) {
    result.typography.fontSizes = semanticFontSizes(result.global.fontSize)
  }
  const roleDefaults = semanticFontSizes(result.global.fontSize)
  for (const [role, [min, max]] of Object.entries(FONT_SIZE_LIMITS)) {
    result.typography.fontSizes[role] = Math.round(
      boundedConfigNumber(result.typography.fontSizes[role], min, max, roleDefaults[role]) * 2
    ) / 2
  }
  result.typography.fontSizes.body = result.global.fontSize

  // The preset is deliberately curated: arbitrary font names would make the
  // browser, PDF worker and Word silently choose different fallbacks.
  const fontSizes = clone(result.typography.fontSizes)
  result.typography = clone(DEFAULT_LAYOUT_CONFIG.typography)
  result.typography.fontSizes = fontSizes
  const suppliedPlacements = suppliedGlobal.sectionPlacements ?? result.global.sectionPlacements
  const placements = suppliedPlacements && typeof suppliedPlacements === 'object' && !Array.isArray(suppliedPlacements)
    ? suppliedPlacements : {}
  result.global.sectionPlacements = Object.fromEntries(
    ['research_interests', 'honors', 'publications', 'others']
      .filter(section => placements[section] === 'education')
      .map(section => [section, 'education'])
  )

  for (const section of ['skills', 'research_interests', 'honors', 'publications', 'custom_sections', 'self_evaluation']) {
    if (!['paragraph', 'bullet', 'numbered'].includes(result[section].listStyle)) {
      result[section].listStyle = DEFAULT_LAYOUT_CONFIG[section].listStyle
    }
  }
  normalizeModuleContracts(result, value, suppliedVersion, boundedConfigNumber)
  return result
}

/**
 * Expand the legacy aggregate custom_sections module into one virtual module
 * per custom section. The stored layout remains backward compatible: old
 * configs may still contain the aggregate id, while newly saved configs can
 * persist custom_sections:<index> entries for independent ordering.
 */
export function expandSectionOrderForData(value = {}, data = {}) {
  const config = normalizeLayoutConfig(value)
  const customCount = Array.isArray(data?.custom_sections) ? data.custom_sections.length : 0
  const customIds = Array.from({ length: customCount }, (_, index) => customSectionModuleId(index))
  const rawOrder = [...(config.global.sectionOrder || [])]
  const expanded = []
  const seen = new Set()
  const push = section => {
    if (!section || seen.has(section)) return
    seen.add(section)
    expanded.push(section)
  }
  let customInserted = false
  for (const section of rawOrder) {
    if (section === 'custom_sections') {
      if (customCount) customIds.forEach(push)
      else push(section)
      customInserted = true
      continue
    }
    if (isCustomSectionModule(section)) {
      const index = customSectionIndex(section)
      if (index !== null && index < customCount) push(section)
      customInserted = true
      continue
    }
    push(section)
  }
  if (customCount) {
    const missing = customIds.filter(section => !seen.has(section))
    if (missing.length) {
      let insertionIndex = expanded.findIndex(section => section === 'project_experience')
      const lastCustomIndex = expanded.reduce((last, section, index) => (
        isCustomSectionModule(section) ? index : last
      ), -1)
      if (lastCustomIndex >= 0) insertionIndex = lastCustomIndex
      insertionIndex = insertionIndex >= 0 ? insertionIndex + 1 : expanded.length
      expanded.splice(insertionIndex, 0, ...missing)
    }
  } else if (customInserted && !expanded.includes('custom_sections')) {
    const anchor = expanded.indexOf('project_experience')
    expanded.splice(anchor >= 0 ? anchor + 1 : expanded.length, 0, 'custom_sections')
  }
  config.global.sectionOrder = expanded
  return config
}

const quoteCssFont = font => font === 'sans-serif' ? font : `"${font}"`

export function resolveLayoutTokens(value = {}, style = {}) {
  const config = normalizeLayoutConfig(value)
  const global = config.global
  const typography = config.typography
  const bounded = (candidate, min, max, fallback) => {
    const number = Number(candidate)
    return Number.isFinite(number) ? Math.min(Math.max(number, min), max) : fallback
  }
  const fontSizePt = bounded(style.fontSize ?? global.fontSize, 8, 11.5, global.fontSize)
  const lineHeight = bounded(style.lineHeight ?? global.lineHeight, 1, 1.8, global.lineHeight)
  const moduleMargin = bounded(style.moduleMargin ?? global.moduleMargin, 0.1, 1, global.moduleMargin)
  const fontSizes = typography.fontSizes
  const bodyFontSizePt = fontSizePt
  const metaFontSizePt = fontSizes.meta
  const entryTitleFontSizePt = fontSizes.entryTitle
  const sectionTitleFontSizePt = fontSizes.sectionTitle
  const nameFontSizePt = fontSizes.name
  const labelFontSizePt = fontSizes.label

  return {
    fontPreset: typography.preset,
    latinFont: typography.latinFont,
    eastAsiaFont: typography.eastAsiaFont,
    fallbackFonts: [...typography.fallbackFonts],
    fontFamilyCss: [typography.latinFont, typography.eastAsiaFont, ...typography.fallbackFonts]
      .map(quoteCssFont).join(', '),
    fontSizePt,
    bodyFontSizePt,
    metaFontSizePt,
    entryTitleFontSizePt,
    sectionTitleFontSizePt,
    nameFontSizePt,
    labelFontSizePt,
    bodyFontWeight: 400,
    metaFontWeight: 400,
    entryTitleFontWeight: 700,
    sectionTitleFontWeight: 700,
    nameFontWeight: 700,
    labelFontWeight: 700,
    letterSpacingPt: 0,
    lineHeight,
    bodyLineHeightPt: bodyFontSizePt * lineHeight,
    metaLineHeightPt: metaFontSizePt * lineHeight,
    entryTitleLineHeightPt: entryTitleFontSizePt * lineHeight,
    sectionTitleLineHeightPt: sectionTitleFontSizePt * lineHeight,
    nameLineHeightPt: nameFontSizePt * lineHeight,
    moduleMargin,
    moduleSpacingPt: fontSizePt * moduleMargin,
    headerNameAfterPt: bodyFontSizePt * 0.27,
    sectionTitleAfterPt: bodyFontSizePt * 0.25,
    sectionTitleBorderGapPt: sectionTitleFontSizePt * 0.1,
    itemSpacingPt: bodyFontSizePt * 0.22,
    paragraphSpacingPt: bodyFontSizePt * 0.09,
    contentBlockSpacingPt: bodyFontSizePt * 0.14,
    contentLabelSpacingPt: bodyFontSizePt * 0.06,
    numberedItemSpacingPt: bodyFontSizePt * 0.08,
    listTextIndentPt: bodyFontSizePt * 1.55,
    listMarkerGapPt: bodyFontSizePt * 0.25,
    educationMiddleMinMm: 30,
    educationColumnBreathingMm: 4,
    // Keep photoWidthMm in the token contract for old callers. Renderers use
    // photoHeightMm plus the stored image ratio for the actual width.
    photoWidthMm: config.basics.photoWidthMm,
    photoHeightMm: config.basics.photoHeightMm,
    marginTopMm: bounded(style.marginTop ?? global.marginVertical, 3, 12, global.marginVertical),
    marginBottomMm: bounded(style.marginBottom ?? global.marginVertical, 3, 12, global.marginVertical),
    marginLeftMm: bounded(style.marginLeft ?? global.marginHorizontal, 3, 12, global.marginHorizontal),
    marginRightMm: bounded(style.marginRight ?? global.marginHorizontal, 3, 12, global.marginHorizontal),
    modules: Object.fromEntries(Object.keys(MODULE_COMPONENTS).map(moduleId => [moduleId, {
      paragraphSpacingPt: bodyFontSizePt * config[moduleId].paragraphSpacing,
      itemSpacingPt: bodyFontSizePt * config[moduleId].itemSpacing,
      contentBlockSpacingPt: bodyFontSizePt * config[moduleId].contentBlockSpacing,
      rowSpacingPt: bodyFontSizePt * config[moduleId].rowSpacing,
      indentPt: bodyFontSizePt * 1.55 * config[moduleId].indentLevel
    }]))
  }
}

export function resolveModuleLayout(value = {}, moduleId) {
  const config = normalizeLayoutConfig(value)
  const resolvedModuleId = isCustomSectionModule(moduleId) ? 'custom_sections' : moduleId
  if (!MODULE_COMPONENTS[resolvedModuleId]) throw new Error(`Unknown layout module: ${moduleId}`)
  return {
    ...clone(config[resolvedModuleId]),
    resolvedTitleStyle: config[resolvedModuleId].titleStyle || config.global.titleStyle,
    resolvedTitleAlignment: config[resolvedModuleId].titleAlignment || 'left',
    resolvedLineHeight: config.global.lineHeight
  }
}

export function componentPosition(value = {}, moduleId, componentId) {
  const module = resolveModuleLayout(value, moduleId)
  if (module.hiddenComponents.includes(componentId)) return null
  for (let rowIndex = 0; rowIndex < module.componentRows.length; rowIndex += 1) {
    for (let cellIndex = 0; cellIndex < module.componentRows[rowIndex].cells.length; cellIndex += 1) {
      if (module.componentRows[rowIndex].cells[cellIndex].components.includes(componentId)) return [rowIndex, cellIndex]
    }
  }
  return null
}

export function estimateTextWidthPt(value = '', fontSizePt = 9) {
  let units = 0
  for (const char of String(value ?? '')) {
    const codepoint = char.codePointAt(0)
    if ((codepoint >= 0x3400 && codepoint <= 0x4dbf)
      || (codepoint >= 0x4e00 && codepoint <= 0x9fff)
      || (codepoint >= 0xf900 && codepoint <= 0xfaff)
      || (codepoint >= 0xff00 && codepoint <= 0xffef)) units += 1
    else if (/\s/u.test(char)) units += 0.28
    else if (/[A-Z]/.test(char)) units += 0.62
    else if (/[a-z]/.test(char)) units += 0.52
    else if (/[0-9]/.test(char)) units += 0.56
    else units += 0.35
  }
  return units * Number(fontSizePt)
}

export function resolveEducationColumnWidths(tokens, { schools = [], dates = [], degreeMajors = [], compactMetrics = [] } = {}) {
  const printableMm = 210 - tokens.marginLeftMm - tokens.marginRightMm
  const breathingMm = tokens.educationColumnBreathingMm
  // Determine the middle column from its own field-label content first. The
  // side columns only constrain it when preserving their minimum readable
  // width would otherwise be impossible; the remaining width is always split
  // equally between the left and right columns.
  let middleNeededMm = tokens.educationMiddleMinMm
  degreeMajors.forEach((degreeMajor, index) => {
    const metric = compactMetrics[index] || ''
    const parts = [degreeMajor, metric].filter(Boolean).map(value => String(value).replace(/\*\*/g, ''))
    const displayValue = parts.join(' · ')
    const widthPt = estimateTextWidthPt(displayValue, tokens.labelFontSizePt) * 1.08
    middleNeededMm = Math.max(middleNeededMm, widthPt * 25.4 / 72 + breathingMm)
  })

  const sideNeededMm = Math.max(
    36,
    ...schools.map(value => estimateTextWidthPt(String(value).replace(/\*\*/g, ''), tokens.entryTitleFontSizePt) * 25.4 / 72),
    ...dates.map(value => estimateTextWidthPt(String(value).replace(/\*\*/g, ''), tokens.labelFontSizePt) * 25.4 / 72)
  ) + breathingMm

  // Preserve the middle width unless reserving both side minima is necessary.
  const middleMaxMm = Math.max(tokens.educationMiddleMinMm, printableMm - sideNeededMm * 2)
  const middleMm = Math.min(middleNeededMm, middleMaxMm)
  return {
    sideMm: Math.max(0, (printableMm - middleMm) / 2),
    middleMm
  }
}

export function resolvePhotoHeightMm(resumeData = {}, config = {}, tokens = {}) {
  const basics = resumeData?.basics && typeof resumeData.basics === 'object' ? resumeData.basics : {}
  const desired = Number(tokens.photoHeightMm) || 26
  if (!basics.photo) return desired
  const global = config?.global || {}
  const hidden = new Set(global.hiddenSections || [])
  const others = resumeData?.others && typeof resumeData.others === 'object' ? resumeData.others : {}
  const hasValues = value => Array.isArray(value) && value.some(item => String(item || '').trim())
  const sectionHasContent = section => {
    const customIndex = customSectionIndex(section)
    if (customIndex !== null) {
      const custom = resumeData?.custom_sections?.[customIndex]
      return Boolean(custom?.title && hasValues(custom.items))
    }
    if (section === 'education') return Array.isArray(resumeData.education) && resumeData.education.length > 0
    if (section === 'skills') return hasValues(others.skills)
    if (['research_interests', 'honors', 'publications', 'self_evaluation'].includes(section)) return hasValues(resumeData[section])
    if (section === 'work_experience') return (resumeData.work_experience || []).length > 0
    if (section === 'project_experience') return hasValues(resumeData.project_experience || resumeData.projects)
    if (section === 'custom_sections') return (resumeData.custom_sections || [])
      .some(item => String(item?.title || '').trim() && hasValues(item?.items))
    if (section === 'others') return ['certificates', 'languages'].some(key => hasValues(others[key]))
    return false
  }
  if (!(global.sectionOrder || []).some(section => sectionHasContent(section)
    && !hidden.has(section)
    && !(isCustomSectionModule(section) && hidden.has('custom_sections')))) return desired

  const printableWidthPt = Math.max(1, (210 - Number(tokens.marginLeftMm || 0) - Number(tokens.marginRightMm || 0)) * 72 / 25.4)
  const ratio = Math.min(3, Math.max(0.2, Number(basics.photo_aspect_ratio) || 21 / 26))
  const photoWidthPt = desired * ratio * 72 / 25.4
  const textWidthPt = Math.max(120, printableWidthPt - photoWidthPt)
  const lineCount = (value, fontSize) => {
    const text = String(value || '').replace(/\*\*/g, '').trim()
    if (!text) return 0
    return Math.max(1, Math.ceil(estimateTextWidthPt(text, fontSize) / textWidthPt))
  }
  const nameLines = lineCount(basics.name, tokens.nameFontSizePt)
  const targetLines = lineCount(basics.target_position, tokens.metaFontSizePt)
  const contactValues = ['gender', 'birth_date', 'phone', 'email'].map(key => basics[key])
  for (const field of basics.additional_fields || []) {
    if (field?.label || field?.value) contactValues.push(field.label || field.value)
  }
  const contactLines = lineCount(contactValues.filter(Boolean).join(' | '), tokens.metaFontSizePt)
  const headerPt = (
    nameLines * tokens.nameLineHeightPt
    + (nameLines ? tokens.headerNameAfterPt : 0)
    + targetLines * tokens.metaLineHeightPt
    + contactLines * tokens.metaLineHeightPt
    // Cap the photo before the next title/divider. The title's own line box
    // must not be included, otherwise the image overlaps that divider.
    + tokens.moduleSpacingPt
    + tokens.bodyFontSizePt * 0.35
    + tokens.sectionTitleLineHeightPt
  )
  // Let the photo reach the next divider while preserving a physical safety
  // gap for browser/PDF/Word font and table-box differences.
  const availableMm = headerPt * 25.4 / 72 - PHOTO_BOTTOM_GAP_MM
  return Math.round(Math.max(10, Math.min(desired, availableMm)) * 100) / 100
}

export function formatCompactAcademicMetric(item = {}, hiddenMetrics = []) {
  const hidden = new Set(hiddenMetrics)
  let metric = ''
  if (item?.gpa && !hidden.has('gpa')) {
    metric = String(item.gpa)
    if (item.gpa_scale) {
      metric = joinInlineWithInheritedSeparator([metric, item.gpa_scale], '/')
    }
  }
  if (item?.ranking && !hidden.has('ranking')) {
    const ranking = String(item.ranking).trim().replace(/^[（(]|[）)]$/g, '')
    const rankingValue = isFullyBoldInlineText(ranking)
      ? `**(${plainInlineText(ranking)})**`
      : `(${ranking})`
    metric = joinInlineWithInheritedSeparator([metric, rankingValue], ' ')
  }
  return metric
}

export function isCompactAcademicMetricLeadingBold(item = {}, hiddenMetrics = []) {
  const hidden = new Set(hiddenMetrics)
  return Boolean(item?.gpa && !hidden.has('gpa') && isFullyBoldInlineText(item.gpa))
}

// Keep content-flow decisions in one place. Preview rendering and editor line
// measurement both consume this descriptor, so an inline label participates in
// wrapping while a label rendered as its own paragraph does not.
export function resolveContentBlockFlow(block = {}) {
  const normalized = normalizeContentBlock(block)
  const type = normalized.type
  const label = normalized.label
  const semanticRole = normalized.semantic_role
  const requiresLabel = semanticRole !== 'generic'
  // Labeled lists preserve two visible hierarchy levels: the outer semantic
  // label and its child bullets/numbers. Generic lists use one level.
  const isList = ['numbered_list', 'bullet_list'].includes(type)
  const contentIndentLevels = requiresLabel && label && isList
    ? 2
    : ((requiresLabel || isList) ? 1 : 0)
  const labelPlacement = !label ? 'none' : (type === 'paragraph' ? 'inline' : 'separate')
  return {
    type,
    label,
    semanticRole,
    requiresLabel,
    visible: !requiresLabel || Boolean(label),
    labelMarker: requiresLabel && label ? 'bullet' : 'none',
    contentIndentLevels,
    labelPlacement,
    labelBold: normalized.label_bold,
    prefixText: label ? `${label}：` : ''
  }
}

export function sectionTitle(config, section, lang, fallback) {
  return config?.global?.titleOverrides?.[section]?.[lang] || fallback
}

export function sectionOrder(config, section) {
  const index = config?.global?.sectionOrder?.indexOf(section)
  return index >= 0 ? index + 1 : 99
}

export function isSectionHidden(config, section) {
  const baseSection = isCustomSectionModule(section) ? 'custom_sections' : section
  return config?.global?.hiddenSections?.includes(section)
    || config?.global?.hiddenSections?.includes(baseSection)
    || false
}
