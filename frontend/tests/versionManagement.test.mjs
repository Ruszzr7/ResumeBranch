import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const appSource = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
const homepageSource = readFileSync(new URL('../src/views/Homepage.vue', import.meta.url), 'utf8')

test('main resume and version names use dedicated rename endpoints', () => {
  assert.ok(homepageSource.includes('method: \'PATCH\''))
  assert.ok(homepageSource.includes('`/projects/${projectToRename.value.id}`'))
  assert.ok(homepageSource.includes('aria-label="重命名简历组"'))
  assert.ok(homepageSource.includes('简历组名称'))
  assert.ok(appSource.includes('`/tasks/${taskToRename.value.id}`'))
  assert.ok(appSource.includes('aria-label="打开版本操作"'))
})

test('base replacement is explicit and preserves the selected version', () => {
  assert.ok(appSource.includes('`/tasks/${taskToSetBase.value.id}/set-as-base`'))
  assert.ok(appSource.includes('原主简历会变为“版本简历”'))
  assert.ok(appSource.includes('双方内容、照片、排版、JD 和对话均保留'))
  assert.ok(appSource.includes('>设为主简历</button>'))
})

test('base task display uses its stored title instead of a hard-coded label', () => {
  assert.ok(appSource.includes('function displayTaskTitle(task)'))
  assert.ok(appSource.includes('{{ displayTaskTitle(task) }}'))
  assert.equal(appSource.includes('plainDisplayText(task.is_base ? \'基础简历\' : task.title)'), false)
})
