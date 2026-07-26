const fallbackConfig = {
  app_mode: 'multi_user',
  authentication_required: true,
  account_management_enabled: true,
  local_user_email: null
}

let configPromise = null

export function loadAppConfig() {
  if (!configPromise) {
    configPromise = fetch('/app/config')
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Failed to load app config: HTTP ${response.status}`)
        }
        return response.json()
      })
      .catch((error) => {
        console.error('加载应用模式失败，回退到多用户模式:', error)
        return fallbackConfig
      })
  }
  return configPromise
}

export function buildAuthorizationHeaders(token = localStorage.getItem('access_token')) {
  return token ? { Authorization: `Bearer ${token}` } : {}
}
