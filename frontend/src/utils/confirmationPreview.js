import { normalizeLayoutConfig } from './layoutConfig.js'

const clone = value => (value == null ? value : JSON.parse(JSON.stringify(value)))

const lastListIndex = path => {
  for (let index = path.length - 1; index >= 0; index -= 1) {
    if (Number.isInteger(path[index])) return path[index]
  }
  return -1
}

export function applySelectedResumeChanges(baseData, changes = [], selectedIds = []) {
  const selected = new Set(selectedIds)
  const chosen = changes
    .filter(change => change?.kind !== 'layout' && selected.has(change?.id))
    .slice()
    .sort((left, right) => {
      const leftRemoveOrder = left?.operation === 'remove' ? 0 : 1
      const rightRemoveOrder = right?.operation === 'remove' ? 0 : 1
      if (leftRemoveOrder !== rightRemoveOrder) return leftRemoveOrder - rightRemoveOrder
      return lastListIndex(right?.path || []) - lastListIndex(left?.path || [])
    })

  let result = clone(baseData || {})
  for (const change of chosen) {
    const path = Array.isArray(change.path) ? change.path : []
    if (!path.length) {
      result = clone(change.after || {})
      continue
    }

    let parent = result
    for (let position = 0; position < path.length - 1; position += 1) {
      const part = path[position]
      const nextPart = path[position + 1]
      if (Number.isInteger(part)) {
        while (parent.length <= part) parent.push({})
        parent = parent[part]
      } else {
        if (parent[part] == null || typeof parent[part] !== 'object') {
          parent[part] = Number.isInteger(nextPart) ? [] : {}
        }
        parent = parent[part]
      }
    }

    const leaf = path[path.length - 1]
    if (change.operation === 'remove') {
      if (Array.isArray(parent) && Number.isInteger(leaf) && leaf < parent.length) {
        parent.splice(leaf, 1)
      } else if (parent && typeof parent === 'object') {
        delete parent[leaf]
      }
    } else if (Array.isArray(parent) && Number.isInteger(leaf)) {
      if (leaf < parent.length) parent[leaf] = clone(change.after)
      else parent.push(clone(change.after))
    } else {
      parent[leaf] = clone(change.after)
    }
  }
  return result
}

export function applySelectedLayoutChanges(
  baseConfig,
  candidateConfig,
  changes = [],
  selectedIds = []
) {
  const selected = new Set(selectedIds)
  const result = normalizeLayoutConfig(baseConfig || {})
  const candidate = normalizeLayoutConfig(candidateConfig || {})
  for (const change of changes) {
    if (change?.kind !== 'layout' || !selected.has(change.id)) continue
    const moduleId = change.module
    if (!moduleId || !candidate[moduleId]) continue
    result[moduleId] = clone(candidate[moduleId])
    if (moduleId === 'global') result.typography = clone(candidate.typography)
  }
  return normalizeLayoutConfig(result)
}

export function buildConfirmationPreview({
  baseResumeData,
  baseLayoutConfig,
  candidateLayoutConfig,
  changes,
  selectedChangeIds,
}) {
  return {
    resumeData: applySelectedResumeChanges(baseResumeData, changes, selectedChangeIds),
    layoutConfig: applySelectedLayoutChanges(
      baseLayoutConfig,
      candidateLayoutConfig,
      changes,
      selectedChangeIds
    ),
  }
}
