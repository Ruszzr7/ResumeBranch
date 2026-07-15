<script setup>
import { marked } from 'marked'
import { ref, computed } from 'vue'

// 配置 marked 使用 GitHub Flavored Markdown (gfm)
marked.use({
  gfm: true,
  breaks: true
})

// 预处理函数：将 **text** 替换为 <b>text</b>
// 确保加粗语法被正确渲染
const preprocessMarkdown = (text) => {
  if (typeof text !== 'string') return text
  // 只处理成对出现的 **，使用正则一次性替换
  return text.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
}

// 接收消息属性
const props = defineProps({
  message: {
    type: Object,
    required: true,
    default: () => ({})
  }
})

// 使用 computed 追踪内容变化，实现响应式渲染
const renderedContent = computed(() => {
  const content = props.message.content || ''
  // 预处理加粗语法
  const preprocessed = preprocessMarkdown(content)
  // 使用 marked 解析
  return marked.parse(preprocessed)
})

// 附件弹窗控制
const showPreview = ref(false)
const previewType = ref('image')
const previewUrl = ref('')

// 解析附件数据
const attachments = computed(() => {
  if (!props.message.attachments) return []
  return props.message.attachments
})

// 判断文件类型图标
const getFileIcon = (file) => {
  if (file.type?.startsWith('image/')) {
    return 'image'
  }
  if (file.type === 'application/pdf' || file.name?.toLowerCase().endsWith('.pdf')) {
    return 'pdf'
  }
  return 'file'
}

// 打开预览 - 只支持图片
const openPreview = (file) => {
  if (getFileIcon(file) === 'image') {
    previewType.value = 'image'
    previewUrl.value = file.thumbnail || file.url || file.content
    showPreview.value = true
  }
}

// 关闭预览
const closePreview = () => {
  showPreview.value = false
  previewUrl.value = ''
}

// 确认按钮事件
const emit = defineEmits(['optionClick'])

const handleOptionClick = (option) => {
  emit('optionClick', {
    confirm_id: props.message.confirm_id,
    value: option.value
  })
}
</script>

<template>
  <!-- 只有当消息有实际内容时才渲染气泡框 -->
  <!-- 对于 confirm 类型，只渲染 confirm area，不渲染消息内容 -->
  <div
    v-if="(props.message.role === 'user' && props.message.role !== '') || (props.message.content.trim() !== '') || (props.message.type === 'confirm' && props.message.confirm_id)"
    class="chat-message"
    :class="{
      'chat-message--user': props.message.role === 'user' && props.message.role !== '',
      'chat-message--assistant': props.message.role === 'assistant' || props.message.role === '',
      'chat-message--confirm': props.message.type === 'confirm'
    }"
  >
    <!-- 确认按钮区域（独立渲染，不在消息气泡内） -->
    <!-- 只有当消息未被处理过时才显示 -->
    <div v-if="props.message.type === 'confirm' && props.message.confirm_id && !props.message.handled" class="confirm-area">
      <p class="confirm-content">{{ props.message.content }}</p>
      <div class="confirm-buttons">
        <button
          v-for="option in props.message.options"
          :key="option.value"
          :class="['confirm-btn', `confirm-btn--${option.style}`]"
          @click="handleOptionClick(option)"
        >
          {{ option.label }}
        </button>
      </div>
    </div>

    <!-- 消息内容 - 无头像（confirm 类型不显示） -->
    <div
      v-if="props.message.type !== 'confirm'"
      class="chat-message__content"
      :class="{
        'chat-message__content--user': props.message.role === 'user' && props.message.role !== '',
        'chat-message__content--assistant': !(props.message.role === 'user' && props.message.role !== '')
      }"
    >
      <!-- 渲染消息内容 -->
      <div v-html="renderedContent"></div>
    </div>
  </div>

  <!-- 附件显示 - 在气泡框外部下方 -->
  <div v-if="attachments.length > 0" class="chat-attachments">
    <div
      v-for="(file, index) in attachments"
      :key="index"
      class="chat-attachment"
      :class="'chat-attachment--' + getFileIcon(file)"
      :style="{ cursor: getFileIcon(file) === 'image' ? 'pointer' : 'default' }"
      @click="openPreview(file)"
    >
      <!-- 图片图标 -->
      <svg v-if="getFileIcon(file) === 'image'" class="chat-attachment__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
        <circle cx="8.5" cy="8.5" r="1.5"></circle>
        <polyline points="21 15 16 10 5 21"></polyline>
      </svg>

      <!-- PDF图标 -->
      <svg v-else-if="getFileIcon(file) === 'pdf'" class="chat-attachment__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
        <polyline points="14 2 14 8 20 8"></polyline>
        <line x1="16" y1="13" x2="8" y2="13"></line>
        <line x1="16" y1="17" x2="8" y2="17"></line>
        <polyline points="10 9 9 9 8 9"></polyline>
      </svg>

      <!-- 通用文件图标 -->
      <svg v-else class="chat-attachment__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path>
        <polyline points="13 2 13 9 20 9"></polyline>
      </svg>
    </div>
  </div>

  <!-- 预览弹窗 -->
  <Teleport to="body">
    <div v-if="showPreview" class="preview-modal" @click="closePreview">
      <div class="preview-modal__content" @click.stop>
        <!-- 关闭按钮 -->
        <button class="preview-modal__close" @click="closePreview">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>

        <!-- 图片预览 -->
        <img v-if="previewType === 'image'" :src="previewUrl" class="preview-modal__image" alt="Preview" />

        <!-- PDF提示 -->
        <div v-else-if="previewType === 'pdf'" class="preview-modal__pdf">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
          </svg>
          <p>PDF 文件，请在新标签页中查看</p>
          <a :href="previewUrl" target="_blank" class="preview-modal__link">在新标签页打开</a>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* 基础消息样式 */
