// Canonical content-block vocabulary shared by editor and preview helpers.
// Keep these values in one place so internal parser names never become UI text.

export const CONTENT_BLOCK_TYPES = Object.freeze([
  'paragraph', 'numbered_list', 'bullet_list'
])

export const CONTENT_BLOCK_SEMANTIC_ROLES = Object.freeze([
  'tech_stack', 'introduction', 'responsibilities', 'generic'
])

export const CONTENT_BLOCK_TYPE_OPTIONS = Object.freeze({
  paragraph: '段落',
  bullet_list: '分点',
  numbered_list: '编号'
})

export const CONTENT_BLOCK_ROLE_LABELS = Object.freeze({
  tech_stack: '技术栈',
  introduction: '项目简介',
  responsibilities: '项目职责',
  generic: '普通内容'
})

export const DEFAULT_CONTENT_BLOCK_TYPES = Object.freeze({
  tech_stack: 'paragraph',
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
  tech_stack: 'tech_stack', technology_stack: 'tech_stack', technology: 'tech_stack',
  '技术栈': 'tech_stack', '技术选型': 'tech_stack', '使用技术': 'tech_stack', '技术工具': 'tech_stack',
  introduction: 'introduction', intro: 'introduction', '项目简介': 'introduction', '项目背景': 'introduction', '项目概述': 'introduction',
  responsibilities: 'responsibilities', responsibility: 'responsibilities', duty: 'responsibilities', duties: 'responsibilities', '主要职责': 'responsibilities', '项目职责': 'responsibilities',
  generic: 'generic', other: 'generic', '普通内容': 'generic', '普通工作内容': 'generic',
  '其他项目内容': 'generic', '其他工作内容': 'generic', '普通项目内容': 'generic'
})

const LEADING_NUMBER_RE = /^\s*[（(]?\s*\d{1,2}\s*[）).、．]\s*/
const LEADING_BULLET_RE = /^\s*(?:[•·▪‣●○◦]\s*|-\s+)/
const INTRO_RE = /^(项目简介|项目背景|项目概述|项目说明)\s*[：:]\s*(.*)$/
const DUTY_RE = /^(项目职责|主要职责|个人职责|负责内容)\s*[：:]?\s*(.*)$/
const TECH_STACK_RE = /^(技术栈|技术选型|使用技术|技术工具)\s*[：:]?\s*(.*)$/
const BOLD_HEADING_RE = /^\*\*(技术栈|技术选型|使用技术|技术工具|项目简介|项目背景|项目概述|项目说明|项目职责|主要职责|个人职责|负责内容)\*\*\s*[：:]?\s*(.*)$/

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

function sourceVisualSignature(source) {
  if (!source || typeof source !== 'object') return { group: '', indent: null, marker: '' }
  const group = text(source.source_layout_group || source.source_visual_group || source.visual_group)
  const rawIndent = source.source_indent_level ?? source.visual_indent_level
  const parsedIndent = rawIndent == null || String(rawIndent).trim() === '' ? null : Number.parseInt(rawIndent, 10)
  const indent = Number.isFinite(parsedIndent) ? parsedIndent : null
  const markerValue = text(source.source_marker_type || source.visual_marker_type).toLowerCase()
  const marker = {
    paragraph: 'paragraph',
    段落: 'paragraph',
    text: 'paragraph',
    bullet: 'bullet',
    bullet_list: 'bullet',
    分点: 'bullet',
    numbered: 'numbered',
    numbered_list: 'numbered',
    编号: 'numbered'
  }[markerValue] || ''
  return { group, indent, marker }
}

function visualGroupKey(signature) {
  if (!signature) return null
  if (signature.group) return `group:${signature.group}`
  if (signature.indent != null || signature.marker) return `shape:${signature.indent ?? ''}:${signature.marker}`
  return null
}

function normalizeHeadingSurface(value) {
  let surface = text(value)
  if (!surface) return { surface: '', wholeBold: false }
  const wholeBold = surface.startsWith('**') && surface.endsWith('**') && surface.length >= 4
    && (surface.match(/\*\*/g) || []).length === 2
  if (wholeBold) surface = surface.slice(2, -2).trim()
  surface = surface.replace(/^\*\*(技术栈|技术选型|使用技术|技术工具|项目简介|项目背景|项目概述|项目说明|项目职责|主要职责|个人职责|负责内容)\*\*/, '$1')
  return { surface, wholeBold }
}

