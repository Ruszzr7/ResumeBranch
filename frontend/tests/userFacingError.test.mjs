import test from 'node:test'
import assert from 'node:assert/strict'

import { userFacingApiError } from '../src/utils/userFacingError.js'

test('stable server errors use their Chinese public message', () => {
  assert.equal(
    userFacingApiError({ code: 'PDF_EXPORT_FAILED', detail: 'ValueError: chromium path' }),
    'PDF 导出失败，请稍后重试。'
  )
})

test('raw diagnostics fall back while ordinary Chinese validation remains visible', () => {
  assert.equal(
    userFacingApiError({ detail: 'sqlalchemy.exc.OperationalError: mysql' }, '加载失败'),
    '加载失败'
  )
  assert.equal(userFacingApiError({ detail: '邮箱格式不正确' }), '邮箱格式不正确')
})
