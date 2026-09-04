import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  applySelectedLayoutChanges,
  applySelectedResumeChanges,
  buildConfirmationPreview,
} from '../src/utils/confirmationPreview.js'
import { normalizeLayoutConfig } from '../src/utils/layoutConfig.js'

test('confirmation checkboxes drive the workspace preview state', () => {
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const message = readFileSync(new URL('../src/components/ChatMessage.vue', import.meta.url), 'utf8')

  assert.match(message, /@change="handleSelectionChange"/)
  assert.match(message, /emit\('selectionChange'/)
  assert.match(app, /@selectionChange="handleConfirmationSelectionChange"/)
  assert.match(app, /refreshConfirmationPreview\(targetState, selected_change_ids\)/)
})

test('selected content changes rebuild the right-side preview from the saved resume', () => {
  const base = {
    education: [
      { school_name: '广东工业大学', degree: '本科' },
      { school_name: '广东工业大学', degree: '硕士' },
    ],
  }
  const changes = [
    {
      id: 'change-1', operation: 'replace',
      path: ['education', 0, 'school_name'], after: '暨南大学',
    },
    {
      id: 'change-2', operation: 'replace',
      path: ['education', 1, 'school_name'], after: '暨南大学',
    },
  ]

  const preview = applySelectedResumeChanges(base, changes, ['change-1'])

  assert.equal(preview.education[0].school_name, '暨南大学')
  assert.equal(preview.education[1].school_name, '广东工业大学')
  assert.equal(base.education[0].school_name, '广东工业大学')
})

test('no selected content changes restores the saved resume', () => {
  const base = { basics: { name: '原姓名' } }
  const changes = [{
    id: 'change-1', operation: 'replace', path: ['basics', 'name'], after: '新姓名',
  }]

  assert.deepEqual(applySelectedResumeChanges(base, changes, []), base)
})

test('selected list removals use descending indexes like backend confirmation', () => {
  const base = { education: [{ school_name: 'A' }, { school_name: 'B' }, { school_name: 'C' }] }
  const changes = [
    { id: 'change-1', operation: 'remove', path: ['education', 1], after: null },
    { id: 'change-2', operation: 'remove', path: ['education', 2], after: null },
  ]

  const preview = applySelectedResumeChanges(base, changes, ['change-1', 'change-2'])

  assert.deepEqual(preview.education, [{ school_name: 'A' }])
})

test('layout groups update only the selected module', () => {
  const base = normalizeLayoutConfig({})
  const candidate = normalizeLayoutConfig({
    ...base,
    global: { ...base.global, lineHeight: 1.5 },
    education: { ...base.education, supplementListStyle: 'numbered' },
  })
  const changes = [
    { id: 'layout-global', kind: 'layout', module: 'global' },
    { id: 'layout-education', kind: 'layout', module: 'education' },
  ]

  const preview = applySelectedLayoutChanges(
    base, candidate, changes, ['layout-education']
  )

  assert.equal(preview.global.lineHeight, base.global.lineHeight)
  assert.equal(preview.education.supplementListStyle, 'numbered')
})

test('combined confirmation preview applies selected content and layout together', () => {
  const baseLayout = normalizeLayoutConfig({})
  const candidateLayout = normalizeLayoutConfig({
    ...baseLayout,
    education: { ...baseLayout.education, supplementListStyle: 'numbered' },
  })
  const changes = [
    { id: 'change-1', operation: 'replace', path: ['basics', 'name'], after: '新姓名' },
    { id: 'layout-education', kind: 'layout', module: 'education' },
  ]

  const preview = buildConfirmationPreview({
    baseResumeData: { basics: { name: '原姓名' } },
    baseLayoutConfig: baseLayout,
    candidateLayoutConfig: candidateLayout,
    changes,
    selectedChangeIds: ['change-1'],
  })

  assert.equal(preview.resumeData.basics.name, '新姓名')
  assert.equal(
    preview.layoutConfig.education.supplementListStyle,
    baseLayout.education.supplementListStyle
  )
})
