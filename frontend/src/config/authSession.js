export const AUTH_SESSION_NOTICE_KEY = 'resume_assistant_auth_notice'

let installed = false
let redirecting = false

function requestHasAuthorization(input, init) {
  const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined))
  return headers.has('Authorization')
}

function requestPath(input) {
  const raw = input instanceof Request ? input.url : String(input || '')
  try {
    return new URL(raw, window.location.origin).pathname
  } catch {
    return raw
  }
}

async function expiredMessage(response) {
  try {
    const payload = await response.clone().json()
    const detail = String(payload?.detail || payload?.message || '')
    if (detail.includes('其他设备') || detail.includes('其他位置')) {
      return '该账号已在其他位置重新登录，当前登录已失效。请重新登录。'
    }
  } catch {
    // A non-JSON 401 still follows the same public session-expired path.
  }
  return '登录状态已失效，请重新登录。'
}

export function installAuthFailureInterceptor() {
  if (installed || typeof window === 'undefined') return
  installed = true
  const nativeFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const response = await nativeFetch(input, init)
    const path = requestPath(input)
    if (
      response.status === 401
      && requestHasAuthorization(input, init)
      && !path.startsWith('/auth/login')
      && !path.startsWith('/auth/register')
      && !redirecting
    ) {
      redirecting = true
      sessionStorage.setItem(AUTH_SESSION_NOTICE_KEY, await expiredMessage(response))
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      window.location.replace('/login')
    }
    return response
  }
}

export function consumeAuthSessionNotice() {
  const message = sessionStorage.getItem(AUTH_SESSION_NOTICE_KEY) || ''
  sessionStorage.removeItem(AUTH_SESSION_NOTICE_KEY)
  return message
}
