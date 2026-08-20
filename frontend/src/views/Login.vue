<template>
  <main class="login-page">
    <header class="login-topbar">
      <router-link to="/" class="brand-link" aria-label="返回 ResumeBranch 首页">
        <BrandLogo />
      </router-link>

      <span class="mode-label">
        <i aria-hidden="true"></i>
        多用户模式
      </span>
    </header>

    <section class="login-stage" aria-labelledby="login-title">
      <div class="login-card">
        <header class="login-header">
          <p class="login-kicker">ACCOUNT ACCESS</p>
          <h1 id="login-title">登录</h1>
          <p class="login-description">继续管理你的简历、岗位版本和求职记录。</p>
        </header>

        <form class="login-form" @submit.prevent="handleLogin">
          <div class="form-group">
            <label for="email">邮箱</label>
            <input
              id="email"
              v-model.trim="email"
              type="email"
              name="email"
              autocomplete="username"
              placeholder="输入邮箱"
              required
            />
          </div>

          <div class="form-group">
            <label for="password">密码</label>
            <input
              id="password"
              v-model="password"
              type="password"
              name="password"
              autocomplete="current-password"
              placeholder="输入密码"
              required
            />
          </div>

          <p v-if="errorMessage" class="status-message error" role="alert">
            {{ errorMessage }}
          </p>

          <div class="button-wrapper">
            <div class="button-shadow" aria-hidden="true"></div>
            <button type="submit" class="submit-btn" :disabled="loading">
              {{ loading ? '登录中…' : '登录' }}
            </button>
          </div>
        </form>

        <footer class="login-footer">
          <span>没有账号？</span>
          <router-link to="/register" class="link-btn">注册</router-link>
        </footer>
      </div>
    </section>
  </main>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import BrandLogo from '../components/BrandLogo.vue'

const router = useRouter()
const email = ref('')
const password = ref('')
const errorMessage = ref('')
const loading = ref(false)

async function handleLogin() {
  if (loading.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const body = new URLSearchParams()
    body.set('username', email.value.trim().toLowerCase())
    body.set('password', password.value)
    const response = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '登录失败，请检查邮箱和密码')
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    await router.replace('/')
  } catch (error) {
    errorMessage.value = error.message || '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  color: #f5f5f7;
  background:
    radial-gradient(circle at 64% -20%, rgba(100, 130, 220, 0.12), transparent 36%),
    #050506;
  background-image:
    radial-gradient(circle at 64% -20%, rgba(100, 130, 220, 0.12), transparent 36%),
    url("data:image/svg+xml,%3Csvg viewBox='0 0 220 220' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='3.1' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)' opacity='.16'/%3E%3C/svg%3E"),
    #050506;
  background-blend-mode: screen, soft-light, normal;
}

.login-topbar {
  width: 100%;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem 2rem;
}

.brand-link {
  display: inline-flex;
  color: inherit;
  text-decoration: none;
}

.mode-label {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  color: #85858f;
  font-family: 'GTPressuraMono-Light', monospace;
  font-size: 0.66rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.mode-label i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #78a6ff;
  box-shadow: 0 0 8px rgba(120, 166, 255, 0.55);
}

.login-stage {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  padding: 2rem 1.5rem 5rem;
}

.login-card {
  width: min(100%, 28rem);
  box-sizing: border-box;
  background: rgba(18, 19, 23, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.17);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.28);
}

.login-header {
  padding: 2rem 2rem 1.7rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.11);
}

.login-kicker {
  margin: 0 0 1rem;
  color: #78a6ff;
  font-family: 'GTPressuraMono-Light', monospace;
  font-size: 0.62rem;
  letter-spacing: 0.19em;
}

h1 {
  margin: 0;
  color: #f5f5f7;
  font-family: 'Plaak-CondensedBold', sans-serif;
  font-size: 2rem;
  font-weight: 400;
  letter-spacing: 0.02em;
}

.login-description {
  max-width: 19rem;
  margin: 0.8rem 0 0;
  color: #85858f;
  font-family: 'GTPressuraMono-Light', monospace;
  font-size: 0.72rem;
  line-height: 1.7;
}

.login-form {
  padding: 2rem;
}

.form-group {
  margin-bottom: 1.25rem;
}

label {
  display: block;
  margin-bottom: 0.55rem;
  color: #c9c9cf;
  font-family: 'GTPressuraMono-Light', monospace;
  font-size: 0.7rem;
  letter-spacing: 0.08em;
}

input {
  width: 100%;
  height: 3.6rem;
  box-sizing: border-box;
  padding: 0 1rem;
  color: #f5f5f7;
  background: #2b2c32;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 0;
  outline: none;
  font-family: 'GTPressuraMono-Light', monospace;
  font-size: 0.8rem;
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}

input::placeholder {
  color: #777983;
}

input:hover {
  background: #303139;
}

input:focus {
  background: #303139;
  border-color: rgba(120, 166, 255, 0.72);
  box-shadow: 0 0 0 3px rgba(120, 166, 255, 0.1);
}

.status-message {
  margin: -0.15rem 0 1rem;
  padding: 0.72rem 0.85rem;
  color: #9ebdff;
  background: rgba(120, 166, 255, 0.08);
  border-left: 2px solid #78a6ff;
  font-family: 'GTPressuraMono-Light', monospace;
  font-size: 0.7rem;
  line-height: 1.5;
}

.status-message.error {
  color: #ffaaaa;
  background: rgba(255, 96, 96, 0.08);
  border-left-color: #ff6060;
}

.button-wrapper {
  position: relative;
  width: 100%;
  height: 3.15rem;
  margin-top: 1.65rem;
}

.button-shadow {
  position: absolute;
  inset: 0;
  transform: translate(3px, 3px);
  background: #000;
}

.submit-btn {
  position: relative;
  width: 100%;
  height: 100%;
  padding: 0 3.125rem;
  color: #fff;
  background: #5f8ff2;
  border: 1px solid #78a6ff;
  border-radius: 0;
  cursor: pointer;
  font-family: 'GTPressuraMono-Light', monospace;
  font-size: 0.75rem;
  letter-spacing: 0.24em;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.submit-btn:hover {
  background: #78a6ff;
  border-color: #a9c5ff;
  transform: translate(2px, 2px);
}

.submit-btn:active {
  transform: translate(3px, 3px);
}

.submit-btn:disabled {
  opacity: 0.58;
  cursor: wait;
  transform: none;
}

.submit-btn:focus-visible,
.link-btn:focus-visible,
.brand-link:focus-visible {
  outline: 2px solid #78a6ff;
  outline-offset: 4px;
}

.login-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  padding: 1.35rem 2rem 1.5rem;
  color: #85858f;
  border-top: 1px solid rgba(255, 255, 255, 0.11);
  font-family: 'GTPressuraMono-Light', monospace;
  font-size: 0.68rem;
}

.link-btn {
  color: #78a6ff;
  text-decoration: none;
  transition: color 0.18s ease;
}

.link-btn:hover {
  color: #b5cdff;
}

@media (max-width: 640px) {
  .login-topbar {
    padding: 1.2rem 1.1rem;
  }

  .mode-label {
    font-size: 0.58rem;
  }

  .login-stage {
    align-items: flex-start;
    padding: 3.5rem 1rem 2.5rem;
  }

  .login-header,
  .login-form {
    padding-left: 1.3rem;
    padding-right: 1.3rem;
  }

  .login-footer {
    padding-left: 1.3rem;
    padding-right: 1.3rem;
  }
}
</style>
