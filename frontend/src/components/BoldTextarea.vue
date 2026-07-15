<template>
  <div class="bold-textarea" :class="{ 'has-content': localValue && localValue.includes('**') }">
    <div
      ref="contentDiv"
      class="content-area"
      contenteditable="true"
      @input="onInput"
      @keydown.ctrl.b="handleCtrlB"
      @keydown.meta.b="handleCtrlB"
      @blur="onBlur"
      :placeholder="placeholder"
      :class="{ 'with-placeholder': !localValue && placeholder }"
    ></div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from 'vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue'])

const contentDiv = ref(null)
const localValue = ref(props.modelValue)

// 格式化显示：将 **文本** 转为 <b>文本</b>
function formatDisplay(text) {
  if (!text) return ''
  // 转义 HTML 特殊字符
  let escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  // 将 **text** 转为 <b>text</b>
  return escaped.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
}

function onInput(e) {
  const plainText = e.target.innerText
  localValue.value = plainText
  emit('update:modelValue', plainText)
}

function onBlur() {
  // 失去焦点时同步内容
  if (contentDiv.value) {
    const currentText = contentDiv.value.innerText
    if (currentText !== localValue.value) {
      localValue.value = currentText
      emit('update:modelValue', currentText)
    }
  }
}

function handleCtrlB(e) {
  e.preventDefault()
  const selection = window.getSelection()
  if (selection.rangeCount > 0) {
    const range = selection.getRangeAt(0)
    const selectedText = range.toString()

    if (selectedText) {
      // 使用 **包裹选中文本
      const newText = `**${selectedText}**`
      document.execCommand('insertText', false, newText)
      // 触发更新
      localValue.value = contentDiv.value.innerText
      emit('update:modelValue', localValue.value)
    }
  }
}

// 更新显示
function updateDisplay() {
  if (contentDiv.value) {
    const formatted = formatDisplay(localValue.value || '')
    // 只有当内容真正改变时才更新，避免光标跳动
    if (contentDiv.value.innerHTML !== formatted) {
      contentDiv.value.innerHTML = formatted
    }
  }
}

// 监听 modelValue 变化更新显示
watch(() => props.modelValue, (newVal) => {
  if (newVal !== localValue.value) {
    localValue.value = newVal
    nextTick(() => {
      updateDisplay()
    })
  }
}, { immediate: false })

onMounted(() => {
  nextTick(() => {
    updateDisplay()
  })
})
</script>

<style scoped>
.bold-textarea {
  border: 1px solid #e9ecef;
  border-radius: var(--radius-sm);
  background: #fafafa;
  transition: all 0.2s ease;
  width: 100%;
}

.bold-textarea:focus-within {
  border-color: var(--primary-color);
  background: #fff;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.08);
}

.content-area {
  width: 100%;
  min-height: 80px;
  max-height: 150px;
  padding: 0.5rem 0.6rem;
  font-size: 0.8rem;
  line-height: 1.5;
  outline: none;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-y: auto;
  font-family: inherit;
}

.content-area:empty:before {
  content: attr(placeholder);
  color: #adb5bd;
  pointer-events: none;
}

.content-area b {
  font-weight: 600;
  color: var(--text-primary);
}

/* 隐藏滚动条但保留功能 */
.content-area::-webkit-scrollbar {
  width: 6px;
}

.content-area::-webkit-scrollbar-track {
  background: transparent;
}

.content-area::-webkit-scrollbar-thumb {
  background: #dee2e6;
  border-radius: 3px;
}

.content-area::-webkit-scrollbar-thumb:hover {
  background: #ced4da;
}
</style>
