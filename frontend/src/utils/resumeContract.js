// Canonical content-block vocabulary shared by editor and preview helpers.
// Keep these values in one place so internal parser names never become UI text.

export const CONTENT_BLOCK_TYPES = Object.freeze([
  'paragraph', 'numbered_list', 'bullet_list'
])

export const CONTENT_BLOCK_SEMANTIC_ROLES = Object.freeze([
  'introduction', 'responsibilities', 'generic'
])

export const CONTENT_BLOCK_TYPE_OPTIONS = Object.freeze({
  paragraph: '段落',
  bullet_list: '分点',
  numbered_list: '编号'
})

export const CONTENT_BLOCK_ROLE_LABELS = Object.freeze({
  introduction: '项目简介',
  responsibilities: '项目职责',
  generic: '普通内容'
})

export const DEFAULT_CONTENT_BLOCK_TYPES = Object.freeze({
  introduction: 'paragraph',
  responsibilities: 'numbered_list',
  generic: 'bullet_list'
})

export const EDITABLE_RESUME_MODULE_ORDER = Object.freeze([
  'education', 'honors', 'publications', 'research_interests', 'skills',
  'work_experience', 'project_experience', 'custom_sections', 'others', 'self_evaluation'
])

export const EDITABLE_RESUME_MODULE_TITLE_DEFAULTS = Object.freeze({
  education: '教育经历',
  honors: '主要荣誉',
  publications: '论文',
  research_interests: '研究方向',
  skills: '专业技能',
  work_experience: '工作经历',
  project_experience: '项目经历',
  others: '证书与语言',
  self_evaluation: '自我评价'
})

const TYPE_ALIASES = Object.freeze({
  paragraph: 'paragraph', paragraphs: 'paragraph', text: 'paragraph', '段落': 'paragraph', '分段': 'paragraph',
  bullet: 'bullet_list', bullets: 'bullet_list', bullet_list: 'bullet_list', unordered_list: 'bullet_list', list: 'bullet_list', '分点': 'bullet_list',
  numbered: 'numbered_list', numbered_list: 'numbered_list', ordered_list: 'numbered_list', numbers: 'numbered_list', '编号': 'numbered_list'
})

const ROLE_ALIASES = Object.freeze({
  introduction: 'introduction', intro: 'introduction', '项目简介': 'introduction', '项目背景': 'introduction', '项目概述': 'introduction',
  responsibilities: 'responsibilities', responsibility: 'responsibilities', duty: 'responsibilities', duties: 'responsibilities', '主要职责': 'responsibilities', '项目职责': 'responsibilities',
  generic: 'generic', other: 'generic', '普通内容': 'generic', '普通工作内容': 'generic',
  '其他项目内容': 'generic', '其他工作内容': 'generic', '普通项目内容': 'generic'
})

const LEADING_NUMBER_RE = /^\s*[（(]?\s*\d{1,2}\s*[）).、．]\s*/
const LEADING_BULLET_RE = /^\s*(?:[•·▪‣●○◦]\s*|-\s+)/
const INTRO_RE = /^(项目简介|项目背景|项目概述|项目说明)\s*[：:]\s*(.*)$/
const DUTY_RE = /^(项目职责|主要职责|个人职责|负责内容)\s*[：:]?\s*(.*)$/
const BOLD_HEADING_RE = /^\*\*(项目简介|项目背景|项目概述|项目说明|项目职责|主要职责|个人职责|负责内容)\*\*\s*[：:]?\s*(.*)$/

const text = value => value == null ? '' : String(value).trim()
const defaultContentBlockType = semanticRole => DEFAULT_CONTENT_BLOCK_TYPES[semanticRole] || 'bullet_list'

function boolValue(value, fallback = true) {
  if (value == null) return fallback
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (['false', '0', 'no', 'off', '否', '不'].includes(normalized)) return false
    if (['true', '1', 'yes', 'on', '是', '加粗'].includes(normalized)) return true
  }
  return Boolean(value)
}

