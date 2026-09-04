import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('multi-user login is wired to JWT without changing the shared workspace', () => {
  const login = source('views/Login.vue')
  const router = source('router/index.js')

  assert.match(login, /fetch\('\/auth\/login'/)
  assert.match(login, /application\/x-www-form-urlencoded/)
  assert.match(login, /type="text"[\s\S]*name="username"/)
  assert.match(login, /邮箱 \/ 管理员账号/)
  assert.match(login, /普通用户输入邮箱，管理员可输入账号/)
  assert.match(login, /localStorage\.setItem\('access_token'/)
  assert.doesNotMatch(login, /登录接口待接入/)
  assert.match(router, /user\?\.is_admin === true/)
  assert.doesNotMatch(router, /admin@qq\.com/)
})

test('headers omit the local-mode badge and expose only server-backed account state', () => {
  const homepage = source('views/Homepage.vue')
  const app = source('App.vue')
  const accountMenu = source('components/AccountMenu.vue')

  assert.doesNotMatch(homepage, />\s*本地模式\s*</)
  assert.doesNotMatch(app, />\s*本地模式\s*</)
  assert.doesNotMatch(homepage, /class="mode-pill"/)
  assert.doesNotMatch(app, /class="workspace-mode-pill"/)
  assert.match(homepage, /<AccountMenu v-if="!isLocalMode && currentUser"/)
  assert.match(app, /<AccountMenu v-if="!isLocalMode && currentUser"/)
  assert.match(accountMenu, /user\?\.is_admin/)
  assert.match(accountMenu, /邀请码管理/)
  assert.match(accountMenu, /退出登录/)
  assert.doesNotMatch(accountMenu, /account-avatar/)
  assert.doesNotMatch(accountMenu, /const initial =/)
  assert.doesNotMatch(accountMenu, /\.account-label \{ display: none; \}/)
})

test('API settings stay local by default and are also visible to multi-user administrators', () => {
  const homepage = source('views/Homepage.vue')

  assert.match(homepage, /v-if="isLocalMode \|\| currentUser\?\.is_admin"/)
  assert.match(homepage, />\s*API 设置\s*</)
  assert.ok(
    homepage.indexOf('API 设置')
      < homepage.indexOf('<AccountMenu')
  )
})

test('multi-user logout is server-backed and task edits reuse the conversation status dot', () => {
  const homepage = source('views/Homepage.vue')
  const app = source('App.vue')

  assert.match(homepage, /fetch\('\/auth\/logout'/)
  assert.match(app, /fetch\('\/auth\/logout'/)
  assert.match(app, /edit-generating/)
  assert.match(app, /edit-awaiting/)
  assert.match(app, /owner_session_id/)
  assert.doesNotMatch(app, /class="edit-status-bar"/)
})

test('exports carry project and version names and report local persistence', () => {
  const preview = source('components/ResumePreview.vue')

  assert.match(preview, /project_name: props\.projectName/)
  assert.match(preview, /version_name: props\.versionName/)
  assert.match(preview, /X-Local-Export-Saved/)
  assert.match(preview, /output\/resumes/)
})

test('the local export-folder action is routed to the backend', () => {
  const viteConfig = readFileSync(new URL('../vite.config.js', import.meta.url), 'utf8')
  const nginxConfig = readFileSync(new URL('../nginx.conf', import.meta.url), 'utf8')

  assert.match(viteConfig, /'\/local':\s*\{/)
  assert.match(nginxConfig, /local\(\?:\/\.\*\)\?/)
})

test('confirmations use the dedicated endpoint and discard stale previews', () => {
  const app = source('App.vue')

  assert.match(app, /fetch\('\/confirm'/)
  assert.match(app, /formData\.append\('confirm_id', confirm_id\)/)
  assert.match(app, /formData\.append\('selected_change_ids', selected_change_ids\.join\(','\)\)/)
  assert.doesNotMatch(app, /CONFIRM_REPLY/)
  assert.match(app, /clearConfirmationPreview\(targetState\)[\s\S]*await updateResumeData\(\)/)
  assert.match(app, /error\.stalePreview = response\.status === 409/)
  assert.match(app, /if \(error\.stalePreview\)[\s\S]*clearConfirmationPreview\(targetState\)[\s\S]*await updateResumeData\(\)/)
})

test('login, registration and invite-code management retain the dark visual theme', () => {
  const login = source('views/Login.vue')
  const register = source('views/Register.vue')
  const admin = source('views/Admin.vue')

  assert.match(login, /input:-webkit-autofill/)
  assert.match(register, /input:-webkit-autofill/)
  assert.match(admin, /background:[\s\S]*#050506/)
  assert.match(admin, /background: #121317/)
  assert.match(admin, /class="\['admin-notice', notice\.type\]"/)
  assert.doesNotMatch(admin, /\balert\(/)
  assert.doesNotMatch(admin, /background(?:-color)?: (?:white|rgb\(254, 253, 251\)|rgb\(249, 245, 242\))/)
})

test('authorized 401 responses redirect to login with a visible session notice', () => {
  const main = source('main.js')
  const authSession = source('config/authSession.js')
  const login = source('views/Login.vue')

  assert.match(main, /installAuthFailureInterceptor\(\)/)
  assert.match(authSession, /response\.status === 401/)
  assert.match(authSession, /headers\.has\('Authorization'\)/)
  assert.match(authSession, /sessionStorage\.setItem\(AUTH_SESSION_NOTICE_KEY/)
  assert.match(authSession, /window\.location\.replace\('\/login'\)/)
  assert.match(login, /consumeAuthSessionNotice\(\)/)
  assert.match(login, /role="alertdialog"/)
})
