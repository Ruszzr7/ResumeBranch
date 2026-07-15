<template>
  <div class="register-container">
    <div class="register-card">
      <div class="register-header">
        <h1>注册</h1>
      </div>
      
      <form @submit.prevent="handleRegister" class="register-form">
        <div class="form-group">
          <input
            id="email"
            v-model="email"
            type="email"
            placeholder="邮箱"
            required
          />
        </div>
        
        <div class="form-group">
          <input
            id="password"
            v-model="password"
            type="password"
            placeholder="密码（至少6位）"
            required
            minlength="6"
          />
        </div>
        
        <div class="form-group">
          <input
            id="inviteCode"
            v-model="inviteCode"
            type="text"
            placeholder="邀请码"
            required
          />
        </div>
        
        <div v-if="error" class="error-message">{{ error }}</div>
        <div v-if="success" class="success-message">{{ success }}</div>
        
        <div class="button-wrapper">
          <div class="button-shadow"></div>
          <button type="submit" class="submit-btn" :disabled="loading">
            {{ loading ? '注册中...' : '注册' }}
          </button>
        </div>
      </form>
      
      <div class="register-footer">
        <router-link to="/login" class="link-btn">已有账号？登录</router-link>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'Register',
  data() {
    return {
      email: '',
      password: '',
      inviteCode: '',
      loading: false,
      error: '',
      success: ''
    }
  },
  methods: {
    async handleRegister() {
      this.loading = true
      this.error = ''
      this.success = ''

      try {
        const response = await fetch('/auth/register', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            email: this.email,
            password: this.password,
            invite_code: this.inviteCode
          })
        })

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.detail || '注册失败')
        }

        const data = await response.json()

        this.success = '注册成功！正在跳转...'

        // 保存 token
        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('user', JSON.stringify(data.user))

        // 2秒后跳转到首页（由路由守卫和 watch 处理后续逻辑）
        setTimeout(() => {
          this.$router.replace('/')
        }, 2000)
      } catch (err) {
        this.error = err.message
      } finally {
        this.loading = false
      }
    }
  }
}
</script>

<style scoped>
.register-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #e6e2dd;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='3.0' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
  background-blend-mode: overlay;
  background-repeat: repeat;
  background-size: auto;
  padding: 1.5rem;
}

.register-card {
  background: white;
  border: 1px solid #303030;
  width: 100%;
  max-width: 28rem;
}

.register-header {
  padding: 1.5rem;
  border-bottom: 1px solid #303030;
}

h1 {
  margin: 0;
  font-family: 'Plaak-CondensedBold', sans-serif;
  font-weight: 400;
  font-size: 1.5rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: #303030;
  text-align: center;
}

.register-form {
  padding: 1.5rem;
}

.form-group {
  margin-bottom: 1.25rem;
}

input {
  width: 100%;
  height: 4.0625rem;
  padding: 1.125rem;
  background-color: #c8cbc9;
  border: 1px solid #303030;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-weight: 400;
  font-size: 0.875rem;
  color: #303030;
  border-radius: 0;
  box-shadow: none;
  outline: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  appearance: none;
  transition: all 0.2s ease;
}

input::placeholder {
  color: #666;
}

input:focus {
  background-color: white;
}

input:hover {
  background-color: white;
}

/* 按钮包装器 - 包含黑色底层和米色按钮 */
.button-wrapper {
  position: relative;
  width: 100%;
  height: 3.125rem;
  margin-top: 0.5rem;
}

/* 黑色底层 - 固定在右下方 */
.button-shadow {
  position: absolute;
  top: 0.125rem;
  left: 0.125rem;
  width: 100%;
  height: 100%;
  background-color: #000;
}

/* 米色按钮 - 向左上偏移，露出右下角黑色 */
.submit-btn {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  padding: 0 3.125rem;
  background-color: #e6e2dd;
  border: 1px solid #303030;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-weight: 400;
  font-size: 0.8125rem;
  text-transform: uppercase;
  letter-spacing: 0.25em;
  color: #000;
  cursor: pointer;
  transition: background-color 0.3s;
  border-radius: 0;
}

.submit-btn:hover:not(:disabled) {
  background-color: #f8bebe;
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.error-message {
  color: #ff6060;
  font-family: 'GTPressuraMono', sans-serif;
  font-size: 0.875rem;
  padding: 0.75rem 1rem;
  background-color: #fef2f2;
  border: 1px solid #ff6060;
  margin-top: 1rem;
}

.success-message {
  color: #16a34a;
  font-family: 'GTPressuraMono', sans-serif;
  font-size: 0.875rem;
  padding: 0.75rem 1rem;
  background-color: #f0fdf4;
  border: 1px solid #16a34a;
  margin-top: 1rem;
}

.register-footer {
  padding: 1.5rem;
  border-top: 1px solid #303030;
  text-align: center;
}

.link-btn {
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-weight: 400;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.25em;
  color: #303030;
  text-decoration: none;
  transition: color 0.2s ease;
}

.link-btn:hover {
  color: #f8bebe;
}
</style>