function normalizeHeadingSurface(value) {
  let surface = text(value)
  if (!surface) return { surface: '', wholeBold: false }
  const wholeBold = surface.startsWith('**') && surface.endsWith('**') && surface.length >= 4
    && (surface.match(/\*\*/g) || []).length === 2
  if (wholeBold) surface = surface.slice(2, -2).trim()
  surface = surface.replace(/^\*\*(项目简介|项目背景|项目概述|项目说明|项目职责|主要职责|个人职责|负责内容)\*\*/, '$1')
  return { surface, wholeBold }
}

function semanticHeading(value) {
  const { surface, wholeBold } = normalizeHeadingSurface(value)
  const intro = surface.match(INTRO_RE)
  if (intro) return { role: 'introduction', label: intro[1], body: intro[2].trim(), wholeBold }
  const duty = surface.match(DUTY_RE)
  if (duty) return { role: 'responsibilities', label: duty[1], body: duty[2].trim(), wholeBold }
  const bold = text(value).match(BOLD_HEADING_RE)
  if (bold) {
    const role = ['项目简介', '项目背景', '项目概述', '项目说明'].includes(bold[1])
      ? 'introduction'
      : 'responsibilities'
    return { role, label: bold[1], body: bold[2].trim(), wholeBold: true }
  }
  return null
}

export function stripContentMarker(value) {
  return text(value).replace(LEADING_NUMBER_RE, '').replace(LEADING_BULLET_RE, '').trim()
}

function genericLabelPrefix(label, labelBold) {
  let rendered = text(label)
  if (!rendered) return ''
  if (labelBold && !(rendered.startsWith('**') && rendered.endsWith('**'))) rendered = `**${rendered}**`
  const separator = /[：:]$/.test(rendered) ? '' : '：'
  return `${rendered}${separator}`
}

function flattenGenericLabel(label, labelBold, body, items) {
  const prefix = genericLabelPrefix(label, labelBold)
  if (!prefix) return { text: body, items }
  if (items.length) return { text: body, items: [`${prefix}${items[0]}`, ...items.slice(1)] }
  if (body) return { text: `${prefix}${body}`, items }
  return { text: '', items: [prefix.replace(/[：:]$/, '')] }
}

export function normalizeContentBlock(block = {}, { keepEmpty = true } = {}) {
  const source = block && typeof block === 'object' ? block : {}
  const requestedType = text(source.type).toLowerCase()
  let type = TYPE_ALIASES[requestedType] || ''
  let label = text(source.label)
  const labelWrappedBold = label.startsWith('**') && label.endsWith('**') && label.length >= 4
  if (labelWrappedBold) label = label.slice(2, -2).trim()
  const requestedRole = text(source.semantic_role).toLowerCase()
  let semantic_role = ROLE_ALIASES[requestedRole]
  const labelRole = ROLE_ALIASES[label.toLowerCase()]
  if (semantic_role === 'generic' && ['introduction', 'responsibilities'].includes(labelRole)) semantic_role = labelRole
  if (!semantic_role) semantic_role = labelRole || 'generic'
  if (!type) type = defaultContentBlockType(semantic_role)
  const items = (Array.isArray(source.items) ? source.items : [])
    .map(stripContentMarker)
    .filter(Boolean)
  const labelBold = boolValue(source.label_bold, true) || labelWrappedBold
  let normalizedText = text(source.text)
  let normalizedItems = items
  if (semantic_role === 'generic') {
    if (labelRole === 'generic') {
      label = ''
    } else if (label) {
      const flattened = flattenGenericLabel(label, labelBold, normalizedText, normalizedItems)
      normalizedText = flattened.text
      normalizedItems = flattened.items
      label = ''
    }
  }
  const normalized = {
    type,
    semantic_role,
    label,
    label_bold: labelBold,
    text: normalizedText,
    items: normalizedItems
  }
  if (!keepEmpty && !normalized.text && !normalized.items.length) return null
  return normalized
}

