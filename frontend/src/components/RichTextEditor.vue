<template>
  <div class="rich-editor" :class="{ compact, 'allow-line-breaks': allowLineBreaks, 'default-bold-active': defaultBoldActive }">
    <!-- 编辑区域 -->
    <div
      ref="editorRef"
      class="editor-content"
      contenteditable="true"
      :placeholder="placeholder"
      @input="onInput"
      @keydown.ctrl.b="handleCtrlB"
      @keydown.meta.b="handleCtrlB"
      @keydown.enter="handleEnter"
      @paste="handlePaste"
      @focus="onFocus"
      @blur="onBlur"
    ></div>
    <!-- 行数 -->
    <div v-if="!compact" class="editor-hint">
      <span class="line-count">简历约 {{ displayLineCount }} 行</span>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from 'vue'
import {
  formatInlineHtml,
  plainInlineText,
  serializeInlineBold,
  toggleInlineBoldRange
} from '../utils/inlineFormatting.js'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '请输入内容'
  },
  compact: {
    type: Boolean,
    default: false
  },
  allowLineBreaks: {
    type: Boolean,
    default: false
  },
  defaultBold: {
    type: Boolean,
    default: false
  },
  resumeMetrics: {
    type: Object,
    default: () => ({ fontSizePt: 9, lineHeight: 1.28, contentWidthPx: 725 })
  },
  resumeFlow: {
    type: Object,
    default: () => ({ labelPlacement: 'none', prefixText: '', labelBold: true })
  }
})

const emit = defineEmits(['update:modelValue'])

const editorRef = ref(null)
const isUpdating = ref(false) // 避免循环更新
const defaultBoldActive = ref(false)
const displayLineCount = ref(0) // 按当前简历正文排版估算的视觉行数

function measureResumeLineCount(text) {
  if (!text?.trim() || typeof document === 'undefined') return 0
  const metrics = props.resumeMetrics || {}
  const flow = props.resumeFlow || {}
  if (flow.visible === false) return 0
  const indentPx = (Number(metrics.listTextIndentPt) || 0) * (96 / 72) * (Number(flow.contentIndentLevels) || 0)
  const measurer = document.createElement('div')
  Object.assign(measurer.style, {
    position: 'fixed',
    left: '-10000px',
    top: '0',
    width: `${Math.max(1, (Number(metrics.contentWidthPx) || 725) - indentPx)}px`,
    height: 'auto',
    margin: '0',
    padding: '0',
    border: '0',
    visibility: 'hidden',
    pointerEvents: 'none',
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
    wordBreak: 'break-word',
    textAlign: 'justify',
    textJustify: 'inter-ideograph',
    fontFamily: metrics.fontFamilyCss || "'Microsoft YaHei', Arial, sans-serif",
    fontSize: `${Number(metrics.fontSizePt) || 9}pt`,
    fontWeight: '400',
    lineHeight: String(Number(metrics.lineHeight) || 1.28)
  })
  if (flow.labelPlacement === 'inline' && flow.prefixText) {
    const prefix = document.createElement(flow.labelBold === false ? 'span' : 'strong')
    prefix.textContent = flow.prefixText
    prefix.style.fontSize = `${Number(metrics.labelFontSizePt) || Number(metrics.fontSizePt) || 9}pt`
    prefix.style.fontWeight = String(Number(metrics.labelFontWeight) || 700)
    measurer.appendChild(prefix)
  }
  const content = document.createElement('span')
  content.innerHTML = formatToHtml(text)
  measurer.appendChild(content)
  document.body.appendChild(measurer)
  const computedLineHeight = Number.parseFloat(window.getComputedStyle(measurer).lineHeight)
  const contentRange = document.createRange()
  contentRange.selectNodeContents(measurer)
  const lineTops = []
  for (const rect of contentRange.getClientRects()) {
    if (rect.height <= 0) continue
    if (!lineTops.some(top => Math.abs(top - rect.top) < 1)) lineTops.push(rect.top)
  }
  const fallbackLineCount = computedLineHeight > 0
    ? Math.max(1, Math.round(measurer.scrollHeight / computedLineHeight))
    : 1
  const lineCount = lineTops.length || fallbackLineCount
  contentRange.detach()
  measurer.remove()
  return lineCount
}

// 使用共享正文排版参数计算自动换行后的预计视觉行数。
function updateLineCount() {
  if (!editorRef.value) return
  displayLineCount.value = measureResumeLineCount(parseToText(editorRef.value.innerHTML))
}

function syncValue() {
  if (!editorRef.value || isUpdating.value) return
  const text = parseToText(editorRef.value.innerHTML)
  if (text !== props.modelValue) emit('update:modelValue', text)
}

