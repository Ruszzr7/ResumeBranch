import test from 'node:test'
import assert from 'node:assert/strict'

import { DEFAULT_LAYOUT_CONFIG, componentPosition, customSectionIndex, customSectionModuleId, expandSectionOrderForData, formatCompactAcademicMetric, isCompactAcademicMetricLeadingBold, isCustomSectionModule, normalizeLayoutConfig, resolveContentBlockFlow, resolveEducationColumnWidths, resolveLayoutTokens, resolveModuleLayout, resolvePhotoHeightMm } from '../src/utils/layoutConfig.js'

test('current defaults use the compact practical spacing range', () => {
  const result = normalizeLayoutConfig(DEFAULT_LAYOUT_CONFIG)
  assert.equal(result.global.lineHeight, 1.25)
  assert.equal(result.global.moduleMargin, 0.5)
  assert.equal(result.global.titleStyle, 'underline')
  assert.equal(result.education.supplementListStyle, 'bullet')
  assert.deepEqual(result.education.childSectionOrder, [
    'education_supplement', 'honors', 'publications', 'research_interests', 'others'
  ])
  assert.equal(result.basics.photoWidthMm, 21)
  assert.equal(normalizeLayoutConfig({ global: { lineHeight: 9, moduleMargin: 9 } }).global.lineHeight, 1.8)
  assert.equal(normalizeLayoutConfig({ global: { lineHeight: 9, moduleMargin: 9 } }).global.moduleMargin, 1)
  assert.deepEqual(result.global.sectionPlacements, {})
  assert.deepEqual(result.others.componentRows.map(row => row.cells[0].components), [['certificates'], ['languages']])
  assert.deepEqual(result.global.sectionOrder, [
    'education', 'honors', 'publications', 'research_interests', 'skills',
    'work_experience', 'project_experience', 'custom_sections', 'others', 'self_evaluation'
  ])
})

test('education supplement list style is normalized as part of the shared education contract', () => {
  assert.equal(normalizeLayoutConfig({ version: 8, education: { supplementListStyle: 'numbered' } }).education.supplementListStyle, 'numbered')
  assert.equal(normalizeLayoutConfig({ version: 8, education: { supplementListStyle: 'invalid' } }).education.supplementListStyle, 'bullet')
})

test('education child order keeps explicit order and appends missing children', () => {
  assert.deepEqual(normalizeLayoutConfig({
    education: { childSectionOrder: ['research_interests', 'education_supplement', 'research_interests', 'invalid'] }
  }).education.childSectionOrder, [
    'research_interests', 'education_supplement', 'honors', 'publications', 'others'
  ])
})

test('retired education metrics placement is discarded', () => {
  const education = normalizeLayoutConfig({ education: { metricsPlacement: 'below' } }).education
  assert.equal('metricsPlacement' in education, false)
})

test('v7 default section order migrates without overwriting a user order', () => {
  const oldDefault = [
    'education', 'skills', 'research_interests', 'honors', 'publications',
    'work_experience', 'project_experience', 'custom_sections', 'others', 'self_evaluation'
  ]
  assert.deepEqual(normalizeLayoutConfig({ version: 7, global: { sectionOrder: oldDefault } }).global.sectionOrder, DEFAULT_LAYOUT_CONFIG.global.sectionOrder)

  const custom = [
    'education', 'publications', 'honors', 'research_interests', 'skills',
    'work_experience', 'project_experience', 'custom_sections', 'others', 'self_evaluation'
  ]
  assert.deepEqual(normalizeLayoutConfig({ version: 7, global: { sectionOrder: custom } }).global.sectionOrder, custom)
})

test('custom sections expand into individually sortable virtual modules', () => {
  const data = {
    custom_sections: [
      { title: '项目A', items: ['A'] },
      { title: '项目B', items: ['B'] }
    ]
  }
  const expanded = expandSectionOrderForData({
    global: { sectionOrder: ['education', 'custom_sections', 'work_experience'] }
  }, data).global.sectionOrder
  assert.equal(customSectionModuleId(0), 'custom_sections:0')
  assert.equal(customSectionIndex('custom_sections:1'), 1)
  assert.equal(isCustomSectionModule('custom_sections:1'), true)
  assert.ok(expanded.indexOf('custom_sections:0') < expanded.indexOf('work_experience'))
  assert.ok(expanded.indexOf('custom_sections:1') < expanded.indexOf('work_experience'))

  const reordered = normalizeLayoutConfig({
    global: { sectionOrder: ['custom_sections:1', 'work_experience', 'custom_sections:0'] }
  })
  assert.equal(reordered.global.sectionOrder.includes('custom_sections'), false)
  assert.deepEqual(resolveModuleLayout(reordered, 'custom_sections:1').componentRows, reordered.custom_sections.componentRows)
})

