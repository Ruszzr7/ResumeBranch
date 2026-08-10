import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const tabBarSource = readFileSync(resolve(currentDir, '../src/components/MobileTabBar.vue'), 'utf8')
const previewSource = readFileSync(resolve(currentDir, '../src/components/ResumePreview.vue'), 'utf8')

test('small-screen navigation keeps the dark workspace theme', () => {
  assert.ok(tabBarSource.includes('background: rgba(27, 28, 32, 0.98)'))
  assert.ok(tabBarSource.includes('background: #292a30'))
  assert.ok(tabBarSource.includes('color: #e4e6ed'))
  assert.ok(tabBarSource.includes('.pixel-switch.active .pixel-switch-label'))
  assert.ok(tabBarSource.includes('color: #ffffff'))
  assert.ok(tabBarSource.includes('border-radius: 0'))
  assert.ok(tabBarSource.includes('box-shadow: 2px 2px 0 #4a4d57'))
  assert.ok(tabBarSource.includes('box-shadow: 2px 2px 0 #78a6ff'))
})

test('small-screen resume controls remain legible on the dark toolbar', () => {
  assert.ok(previewSource.includes('background: rgba(30, 31, 36, 0.98)'))
  assert.ok(previewSource.includes('.compact-toolbar-btn'))
  assert.ok(previewSource.includes('color: #e4e6ed'))
  assert.ok(previewSource.includes('position: sticky'))
  assert.ok(previewSource.includes('bottom: auto'))
  assert.equal(previewSource.includes('<template v-if="isMobile">'), false)
})

test('resume contact details use a readable dark gray', () => {
  assert.ok(previewSource.includes('.contact-info'))
  assert.ok(previewSource.includes('color: #333333'))
})