function semanticHeading(value) {
  const { surface, wholeBold } = normalizeHeadingSurface(value)
  const intro = surface.match(INTRO_RE)
  if (intro) return { role: 'introduction', label: intro[1], body: intro[2].trim(), wholeBold }
  const duty = surface.match(DUTY_RE)
  if (duty) return { role: 'responsibilities', label: duty[1], body: duty[2].trim(), wholeBold }
  const techStack = surface.match(TECH_STACK_RE)
  if (techStack) return { role: 'tech_stack', label: techStack[1], body: techStack[2].trim(), wholeBold }
  const bold = text(value).match(BOLD_HEADING_RE)
  if (bold) {
    const role = ['技术栈', '技术选型', '使用技术', '技术工具'].includes(bold[1])
      ? 'tech_stack'
      : (['项目简介', '项目背景', '项目概述', '项目说明'].includes(bold[1]) ? 'introduction' : 'responsibilities')
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
  if (semantic_role === 'generic' && ['tech_stack', 'introduction', 'responsibilities'].includes(labelRole)) semantic_role = labelRole
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
    if (heading?.role === 'tech_stack') {
      flush()
      index += 1
      const first = heading.wholeBold && heading.body ? `**${heading.body}**` : heading.body
      const following = first ? [first] : []
      while (index < details.length && !semanticHeading(text(details[index]))) following.push(details[index++])
      const values = following.map(text).filter(Boolean)
      if (values.length) blocks.push({ type: 'paragraph', semantic_role: 'tech_stack', label: heading.label, label_bold: true, text: values.join('\n'), items: [] })
      continue
    }
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
  let activeSemanticGroup = null
  let responsibilityVisualKey = null

  const asResponsibilities = block => {
    const items = block.items?.length ? [...block.items] : (block.text ? [block.text] : [])
    return {
      ...block,
      type: 'numbered_list',
      semantic_role: 'responsibilities',
      label: '项目职责',
      label_bold: true,
      text: '',
      items
    }
  }

  const appendResponsibilities = block => {
    const previous = normalizedExplicit[normalizedExplicit.length - 1]
    if (previous?.semantic_role === 'responsibilities'
      && previous.label === '项目职责'
      && previous.type === block.type) {
      const items = block.items?.length ? block.items : (block.text ? [block.text] : [])
      if (previous.type === 'paragraph') {
        previous.text = [previous.text, ...items].filter(Boolean).join('\n')
      } else {
        previous.items.push(...items)
      }
    } else {
      normalizedExplicit.push(block)
    }
  }

  if (Array.isArray(value)) {
    value.forEach(raw => {
      let block = normalizeContentBlock(raw, { keepEmpty: false })
      if (!block) return
      const visualKey = visualGroupKey(sourceVisualSignature(raw))
      const hasExplicitSemanticRole = raw && typeof raw === 'object'
        && Object.prototype.hasOwnProperty.call(raw, 'semantic_role')
        && text(raw.semantic_role)
      if (block.semantic_role === 'tech_stack') {
        // A project technical-stack block is a fixed semantic boundary. The
        // final stable partition places it before the introduction.
        normalizedExplicit.push(block)
        activeSemanticGroup = null
        responsibilityVisualKey = null
      } else if (block.semantic_role === 'introduction') {
        normalizedExplicit.push(block)
        activeSemanticGroup = block.label ? 'introduction' : null
        responsibilityVisualKey = null
      } else if (block.semantic_role === 'responsibilities') {
        // An editor-created responsibility block has an explicit display
        // type. Preserve paragraph/bullets/numbering exactly as authored.
        appendResponsibilities(block)
        activeSemanticGroup = block.label ? 'responsibilities' : null
        responsibilityVisualKey = visualKey
      } else if (hasExplicitSemanticRole) {
        // An explicit generic block is a real boundary. It must not be
        // mistaken for an unlabeled responsibility continuation merely
        // because it follows an introduction or responsibility block.
        normalizedExplicit.push(block)
        activeSemanticGroup = null
        responsibilityVisualKey = null
      } else if (['introduction', 'responsibilities'].includes(activeSemanticGroup)) {
        if (responsibilityVisualKey == null && visualKey != null) responsibilityVisualKey = visualKey
        const distinctVisualGroup = responsibilityVisualKey != null && visualKey != null && visualKey !== responsibilityVisualKey
        if (!distinctVisualGroup) {
          appendResponsibilities(asResponsibilities(block))
        } else {
          normalizedExplicit.push({
            ...block,
            type: block.type === 'numbered_list' ? 'bullet_list' : block.type,
            semantic_role: 'generic',
            label: ''
          })
        }
      } else {
        // Without an explicit semantic heading, do not invent introduction or
        // responsibility labels; retain the generic source block.
        normalizedExplicit.push(block)
      }
    })
  }
  const legacy = (Array.isArray(legacyDetails) ? legacyDetails : [legacyDetails]).map(text).filter(Boolean)
  const orderProjectBlocks = blocks => {
    if (experienceKind !== 'project') return blocks
    if (!blocks.some(block => block.semantic_role === 'tech_stack')) return blocks
    const roleOrder = { tech_stack: 0, introduction: 1, responsibilities: 2, generic: 3 }
    return blocks
      .map((block, index) => ({ block, index }))
      .sort((left, right) => (
        (roleOrder[left.block.semantic_role] ?? 3) - (roleOrder[right.block.semantic_role] ?? 3)
        || left.index - right.index
      ))
      .map(({ block }) => block)
  }
  if (normalizedExplicit.length || !legacy.length) return orderProjectBlocks(normalizedExplicit)
  if (experienceKind === 'work' && !legacy.some(item => semanticHeading(item))) {
    return orderProjectBlocks([{ type: 'bullet_list', semantic_role: 'generic', label: '', label_bold: true, text: '', items: legacy }])
  }
  return orderProjectBlocks(legacySemanticBlocks(legacy))
}
