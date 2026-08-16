import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CONTENT_BLOCK_TYPE_OPTIONS,
  normalizeContentBlock,
  normalizeContentBlocks
} from '../src/utils/resumeContract.js'

test('content block contract exposes Chinese UI labels for internal types', () => {
  assert.deepEqual(CONTENT_BLOCK_TYPE_OPTIONS, {
    paragraph: '段落',
    bullet_list: '分点',
    numbered_list: '编号'
  })
})

test('content block aliases and boolean strings normalize consistently', () => {
  assert.deepEqual(normalizeContentBlock({
    type: 'numbered',
    semantic_role: 'responsibility',
    label: '项目职责',
    label_bold: 'false',
    items: ['(1) 设计模块', '2. 验证模块']
  }), {
    type: 'numbered_list',
    semantic_role: 'responsibilities',
    label: '项目职责',
    label_bold: false,
    text: '',
    items: ['设计模块', '验证模块']
  })
})

test('content block defaults follow semantic roles and unknown labels stay inline', () => {
  assert.equal(normalizeContentBlock({ semantic_role: 'introduction', label: '项目简介', text: '背景' }).type, 'paragraph')
  assert.equal(normalizeContentBlock({ semantic_role: 'responsibilities', label: '项目职责', items: ['职责'] }).type, 'numbered_list')
  assert.equal(normalizeContentBlock({ semantic_role: 'generic', label: '', items: ['普通内容'] }).type, 'bullet_list')
  assert.deepEqual(normalizeContentBlock({ label: '未定义前缀', items: ['基于 **方法** 完成'] }), {
    type: 'bullet_list',
    semantic_role: 'generic',
    label: '',
    label_bold: true,
    text: '',
    items: ['**未定义前缀**：基于 **方法** 完成']
  })
})

test('legacy introduction followed by points shares the responsibilities contract', () => {
  const blocks = normalizeContentBlocks([], [
    '项目简介：负责展厅导航系统',
    '完成模块设计与实现',
    '完成联调与性能验证'
  ], { experienceKind: 'work' })
  assert.equal(blocks[0].semantic_role, 'introduction')
  assert.equal(blocks[1].semantic_role, 'responsibilities')
  assert.equal(blocks[1].label, '项目职责')
  assert.deepEqual(blocks[1].items, ['完成模块设计与实现', '完成联调与性能验证'])
})

test('legacy scalar details are normalized instead of being dropped', () => {
  const blocks = normalizeContentBlocks([], '项目简介：负责模块设计', { experienceKind: 'project' })
  assert.equal(blocks[0].semantic_role, 'introduction')
  assert.equal(blocks[0].text, '负责模块设计')
})

test('explicit responsibility headings also work for legacy work details', () => {
  const blocks = normalizeContentBlocks([], [
    '项目职责：',
    '（1）完成模块设计',
    '（2）完成联调验证'
  ], { experienceKind: 'work' })
  assert.equal(blocks[0].semantic_role, 'responsibilities')
  assert.equal(blocks[0].type, 'numbered_list')
  assert.deepEqual(blocks[0].items, ['完成模块设计', '完成联调验证'])
})

test('bold semantic headings and unlabeled lists keep their responsibility role', () => {
  const legacy = normalizeContentBlocks([], [
    '**项目简介**：**负责导航系统设计**',
    '**完成模块实现**',
    '完成联调验证'
  ], { experienceKind: 'work' })
  assert.equal(legacy[0].semantic_role, 'introduction')
  assert.equal(legacy[0].text, '**负责导航系统设计**')
  assert.equal(legacy[1].semantic_role, 'responsibilities')

  const explicit = normalizeContentBlocks([
    { type: 'paragraph', semantic_role: 'introduction', label: '项目简介', text: '项目背景' },
     { type: 'bullet_list', semantic_role: 'generic', label: '', items: ['补充说明'] }
  ])
  assert.equal(explicit[1].semantic_role, 'responsibilities')
  assert.equal(explicit[1].type, 'numbered_list')
  assert.deepEqual(explicit[1].items, ['补充说明'])
})

test('visual group is required for generic content after an intro', () => {
  const blocks = normalizeContentBlocks([
    { type: 'paragraph', semantic_role: 'introduction', label: '项目简介', text: '背景' },
    { type: 'bullet_list', label: '普通工作内容', items: ['完成设计'], source_layout_group: 'duties' },
    { type: 'bullet_list', label: '其他项目内容', items: ['补充说明'], source_layout_group: 'generic' }
  ])
  assert.deepEqual(blocks.map(block => block.semantic_role), ['introduction', 'responsibilities', 'generic'])
  assert.deepEqual(blocks.map(block => block.type), ['paragraph', 'numbered_list', 'bullet_list'])
  assert.deepEqual(blocks.map(block => block.label), ['项目简介', '项目职责', ''])
  assert.deepEqual(blocks.slice(1).map(block => block.items), [['完成设计'], ['补充说明']])
})

test('unlabelled content after an explicit introduction defaults to responsibilities', () => {
  const blocks = normalizeContentBlocks([
    { type: 'paragraph', semantic_role: 'introduction', label: '项目简介', text: '背景' },
    { type: 'bullet_list', items: ['职责条目一'] }
  ])
  assert.equal(blocks[1].semantic_role, 'responsibilities')
  assert.equal(blocks[1].type, 'numbered_list')
  assert.equal(blocks[1].label, '项目职责')
  assert.deepEqual(blocks[1].items, ['职责条目一'])
})

test('unlabelled paragraph after an explicit introduction becomes one responsibility item', () => {
  const blocks = normalizeContentBlocks([
    { type: 'paragraph', semantic_role: 'introduction', label: '项目简介', text: '背景' },
    { type: 'paragraph', text: '职责段落' }
  ])
  assert.deepEqual(blocks.map(block => block.semantic_role), ['introduction', 'responsibilities'])
  assert.equal(blocks[1].type, 'numbered_list')
  assert.equal(blocks[1].label, '项目职责')
  assert.deepEqual(blocks[1].items, ['职责段落'])
})

test('an experience without semantic headings stays generic', () => {
  const blocks = normalizeContentBlocks([
    { type: 'bullet_list', items: ['内容一', '内容二'] },
    { type: 'paragraph', text: '补充内容' }
  ])
  assert.deepEqual(blocks.map(block => block.semantic_role), ['generic', 'generic'])
  assert.deepEqual(blocks.map(block => block.type), ['bullet_list', 'paragraph'])
})

test('explicit generic multi-item content after an introduction stays generic', () => {
  const blocks = normalizeContentBlocks([
    { type: 'paragraph', semantic_role: 'introduction', label: '项目简介', text: '背景' },
     { type: 'bullet_list', semantic_role: 'generic', label: '', items: ['补充说明一', '补充说明二'] }
  ])
  assert.equal(blocks[1].semantic_role, 'responsibilities')
  assert.equal(blocks[1].type, 'numbered_list')
  assert.deepEqual(blocks[1].items, ['补充说明一', '补充说明二'])
})
