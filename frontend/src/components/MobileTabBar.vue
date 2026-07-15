<script setup>
defineProps({
  activeTab: {
    type: String,
    required: true,
    validator: (value) => ['chat', 'resume'].includes(value)
  }
})

const emit = defineEmits(['update:activeTab'])

function switchTab(tabId) {
  emit('update:activeTab', tabId)
}
</script>

<template>
  <div class="mobile-tab-bar">
    <button
      class="pixel-switch"
      :class="{ active: activeTab === 'chat' }"
      @click="switchTab('chat')"
    >
      <span class="pixel-switch-label">聊天</span>
    </button>
    <button
      class="pixel-switch"
      :class="{ active: activeTab === 'resume' }"
      @click="switchTab('resume')"
    >
      <span class="pixel-switch-label">简历</span>
    </button>
  </div>
</template>

<style scoped>
.mobile-tab-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 56px;
  background: rgb(254, 253, 251);
  border-top: 2px solid #303030;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  z-index: 1000;
  padding: 0 16px;
  padding-bottom: env(safe-area-inset-bottom, 0);
}

.pixel-switch {
  flex: 1;
  max-width: 160px;
  height: 40px;
  background: transparent;
  border: 2px solid #303030;
  border-radius: 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
  position: relative;
  box-shadow: 2px 2px 0 #303030;
}

.pixel-switch:active {
  transform: translate(2px, 2px);
  box-shadow: none;
}

.pixel-switch.active {
  background: #f8bebe;
  box-shadow: inset 2px 2px 0 rgba(0, 0, 0, 0.1);
}

.pixel-switch.active:active {
  background: #f8bebe;
  box-shadow: none;
  transform: translate(2px, 2px);
}

.pixel-switch-label {
  font-family: 'GTPressuraMono-Light', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: #303030;
}

.pixel-switch.active .pixel-switch-label {
  color: #303030;
}

/* 适配更小屏幕 */
@media (max-width: 360px) {
  .pixel-switch {
    max-width: 140px;
    height: 36px;
  }
  
  .pixel-switch-label {
    font-size: 0.6875rem;
    letter-spacing: 0.1em;
  }
}
</style>
