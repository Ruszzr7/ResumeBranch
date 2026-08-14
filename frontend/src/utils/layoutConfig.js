export const MODULE_COMPONENTS = Object.freeze({
  basics: ['name', 'target_position', 'personal_meta', 'contact', 'additional_fields', 'photo'],
  education: ['school', 'school_tags', 'degree', 'major', 'metrics', 'date', 'theses'],
  skills: ['items'], research_interests: ['items'], honors: ['items'], publications: ['items'],
  work_experience: ['organization', 'position', 'job_type', 'date', 'content'],
  internship_experience: ['organization', 'position', 'job_type', 'date', 'content'],
  project_experience: ['project_name', 'role', 'date', 'content'],
  custom_sections: ['items'], others: ['certificates', 'languages'], self_evaluation: ['items']
})

const REQUIRED_COMPONENTS = Object.freeze({
  basics: ['name'], education: ['school'], skills: ['items'], research_interests: ['items'], honors: ['items'], publications: ['items'],
  work_experience: ['organization', 'content'], internship_experience: ['organization', 'content'],
  project_experience: ['project_name', 'content'], custom_sections: ['items'], others: [], self_evaluation: ['items']
})

const LONG_TEXT_COMPONENTS = new Set([
  'education.theses', 'work_experience.content', 'internship_experience.content', 'project_experience.content',
  'skills.items', 'research_interests.items', 'honors.items', 'publications.items', 'custom_sections.items', 'self_evaluation.items'
])

