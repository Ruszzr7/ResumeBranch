const IGNORED_KEYS = new Set(['parsing_status', 'photo'])

function hasMeaningfulValue(value, key = '') {
  if (IGNORED_KEYS.has(key)) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (typeof value === 'number') return Number.isFinite(value)
  if (typeof value === 'boolean') return value
  if (Array.isArray(value)) return value.some(item => hasMeaningfulValue(item))
  if (value && typeof value === 'object') {
    return Object.entries(value).some(([childKey, childValue]) => (
      hasMeaningfulValue(childValue, childKey)
    ))
  }
  return false
}

export function hasMeaningfulResumeContent(resume) {
  return hasMeaningfulValue(resume)
}
