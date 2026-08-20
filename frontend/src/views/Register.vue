<template>
  <main class="register-page">
    <header class="register-topbar">
      <router-link to="/login" class="brand-link" aria-label="返回登录页"><BrandLogo /></router-link>
      <span class="mode-label"><i></i>多用户模式</span>
    </header>
    <section class="register-container">
    <div class="register-card">
      <div class="register-header">
        <p>ACCOUNT CREATION</p>
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
            placeholder="密码（至少 8 位）"
            required
            minlength="8"
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
    </section>
  </main>
</template>

<script>
import BrandLogo from '../components/BrandLogo.vue'

export default {
  name: 'Register',
  components: { BrandLogo },
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
            email: this.email.trim().toLowerCase(),
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
.register-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  color: #f5f5f7;
  background: radial-gradient(circle at 64% -20%, rgba(100, 130, 220, 0.12), transparent 36%), #050506;
}

.register-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem 2rem;
}

.brand-link { color: inherit; text-decoration: none; }
.mode-label { display: inline-flex; align-items: center; gap: 0.45rem; color: #85858f; font: 0.66rem 'GTPressuraMono-Light', monospace; letter-spacing: 0.12em; }
.mode-label i { width: 5px; height: 5px; border-radius: 50%; background: #78a6ff; box-shadow: 0 0 8px rgba(120, 166, 255, 0.55); }

.register-container {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem 1.5rem 5rem;
}

.register-card {
  background: rgba(18, 19, 23, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.17);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.28);
  width: 100%;
  max-width: 28rem;
}

.register-header {
  padding: 2rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.11);
}

.register-header p { margin: 0 0 1rem; color: #78a6ff; font: 0.62rem 'GTPressuraMono-Light', monospace; letter-spacing: 0.19em; }

h1 {
  margin: 0;
  font-family: 'Plaak-CondensedBold', sans-serif;
  font-weight: 400;
  font-size: 1.5rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: #f5f5f7;
}

.register-form {
  padding: 2rem;
}

.form-group {
  margin-bottom: 1.25rem;
}

input {
  width: 100%;
  height: 4.0625rem;
  padding: 1.125rem;
  background-color: #2b2c32;
  border: 1px solid rgba(255, 255, 255, 0.14);
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-weight: 400;
  font-size: 0.875rem;
  color: #f5f5f7;
  border-radius: 0;
  box-shadow: none;
  outline: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  appearance: none;
  transition: all 0.2s ease;
}

input::placeholder {
  color: #777983;
}

input:focus {
  background-color: #303139;
  border-color: rgba(120, 166, 255, 0.72);
}

input:hover {
  background-color: #303139;
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
  background-color: #5f8ff2;
  border: 1px solid #78a6ff;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-weight: 400;
  font-size: 0.8125rem;
  text-transform: uppercase;
  letter-spacing: 0.25em;
  color: #fff;
  cursor: pointer;
  transition: background-color 0.3s;
  border-radius: 0;
}

.submit-btn:hover:not(:disabled) {
  background-color: #78a6ff;
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
  background-color: rgba(255, 96, 96, 0.08);
  border-left: 2px solid #ff6060;
  margin-top: 1rem;
}

.success-message {
  color: #16a34a;
  font-family: 'GTPressuraMono', sans-serif;
  font-size: 0.875rem;
  padding: 0.75rem 1rem;
  background-color: rgba(22, 163, 74, 0.08);
  border-left: 2px solid #16a34a;
  margin-top: 1rem;
}

.register-footer {
  padding: 1.5rem;
  border-top: 1px solid rgba(255, 255, 255, 0.11);
  text-align: center;
}

.link-btn {
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-weight: 400;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.25em;
  color: #78a6ff;
  text-decoration: none;
  transition: color 0.2s ease;
}

.link-btn:hover {
  color: #78a6ff;
}
</style>
