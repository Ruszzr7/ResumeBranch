import test from 'node:test'
import assert from 'node:assert/strict'

import { localizeInternalFieldReferences, userFacingFieldLabel } from '../src/utils/fieldLabels.js'


test('internal resume field paths are rendered in Chinese', () => {
  assert.equal(userFacingFieldLabel('basics.target_position'), '目标岗位')
  assert.equal(userFacingFieldLabel('birth_date'), '出生年月')
  assert.equal(userFacingFieldLabel('基础信息 · target_position'), '基础信息 · 目标岗位')
  assert.equal(userFacingFieldLabel('custom_sections.0.items'), '条目')
})

test('unknown code-like fields use a safe Chinese fallback', () => {
  assert.equal(userFacingFieldLabel('future_internal_field'), '简历字段')
  assert.equal(userFacingFieldLabel('自定义说明'), '自定义说明')
  assert.equal(userFacingFieldLabel('numbered_list'), '编号')
  assert.equal(userFacingFieldLabel('bullet_list'), '分点')
})

test('historical assistant text localizes embedded internal field names', () => {
  assert.equal(
    localizeInternalFieldReferences('目标岗位(target_position)为空，self_evaluation 也为空。'),
    '目标岗位(目标岗位)为空，自我评价 也为空。'
  )
  assert.equal(
    localizeInternalFieldReferences('请检查 basics.target_position、school_name 与荣誉(honors)。'),
    '请检查 基础信息中的目标岗位、学校名称 与荣誉(主要荣誉)。'
  )
  assert.equal(
    localizeInternalFieldReferences('项目职责使用 numbered_list，普通内容使用 bullet_list。'),
    '项目职责使用 编号，普通内容使用 分点。'
  )
  assert.equal(
    localizeInternalFieldReferences('request_resume_edit 返回了 layout_config。'),
    '系统能力 返回了 内部信息。'
  )
})