// 所有编辑器在输入时同步，确保草稿数据与实时预览保持一致。
function onInput() {
  updateLineCount()
  syncValue()
}

function formatToHtml(text) {
  return formatInlineHtml(text).replace(/\n/g, '<br>')
}

function domToInlineText(root, { trim = true, baseBold = false } = {}) {
  const segments = []
  const push = (text, bold) => {
    if (!text) return
    const previous = segments[segments.length - 1]
    if (previous && previous.bold === bold) previous.text += text
    else segments.push({ text, bold })
  }
  const endsWithNewline = () => segments.length > 0 && segments[segments.length - 1].text.endsWith('\n')
  const walk = (node, inheritedBold = false) => {
    if (node.nodeType === Node.TEXT_NODE) {
      push(node.textContent || '', inheritedBold)
      return
    }
    if (![Node.ELEMENT_NODE, Node.DOCUMENT_FRAGMENT_NODE].includes(node.nodeType)) return
    const tag = node.nodeType === Node.ELEMENT_NODE ? node.tagName : ''
    if (tag === 'BR') {
      push('\n', inheritedBold)
      return
    }
    let bold = inheritedBold
    if (tag === 'B' || tag === 'STRONG') bold = true
    const fontWeight = node.nodeType === Node.ELEMENT_NODE ? String(node.style?.fontWeight || '').toLowerCase() : ''
    if (fontWeight === 'normal' || fontWeight === '400') bold = false
    else if (fontWeight === 'bold' || Number(fontWeight) >= 600) bold = true
    const isBlock = tag === 'DIV' || tag === 'P'
    if (isBlock && segments.length && !endsWithNewline()) push('\n', inheritedBold)
    node.childNodes.forEach(child => walk(child, bold))
    if (isBlock && !endsWithNewline()) push('\n', inheritedBold)
  }
  walk(root, baseBold)
  let value = serializeInlineBold(segments).replace(/\n{3,}/g, '\n\n')
  if (trim) value = value.trim()
  return value
}

// 解析编辑器 DOM 为存储协议；不会把浏览器生成的 normal 样式误判成粗体。
function parseToText() {
  if (!editorRef.value) return ''
  return domToInlineText(editorRef.value, { baseBold: defaultBoldActive.value })
}

function onBlur() {
  syncValue()
  defaultBoldActive.value = false
  nextTick(updateDisplay)
}

function onFocus() {
  // 新建的标题类字段第一次输入即写入显式粗体；已有内容完全尊重已保存字重。
  defaultBoldActive.value = Boolean(props.defaultBold && !parseToText())
}

function handleEnter(event) {
  if (props.compact && !props.allowLineBreaks) {
    event.preventDefault()
    return
  }
  if (!editorRef.value) return
  event.preventDefault()
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) return
  const range = selection.getRangeAt(0)
  if (!editorRef.value.contains(range.commonAncestorContainer)) return
  range.deleteContents()
  const lineBreak = document.createElement('br')
  range.insertNode(lineBreak)
  range.setStartAfter(lineBreak)
  range.collapse(true)
  selection.removeAllRanges()
  selection.addRange(range)
  syncValue()
  nextTick(updateLineCount)
}

function handleCtrlB(e) {
  e.preventDefault()
  const selection = window.getSelection()
  if (selection.rangeCount === 0) return

  const range = selection.getRangeAt(0)
  if (!editorRef.value?.contains(range.commonAncestorContainer) || range.collapsed) return
  const before = document.createRange()
  before.selectNodeContents(editorRef.value)
  before.setEnd(range.startContainer, range.startOffset)
  const throughSelection = document.createRange()
  throughSelection.selectNodeContents(editorRef.value)
  throughSelection.setEnd(range.endContainer, range.endOffset)
  const fragmentText = sourceRange => {
    const holder = document.createDocumentFragment()
    holder.appendChild(sourceRange.cloneContents())
    return plainInlineText(domToInlineText(holder, { trim: false })).length
  }
  const start = fragmentText(before)
  const end = fragmentText(throughSelection)
  const current = parseToText()
  const updated = toggleInlineBoldRange(current, start, end)
  defaultBoldActive.value = false
  isUpdating.value = true
  editorRef.value.innerHTML = formatToHtml(updated) || '<br>'
  emit('update:modelValue', updated)
  nextTick(() => {
    isUpdating.value = false
    placeCaretAtOffset(end)
    updateLineCount()
  })
}

