import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const previewSource = readFileSync(new URL('../src/components/ResumePreview.vue', import.meta.url), 'utf8')

test('work and project details share semantic block rendering', () => {
  assert.ok(previewSource.includes('projectContentBlocks(entry.item).length'))
  assert.ok(previewSource.includes("block.type === 'numbered_list'"))
  assert.ok(previewSource.includes('project-block-label'))
})

test('preview pagination uses a small safety margin consistent with PDF export', () => {
  assert.equal(previewSource.includes('pageContentHeight - 120'), false)
  assert.equal(previewSource.includes('pageContentHeight - 150'), false)
  assert.ok(previewSource.includes('pageContentHeight - 8'))
})

test('layout menu opens a dedicated bidirectional manual ordering dialog', () => {
  assert.ok(previewSource.includes('调整模块顺序'))
  assert.ok(previewSource.includes('showSectionOrderDialog'))
  assert.ok(previewSource.includes('dragOverSection($event, section)'))
  assert.ok(previewSource.includes('拖动和箭头均支持双向调整'))
  assert.equal(previewSource.includes('根据 JD 推荐排序'), false)
})

test('section ordering uses a compact left-side dialog so the PDF stays visible', () => {
  assert.ok(previewSource.includes('width: calc((100vw - 156px) * 0.39)'))
  assert.ok(previewSource.includes('justify-content: flex-end'))
  assert.ok(previewSource.includes('width: min(340px, calc(100vw - 40px))'))
  assert.ok(previewSource.includes('background: rgba(7, 8, 11, 0.16)'))
})

test('section names are larger without enlarging the drag and arrow controls', () => {
  assert.ok(previewSource.includes('class="section-order-name"'))
  assert.ok(previewSource.includes('.section-order-name {'))
  assert.ok(previewSource.includes('font-size: 0.82rem'))
})

test('empty resume action remains visible on the dark preview background', () => {
  assert.ok(previewSource.includes('.no-data .jd-upload-btn'))
  assert.ok(previewSource.includes('color: #e4edff'))
  assert.ok(previewSource.includes('background: rgba(95, 143, 242, 0.2)'))
})

test('numbered generic items suppress the redundant outer bullet', () => {
  assert.ok(previewSource.includes('hasNativeListMarker'))
  assert.ok(previewSource.includes("'has-native-marker': hasNativeListMarker(item)"))
  assert.ok(previewSource.includes('.generic-list-item.has-native-marker::before'))
})
