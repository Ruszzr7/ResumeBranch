import test from 'node:test'
import assert from 'node:assert/strict'

import { normalizeLayoutConfig, resolveContentBlockFlow, resolveLayoutTokens } from '../src/utils/layoutConfig.js'

test('content block flow keeps inline and separate labels explicit', () => {
  assert.deepEqual(resolveContentBlockFlow({ type: 'paragraph', label: '项目简介' }), {
    type: 'paragraph', label: '项目简介', labelPlacement: 'inline', labelBold: true, prefixText: '项目简介：'
  })
  assert.equal(resolveContentBlockFlow({ type: 'numbered_list', label: '项目职责' }).labelPlacement, 'separate')
  assert.equal(resolveContentBlockFlow({ type: 'bullet_list', label: '' }).labelPlacement, 'none')
  assert.equal(resolveContentBlockFlow({ type: 'paragraph', label: '项目简介', label_bold: false }).labelBold, false)
})

test('legacy default layout migrates to compact v5 and exposes skills order', () => {
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

  assert.equal(result.version, 5)
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
  assert.equal(tokens.letterSpacingPt, 0)
  assert.ok(Math.abs(tokens.moduleSpacingPt - 4.95) < 1e-9)
})

test('saved v3 defaults migrate through v4 scale to explicit v5 semantic sizes', () => {
  const result = normalizeLayoutConfig({
    version: 3,
    global: { fontSize: 10.5, lineHeight: 1.32, moduleMargin: 0.45 }
  })

  assert.equal(result.version, 5)
  assert.equal(result.global.fontSize, 9)
  assert.equal(result.global.lineHeight, 1.28)
  assert.equal(result.global.moduleMargin, 0.55)
  assert.deepEqual(result.typography.fontSizes, {
    name: 14, sectionTitle: 11, entryTitle: 10, meta: 9, body: 9, label: 9
  })
})

test('saved v4 body size migrates without changing its visual hierarchy', () => {
  const result = normalizeLayoutConfig({ version: 4, global: { fontSize: 9.5 } })
  assert.deepEqual(result.typography.fontSizes, {
    name: 14, sectionTitle: 11.5, entryTitle: 10.5, meta: 9.5, body: 9.5, label: 9.5
  })
})

test('semantic font sizes use half-point bounds and discard unknown roles', () => {
  const result = normalizeLayoutConfig({
    version: 5,
    global: { fontSize: 10.25 },
    typography: { fontSizes: {
      name: 99, sectionTitle: 11.26, entryTitle: 8,
      meta: 10.24, body: 8, label: 11.75, unknown: 42
    } }
  })
  assert.equal(result.global.fontSize, 10.5)
  assert.deepEqual(result.typography.fontSizes, {
    name: 20, sectionTitle: 11.5, entryTitle: 8.5,
    meta: 10, body: 10.5, label: 12
  })
  const tokens = resolveLayoutTokens(result)
  assert.equal(tokens.labelFontSizePt, 12)
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