function placeCaretAtOffset(targetOffset) {
  const editor = editorRef.value
  if (!editor) return
  let offset = 0
  let targetNode = editor
  let targetNodeOffset = editor.childNodes.length
  const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT)
  let node = walker.nextNode()
  while (node) {
    if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'BR') {
      if (offset >= targetOffset) {
        targetNode = node.parentNode
        targetNodeOffset = Array.prototype.indexOf.call(node.parentNode.childNodes, node) + 1
        break
      }
      offset += 1
    } else if (node.nodeType === Node.TEXT_NODE) {
      const length = node.textContent?.length || 0
      if (offset + length >= targetOffset) {
        targetNode = node
        targetNodeOffset = Math.max(0, targetOffset - offset)
        break
      }
      offset += length
    }
    node = walker.nextNode()
  }
  const range = document.createRange()
  range.setStart(targetNode, targetNodeOffset)
  range.collapse(true)
  const selection = window.getSelection()
  selection.removeAllRanges()
  selection.addRange(range)
}

function handlePaste(e) {
  e.preventDefault()
  const raw = e.clipboardData.getData('text/plain')
  const text = props.compact && !props.allowLineBreaks ? raw.replace(/[\r\n]+/g, ' ') : raw
  // 插入纯文本
  document.execCommand('insertText', false, text)
  // 更新行数
  updateLineCount()
}

// 更新显示（从 modelValue 到 HTML）
function updateDisplay() {
  if (editorRef.value && !isUpdating.value) {
    const formatted = formatToHtml(props.modelValue || '')

    // 比较并更新
    const currentText = parseToText()
    if (currentText !== props.modelValue) {
      isUpdating.value = true
      editorRef.value.innerHTML = formatted || '<br>'
      nextTick(() => {
        isUpdating.value = false
        updateLineCount()
      })
    }
  }
}

// 监听 modelValue 变化（从父组件传入）
watch(() => props.modelValue, (newVal) => {
  if (newVal !== undefined) {
    nextTick(() => {
      updateDisplay()
    })
  }
}, { immediate: true })

watch(() => [
  props.resumeMetrics?.fontSizePt,
  props.resumeMetrics?.labelFontSizePt,
  props.resumeMetrics?.labelFontWeight,
  props.resumeMetrics?.lineHeight,
  props.resumeMetrics?.contentWidthPx,
  props.resumeMetrics?.fontFamilyCss,
  props.resumeMetrics?.listTextIndentPt,
  props.resumeFlow?.labelPlacement,
  props.resumeFlow?.prefixText,
  props.resumeFlow?.labelBold,
  props.resumeFlow?.visible,
  props.resumeFlow?.contentIndentLevels
], () => nextTick(updateLineCount))

onMounted(() => {
  nextTick(() => {
    updateDisplay()
    updateLineCount()
  })
})
</script>

<style scoped>
.rich-editor {
  width: 100%;
  color: #ededf1;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.035);
  transition: all 0.2s ease;
  overflow: hidden;
}

.rich-editor:focus-within {
  border-color: rgba(120, 166, 255, 0.55);
  background: #25262c;
  box-shadow: 0 0 0 3px rgba(120, 166, 255, 0.09);
}

.rich-editor.compact {
  min-height: 46px;
  padding: 0;
  border-radius: 10px;
  box-sizing: border-box;
}

.rich-editor.compact .editor-content {
  min-height: 44px;
  max-height: 44px;
  padding: 0.8rem 0.75rem;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
}

.rich-editor.compact.allow-line-breaks .editor-content {
  max-height: none;
  white-space: pre-wrap;
  overflow-x: hidden;
  overflow-y: auto;
}

.editor-content {
  width: 100%;
  min-height: 120px;
  max-height: 250px;
  padding: 0.75rem;
  font-size: 0.85rem;
  line-height: 1.6;
  outline: none;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-y: auto;
  font-family: inherit;
  color: #ededf1;
  background: transparent;
}

/* 让 contenteditable 按 Enter 时插入 <br> 而不是 <div> */
.editor-content div {
  display: inline;
}

.editor-content:empty:before {
  content: attr(placeholder);
  color: #777780;
  pointer-events: none;
}

.editor-content b {
  font-weight: 600;
  color: #fff;
}

.default-bold-active .editor-content {
  font-weight: 600;
  color: #fff;
}

.editor-hint {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 0.4rem 0.75rem;
  background: rgba(255, 255, 255, 0.025);
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 0.75rem;
  color: #777780;
  border-radius: 0 0 var(--radius-sm) var(--radius-sm);
}

.line-count {
  color: #777780;
}

/* 隐藏滚动条但保留功能 */
.editor-content::-webkit-scrollbar {
  width: 6px;
}

.editor-content::-webkit-scrollbar-track {
  background: transparent;
}

.editor-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.16);
  border-radius: 3px;
}

.editor-content::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.24);
}
</style>