test('module headings stay global and retired module layouts are discarded', () => {
  const result = normalizeLayoutConfig({
    basics: { photoWidthMm: 99, titleAlignment: 'center', contactLayout: 'stacked' },
    education: { titleStyle: 'plain', titleAlignment: 'right' },
    work_experience: { preset: 'classic' },
    internship_experience: { preset: 'classic' }
  })
  assert.equal(result.basics.photoWidthMm, 30)
  assert.equal('contactLayout' in result.basics, false)
  assert.equal(result.basics.titleAlignment, null)
  assert.equal(result.education.titleStyle, null)
  assert.equal(result.education.titleAlignment, null)
  assert.equal('preset' in result.work_experience, false)
  assert.equal('internship_experience' in result, false)
  const tokens = resolveLayoutTokens(result)
  assert.equal(tokens.photoWidthMm, 30)
  assert.equal(tokens.photoHeightMm, 30 * 26 / 21)
})

test('photo height is capped before the next visible module while preserving the token fallback', () => {
  const config = normalizeLayoutConfig(DEFAULT_LAYOUT_CONFIG)
  const tokens = resolveLayoutTokens(config)
  const data = {
    basics: { name: '张三', photo: 'data:image/png;base64,placeholder', photo_aspect_ratio: 0.75 },
    education: [{ school_name: '示例大学' }]
  }

  const resolved = resolvePhotoHeightMm(data, config, tokens)

  assert.ok(resolved >= 10)
  assert.ok(resolved < tokens.photoHeightMm)
  assert.equal(resolvePhotoHeightMm({ basics: {} }, config, tokens), tokens.photoHeightMm)
})

test('content block flow keeps inline and separate labels explicit', () => {
  assert.deepEqual(resolveContentBlockFlow({ type: 'paragraph', label: '项目简介' }), {
    type: 'paragraph', label: '项目简介', semanticRole: 'introduction', requiresLabel: true,
    visible: true, labelMarker: 'bullet', contentIndentLevels: 1,
    labelPlacement: 'inline', labelBold: true, prefixText: '项目简介：'
  })
  assert.equal(resolveContentBlockFlow({ type: 'numbered_list', label: '项目职责' }).labelPlacement, 'separate')
  assert.equal(resolveContentBlockFlow({ type: 'bullet_list', label: '' }).labelPlacement, 'none')
  assert.equal(resolveContentBlockFlow({ type: 'paragraph', label: '项目简介', label_bold: false }).labelBold, false)
  assert.equal(resolveContentBlockFlow({ type: 'paragraph', semantic_role: 'introduction', label: '' }).visible, false)
  assert.equal(resolveContentBlockFlow({ type: 'bullet_list', semantic_role: 'generic', label: '' }).visible, true)
  assert.equal(resolveContentBlockFlow({ type: 'numbered_list', semantic_role: 'responsibilities', label: '主要贡献' }).contentIndentLevels, 2)
})

test('legacy default layout migrates to schema v10 and exposes every module in the new default order', () => {
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

  assert.equal(result.version, 10)
  assert.equal(result.global.fontSize, 9)
  assert.equal(result.global.lineHeight, 1.28)
  assert.ok(result.global.sectionOrder.indexOf('skills') > result.global.sectionOrder.indexOf('education'))
  assert.ok(result.global.sectionOrder.indexOf('skills') < result.global.sectionOrder.indexOf('project_experience'))
  assert.ok(result.global.sectionOrder.includes('publications'))
})

