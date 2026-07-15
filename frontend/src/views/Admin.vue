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
export default {
  name: 'Admin',
  data() {
    return {
      count: 5,
      loading: false,
      codes: []
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
        } else {
          alert('获取邀请码列表失败')
        }
      } catch (error) {
        console.error('获取邀请码列表失败:', error)
        alert('获取邀请码列表失败')
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
          const newCodes = await response.json()
          // 合并到列表
          this.codes = [...newCodes, ...this.codes]
          alert(`成功创建 ${newCodes.length} 个邀请码`)
        } else {
          const error = await response.json()
          alert(error.detail || '创建失败')
        }
      } catch (error) {
        console.error('创建邀请码失败:', error)
        alert('创建邀请码失败')
      } finally {
        this.loading = false
      }
    },

    formatTime(timeStr) {
      if (!timeStr) return '-'
      const date = new Date(timeStr)
      return date.toLocaleString('zh-CN')
    }
  }
}
</script>

<style scoped>
/* 页面布局 */
.admin-page {
  min-height: 100vh;
  background-color: rgb(254, 253, 251);
  display: flex;
  flex-direction: column;
}

/* 顶部导航 */
.admin-header {
  background-color: rgb(249, 245, 242);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
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
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.02em;
}

.back-link {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--text-secondary);
  font-size: 0.9rem;
  text-decoration: none;
  transition: color 0.2s;
}

.back-link:hover {
  color: var(--primary-color);
}

/* 主容器 */
.admin-container {
  flex: 1;
  display: flex;
  justify-content: center;
  padding: 2rem 1.5rem;
}

/* 卡片样式 */
.admin-card {
  background: white;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
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
  color: var(--text-primary);
  margin: 0 0 1rem 0;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border-color);
}

/* 创建表单 */
.create-form {
  display: flex;
  gap: 0.75rem;
}

.count-input {
  width: 80px;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 0.95rem;
  background: white;
  transition: border-color 0.2s;
}

.count-input:focus {
  outline: none;
  border-color: var(--primary-color);
}

.create-btn {
  flex: 1;
  padding: 0.6rem 1.25rem;
  background-color: var(--primary-color);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.create-btn:hover:not(:disabled) {
  background-color: var(--primary-hover);
}

.create-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* 刷新行 */
.refresh-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0.4rem 0.8rem;
  background: white;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover {
  background: var(--accent-color);
  color: var(--text-primary);
}

/* 表格容器 */
.table-container {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.code-table {
  width: 100%;
  border-collapse: collapse;
  background: white;
}

.code-table th,
.code-table td {
  padding: 0.7rem 1rem;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.code-table th {
  background: rgb(249, 245, 242);
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.code-table tr:last-child td {
  border-bottom: none;
}

.code-table tr:hover td {
  background: rgb(254, 253, 251);
}

.code-cell {
  font-family: 'SF Mono', 'Fira Code', 'Courier New', monospace;
  font-size: 0.9rem;
  letter-spacing: 0.5px;
  color: var(--text-primary);
}

.status {
  display: inline-block;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 500;
}

.status.unused {
  background: #ecfccb;
  color: #3f6212;
}

.status.used {
  background: #fef2f2;
  color: #991b1b;
}

/* 响应式 */
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
