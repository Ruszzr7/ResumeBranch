const BOLD_PAIR = /\*\*(.+?)\*\*/gs

export function parseInlineBold(value = '') {
  const text = String(value ?? '')
  const segments = []
  let cursor = 0
  for (const match of text.matchAll(BOLD_PAIR)) {
    if (match.index > cursor) segments.push({ text: text.slice(cursor, match.index), bold: false })
    segments.push({ text: match[1], bold: true })
    cursor = match.index + match[0].length
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), bold: false })
  return segments
}

export function plainInlineText(value = '') {
  return parseInlineBold(value).map(segment => segment.text).join('')
}

export function serializeInlineBold(segments = []) {
  const merged = []
  for (const segment of segments) {
    const text = String(segment?.text ?? '')
    if (!text) continue
    const bold = Boolean(segment?.bold)
    const previous = merged[merged.length - 1]
    if (previous && previous.bold === bold) previous.text += text
    else merged.push({ text, bold })
  }
  return merged.map(segment => {
    if (!segment.bold) return segment.text
    // 多行字段保存时会按换行拆成数组，因此每一行必须拥有完整的一对标记。
    return segment.text.split('\n').map(line => line ? `**${line}**` : '').join('\n')
  }).join('')
}

export function setInlineBoldRange(value = '', start = 0, end = 0, bold = true) {
  const text = String(value ?? '')
  const plainLength = plainInlineText(text).length
  const safeStart = Math.max(0, Math.min(plainLength, Number(start) || 0))
  const safeEnd = Math.max(safeStart, Math.min(plainLength, Number(end) || 0))
  if (safeStart === safeEnd) return text

  const result = []
  let cursor = 0
  for (const segment of parseInlineBold(text)) {
    const segmentStart = cursor
    const segmentEnd = cursor + segment.text.length
    cursor = segmentEnd
    const overlapStart = Math.max(safeStart, segmentStart)
    const overlapEnd = Math.min(safeEnd, segmentEnd)
    if (overlapStart >= overlapEnd) {
      result.push(segment)
      continue
    }
    const localStart = overlapStart - segmentStart
    const localEnd = overlapEnd - segmentStart
    if (localStart) result.push({ text: segment.text.slice(0, localStart), bold: segment.bold })
    result.push({ text: segment.text.slice(localStart, localEnd), bold: Boolean(bold) })
    if (localEnd < segment.text.length) result.push({ text: segment.text.slice(localEnd), bold: segment.bold })
  }
  return serializeInlineBold(result)
}

export function toggleInlineBoldRange(value = '', start = 0, end = 0) {
  const safeStart = Math.max(0, Number(start) || 0)
  const safeEnd = Math.max(safeStart, Number(end) || 0)
  let cursor = 0
  let hasSelectedText = false
  let selectionIsFullyBold = true
  for (const segment of parseInlineBold(value)) {
    const segmentStart = cursor
    const segmentEnd = cursor + segment.text.length
    cursor = segmentEnd
    const overlapStart = Math.max(safeStart, segmentStart)
    const overlapEnd = Math.min(safeEnd, segmentEnd)
    if (overlapStart >= overlapEnd) continue
    // Newlines and spacing are formatting-neutral. A selection spanning
    // several fully-bold lines must still be recognized as fully bold so
    // Ctrl+B can remove the markers from every line.
    const selectedText = segment.text.slice(overlapStart - segmentStart, overlapEnd - segmentStart)
    if (!selectedText.trim()) continue
    hasSelectedText = true
    if (!segment.bold) selectionIsFullyBold = false
  }
  return setInlineBoldRange(value, safeStart, safeEnd, !(hasSelectedText && selectionIsFullyBold))
}

export function isFullyBoldInlineText(value = '') {
  const segments = parseInlineBold(value).filter(segment => segment.text.length > 0)
  return segments.length > 0 && segments.every(segment => segment.bold)
}

export function formatInlineHtml(value = '') {
  return parseInlineBold(String(value ?? '').trim()).map(segment => {
    const content = escapeHtml(segment.text)
    return segment.bold ? `<strong>${content}</strong>` : content
  }).join('')
}

function escapeHtml(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
