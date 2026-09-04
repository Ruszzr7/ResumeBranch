<script setup>
import { marked } from 'marked'
import { ref, computed, watch } from 'vue'
import { localizeInternalFieldReferences, userFacingFieldLabel } from '../utils/fieldLabels.js'

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
  const rawContent = props.message.content || ''
  const content = props.message.role === 'assistant'
    ? localizeInternalFieldReferences(rawContent)
    : rawContent
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
const emit = defineEmits(['optionClick', 'selectionChange', 'undoClick', 'contextClick'])

const changes = computed(() => props.message.changes || [])
const selectedChangeIds = ref([])

watch(
  [changes, () => props.message.selected_change_ids],
  ([items, selected]) => {
    const available = new Set(items.map(item => item.id))
    selectedChangeIds.value = Array.isArray(selected)
      ? selected.filter(id => available.has(id))
      : items.map(item => item.id)
  },
  { immediate: true }
)

const handleSelectionChange = () => {
  emit('selectionChange', {
    confirm_id: props.message.confirm_id,
    selected_change_ids: [...selectedChangeIds.value]
  })
}

const handleOptionClick = (option) => {
  emit('optionClick', {
    confirm_id: props.message.confirm_id,
    value: option.value,
    selected_change_ids: option.value === 'confirm_selected' ? [...selectedChangeIds.value] : []
  })
}

const handleUndoClick = () => emit('undoClick', { message_id: props.message.id })

const isContextClosed = computed(() => (
  props.message.type === 'context_event'
  && (props.message.action === 'closed' || props.message.status === 'closed')
))

const handleContextClick = () => {
  if (!isContextClosed.value) {
    emit('contextClick', { context_id: props.message.context_id })
  }
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
    <div
      v-if="props.message.type === 'context_event'"
      :class="['context-event-card', { 'context-event-card--closed': isContextClosed }]"
      @click="handleContextClick"
    >
      <span class="context-event-dot" aria-hidden="true"></span>
      <span class="context-event-copy">
        <strong>{{ props.message.title || '任务会话' }}</strong>
        <span>{{ props.message.content }}</span>
      </span>
      <span class="context-event-link">{{ isContextClosed ? '已关闭' : '打开' }}</span>
    </div>

    <!-- 确认按钮区域（独立渲染，不在消息气泡内） -->
    <!-- 只有当消息未被处理过时才显示 -->
    <div v-if="props.message.type === 'confirm' && props.message.confirm_id && !props.message.handled" class="confirm-area">
      <p class="confirm-content">{{ props.message.content }}</p>
      <p class="preview-status">
        右侧实时显示当前选择，接受前不会保存。
        <span v-if="changes.length > 1">已选择 {{ selectedChangeIds.length }} / {{ changes.length }} 项。</span>
      </p>
      <div v-if="changes.length" class="change-preview-list">
        <label v-for="change in changes" :key="change.id" class="change-preview-item">
          <input v-if="changes.length > 1" v-model="selectedChangeIds" type="checkbox" :value="change.id" @change="handleSelectionChange" />
          <span class="change-preview-copy">
            <strong>{{ userFacingFieldLabel(change.label) }}</strong>
            <span v-if="change.kind !== 'layout'" class="change-values">
              <del>{{ change.before_display }}</del>
              <span aria-hidden="true">→</span>
              <ins>{{ change.after_display }}</ins>
            </span>
            <span v-else class="layout-change-details">
              <span v-for="detail in change.details || []" :key="detail.field" class="change-values">
                <small>{{ userFacingFieldLabel(detail.field_label || detail.field) }}</small>
                <del>{{ detail.before_display }}</del>
                <span aria-hidden="true">→</span>
                <ins>{{ detail.after_display }}</ins>
              </span>
            </span>
          </span>
        </label>
      </div>
      <div v-if="changes.length" class="confirm-buttons change-actions">
        <button class="confirm-btn confirm-btn--primary" @click="handleOptionClick({ value: 'confirm_all' })">
          {{ changes.length > 1 ? '全部接受' : '接受' }}
        </button>
        <button
          v-if="changes.length > 1"
          class="confirm-btn confirm-btn--default"
          :disabled="selectedChangeIds.length === 0"
          @click="handleOptionClick({ value: 'confirm_selected' })"
        >
          应用已选（{{ selectedChangeIds.length }}）
        </button>
        <button class="confirm-btn confirm-btn--danger" @click="handleOptionClick({ value: 'cancel' })">
          {{ changes.length > 1 ? '全部拒绝' : '拒绝' }}
        </button>
      </div>
      <div v-else class="confirm-buttons">
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

    <div v-if="props.message.type === 'undo'" class="undo-area">
      <span>{{ props.message.content }}</span>
      <button v-if="!props.message.handled" class="undo-btn" @click="handleUndoClick">撤回本次修改</button>
    </div>

    <!-- 消息内容 - 无头像（confirm 类型不显示） -->
    <div
      v-if="props.message.type !== 'confirm' && props.message.type !== 'undo' && props.message.type !== 'context_event'"
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
        <img v-if="previewType === 'image'" :src="previewUrl" class="preview-modal__image" alt="图片预览" />

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
  width: 100%;
  min-width: 0;
  margin-bottom: 12px;
  align-items: flex-start;
}

