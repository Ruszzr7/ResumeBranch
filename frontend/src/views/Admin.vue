<template>
  <div class="admin-page">
    <header class="admin-header">
      <div class="header-content">
        <h1 class="admin-title">邀请码管理</h1>
        <router-link to="/" class="back-link">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
          返回首页
        </router-link>
      </div>
    </header>

    <main class="admin-container">
      <div class="admin-card">
        <div v-if="notice.message" :class="['admin-notice', notice.type]" role="status">
          {{ notice.message }}
        </div>
        <!-- 创建邀请码 -->
        <div class="section">
          <h2>创建邀请码</h2>
          <div class="create-form">
            <input v-model.number="count" type="number" min="1" max="20" placeholder="数量" class="count-input" />
            <button @click="createCodes" :disabled="loading" class="create-btn">
              {{ loading ? '创建中...' : `生成 ${count || 1} 个邀请码` }}
            </button>
          </div>
        </div>

        <!-- 邀请码列表 -->
        <div class="section">
          <h2>邀请码列表</h2>
          <div class="refresh-row">
            <span>共 {{ codes.length }} 个邀请码</span>
            <button @click="fetchCodes" class="refresh-btn">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10"></polyline>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
              </svg>
              刷新
            </button>
          </div>
          <div class="table-container">
            <table class="code-table">
              <thead>
                <tr>
                  <th>邀请码</th>
                  <th>状态</th>
                  <th>创建时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="code in codes" :key="code.code">
                  <td class="code-cell">{{ code.code }}</td>
                  <td>
                    <span :class="['status', code.is_used ? 'used' : 'unused']">
                      {{ code.is_used ? '已使用' : '未使用' }}
                    </span>
                  </td>
                  <td>{{ formatTime(code.created_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script>
import { parseBackendDate } from '../utils/dateTime.js'

export default {
  name: 'Admin',
  data() {
    return {
      count: 5,
      loading: false,
      codes: [],
      notice: { type: '', message: '' }
    }
  },
  mounted() {
    this.fetchCodes()
  },
  methods: {
    async fetchCodes() {
      try {
        const token = localStorage.getItem('access_token')
        const response = await fetch('/auth/invite-codes', {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })
        if (response.ok) {
          this.codes = await response.json()
        } else if (response.status === 401) {
          this.clearSession()
        } else if (response.status === 403) {
          this.$router.replace('/')
        } else {
          this.showNotice('获取邀请码列表失败', 'error')
        }
      } catch (error) {
        console.error('获取邀请码列表失败:', error)
        this.showNotice('获取邀请码列表失败', 'error')
      }
    },

    async createCodes() {
      this.loading = true
      try {
        const token = localStorage.getItem('access_token')
        const response = await fetch('/auth/invite-codes', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ count: this.count || 5 })
        })
        if (response.ok) {
          const result = await response.json()
          const newCodes = Array.isArray(result) ? result : [result]
          // 合并到列表
          this.codes = [...newCodes, ...this.codes]
          this.showNotice(`成功创建 ${newCodes.length} 个邀请码`, 'success')
        } else if (response.status === 401) {
          this.clearSession()
        } else if (response.status === 403) {
          this.$router.replace('/')
        } else {
          const error = await response.json()
          this.showNotice(error.detail || '创建失败', 'error')
        }
      } catch (error) {
        console.error('创建邀请码失败:', error)
        this.showNotice('创建邀请码失败', 'error')
      } finally {
        this.loading = false
      }
    },

    formatTime(timeStr) {
      if (!timeStr) return '-'
      const date = parseBackendDate(timeStr)
      return date ? date.toLocaleString('zh-CN') : '-'
    },

    showNotice(message, type = 'success') {
      this.notice = { type, message }
    },

    clearSession() {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      this.$router.replace('/login')
    }
  }
}
</script>

<style scoped>
.admin-page {
  min-height: 100vh;
  color-scheme: dark;
  color: #f5f5f7;
  background:
    radial-gradient(circle at 18% 0%, rgba(120, 166, 255, 0.09), transparent 32rem),
    #050506;
  display: flex;
  flex-direction: column;
}

