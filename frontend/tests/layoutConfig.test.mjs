import test from 'node:test'
import assert from 'node:assert/strict'

import { normalizeLayoutConfig, resolveLayoutTokens } from '../src/utils/layoutConfig.js'

test('legacy default layout migrates to compact v4 and exposes skills order', () => {
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

  assert.equal(result.version, 4)
  assert.equal(result.global.fontSize, 9)
  assert.equal(result.global.lineHeight, 1.28)
  assert.ok(result.global.sectionOrder.indexOf('skills') > result.global.sectionOrder.indexOf('education'))
  assert.ok(result.global.sectionOrder.indexOf('skills') < result.global.sectionOrder.indexOf('project_experience'))
})

test('all renderers receive the recorded Microsoft and Arial typography contract', () => {
  const config = normalizeLayoutConfig({
    version: 2,
    typography: { preset: 'unknown', latinFont: 'Random', eastAsiaFont: 'Random CJK' }
  })
  const tokens = resolveLayoutTokens(config, { fontSize: 9, moduleMargin: 0.55 })

  assert.equal(config.typography.preset, 'microsoft-office')
  assert.equal(config.typography.latinFont, 'Arial')
  assert.equal(config.typography.eastAsiaFont, 'Microsoft YaHei')
  assert.equal(tokens.fontFamilyCss, '"Arial", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif')
  assert.equal(tokens.bodyFontSizePt, 9)
  assert.equal(tokens.metaFontSizePt, 9)
  assert.equal(tokens.entryTitleFontSizePt, 10)
  assert.equal(tokens.sectionTitleFontSizePt, 11)
  assert.equal(tokens.nameFontSizePt, 14)
  assert.equal(tokens.bodyFontWeight, 400)
  assert.equal(tokens.metaFontWeight, 400)
  assert.equal(tokens.entryTitleFontWeight, 700)
  assert.equal(tokens.sectionTitleFontWeight, 700)
  assert.equal(tokens.nameFontWeight, 700)
  assert.equal(tokens.labelFontWeight, 700)
  assert.ok(Math.abs(tokens.moduleSpacingPt - 4.95) < 1e-9)
})

test('saved v3 defaults migrate to the v4 semantic body size', () => {
  const result = normalizeLayoutConfig({
    version: 3,
    global: { fontSize: 10.5, lineHeight: 1.32, moduleMargin: 0.45 }
  })

  assert.equal(result.version, 4)
  assert.equal(result.global.fontSize, 9)
  assert.equal(result.global.lineHeight, 1.28)
  assert.equal(result.global.moduleMargin, 0.55)
})

test('user-customized legacy spacing keeps its visual scale within safe bounds', () => {
  const result = normalizeLayoutConfig({
    version: 1,
    global: { fontSize: 9.5, lineHeight: 1.2, moduleMargin: 0.3, marginVertical: 6 }
  })

  assert.equal(result.global.fontSize, 8)
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
