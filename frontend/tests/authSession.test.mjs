import assert from 'node:assert/strict'
import test from 'node:test'

function storage() {
  const values = new Map()
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key)
  }
}

test('an authorized expired session is redirected with a one-time Chinese notice', async () => {
  const redirects = []
  globalThis.localStorage = storage()
  globalThis.sessionStorage = storage()
  localStorage.setItem('access_token', 'old-token')
  localStorage.setItem('user', '{"id":1}')
  globalThis.window = {
    location: {
      origin: 'http://127.0.0.1:5173',
      replace: path => redirects.push(path)
    },
    fetch: async () => new Response(
      JSON.stringify({ detail: '账号已在其他设备登录' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } }
    )
  }

  const { installAuthFailureInterceptor, consumeAuthSessionNotice } = await import('../src/config/authSession.js')
  installAuthFailureInterceptor()

  const response = await window.fetch('/api/resume', {
    headers: { Authorization: 'Bearer old-token' }
  })

  assert.equal(response.status, 401)
  assert.deepEqual(redirects, ['/login'])
  assert.equal(localStorage.getItem('access_token'), null)
  assert.match(consumeAuthSessionNotice(), /其他位置重新登录/)
  assert.equal(consumeAuthSessionNotice(), '')
})
