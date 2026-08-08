import test from 'node:test'
import assert from 'node:assert/strict'

import { normalizeLayoutConfig } from '../src/utils/layoutConfig.js'

test('legacy default layout migrates to compact v2 and exposes skills order', () => {
  const result = normalizeLayoutConfig({
    version: 1,
    global: {
      fontSize: 11,
      lineHeight: 1.6,
      moduleMargin: 1,
      marginVertical: 9,
      sectionOrder: ['education', 'project_experience', 'others']
    }
  })

  assert.equal(result.version, 2)
  assert.equal(result.global.fontSize, 10.5)
  assert.equal(result.global.lineHeight, 1.32)
  assert.ok(result.global.sectionOrder.indexOf('skills') > result.global.sectionOrder.indexOf('education'))
  assert.ok(result.global.sectionOrder.indexOf('skills') < result.global.sectionOrder.indexOf('project_experience'))
})

test('user-customized legacy spacing is preserved', () => {
  const result = normalizeLayoutConfig({
    version: 1,
    global: { fontSize: 9.5, lineHeight: 1.2, moduleMargin: 0.3, marginVertical: 6 }
  })

  assert.equal(result.global.fontSize, 9.5)
  assert.equal(result.global.lineHeight, 1.2)
  assert.equal(result.global.moduleMargin, 0.3)
  assert.equal(result.global.marginVertical, 6)
})

test('unknown model-generated module ids are discarded', () => {
  const result = normalizeLayoutConfig({
    version: 2,
    global: { sectionOrder: ['education', '乱码模块', 'skills', 'project_experience'] }
  })

  assert.equal(result.global.sectionOrder.includes('乱码模块'), false)
  assert.equal(new Set(result.global.sectionOrder).size, result.global.sectionOrder.length)
})