function legacyListType(values) {
  const nonEmpty = values.map(text).filter(Boolean)
  if (nonEmpty.length && nonEmpty.every(value => LEADING_NUMBER_RE.test(value))) return 'numbered_list'
  if (nonEmpty.length && nonEmpty.every(value => LEADING_BULLET_RE.test(value))) return 'bullet_list'
  return 'numbered_list'
}

function legacySemanticBlocks(details) {
  const blocks = []
  let unmatched = []
  const flush = () => {
    if (!unmatched.length) return
    blocks.push({ type: 'bullet_list', semantic_role: 'generic', label: '', label_bold: true, text: '', items: unmatched.map(stripContentMarker).filter(Boolean) })
    unmatched = []
  }
  let index = 0
  while (index < details.length) {
    const value = text(details[index])
    const heading = semanticHeading(value)
    if (heading?.role === 'introduction') {
      flush()
      const body = heading.wholeBold && heading.body ? `**${heading.body}**` : heading.body
      if (body) blocks.push({ type: 'paragraph', semantic_role: 'introduction', label: heading.label, label_bold: true, text: body, items: [] })
      index += 1
      const following = []
      while (index < details.length && !semanticHeading(text(details[index]))) following.push(details[index++])
      const items = following.map(stripContentMarker).filter(Boolean)
      if (items.length) blocks.push({ type: legacyListType(following), semantic_role: 'responsibilities', label: '项目职责', label_bold: true, text: '', items })
      continue
    }
    if (heading?.role === 'responsibilities') {
      flush()
      index += 1
      const first = heading.wholeBold && heading.body ? `**${heading.body}**` : heading.body
      const following = first ? [first] : []
      while (index < details.length && !semanticHeading(text(details[index]))) following.push(details[index++])
      const items = following.map(stripContentMarker).filter(Boolean)
      if (items.length) blocks.push({ type: legacyListType(following), semantic_role: 'responsibilities', label: heading.label, label_bold: true, text: '', items })
      continue
    }
    unmatched.push(value)
    index += 1
  }
  flush()
  return blocks.filter(block => block.text || block.items?.length)
}

export function normalizeContentBlocks(value, legacyDetails = [], { experienceKind = 'project' } = {}) {
  const normalizedExplicit = []
  let sawLabeledIntroduction = false
  if (Array.isArray(value)) {
    value.forEach(raw => {
      let block = normalizeContentBlock(raw, { keepEmpty: false })
      if (!block) return
      const rawRole = raw && typeof raw === 'object'
        ? (ROLE_ALIASES[text(raw.semantic_role).toLowerCase()] || '')
        : ''
      const rawLabel = raw && typeof raw === 'object' ? text(raw.label) : ''
      if (block.semantic_role === 'introduction') {
        sawLabeledIntroduction = Boolean(block.label)
      } else if (block.semantic_role === 'responsibilities') {
        sawLabeledIntroduction = false
      } else if (sawLabeledIntroduction && block.semantic_role === 'generic') {
        const candidate = !rawRole && !rawLabel && (block.text || block.items?.length)
        if (candidate) {
          const items = block.items?.length ? [...block.items] : [block.text]
          block = {
            ...block,
            type: 'numbered_list',
            semantic_role: 'responsibilities',
            label: '项目职责',
            label_bold: true,
            text: '',
            items
          }
          const previous = normalizedExplicit[normalizedExplicit.length - 1]
          if (previous?.semantic_role === 'responsibilities' && previous.label === '项目职责') {
            previous.items.push(...block.items)
            return
          }
        } else {
          sawLabeledIntroduction = false
        }
      }
      normalizedExplicit.push(block)
    })
  }
  const legacy = (Array.isArray(legacyDetails) ? legacyDetails : [legacyDetails]).map(text).filter(Boolean)
  if (normalizedExplicit.length || !legacy.length) return normalizedExplicit
  if (experienceKind === 'work' && !legacy.some(item => semanticHeading(item))) {
    return [{ type: 'bullet_list', semantic_role: 'generic', label: '', label_bold: true, text: '', items: legacy }]
  }
  return legacySemanticBlocks(legacy)
}