test('all renderers receive the recorded Microsoft and Times New Roman typography contract', () => {
  const config = normalizeLayoutConfig({
    version: 2,
    typography: { preset: 'unknown', latinFont: 'Random', eastAsiaFont: 'Random CJK' }
  })
  const tokens = resolveLayoutTokens(config, { fontSize: 9, moduleMargin: 0.55 })

  assert.equal(config.typography.preset, 'microsoft-office')
  assert.equal(config.typography.latinFont, 'Times New Roman')
  assert.equal(config.typography.eastAsiaFont, 'Microsoft YaHei')
  assert.equal(tokens.fontFamilyCss, '"Times New Roman", "Liberation Serif", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif')
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

test('compact education expands a symmetric middle frame for GPA and rank', () => {
  const tokens = resolveLayoutTokens(normalizeLayoutConfig())
  const short = resolveEducationColumnWidths(tokens, {
    schools: ['中山大学'], dates: ['2024.09 - 2027.06'],
    degreeMajors: ['硕士 · 电子信息'], compactMetrics: ['4.0/5.0 (前5%)']
  })
  const long = resolveEducationColumnWidths(tokens, {
    schools: ['中山大学'], dates: ['2024.09 - 2027.06'],
    degreeMajors: ['硕士 · 电子信息工程与人工智能'], compactMetrics: ['4.0/5.0 (前5%)']
  })
  assert.ok(long.middleMm > short.middleMm)
  assert.ok(Math.abs(short.sideMm * 2 + short.middleMm - 192) < 0.01)
  assert.ok(Math.abs(long.sideMm * 2 + long.middleMm - 192) < 0.01)
})

test('compact metric preserves the ranking wording entered by the user', () => {
  const base = { gpa: '3.8', gpa_scale: '5.0' }
  assert.equal(formatCompactAcademicMetric({ ...base, ranking: '10%' }), '3.8/5.0 (10%)')
  assert.equal(formatCompactAcademicMetric({ ...base, ranking: '前10%' }), '3.8/5.0 (前10%)')
})

test('compact metric treats score and ranking as separate groups', () => {
  assert.equal(
    formatCompactAcademicMetric({ gpa: '**4.0**', gpa_scale: '**5.0**', ranking: '**前5%**' }),
    '**4.0/5.0 (前5%)**'
  )
  assert.equal(
    formatCompactAcademicMetric({ gpa: '**4.0**', gpa_scale: '**5.0**', ranking: '前5%' }),
    '**4.0/5.0** (前5%)'
  )
  assert.equal(isCompactAcademicMetricLeadingBold({ gpa: '**4.0**', gpa_scale: '5.0', ranking: '前5%' }), true)
  assert.equal(isCompactAcademicMetricLeadingBold({ gpa: '**4.0**', gpa_scale: '5.0', ranking: '**前5%**' }), true)
  assert.equal(isCompactAcademicMetricLeadingBold({ gpa: '4.0', gpa_scale: '**5.0**', ranking: '**前5%**' }), false)
  assert.equal(isCompactAcademicMetricLeadingBold({ gpa: '', gpa_scale: '', ranking: '**前5%**' }), false)
})

test('saved v3 defaults migrate through the semantic scale to schema v10', () => {
  const result = normalizeLayoutConfig({
    version: 3,
    global: { fontSize: 10.5, lineHeight: 1.32, moduleMargin: 0.45 }
  })

  assert.equal(result.version, 10)
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

test('v5 standard default line height migrates to the compact export rhythm', () => {
  const result = normalizeLayoutConfig({ version: 5, global: { density: 'standard', lineHeight: 1.35 } })
  assert.equal(result.version, 10)
  assert.equal(result.global.lineHeight, 1.28)

  const custom = normalizeLayoutConfig({ version: 5, global: { density: 'standard', lineHeight: 1.4 } })
  assert.equal(custom.global.lineHeight, 1.4)
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

test('invalid enums unknown fields and duplicate sections normalize deterministically', () => {
  const config = normalizeLayoutConfig({
    version: 6,
    global: {
      density: 'invalid', titleStyle: 'invalid',
      sectionOrder: ['skills', 'education', 'skills', 'invalid'],
      hiddenSections: ['honors', 'invalid']
    },
    project_experience: { detailsStyle: 'numbered' },
    basics: { hiddenFields: ['phone', 'invalid'] }
  })
  assert.equal(config.global.density, 'compact')
  assert.equal(config.global.titleStyle, 'underline')
  assert.equal(config.global.sectionOrder.filter(item => item === 'skills').length, 1)
  assert.deepEqual(config.global.hiddenSections, ['honors'])
  assert.equal(config.project_experience.detailsStyle, 'bullets')
  assert.deepEqual(config.basics.hiddenFields, ['phone'])
})

test('module contracts inherit one global line height and normalize constrained component rows', () => {
  const config = normalizeLayoutConfig({
    version: 7,
    global: { lineHeight: 1.45 },
    work_experience: {
      indentLevel: 99,
      hiddenComponents: ['position', 'content', 'unknown'],
      componentRows: [{ cells: [{
        components: ['organization', 'content', 'unknown'],
        flow: 'inline', width: 'content', alignment: 'right'
      }] }]
    }
  })
  const module = resolveModuleLayout(config, 'work_experience')
  assert.equal(module.resolvedLineHeight, 1.45)
  assert.equal('lineHeight' in config.work_experience, false)
  assert.equal(config.work_experience.indentLevel, 3)
  assert.deepEqual(config.work_experience.hiddenComponents, ['position'])
  assert.deepEqual(componentPosition(config, 'work_experience', 'organization'), [1, 0])
  const contentRow = config.work_experience.componentRows.find(row => row.cells.some(cell => cell.components.includes('content')))
  assert.deepEqual(contentRow.cells, [{ components: ['content'], flow: 'stacked', width: 'fill', alignment: 'justify' }])
})

test('default compact education and list indents preserve the stable template geometry', () => {
  const config = normalizeLayoutConfig()
  assert.equal(config.education.componentRows[0].cells[1].alignment, 'left')
  assert.equal(config.skills.indentLevel, 0)
  assert.equal(config.research_interests.indentLevel, 0)
  assert.equal(config.honors.indentLevel, 0)
})
