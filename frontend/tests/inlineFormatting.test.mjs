import test from 'node:test'
import assert from 'node:assert/strict'

import { formatInlineHtml, parseInlineBold, plainInlineText } from '../src/utils/inlineFormatting.js'

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
