import test from 'node:test'
import assert from 'node:assert/strict'

import {
  formatInlineHtml,
  isFullyBoldInlineText,
  joinInlineLabelValue,
  joinInlineWithInheritedSeparator,
  parseInlineBold,
  plainInlineText,
  toggleInlineBoldRange
} from '../src/utils/inlineFormatting.js'

test('rendering preserves source whitespace and natural break points', () => {
  for (const value of [
    '中文与 ASCII token 保留普通空格',
    '括号（全角）与(parentheses)保持原样',
    '混排 A1/B2、C++ API，标点不被改写'
  ]) {
    assert.equal(plainInlineText(value), value)
    assert.equal(formatInlineHtml(value), value)
  }
})

test('paired bold markers become the only allowed inline element', () => {
  assert.equal(
    formatInlineHtml('<img src=x onerror="boom"> **安全结果**'),
    '&lt;img src=x onerror=&quot;boom&quot;&gt; <strong>安全结果</strong>'
  )
})

test('unmatched markers stay literal and visible', () => {
  const value = '负责 **核心模块'
  assert.deepEqual(parseInlineBold(value), [{ text: value, bold: false }])
  assert.equal(plainInlineText(value), value)
})

test('mixed Chinese and English text keeps exact content around bold runs', () => {
  const value = '将 P95 latency **降低 35%**，并支持 10k QPS'
  assert.equal(plainInlineText(value), '将 P95 latency 降低 35%，并支持 10k QPS')
  assert.equal(
    formatInlineHtml(value),
    '将 P95 latency <strong>降低 35%</strong>，并支持 10k QPS'
  )
})

test('selection formatting toggles deterministically without exposing storage markers', () => {
  assert.equal(toggleInlineBoldRange('姓名', 0, 2), '**姓名**')
  assert.equal(toggleInlineBoldRange('**姓名**', 0, 2), '姓名')
  assert.equal(toggleInlineBoldRange('A **粗体** C', 2, 4), 'A 粗体 C')
  assert.equal(toggleInlineBoldRange('A **粗体** C', 0, 6), '**A 粗体 C**')
})

test('number marker is bold only when all visible content is bold', () => {
  assert.equal(isFullyBoldInlineText('**整段粗体**'), true)
  assert.equal(isFullyBoldInlineText('**部分粗体**其余常规'), false)
  assert.equal(isFullyBoldInlineText('**粗体一**常规**粗体二**'), false)
})

test('a bold selection spanning lines closes markers on every line', () => {
  const bold = toggleInlineBoldRange('第一行\n第二行', 0, 7)
  assert.equal(bold, '**第一行**\n**第二行**')
  assert.equal(plainInlineText(bold), '第一行\n第二行')
  assert.equal(toggleInlineBoldRange(bold, 0, 7), '第一行\n第二行')
})

test('joined separators require both adjacent fields to be bold', () => {
  const value = joinInlineWithInheritedSeparator(['**2024.01**', '2024.06'], ' - ')
  assert.equal(value, '**2024.01** - 2024.06')
  assert.equal(formatInlineHtml(value), '<strong>2024.01</strong> - 2024.06')

  const mixed = joinInlineWithInheritedSeparator(['**本科**', '专业', '**成绩**'], ' · ')
  assert.equal(plainInlineText(mixed), '本科 · 专业 · 成绩')
  assert.equal(formatInlineHtml(mixed), '<strong>本科</strong> · 专业 · <strong>成绩</strong>')

  const labeled = joinInlineLabelValue('**证书**', '软件设计师', '：')
  assert.equal(formatInlineHtml(labeled), '<strong>证书：</strong>软件设计师')
})