.chat-message {
  display: flex;
  margin-bottom: 12px;
  align-items: flex-start;
}

/* 用户消息样式 - 右对齐 */
.chat-message--user {
  justify-content: flex-end;
}

/* 助手消息样式 - 左对齐 */
.chat-message--assistant {
  justify-content: flex-start;
}

/* 确认消息样式 - 居中 */
.chat-message--confirm {
  justify-content: center;
}

/* 消息内容基础样式 */
.chat-message__content {
  line-height: 2.2;  /* 继续增大行高 */
  padding: 6px 0;
}

/* 用户消息内容 */
.chat-message__content--user {
  background-color: #1a1a1a;
  color: white;
  padding: 0px 16px;  /* 减小内边距，让气泡更紧凑 */
  border-radius: 24px;  /* 四角等倒圆角 */
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  max-width: 75%;
  line-height: 1.7;
  margin: 8px 0;
}

/* 用户消息中的链接样式 */
.chat-message__content--user a {
  color: #f0c14b;
  text-decoration: underline;
  font-weight: normal;
}

/* 确保链接在悬停时也清晰可见 */
.chat-message__content--user a:hover {
  color: #f4d03f;
  text-decoration: underline;
}

/* 助手消息内容 - 简洁样式 */
.chat-message__content--assistant {
  background-color: transparent;
  color: #1a1a1a;
  padding: 8px 0;
  border-radius: 0;
  box-shadow: none;
  max-width: 100%;
  line-height: 1.8;
}

/* ========== 附件样式 ========== */
.chat-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 0;
}

/* 用户消息的附件右对齐 */
.chat-message--user + .chat-attachments {
  justify-content: flex-end;
  padding-right: 0;
}

/* 助手消息的附件左对齐 */
.chat-message--assistant + .chat-attachments {
  justify-content: flex-start;
  padding-left: 0;
}

.chat-attachment {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px;
  background-color: #f1f3f4;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.chat-attachment:hover {
  background-color: #e5e7eb;
  transform: translateY(-1px);
}

.chat-attachment--image {
  background-color: #fef3c7;
}

.chat-attachment--image:hover {
  background-color: #fde68a;
}

.chat-attachment--pdf {
  background-color: #fee2e2;
}

.chat-attachment--pdf:hover {
  background-color: #fecaca;
}

.chat-attachment__icon {
  width: 25px;
  height: 25px;
  flex-shrink: 0;
}

.chat-attachment--image .chat-attachment__icon {
  color: #d97706;
}

.chat-attachment--pdf .chat-attachment__icon {
  color: #dc2626;
}

/* ========== 预览弹窗样式 ========== */
.preview-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 20px;
}

