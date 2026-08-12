export const DEFAULT_LAYOUT_CONFIG = Object.freeze({
  version: 5,
  typography: {
    preset: 'microsoft-office',
    latinFont: 'Arial',
    eastAsiaFont: 'Microsoft YaHei',
    fallbackFonts: ['Noto Sans CJK SC', 'sans-serif'],
    fontSizes: { name: 14, sectionTitle: 11, entryTitle: 10, meta: 9, body: 9, label: 9 }
  },
  global: {
    density: 'compact', fontSize: 9, lineHeight: 1.28, moduleMargin: 0.55,
    marginVertical: 8, marginHorizontal: 9, titleStyle: 'underline',
    sectionOrder: ['education', 'skills', 'research_interests', 'honors', 'work_experience', 'project_experience', 'custom_sections', 'others', 'self_evaluation'],
    hiddenSections: [], splitWorkExperience: false, titleOverrides: {}
  },
  basics: { preset: 'centered', contactLayout: 'inline', photoPosition: 'right', hiddenFields: [] },
  education: { preset: 'classic', schoolTagStyle: 'filled', metricsPlacement: 'below', hiddenMetrics: [], thesisDisplay: 'expanded' },
  work_experience: { preset: 'classic', detailsStyle: 'bullets', datePosition: 'right', showJobType: true },
  project_experience: { preset: 'classic', detailsStyle: 'bullets', datePosition: 'right', showRole: true, showDate: true },
  others: { preset: 'inline', fieldOrder: ['certificates', 'languages'], hiddenFields: [], separator: 'pipe' },
  self_evaluation: { preset: 'paragraphs' }
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
  meta: '元信息', body: '正文内容', label: '标签与字段标签'
})
const semanticFontSizes = body => ({
  name: 14, sectionTitle: body + 2, entryTitle: body + 1,
  meta: body, body, label: body
})
const SECTION_IDS = new Set([
  'education', 'skills', 'research_interests', 'honors', 'work_experience',
  'internship_experience', 'project_experience', 'custom_sections', 'others', 'self_evaluation'
])

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

export function normalizeLayoutConfig(value = {}) {
  const suppliedVersion = Number(value?.version || 1)
  const result = clone(DEFAULT_LAYOUT_CONFIG)
  mergeKnown(result, value, DEFAULT_LAYOUT_CONFIG)
  result.version = 5
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
  result.global.fontSize = Math.round(boundedConfigNumber(result.global.fontSize, 8, 11.5, 9) * 2) / 2
  result.global.lineHeight = boundedConfigNumber(result.global.lineHeight, 1.1, 2.2, 1.28)
  result.global.moduleMargin = boundedConfigNumber(result.global.moduleMargin, 0.25, 2, 0.55)
  if (result.education.preset === 'three-column') result.education.metricsPlacement = 'info-column'
  if (result.basics.photoPosition === 'hidden' && !result.basics.hiddenFields.includes('photo')) result.basics.hiddenFields.push('photo')
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
  insertAfter('skills', 'education')
  insertAfter('research_interests', 'skills')
  insertAfter('honors', 'research_interests')
  insertAfter('custom_sections', 'project_experience')
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
  const lineHeight = bounded(style.lineHeight ?? global.lineHeight, 1.1, 2.2, global.lineHeight)
  const moduleMargin = bounded(style.moduleMargin ?? global.moduleMargin, 0.25, 2, global.moduleMargin)
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
    moduleMargin,
    moduleSpacingPt: fontSizePt * moduleMargin,
    headerNameAfterPt: bodyFontSizePt * 0.27,
    sectionTitleAfterPt: bodyFontSizePt * 0.25,
    itemSpacingPt: bodyFontSizePt * 0.22,
    paragraphSpacingPt: bodyFontSizePt * 0.09,
    contentBlockSpacingPt: bodyFontSizePt * 0.14,
    contentLabelSpacingPt: bodyFontSizePt * 0.06,
    numberedItemSpacingPt: bodyFontSizePt * 0.08,
    listTextIndentPt: bodyFontSizePt * 1.55,
    listMarkerGapPt: bodyFontSizePt * 0.25,
    marginTopMm: bounded(style.marginTop ?? global.marginVertical, 3, 12, global.marginVertical),
    marginBottomMm: bounded(style.marginBottom ?? global.marginVertical, 3, 12, global.marginVertical),
    marginLeftMm: bounded(style.marginLeft ?? global.marginHorizontal, 3, 12, global.marginHorizontal),
    marginRightMm: bounded(style.marginRight ?? global.marginHorizontal, 3, 12, global.marginHorizontal)
  }
}

// Keep content-flow decisions in one place. Preview rendering and editor line
// measurement both consume this descriptor, so an inline label participates in
// wrapping while a label rendered as its own paragraph does not.
export function resolveContentBlockFlow(block = {}) {
  const type = ['paragraph', 'numbered_list', 'bullet_list'].includes(block?.type)
    ? block.type
    : 'paragraph'
  const label = String(block?.label || '').trim()
  const labelPlacement = !label ? 'none' : (type === 'paragraph' ? 'inline' : 'separate')
  return {
    type,
    label,
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