.context-event-card {
  width: min(100%, 520px);
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 12px;
  border: 1px solid rgba(120, 166, 255, 0.18);
  border-radius: 10px;
  background: rgba(120, 166, 255, 0.065);
  color: #cdd4e7;
  cursor: pointer;
}

.context-event-card:hover {
  border-color: rgba(120, 166, 255, 0.42);
  background: rgba(120, 166, 255, 0.1);
}

.context-event-card--closed {
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.035);
  color: #949aaa;
  cursor: default;
  opacity: 0.72;
}

.context-event-card--closed:hover {
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.035);
}

.context-event-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #78a6ff;
  box-shadow: 0 0 7px rgba(120, 166, 255, 0.55);
}

.context-event-card--closed .context-event-dot {
  background: #878d9a;
  box-shadow: none;
}

.context-event-copy {
  min-width: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}

.context-event-copy strong {
  color: #f0f2f8;
  font-size: 0.78rem;
}

.context-event-card--closed .context-event-copy strong {
  color: #b0b5c1;
}

.context-event-copy span {
  overflow: hidden;
  color: #aeb6ca;
  font-size: 0.72rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-event-link {
  color: #8eb5ff;
  font-size: 0.7rem;
  white-space: nowrap;
}

.context-event-card--closed .context-event-link {
  color: #858b99;
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
  background: #24252a;
  color: #f5f5f7;
  padding: 7px 14px;
  border: 1px solid rgba(255, 255, 255, 0.065);
  border-radius: 16px 16px 5px 16px;
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.2);
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
  color: #d8d8dd;
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
  background: rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.chat-attachment:hover {
  background: rgba(255, 255, 255, 0.1);
  transform: translateY(-1px);
}

.chat-attachment--image {
  background: rgba(120, 166, 255, 0.1);
}

.chat-attachment--image:hover {
  background: rgba(120, 166, 255, 0.16);
}

.chat-attachment--pdf {
  background: rgba(255, 116, 116, 0.1);
}

.chat-attachment--pdf:hover {
  background: rgba(255, 116, 116, 0.16);
}

.chat-attachment__icon {
  width: 25px;
  height: 25px;
  flex-shrink: 0;
}

.chat-attachment--image .chat-attachment__icon {
  color: #78a6ff;
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
  display: block;
  width: min(100%, 520px);
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  margin-top: 16px;
  padding: 20px 28px;
  background: linear-gradient(145deg, rgba(60, 79, 120, 0.2), rgba(255, 255, 255, 0.035));
  border-radius: 14px;
  border: 1px solid rgba(120, 166, 255, 0.18);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.22);
}

