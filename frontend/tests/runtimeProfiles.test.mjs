import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('multi-user login is wired to JWT without changing the shared workspace', () => {
  const login = source('views/Login.vue')
  const router = source('router/index.js')

  assert.match(login, /fetch\('\/auth\/login'/)
  assert.match(login, /application\/x-www-form-urlencoded/)
  assert.match(login, /localStorage\.setItem\('access_token'/)
  assert.doesNotMatch(login, /登录接口待接入/)
  assert.match(router, /user\?\.is_admin === true/)
  assert.doesNotMatch(router, /admin@qq\.com/)
})

test('header identity is mode-aware and exposes only server-backed admin state', () => {
  const homepage = source('views/Homepage.vue')
  const accountMenu = source('components/AccountMenu.vue')

  assert.match(homepage, /v-if="isLocalMode" class="mode-pill"/)
  assert.match(homepage, /<AccountMenu v-else-if="currentUser"/)
  assert.match(accountMenu, /user\?\.is_admin/)
  assert.match(accountMenu, /邀请码管理/)
  assert.match(accountMenu, /退出登录/)
})

test('exports carry project and version names and report local persistence', () => {
  const preview = source('components/ResumePreview.vue')

  assert.match(preview, /project_name: props\.projectName/)
  assert.match(preview, /version_name: props\.versionName/)
  assert.match(preview, /X-Local-Export-Saved/)
  assert.match(preview, /output\/resumes/)
})
