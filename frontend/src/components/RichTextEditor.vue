<template>
  <div class="rich-editor">
    <!-- 编辑区域 -->
    <div
      ref="editorRef"
      class="editor-content"
      contenteditable="true"
      :placeholder="placeholder"
      @input="onInput"
      @keydown.ctrl.b="handleCtrlB"
      @keydown.meta.b="handleCtrlB"
      @paste="handlePaste"
      @blur="onBlur"
    ></div>
    <!-- 提示 -->
    <div class="editor-hint">
      <span class="hint-text">提示：选中文字后按 <kbd>Ctrl+B</kbd> 加粗</span>
      <span class="line-count">{{ displayLineCount }} 行</span>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick, computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '请输入内容'
  }
})

const emit = defineEmits(['update:modelValue'])

const editorRef = ref(null)
const isUpdating = ref(false) // 避免循环更新
const displayLineCount = ref(0) // 实时显示的行数

// 计算行数（从 HTML 内容实时计算）
function updateLineCount() {
  if (!editorRef.value) return
  const html = editorRef.value.innerHTML
  // 将 <br> 转为换行，计算换行次数
  const text = html.replace(/<br\s*\/?>/gi, '\n').replace(/<\/div>/gi, '\n').replace(/<div[^>]*>/gi, '\n')
  // 移除 HTML 标签
  const plainText = text.replace(/<[^>]+>/g, '')
  // 解码 HTML 实体
  const decodedText = plainText.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  // 计算行数
  const lines = decodedText.split('\n').filter(line => line.trim()).length
  displayLineCount.value = lines || 0
}

// 实时输入处理（只用于更新行数，不同步数据）
function onInput() {
  updateLineCount()
}

// 格式化文本：将 **text** 转为 <b>text</b>
function formatToHtml(text) {
  if (!text) return ''
  // 转义 HTML 特殊字符
  let escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  // 将换行转为 <br>
  escaped = escaped.replace(/\n/g, '<br>')
  // 将 **text** 转为 <b>text</b>
  escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
  return escaped
}

// 解析 HTML 为纯文本（保留 ** 标记）
function parseToText(html) {
  if (!html) return ''
  // 将 <b> 转回 **
  let text = html.replace(/<b>/g, '**').replace(/<\/b>/g, '**')
  // 将 <br> 和 <div> 转为换行
  text = text.replace(/<br\s*\/?>/gi, '\n').replace(/<\/div>/gi, '\n').replace(/<div[^>]*>/gi, '\n')
  // 移除其他 HTML 标签
  text = text.replace(/<[^>]+>/g, '')
  // 解码 HTML 实体
  text = text.replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
  // 清理多余的换行
  text = text.replace(/\n{3,}/g, '\n\n')
  return text.trim()
}

function onBlur() {
  // 只在失去焦点时同步数据到父组件
  if (editorRef.value && !isUpdating.value) {
    const text = parseToText(editorRef.value.innerHTML)
    if (text !== props.modelValue) {
      emit('update:modelValue', text)
    }
  }
}

function handleCtrlB(e) {
  e.preventDefault()
  const selection = window.getSelection()
  if (selection.rangeCount === 0) return

  const range = selection.getRangeAt(0)
  const selectedText = range.toString()
  if (!selectedText) return

  // 使用浏览器原生的 execCommand('bold') 命令
  // 这会自动处理各种边界情况
  document.execCommand('bold', false, null)

  // 更新行数
  updateLineCount()
}

// 获取文本节点在父元素中的相对偏移
function getRelativeOffset(textNode, parentElement, absoluteOffset) {
  let offset = 0
  for (const child of parentElement.childNodes) {
    if (child === textNode) {
      return offset + absoluteOffset
    }
    if (child.nodeType === Node.TEXT_NODE) {
      offset += child.textContent.length
    }
  }
  return null
}

