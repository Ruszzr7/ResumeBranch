export const DEFAULT_LAYOUT_CONFIG = Object.freeze({
  version: 2,
  global: {
    density: 'compact', fontSize: 10.5, lineHeight: 1.32, moduleMargin: 0.45,
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
  result.version = 2
  const suppliedGlobal = value?.global || {}
  if (suppliedVersion < 2 && ['fontSize', 'lineHeight', 'moduleMargin', 'marginVertical']
    .every((field, index) => Number(suppliedGlobal[field] ?? [11, 1.6, 1, 9][index]) === [11, 1.6, 1, 9][index])) {
    Object.assign(result.global, { density: 'compact', fontSize: 10.5, lineHeight: 1.32, moduleMargin: 0.45, marginVertical: 8 })
  }
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
  return result
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