export const DEFAULT_COMPONENT_ROWS = Object.freeze({
  basics: [
    { cells: [{ components: ['name'], flow: 'stacked', width: 'fill', alignment: 'left' }, { components: ['photo'], flow: 'stacked', width: 'content', alignment: 'right' }] },
    { cells: [{ components: ['target_position'], flow: 'stacked', width: 'fill', alignment: 'left' }] },
    { cells: [{ components: ['personal_meta', 'contact', 'additional_fields'], flow: 'inline', width: 'fill', alignment: 'left' }] }
  ],
  education: [
    { cells: [{ components: ['school', 'school_tags'], flow: 'inline', width: 'content', alignment: 'left' }, { components: ['degree', 'major', 'metrics'], flow: 'inline', width: 'fill', alignment: 'center' }, { components: ['date'], flow: 'inline', width: 'content', alignment: 'right' }] },
    { cells: [{ components: ['theses'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }
  ],
  work_experience: [
    { cells: [{ components: ['organization', 'position', 'job_type'], flow: 'inline', width: 'fill', alignment: 'left' }, { components: ['date'], flow: 'inline', width: 'content', alignment: 'right' }] },
    { cells: [{ components: ['content'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }
  ],
  internship_experience: [
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
  others: [{ cells: [{ components: ['certificates', 'languages'], flow: 'inline', width: 'fill', alignment: 'left' }] }],
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
  version: 8,
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
    hiddenSections: [], splitWorkExperience: false, titleOverrides: {}, sectionPlacements: {}
  },
  basics: moduleContract('basics', {
    preset: 'left-aligned', contactLayout: 'inline', photoPosition: 'right',
    // Photo height is the only user-facing size control. Width is derived from
    // the imported image's aspect ratio at render time.
    photoHeightMm: 26, photoWidthMm: 21, hiddenFields: []
  }),
  education: moduleContract('education', { preset: 'compact', schoolTagStyle: 'text', metricsPlacement: 'with-degree', hiddenMetrics: [], thesisDisplay: 'expanded' }),
  skills: moduleContract('skills', { listStyle: 'bullet' }),
  research_interests: moduleContract('research_interests', { listStyle: 'bullet' }),
  honors: moduleContract('honors', { listStyle: 'bullet' }),
  publications: moduleContract('publications', { listStyle: 'bullet' }),
  work_experience: moduleContract('work_experience', { preset: 'compact', detailsStyle: 'bullets', datePosition: 'right', showJobType: true }),
  internship_experience: moduleContract('internship_experience', { preset: 'compact', detailsStyle: 'bullets', datePosition: 'right', showJobType: true }),
  project_experience: moduleContract('project_experience', { preset: 'compact', detailsStyle: 'bullets', datePosition: 'right', showRole: true, showDate: true }),
  custom_sections: moduleContract('custom_sections', { listStyle: 'bullet' }),
  others: moduleContract('others', { preset: 'tags', fieldOrder: ['skills', 'certificates', 'languages'], hiddenFields: [], separator: 'dot' }),
  self_evaluation: moduleContract('self_evaluation', { preset: 'compact', listStyle: 'paragraph' })
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
  'internship_experience', 'project_experience', 'custom_sections', 'others', 'self_evaluation'
])
const ENUMS = Object.freeze({
  'typography.preset': ['microsoft-office'],
  'global.density': ['compact', 'standard', 'comfortable'],
  'global.titleStyle': ['underline', 'plain'],
  'basics.preset': ['centered', 'left-aligned'],
  'basics.contactLayout': ['inline', 'stacked'],
  'basics.photoPosition': ['right', 'hidden'],
  'education.preset': ['classic', 'compact', 'three-column'],
  'education.schoolTagStyle': ['filled', 'outline', 'text', 'hidden'],
  'education.metricsPlacement': ['below', 'with-degree', 'info-column'],
  'education.thesisDisplay': ['expanded', 'compact', 'hidden'],
  'work_experience.preset': ['compact'],
  'work_experience.detailsStyle': ['bullets', 'paragraph'],
  'work_experience.datePosition': ['right', 'inline'],
  'internship_experience.preset': ['compact'],
  'internship_experience.detailsStyle': ['bullets', 'paragraph'],
  'internship_experience.datePosition': ['right', 'inline'],
  'project_experience.preset': ['classic', 'compact'],
  'project_experience.detailsStyle': ['bullets', 'paragraph'],
  'project_experience.datePosition': ['right', 'inline'],
  'others.preset': ['inline', 'tags', 'stacked'],
  'others.separator': ['pipe', 'dot'],
  'self_evaluation.preset': ['paragraphs', 'bullets', 'compact']
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
  if (moduleId === 'basics' && config.preset === 'centered') {
    return [
      { cells: [{ components: ['name', 'target_position'], flow: 'stacked', width: 'fill', alignment: 'center' }, { components: ['photo'], flow: 'stacked', width: 'content', alignment: 'right' }] },
      { cells: [{ components: ['personal_meta', 'contact', 'additional_fields'], flow: config.contactLayout || 'inline', width: 'fill', alignment: 'center' }] }
    ]
  }
  if (moduleId === 'education' && config.preset === 'classic') {
    return [
      { cells: [{ components: ['school', 'school_tags'], flow: 'inline', width: 'fill', alignment: 'left' }, { components: ['date'], flow: 'inline', width: 'content', alignment: 'right' }] },
      { cells: [{ components: ['degree', 'major'], flow: 'inline', width: 'fill', alignment: 'left' }] },
      { cells: [{ components: ['metrics'], flow: 'inline', width: 'fill', alignment: 'left' }] },
      { cells: [{ components: ['theses'], flow: 'stacked', width: 'fill', alignment: 'justify' }] }
    ]
  }
  if (['work_experience', 'internship_experience'].includes(moduleId) && config.datePosition === 'inline') {
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
    const required = new Set(REQUIRED_COMPONENTS[moduleId])
    const hidden = new Set((Array.isArray(module.hiddenComponents) ? module.hiddenComponents : [])
      .filter(component => MODULE_COMPONENTS[moduleId].includes(component) && !required.has(component)))
    module.hiddenComponents = MODULE_COMPONENTS[moduleId].filter(component => hidden.has(component))
    const fallback = suppliedVersion < 7 ? legacyComponentRows(moduleId, module) : clone(DEFAULT_COMPONENT_ROWS[moduleId])
    const rawModule = source?.[moduleId] && typeof source[moduleId] === 'object' ? source[moduleId] : {}
    module.componentRows = normalizeComponentRows(moduleId, suppliedVersion >= 7 ? rawModule.componentRows : fallback, fallback, hidden)
    // Compact education keeps a stable three-column geometry: the metadata
    // column is centered while school/date remain left/right aligned. Migrate
    // old persisted rows so all renderers use the same alignment contract.
    if (moduleId === 'education' && module.preset === 'compact') {
      for (const row of module.componentRows) {
        if (row.cells.length !== 3) continue
        if (!row.cells[0].components.includes('school')
          || !row.cells[1].components.some(component => ['degree', 'major', 'metrics'].includes(component))
          || !row.cells[2].components.includes('date')) continue
        row.cells[0].alignment = 'left'
        row.cells[1].alignment = 'center'
        row.cells[2].alignment = 'right'
      }
    }
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
  result.global.splitWorkExperience = Boolean(result.global.splitWorkExperience)
  if (suppliedVersion < 8 && Array.isArray(result.global.sectionOrder)
      && result.global.sectionOrder.join('|') === LEGACY_V7_DEFAULT_SECTION_ORDER.join('|')) {
    result.global.sectionOrder = [...DEFAULT_LAYOUT_CONFIG.global.sectionOrder]
  }
  result.global.sectionOrder = [...new Set((Array.isArray(result.global.sectionOrder) ? result.global.sectionOrder : [])
    .filter(item => SECTION_IDS.has(item)))]
  if (result.global.splitWorkExperience && !result.global.sectionOrder.includes('internship_experience')) {
    const index = result.global.sectionOrder.indexOf('work_experience')
    result.global.sectionOrder.splice(Math.max(0, index + 1), 0, 'internship_experience')
  }
  if (!result.global.splitWorkExperience) {
    result.global.sectionOrder = result.global.sectionOrder.filter(item => item !== 'internship_experience')
  }
  const insertAfter = (item, anchor) => {
    if (result.global.sectionOrder.includes(item)) return
    const index = result.global.sectionOrder.indexOf(anchor)
    result.global.sectionOrder.splice(index >= 0 ? index + 1 : result.global.sectionOrder.length, 0, item)
  }
  insertAfter('honors', 'education')
  insertAfter('publications', 'honors')
  insertAfter('research_interests', 'publications')
  insertAfter('skills', 'research_interests')
  insertAfter('custom_sections', 'project_experience')
  for (const item of SECTION_IDS) {
    if (item !== 'internship_experience' || result.global.splitWorkExperience) insertAfter(item)
  }
  result.global.hiddenSections = [...new Set(
    (Array.isArray(result.global.hiddenSections) ? result.global.hiddenSections : []).filter(item => SECTION_IDS.has(item))
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
  if (result.education.preset === 'three-column') {
    result.education.metricsPlacement = 'info-column'
  } else if (result.education.metricsPlacement === 'info-column') {
    result.education.metricsPlacement = result.education.preset === 'classic' ? 'below' : 'with-degree'
  }
  result.others.fieldOrder = (Array.isArray(result.others.fieldOrder) ? result.others.fieldOrder : [])
    .filter(item => ALLOWED_HIDDEN_FIELDS.others.has(item))
  for (const item of ['skills', 'certificates', 'languages']) {
    if (!result.others.fieldOrder.includes(item)) result.others.fieldOrder.push(item)
  }
  result.work_experience.showJobType = Boolean(result.work_experience.showJobType)
  result.internship_experience.showJobType = Boolean(result.internship_experience.showJobType)
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
    educationSideColumnMm: 42,
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
  if (!MODULE_COMPONENTS[moduleId]) throw new Error(`Unknown layout module: ${moduleId}`)
  return {
    ...clone(config[moduleId]),
    resolvedTitleStyle: config[moduleId].titleStyle || config.global.titleStyle,
    resolvedTitleAlignment: config[moduleId].titleAlignment || 'left',
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
  const sideNeededMm = Math.max(
    36,
    ...schools.map(value => estimateTextWidthPt(String(value).replace(/\*\*/g, ''), tokens.entryTitleFontSizePt) * 25.4 / 72),
    ...dates.map(value => estimateTextWidthPt(String(value).replace(/\*\*/g, ''), tokens.labelFontSizePt) * 25.4 / 72)
  ) + breathingMm
  let middleNeededMm = tokens.educationMiddleMinMm
  degreeMajors.forEach((degreeMajor, index) => {
    const metric = compactMetrics[index] || ''
    const parts = [degreeMajor, metric].filter(Boolean).map(value => String(value).replace(/\*\*/g, ''))
    const displayValue = parts.join(' · ')
    // Degree, major and compact metrics are field-label content. Measure them
    // with the label size and a small safety factor so a larger field label
    // gets the middle column before the side columns absorb the space.
    const widthPt = estimateTextWidthPt(displayValue, tokens.labelFontSizePt) * 1.08
    middleNeededMm = Math.max(middleNeededMm, widthPt * 25.4 / 72 + breathingMm)
  })
  const middleMaxMm = Math.max(tokens.educationMiddleMinMm, printableMm - sideNeededMm * 2)
  const middleMm = Math.min(middleNeededMm, middleMaxMm)
  return {
    sideMm: Math.max(0, (printableMm - middleMm) / 2),
    middleMm
  }
}

export function formatCompactAcademicMetric(item = {}, hiddenMetrics = []) {
  const hidden = new Set(hiddenMetrics)
  let metric = ''
  if (item?.gpa && !hidden.has('gpa')) {
    metric = `${item.gpa}${item.gpa_scale ? `/${item.gpa_scale}` : ''}`
  }
  if (item?.ranking && !hidden.has('ranking')) {
    const ranking = String(item.ranking).trim().replace(/^[（(]|[）)]$/g, '')
    metric = metric ? `${metric} (${ranking})` : `(${ranking})`
  }
  return metric
}

// Keep content-flow decisions in one place. Preview rendering and editor line
// measurement both consume this descriptor, so an inline label participates in
// wrapping while a label rendered as its own paragraph does not.
export function resolveContentBlockFlow(block = {}) {
  const type = ['paragraph', 'numbered_list', 'bullet_list'].includes(block?.type)
    ? block.type
    : 'paragraph'
  const label = String(block?.label || '').trim()
  let semanticRole = String(block?.semantic_role || '').trim()
  if (!['introduction', 'responsibilities', 'generic'].includes(semanticRole)) {
    semanticRole = label && type === 'paragraph'
      ? 'introduction'
      : (label ? 'responsibilities' : 'generic')
  }
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
    labelBold: block?.label_bold !== false,
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
  return config?.global?.hiddenSections?.includes(section) || false
}