// 对整个选区取消加粗
function toggleUnbold(editor, range, selectedText) {
  const selection = window.getSelection()

  // 获取选区的边界
  const startContainer = range.startContainer
  const startOffset = range.startOffset
  const endContainer = range.endContainer
  const endOffset = range.endOffset

  // 如果是同一个文本节点，直接在节点内处理
  if (startContainer === endContainer && startContainer.nodeType === Node.TEXT_NODE) {
    const text = startContainer.textContent
    const beforeText = text.substring(0, startOffset)
    const selectedTextContent = text.substring(startOffset, endOffset)
    const afterText = text.substring(endOffset)

    // 将选中部分的 <b> 标签替换为纯文本
    // 创建一个临时容器来处理
    const tempDiv = document.createElement('div')
    tempDiv.textContent = selectedTextContent

    // 找到所有被选中的文本节点部分
    processTextNodeForUnbold(startContainer, startOffset, endOffset)
  } else {
    // 跨多个节点的情况：遍历选区内的所有节点
    processRangeForUnbold(range)
  }

  // 合并相邻的 <b> 标签
  mergeAdjacentBoldTags(editor)

  // 恢复选区
  try {
    const newRange = document.createRange()
    newRange.setStart(startContainer, startOffset)
    newRange.setEnd(endContainer, endOffset)
    selection.removeAllRanges()
    selection.addRange(newRange)
  } catch (e) {
    console.warn('Failed to restore selection:', e)
  }
}

// 处理单个文本节点的取消加粗
function processTextNodeForUnbold(textNode, start, end) {
  const parent = textNode.parentElement
  if (!parent) return

  // 检查父元素是否是 <b>
  if (parent.tagName === 'B' || parent.tagName === 'STRONG') {
    const grandParent = parent.parentNode
    if (!grandParent) return

    const text = textNode.textContent
    const beforeText = text.substring(0, start)
    const selectedTextContent = text.substring(start, end)
    const afterText = text.substring(end)

    // 构建新的文档片段
    const fragment = document.createDocumentFragment()

    // 前面的文本
    if (beforeText) {
      fragment.appendChild(document.createTextNode(beforeText))
    }

    // 选中的文本 - 去掉 <b> 标签
    if (selectedTextContent) {
      fragment.appendChild(document.createTextNode(selectedTextContent))
    }

    // 后面的文本
    if (afterText) {
      fragment.appendChild(document.createTextNode(afterText))
    }

    grandParent.replaceChild(fragment, parent)
  }
}

// 处理跨多个节点的选区取消加粗
function processRangeForUnbold(range) {
  // 创建一个 TreeWalker 来遍历选区内容
  const container = range.commonAncestorContainer
  const walker = document.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
    null,
    false
  )

  const startContainer = range.startContainer
  const endContainer = range.endContainer

  let node = walker.currentNode
  while (node) {
    // 检查这个节点是否在选区内
    if (isNodeInRange(node, range)) {
      processTextNodeForUnboldInRange(node, range)
    }
    node = walker.nextNode()
  }
}

// 检查节点是否在选区内
function isNodeInRange(node, range) {
  const nodeRange = document.createRange()
  try {
    nodeRange.selectNode(node)
    return range.compareBoundaryPoints(Range.END_TO_START, nodeRange) <= 0 &&
           range.compareBoundaryPoints(Range.START_TO_END, nodeRange) >= 0
  } catch (e) {
    return false
  }
}

// 处理范围内的文本节点取消加粗
function processTextNodeForUnboldInRange(textNode, range) {
  const parent = textNode.parentElement
  if (!parent) return

  // 检查父元素是否是 <b>
  if (parent.tagName !== 'B' && parent.tagName !== 'STRONG') return

  // 计算在文本节点中的偏移
  const text = textNode.textContent
  let start = 0
  let end = text.length

  if (textNode === range.startContainer) {
    start = range.startOffset
  }
  if (textNode === range.endContainer) {
    end = range.endOffset
  }

  if (start >= end) return

  const grandParent = parent.parentNode
  if (!grandParent) return

  const beforeText = text.substring(0, start)
  const selectedTextContent = text.substring(start, end)
  const afterText = text.substring(end)

  // 构建新的文档片段
  const fragment = document.createDocumentFragment()

  if (beforeText) {
    fragment.appendChild(document.createTextNode(beforeText))
  }

  if (selectedTextContent) {
    fragment.appendChild(document.createTextNode(selectedTextContent))
  }

  if (afterText) {
    fragment.appendChild(document.createTextNode(afterText))
  }

  grandParent.replaceChild(fragment, parent)
}

