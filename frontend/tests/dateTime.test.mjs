import assert from 'node:assert/strict'
import test from 'node:test'

import { formatRelativeUpdatedAt, parseBackendDate } from '../src/utils/dateTime.js'

test('treats legacy timezone-less backend timestamps as UTC', () => {
  const date = parseBackendDate('2026-08-25T02:00:00')
  assert.equal(date?.toISOString(), '2026-08-25T02:00:00.000Z')
})

test('keeps explicit timezone offsets intact', () => {
  const date = parseBackendDate('2026-08-25T02:00:00+08:00')
  assert.equal(date?.toISOString(), '2026-08-24T18:00:00.000Z')
})

test('formats a recent UTC edit without an eight-hour shift', () => {
  const now = Date.parse('2026-08-25T10:00:30Z')
  assert.equal(formatRelativeUpdatedAt('2026-08-25T10:00:00', now), '刚刚编辑')
})