.admin-header {
  background: rgba(17, 18, 23, 0.96);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding: 0;
}

.header-content {
  max-width: 800px;
  margin: 0 auto;
  padding: 0.7rem 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.admin-title {
  font-size: 1.1rem;
  font-family: 'Plaak-CondensedBold', sans-serif;
  font-weight: 400;
  color: #f5f5f7;
  margin: 0;
  letter-spacing: -0.02em;
}

.back-link {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #aeb0b8;
  font-size: 0.9rem;
  text-decoration: none;
  transition: color 0.2s;
}

.back-link:hover {
  color: #78a6ff;
}

.admin-container {
  flex: 1;
  display: flex;
  justify-content: center;
  padding: 2rem 1.5rem;
}

.admin-card {
  background: #121317;
  border: 1px solid rgba(255, 255, 255, 0.11);
  border-radius: 8px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.34);
  padding: 1.5rem;
  width: 100%;
  max-width: 700px;
}

.section {
  margin-bottom: 1.5rem;
}

.section:last-child {
  margin-bottom: 0;
}

h2 {
  font-size: 0.95rem;
  font-weight: 600;
  color: #f5f5f7;
  margin: 0 0 1rem 0;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.create-form {
  display: flex;
  gap: 0.75rem;
}

.count-input {
  width: 80px;
  padding: 0.6rem 0.75rem;
  color: #f5f5f7;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: var(--radius-md);
  font-size: 0.95rem;
  background: #2b2c32;
  transition: border-color 0.2s;
}

.count-input:focus {
  outline: none;
  border-color: #78a6ff;
  box-shadow: 0 0 0 3px rgba(120, 166, 255, 0.1);
}

.count-input:-webkit-autofill,
.count-input:-webkit-autofill:hover,
.count-input:-webkit-autofill:focus {
  -webkit-text-fill-color: #f5f5f7 !important;
  -webkit-box-shadow: 0 0 0 1000px #2b2c32 inset !important;
}

.create-btn {
  flex: 1;
  padding: 0.6rem 1.25rem;
  background-color: #5f8ff2;
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.create-btn:hover:not(:disabled) {
  background-color: #78a6ff;
}

.create-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.refresh-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  color: #aeb0b8;
  font-size: 0.9rem;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0.4rem 0.8rem;
  background: #202127;
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
  color: #c6c7ce;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover {
  background: #2b2c32;
  color: #f5f5f7;
}

.table-container {
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.code-table {
  width: 100%;
  border-collapse: collapse;
  color: #d8d9df;
  background: #17181d;
}

.code-table th,
.code-table td {
  padding: 0.7rem 1rem;
  text-align: left;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.code-table th {
  background: #202127;
  font-weight: 600;
  font-size: 0.85rem;
  color: #aeb0b8;
}

.code-table tr:last-child td {
  border-bottom: none;
}

.code-table tr:hover td {
  background: #202127;
}

.code-cell {
  font-family: 'SF Mono', 'Fira Code', 'Courier New', monospace;
  font-size: 0.9rem;
  letter-spacing: 0.5px;
  color: #f5f5f7;
}

.status {
  display: inline-block;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 500;
}

.status.unused {
  background: rgba(76, 210, 146, 0.14);
  color: #79d9a9;
}

.status.used {
  background: rgba(255, 108, 117, 0.14);
  color: #ff9299;
}

.admin-notice {
  margin-bottom: 1rem;
  padding: 0.75rem 0.9rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: #202127;
  font-size: 0.88rem;
}

.admin-notice.success {
  color: #79d9a9;
  border-color: rgba(76, 210, 146, 0.3);
}

.admin-notice.error {
  color: #ff9299;
  border-color: rgba(255, 108, 117, 0.3);
}

@media (max-width: 600px) {
  .header-content {
    flex-direction: column;
    gap: 0.5rem;
    align-items: flex-start;
  }

  .create-form {
    flex-direction: column;
  }

  .count-input {
    width: 100%;
  }

  .code-table th:nth-child(3),
  .code-table td:nth-child(3) {
    display: none;
  }
}
</style>
