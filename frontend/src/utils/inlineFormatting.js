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
