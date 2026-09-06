import test from 'node:test'
import assert from 'node:assert/strict'

import { hasMeaningfulResumeContent } from '../src/utils/resumePresence.js'

test('normalized empty resume is still considered empty', () => {
  assert.equal(hasMeaningfulResumeContent({
    parsing_status: 'none',
    formatting_version: 0,
    basics: { name: '', target_position: '', photo: 'data:image/png;base64,ignored' },
    education: [],
    work_experience: [],
    project_experience: [],
    others: { skills: [], certificates: [], languages: [] },
    self_evaluation: []
  }), false)
})

test('real resume text is considered meaningful at any depth', () => {
  assert.equal(hasMeaningfulResumeContent({ basics: { name: 'Alice' } }), true)
  assert.equal(hasMeaningfulResumeContent({ work_experience: [{ details: ['Built an API'] }] }), true)
})

test('photo alone does not bypass first-use onboarding', () => {
  assert.equal(hasMeaningfulResumeContent({ basics: { photo: 'data:image/png;base64,abc' } }), false)
})
