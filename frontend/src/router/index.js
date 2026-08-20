import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import Register from '../views/Register.vue'
import Admin from '../views/Admin.vue'
import Homepage from '../views/Homepage.vue'
import { loadAppConfig } from '../config/appMode.js'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Homepage,
    meta: { requiresAuth: true }
  },
  {
    path: '/home',
    name: 'Homepage',
    component: Homepage,
    meta: { requiresAuth: true }
  },
  {
    path: '/projects/:projectId/tasks/:taskId',
    name: 'TaskWorkspace',
    component: Homepage,
    meta: { requiresAuth: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { guest: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: Register,
    meta: { guest: true }
  },
  {
    path: '/admin',
    name: 'Admin',
    component: Admin,
    meta: { requiresAuth: true, requiresAdmin: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Navigation guard
router.beforeEach(async (to) => {
  const appConfig = await loadAppConfig()
  if (appConfig.app_mode === 'local') {
    if (to.meta.guest || to.meta.requiresAdmin) {
      return '/'
    }
    return true
  }

  const token = localStorage.getItem('access_token')
  const userStr = localStorage.getItem('user')
  let user = null
  try {
    user = userStr ? JSON.parse(userStr) : null
  } catch {
    localStorage.removeItem('user')
  }

  if (to.meta.requiresAuth && !token) {
    return '/login'
  } else if (to.meta.guest && token) {
    return '/'
  } else if (to.meta.requiresAdmin) {
    if (user?.is_admin === true) {
      return true
    } else {
      return '/'
    }
  }
  return true
})

export default router