.confirm-content {
  margin: 0 0 20px 0;
  color: #f0f0f3;
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
  border-radius: 9px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.065);
  color: #d7d7dc;
  font-family: inherit;
  box-shadow: none;
}

.confirm-btn:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.11);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.2);
}

.confirm-btn:active {
  transform: translateY(0);
  box-shadow: none;
}

.confirm-btn:focus,
.confirm-btn:focus-visible {
  outline: 2px solid #78a6ff;
  outline-offset: 2px;
  border-color: transparent;
  box-shadow: none;
}

.confirm-btn--primary {
  background: #e8eaf0;
  border-color: #e8eaf0;
  color: #0b0b0d;
  box-shadow: none;
}

.confirm-btn--primary:hover {
  background: #ffffff;
  border-color: #ffffff;
  color: #0b0b0d;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.2);
}

.confirm-btn--primary:active {
  background: #d7d9df;
  color: #0b0b0d;
  box-shadow: none;
}

.confirm-btn--default {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.1);
  color: #d7d7dc;
}

.confirm-btn--default:hover {
  background: rgba(255, 255, 255, 0.11);
  border-color: rgba(255, 255, 255, 0.14);
  color: #fff;
}

.confirm-btn--danger {
  background: rgba(255, 100, 100, 0.08);
  border-color: rgba(255, 120, 120, 0.35);
  color: #ff9a9a;
  box-shadow: none;
}

.preview-status {
  margin: -4px 0 14px;
  padding: 9px 11px;
  border: 1px solid rgba(103, 146, 235, 0.24);
  border-radius: 8px;
  color: #b9c8e8;
  background: rgba(77, 112, 184, 0.08);
  font-size: 0.78rem;
  line-height: 1.5;
}

.change-preview-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  max-height: 330px;
  margin: 0 0 18px;
  overflow-y: auto;
  text-align: left;
}

.change-preview-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 11px 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 9px;
  background: rgba(0, 0, 0, 0.12);
  cursor: pointer;
}

.change-preview-item input {
  margin-top: 3px;
  accent-color: #a8bfff;
}

.change-preview-copy,
.change-values {
  display: flex;
  min-width: 0;
}

.layout-change-details {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.layout-change-details .change-values small {
  min-width: 82px;
  color: #b8b9c0;
}

.change-preview-copy {
  flex: 1;
  flex-direction: column;
  gap: 6px;
}

.change-preview-copy strong {
  color: #f0f0f3;
  font-size: 13px;
}

.change-values {
  gap: 8px;
  align-items: baseline;
  color: #9fa0a8;
  font-size: 12px;
}

.change-values del,
.change-values ins {
  max-width: 46%;
  overflow-wrap: anywhere;
}

.change-values del { color: #d89595; }
.change-values ins { color: #9fd1ae; text-decoration: none; }

.change-actions { flex-wrap: wrap; }
.change-actions .confirm-btn {
  flex: 1 1 130px;
  min-width: 0;
  padding-inline: 16px;
}
.confirm-btn:disabled { cursor: not-allowed; opacity: 0.45; transform: none; }

@media (max-width: 520px) {
  .confirm-area { padding: 16px; }
  .confirm-buttons { gap: 10px; }
  .change-actions .confirm-btn { flex-basis: 100%; }
}

.undo-area {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 12px 14px;
  border: 1px solid rgba(120, 166, 255, 0.18);
  border-radius: 10px;
  background: rgba(120, 166, 255, 0.08);
  color: #d8d8dd;
}

.undo-btn {
  border: 0;
  background: transparent;
  color: #a8bfff;
  font: inherit;
  cursor: pointer;
  white-space: nowrap;
}

.undo-btn:hover { color: #d5deff; }

.confirm-btn--danger:hover {
  background: rgba(255, 100, 100, 0.14);
  border-color: rgba(255, 120, 120, 0.5);
  color: #ffb0b0;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.2);
}
</style>
