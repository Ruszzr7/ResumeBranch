/**
 * Parse timestamps returned by the backend.
 *
 * Older API responses omitted the timezone marker even though the stored
 * value was UTC. Treat such date-time strings as UTC for backward
 * compatibility; new responses carry an explicit `Z` marker.
 */
export function parseBackendDate(value) {
  if (!value) return null
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value
  }

  const raw = String(value).trim()
  if (!raw) return null

  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(raw)
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)
  const date = new Date(isDateOnly || hasTimezone ? raw : `${raw}Z`)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatRelativeUpdatedAt(value, now = Date.now()) {
  const date = parseBackendDate(value)
  if (!date) return '最近编辑'

  const distance = Math.max(0, now - date.getTime())
  if (distance < 60_000) return '刚刚编辑'
  if (distance < 3_600_000) return `${Math.max(1, Math.floor(distance / 60_000))} 分钟前编辑`
  if (distance < 86_400_000) return `${Math.max(1, Math.floor(distance / 3_600_000))} 小时前编辑`
  if (distance < 604_800_000) return `${Math.max(1, Math.floor(distance / 86_400_000))} 天前编辑`
  return date.toLocaleDateString('zh-CN')
}
