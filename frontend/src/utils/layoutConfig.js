export const DEFAULT_LAYOUT_CONFIG = Object.freeze({
  version: 1,
  global: {
    density: 'standard', fontSize: 11, lineHeight: 1.6, moduleMargin: 1,
    marginVertical: 9, marginHorizontal: 9, titleStyle: 'underline',
    sectionOrder: ['education', 'work_experience', 'project_experience', 'others', 'self_evaluation'],
    hiddenSections: [], splitWorkExperience: false, titleOverrides: {}
  },
  basics: { preset: 'centered', contactLayout: 'inline', photoPosition: 'right', hiddenFields: [] },
  education: { preset: 'classic', schoolTagStyle: 'filled', metricsPlacement: 'below', hiddenMetrics: [], thesisDisplay: 'expanded' },
  work_experience: { preset: 'classic', detailsStyle: 'bullets', datePosition: 'right', showJobType: true },
  project_experience: { preset: 'classic', detailsStyle: 'bullets', datePosition: 'right', showRole: true, showDate: true },
  others: { preset: 'inline', fieldOrder: ['skills', 'certificates', 'languages'], hiddenFields: [], separator: 'pipe' },
  self_evaluation: { preset: 'paragraphs' }
})

const clone = value => JSON.parse(JSON.stringify(value))

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
  const result = clone(DEFAULT_LAYOUT_CONFIG)
  mergeKnown(result, value, DEFAULT_LAYOUT_CONFIG)
  if (result.education.preset === 'three-column') result.education.metricsPlacement = 'info-column'
  if (result.basics.photoPosition === 'hidden' && !result.basics.hiddenFields.includes('photo')) result.basics.hiddenFields.push('photo')
  if (result.global.splitWorkExperience && !result.global.sectionOrder.includes('internship_experience')) {
    const index = result.global.sectionOrder.indexOf('work_experience')
    result.global.sectionOrder.splice(Math.max(0, index + 1), 0, 'internship_experience')
  }
  if (!result.global.splitWorkExperience) {
    result.global.sectionOrder = result.global.sectionOrder.filter(item => item !== 'internship_experience')
  }
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
