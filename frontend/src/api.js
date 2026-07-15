// 前端 API 配置
// 根据环境自动选择 API 地址

// 获取 API 地址
function getApiBase() {
  // 生产环境：使用相对路径（Nginx 会代理 /api/ 到后端）
  if (import.meta.env.PROD) {
    return ''
  }
  // 开发环境：代理路径（与 vite.config.js 中的 proxy 配置一致）
  return ''
}

// 通用 fetch 封装
async function apiFetch(path, options = {}) {
  const base = getApiBase()
  const url = `${base}${path}`
  
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    }
  })
  
  if (!response.ok) {
    throw new Error(`API Error: ${response.status}`)
  }
  
  return response.json()
}

export { getApiBase, apiFetch }
