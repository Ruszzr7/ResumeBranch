<template>
  <div ref="menuRoot" class="account-menu">
    <button
      type="button"
      class="account-trigger"
      :aria-expanded="open ? 'true' : 'false'"
      aria-haspopup="menu"
      @click="open = !open"
    >
      <span class="account-label">{{ displayName }}</span>
      <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
    </button>

    <Transition name="account-pop">
      <div v-if="open" class="account-dropdown" role="menu">
        <div class="account-summary">
          <span class="summary-label">当前用户</span>
          <strong>{{ user?.email || '未登录' }}</strong>
          <small v-if="user?.is_admin">管理员</small>
        </div>
        <router-link
          v-if="user?.is_admin"
          to="/admin"
          class="account-action"
          role="menuitem"
          @click="open = false"
        >
          邀请码管理
        </router-link>
        <button type="button" class="account-action danger" role="menuitem" @click="logout">
          退出登录
        </button>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  user: {
    type: Object,
    default: () => ({})
  }
})
const emit = defineEmits(['logout'])
const open = ref(false)
const menuRoot = ref(null)
const displayName = computed(() => String(props.user?.email || '用户').split('@')[0] || '用户')

function closeFromOutside(event) {
  if (menuRoot.value && !menuRoot.value.contains(event.target)) open.value = false
}

function logout() {
  open.value = false
  emit('logout')
}

onMounted(() => document.addEventListener('click', closeFromOutside))
onBeforeUnmount(() => document.removeEventListener('click', closeFromOutside))
</script>

<style scoped>
.account-menu {
  position: relative;
  z-index: 20;
}

.account-trigger {
  height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0 0.7rem;
  color: #d9d9df;
  background: rgba(255, 255, 255, 0.055);
  border: 1px solid rgba(255, 255, 255, 0.11);
  border-radius: 8px;
  cursor: pointer;
  font: 0.7rem 'GTPressuraMono-Light', monospace;
}

.account-trigger:hover,
.account-trigger[aria-expanded='true'] {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(120, 166, 255, 0.45);
}

.account-label {
  max-width: 9rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-trigger svg {
  width: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
}

.account-dropdown {
  position: absolute;
  top: calc(100% + 0.55rem);
  right: 0;
  width: 220px;
  overflow: hidden;
  background: #17181d;
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow: 0 18px 45px rgba(0, 0, 0, 0.38);
}

.account-summary {
  display: grid;
  gap: 0.4rem;
  padding: 1rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.09);
}

.account-summary strong {
  overflow: hidden;
  color: #f5f5f7;
  font: 0.72rem 'GTPressuraMono-Light', monospace;
  text-overflow: ellipsis;
}

.summary-label,
.account-summary small {
  color: #85858f;
  font: 0.6rem 'GTPressuraMono-Light', monospace;
  letter-spacing: 0.08em;
}

.account-summary small {
  width: max-content;
  padding: 0.18rem 0.35rem;
  color: #9ebdff;
  background: rgba(120, 166, 255, 0.1);
}

.account-action {
  width: 100%;
  display: block;
  box-sizing: border-box;
  padding: 0.78rem 1rem;
  color: #c9c9cf;
  background: transparent;
  border: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  text-align: left;
  text-decoration: none;
  cursor: pointer;
  font: 0.68rem 'GTPressuraMono-Light', monospace;
}

.account-action:last-child { border-bottom: 0; }
.account-action:hover { color: #fff; background: rgba(255, 255, 255, 0.06); }
.account-action.danger:hover { color: #ff9b9b; }

.account-pop-enter-active,
.account-pop-leave-active { transition: opacity 0.14s ease, transform 0.14s ease; }
.account-pop-enter-from,
.account-pop-leave-to { opacity: 0; transform: translateY(-5px); }

@media (max-width: 640px) {
  .account-label { max-width: 6.5rem; }
  .account-trigger { padding: 0 0.55rem; }
}
</style>