.preview-modal__content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.preview-modal__image {
  max-width: 100%;
  max-height: 85vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.preview-modal__close {
  position: absolute;
  top: -40px;
  right: 0;
  background: none;
  border: none;
  color: white;
  cursor: pointer;
  padding: 8px;
  border-radius: 50%;
  transition: background-color 0.2s;
}

.preview-modal__close:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.preview-modal__pdf {
  display: flex;
  flex-direction: column;
  align-items: center;
  color: white;
  text-align: center;
}

.preview-modal__pdf svg {
  margin-bottom: 16px;
  opacity: 0.8;
}

.preview-modal__pdf p {
  margin: 0 0 16px 0;
  font-size: 16px;
  opacity: 0.8;
}

.preview-modal__link {
  display: inline-block;
  padding: 10px 20px;
  background-color: #3b82f6;
  color: white;
  text-decoration: none;
  border-radius: 6px;
  font-size: 14px;
  transition: background-color 0.2s;
}

.preview-modal__link:hover {
  background-color: #2563eb;
}

/* 确保Markdown内容样式正确 */
.chat-message__content h1,
.chat-message__content h2,
.chat-message__content h3 {
  margin-top: 1em;
  margin-bottom: 0.5em;
  font-weight: 600;
  line-height: 1.2;
}

.chat-message__content h1 {
  font-size: 1.5rem;
}

.chat-message__content h2 {
  font-size: 1.25rem;
}

.chat-message__content h3 {
  font-size: 1.1rem;
}

.chat-message__content ul,
.chat-message__content ol {
  margin: 0.5em 0;
  padding-left: 1.5em;
}

.chat-message__content li {
  margin: 0.25em 0;
}

.chat-message__content strong,
.chat-message__content b {
  font-weight: 600;
}

.chat-message__content code {
  background-color: rgba(0, 0, 0, 0.1);
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 0.9em;
}

.chat-message__content pre {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 1em;
  border-radius: 6px;
  overflow-x: auto;
  font-family: 'Courier New', Courier, monospace;
}

.chat-message__content pre code {
  background-color: transparent;
  padding: 0;
  border-radius: 0;
}

/* 确认区域 - 像素风简洁样式 */
.confirm-area {
  margin-top: 16px;
  padding: 20px 28px;
  background-color: #fafafa;
  border-radius: 12px;
  border: 2px solid #e8e8e8;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
  display: inline-block;
  min-width: 300px;
}

.confirm-content {
  margin: 0 0 20px 0;
  color: #1a1a1a;
  font-size: 15px;
  font-weight: 500;
  text-align: center;
}

/* 按钮组 */
.confirm-buttons {
  display: flex;
  justify-content: center;
  gap: 16px;
}

/* 按钮样式 - 像素风简洁风格 */
.confirm-btn {
  padding: 12px 32px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
  border: 2px solid #1a1a1a;
  background-color: white;
  color: #1a1a1a;
  font-family: inherit;
  box-shadow: 2px 2px 0 #1a1a1a; /* 像素风阴影 */
}

.confirm-btn:hover {
  transform: translate(-1px, -1px);
  box-shadow: 4px 4px 0 #1a1a1a;
}

.confirm-btn:active {
  transform: translate(1px, 1px);
  box-shadow: 1px 1px 0 #1a1a1a;
}

.confirm-btn:focus,
.confirm-btn:focus-visible {
  outline: none;
  border-color: #d97706;
  box-shadow: 2px 2px 0 #d97706;
}

.confirm-btn--primary {
  background-color: #1a1a1a;
  border-color: #1a1a1a;
  color: white;
  box-shadow: 2px 2px 0 #1a1a1a;
}

.confirm-btn--primary:hover {
  background-color: #333333;
  border-color: #333333;
  color: white;
  box-shadow: 4px 4px 0 #1a1a1a;
}

.confirm-btn--primary:active {
  background-color: #1a1a1a;
  box-shadow: 1px 1px 0 #1a1a1a;
}

.confirm-btn--default {
  background-color: white;
  border-color: #1a1a1a;
  color: #1a1a1a;
}

.confirm-btn--default:hover {
  background-color: #f5f5f5;
  border-color: #1a1a1a;
  color: #1a1a1a;
}

.confirm-btn--danger {
  background-color: #fff;
  border-color: #dc3545;
  color: #dc3545;
  box-shadow: 2px 2px 0 #dc3545;
}

.confirm-btn--danger:hover {
  background-color: #fff0f0;
  border-color: #dc3545;
  color: #dc3545;
  box-shadow: 4px 4px 0 #dc3545;
}
</style>