// 对整个选区加粗
function toggleBold(editor, range, selectedText) {
  const selection = window.getSelection()

  // 直接用 range.extractContents() 提取选区内容，然后包裹 <b>
  const contents = range.extractContents()
  const b = document.createElement('b')
  b.appendChild(contents)
  range.insertNode(b)

  // 合并相邻的 <b> 标签
  mergeAdjacentBoldTags(editor)

  // 恢复选区到加粗文本之后
  try {
    const newRange = document.createRange()
    newRange.setStartAfter(b)
    newRange.setEndAfter(b)
    selection.removeAllRanges()
    selection.addRange(newRange)
  } catch (e) {
    console.warn('Failed to restore selection:', e)
  }
}

// 收集所有 <b> 标签及其在编辑器中的位置
function collectBTags(node, bTags, parentElement = null) {
  if (node.nodeType === Node.ELEMENT_NODE) {
    const isB = node.tagName === 'B' || node.tagName === 'STRONG'
    const currentParent = isB ? node : parentElement

    if (isB) {
      // 计算 <b> 在整个编辑器中的位置
      const tempRange = document.createRange()
      tempRange.selectNodeContents(editorRef.value)
      tempRange.setEnd(node, 0)
      const bStart = tempRange.toString().length

      bTags.push({
        element: node,
        start: bStart,
        end: bStart + node.textContent.length
      })
    }

    node.childNodes.forEach(child => collectBTags(child, bTags, currentParent))
  }
}

// 合并相邻的 <b> 标签
function mergeAdjacentBoldTags(editor) {
  const bTags = editor.querySelectorAll('b')
  for (let i = 0; i < bTags.length; i++) {
    const b = bTags[i]
    if (!b.parentNode) continue

    const nextSibling = b.nextSibling
    if (nextSibling && nextSibling.nodeType === Node.ELEMENT_NODE &&
        (nextSibling.tagName === 'B' || nextSibling.tagName === 'STRONG')) {
      b.textContent = b.textContent + nextSibling.textContent
      nextSibling.remove()
    }
  }
}

function handlePaste(e) {
  e.preventDefault()
  const text = e.clipboardData.getData('text/plain')
  // 插入纯文本
  document.execCommand('insertText', false, text)
  // 更新行数
  updateLineCount()
}

// 更新显示（从 modelValue 到 HTML）
function updateDisplay() {
  if (editorRef.value && !isUpdating.value) {
    const currentHtml = editorRef.value.innerHTML
    const formatted = formatToHtml(props.modelValue || '')

    // 比较并更新
    const currentText = parseToText(currentHtml)
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
  border: 1px solid #e9ecef;
  border-radius: var(--radius-sm);
  background: #fafafa;
  transition: all 0.2s ease;
}

.rich-editor:focus-within {
  border-color: var(--primary-color);
  background: #fff;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.08);
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
}

/* 让 contenteditable 按 Enter 时插入 <br> 而不是 <div> */
.editor-content div {
  display: inline;
}

.editor-content:empty:before {
  content: attr(placeholder);
  color: #adb5bd;
  pointer-events: none;
}

.editor-content b {
  font-weight: 600;
  color: var(--text-primary);
}

.editor-hint {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.4rem 0.75rem;
  background: #f8f9fa;
  border-top: 1px solid #e9ecef;
  font-size: 0.75rem;
  color: #adb5bd;
  border-radius: 0 0 var(--radius-sm) var(--radius-sm);
}

.hint-text {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.hint-text kbd {
  display: inline-block;
  padding: 0.15rem 0.4rem;
  font-size: 0.7rem;
  font-family: inherit;
  background: #fff;
  border: 1px solid #dee2e6;
  border-radius: 3px;
  box-shadow: 0 1px 0 #dee2e6;
}

.line-count {
  color: #adb5bd;
}

/* 隐藏滚动条但保留功能 */
.editor-content::-webkit-scrollbar {
  width: 6px;
}

.editor-content::-webkit-scrollbar-track {
  background: transparent;
}

.editor-content::-webkit-scrollbar-thumb {
  background: #dee2e6;
  border-radius: 3px;
}

.editor-content::-webkit-scrollbar-thumb:hover {
  background: #ced4da;
}
</style>
