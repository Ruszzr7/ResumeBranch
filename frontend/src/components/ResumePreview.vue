<script setup>
import { ref, computed, onMounted, watch, nextTick, onUnmounted } from 'vue'
import { labels } from '../utils/labels.js'
import { buildAuthorizationHeaders } from '../config/appMode.js'

const props = defineProps({
  data: {
    type: Object,
    required: false,
    default: () => null
  },
  // 高亮模块 - 值为: 'basics', 'education', 'work_experience', 'project_experience', 'others', 'self_evaluation'
  highlightedModule: {
    type: String,
    required: false,
    default: ''
  },
  // JD数据（新增）
  jdData: {
    type: Object,
    required: false,
    default: null
  },
  // 是否为移动端视图（由父组件传入）
  isMobileView: {
    type: Boolean,
    required: false,
    default: false
  },
  // 语言：'zh' | 'en'
  lang: {
    type: String,
    required: false,
    default: 'zh'
  },
  taskId: {
    type: String,
    required: false,
    default: ''
  }
})

// 获取当前语言的标签
const t = computed(() => labels[props.lang] || labels.zh)

function academicMetrics(item) {
  const metrics = []
  if (item?.gpa) {
    metrics.push(`${t.value.gpa}：${item.gpa}${item.gpa_scale ? `/${item.gpa_scale}` : ''}`)
  }
  if (item?.ranking) {
    metrics.push(`${t.value.ranking}：${item.ranking}`)
  }
  if (item?.average_score) {
    metrics.push(`${t.value.averageScore}：${item.average_score}`)
  }
  return metrics
}

const emit = defineEmits(['open-jd-dialog', 'open-resume-edit', 'toggle-lang'])

// 检测是否为移动端视图
const isMobile = computed(() => props.isMobileView || window.innerWidth < 1200)

// ========== 样式控制变量 ==========
const DEFAULT_STYLE = {
  marginVertical: 9,
  marginHorizontal: 9,
  moduleMargin: 1,
  lineHeight: 1.6,
  fontSize: 11
}
const marginVertical = ref(DEFAULT_STYLE.marginVertical)
const marginHorizontal = ref(DEFAULT_STYLE.marginHorizontal)
const moduleMargin = ref(DEFAULT_STYLE.moduleMargin)
const lineHeight = ref(DEFAULT_STYLE.lineHeight)
const fontSize = ref(DEFAULT_STYLE.fontSize)

function resetStyleSettings(event) {
  marginVertical.value = DEFAULT_STYLE.marginVertical
  marginHorizontal.value = DEFAULT_STYLE.marginHorizontal
  moduleMargin.value = DEFAULT_STYLE.moduleMargin
  lineHeight.value = DEFAULT_STYLE.lineHeight
  fontSize.value = DEFAULT_STYLE.fontSize
  event?.currentTarget?.blur()
}

// 移动端样式面板展开状态
const isStylePanelExpanded = ref(false)
const activeToolbarMenu = ref(null)

function toggleStylePanel() {
  isStylePanelExpanded.value = !isStylePanelExpanded.value
}

function toggleToolbarMenu(menu, event) {
  event?.stopPropagation()
  activeToolbarMenu.value = activeToolbarMenu.value === menu ? null : menu
}

function closeToolbarMenu() {
  activeToolbarMenu.value = null
}

function toggleLanguage() {
  emit('toggle-lang', props.lang === 'zh' ? 'en' : 'zh')
}

function openEditTarget(target) {
  closeToolbarMenu()
  emit(target === 'resume' ? 'open-resume-edit' : 'open-jd-dialog')
}

function handleToolbarOutsideClick(event) {
  if (!event.target.closest('.compact-toolbar-group')) {
    closeToolbarMenu()
  }
}

// A4尺寸（像素，96dpi）
const PAGE_WIDTH = 794
const PAGE_HEIGHT = 1123
const MM_TO_PX = 3.78

// 计算边距的像素值
const marginTopPx = computed(() => marginVertical.value * MM_TO_PX)
const marginBottomPx = computed(() => marginVertical.value * MM_TO_PX)
const marginLeftPx = computed(() => marginHorizontal.value * MM_TO_PX)
const marginRightPx = computed(() => marginHorizontal.value * MM_TO_PX)

// 动态样式 - 设置基础字体大小（使用em单位需要父元素有font-size）
const pageStyles = computed(() => ({
  fontSize: `${fontSize.value}pt`,
  lineHeight: lineHeight.value,
  '--module-margin': `${moduleMargin.value}rem`
}))

const pagePaddingStyle = computed(() => ({
  paddingTop: `${marginTopPx.value}px`,
  paddingBottom: `${marginBottomPx.value}px`,
  paddingLeft: `${marginLeftPx.value}px`,
  paddingRight: `${marginRightPx.value}px`
}))

// ========== 分页相关 ==========
const pageCount = ref(1)
const scale = ref(1)
const fitWidthScale = ref(1)
const zoomMode = ref('width') // width | page | manual
const manualZoom = ref(1)
const observer = ref(null)
const containerRef = ref(null)
const contentRef = ref(null)
const pageRanges = ref([])

// 扁平化的所有可分页项目
const allItems = computed(() => {
  if (!props.data) return []
  const items = []
  let index = 0

  if (props.data.basics) {
    items.push({ type: 'basics', index: index++, visible: true })
  }

  if (props.data.education && props.data.education.length) {
    items.push({ type: 'education-title', index: index++, visible: true })
    props.data.education.forEach((edu, i) => {
      items.push({ type: 'education-item', dataIndex: i, index: index++, visible: true })
      // 添加论文作为独立的可分页项
      if (edu.theses?.length) {
        edu.theses.forEach((_, tIdx) => {
          items.push({ type: 'thesis-item', dataIndex: `${i}-${tIdx}`, index: index++, visible: true })
        })
      }
    })
  }

  if (props.data.work_experience && props.data.work_experience.length) {
    items.push({ type: 'work-title', index: index++, visible: true })
    props.data.work_experience.forEach((work, i) => {
      items.push({ type: 'work-item', dataIndex: i, index: index++, visible: true })
      // 添加工作详情作为独立的可分页项
      if (work.details?.length) {
        items.push({ type: 'work-details', dataIndex: i, index: index++, visible: true })
      }
    })
  }

  if ((props.data.project_experience || props.data.projects) && (props.data.project_experience || props.data.projects).length) {
    items.push({ type: 'projects-title', index: index++, visible: true })
    const projects = props.data.project_experience || props.data.projects
    projects.forEach((proj, i) => {
      items.push({ type: 'project-item', dataIndex: i, index: index++, visible: true })
      // 添加项目详情作为独立的可分页项
      if (proj.details?.length) {
        items.push({ type: 'project-details', dataIndex: i, index: index++, visible: true })
      }
    })
  }

  if (props.data.others && (props.data.others.skills?.length || props.data.others.certificates?.length || props.data.others.languages?.length)) {
    items.push({ type: 'others-title', index: index++, visible: true })
    // 技能一行显示
    if (props.data.others.skills?.length) {
      items.push({ type: 'skill-line', index: index++, visible: true })
    }
    // 证书一行显示
    if (props.data.others.certificates?.length) {
      items.push({ type: 'cert-line', index: index++, visible: true })
    }
    // 语言一行显示
    if (props.data.others.languages?.length) {
      items.push({ type: 'lang-line', index: index++, visible: true })
    }
  }

  // 每条{{ t.selfEvaluation }}独立分页
  if (props.data.self_evaluation && props.data.self_evaluation.length) {
    items.push({ type: 'self-eval-title', index: index++, visible: true })
    props.data.self_evaluation.forEach((_, i) => {
      items.push({ type: 'self-eval-item', dataIndex: i, index: index++, visible: true })
    })
  }

  return items
})

// 页面容器样式
const pageStyle = computed(() => ({
  width: `${PAGE_WIDTH}px`,
  height: `${PAGE_HEIGHT}px`
}))

// 预览区域容器样式
const pagesContainerStyle = computed(() => ({
  transform: `scale(${scale.value})`,
  transformOrigin: 'top left',
  width: `${PAGE_WIDTH}px`,
  position: 'absolute',
  top: '0',
  left: '0'
}))

const pagesViewportStyle = computed(() => {
  const unscaledHeight = pageCount.value * PAGE_HEIGHT + Math.max(0, pageCount.value - 1) * 20
  return {
    width: `${PAGE_WIDTH * scale.value}px`,
    height: `${unscaledHeight * scale.value}px`
  }
})

const zoomPercentage = computed(() => {
  if (!fitWidthScale.value) return 100
  return Math.round((scale.value / fitWidthScale.value) * 100)
})

// ========== 精细分页算法 ==========
const calculatePagination = async () => {
  // 等待字体完全加载（带超时）
  try {
    const fontsPromise = document.fonts.ready
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error('fonts timeout')), 500)
    )
    await Promise.race([fontsPromise, timeoutPromise])
  } catch (e) {
    await new Promise(resolve => setTimeout(resolve, 100))
  }

  await nextTick()
  await nextTick()

  if (!props.data || !contentRef.value) {
    pageRanges.value = []
    pageCount.value = 1
    return
  }

  const container = contentRef.value
  const topMargin = marginTopPx.value
  const bottomMargin = marginBottomPx.value
  const pageContentHeight = PAGE_HEIGHT - topMargin - bottomMargin

  // 只获取直接子元素中的 pageable-item
  const children = Array.from(container.children).filter(el => {
    return el.classList.contains('pageable-item')
  })

  if (children.length === 0) {
    pageCount.value = 1
    return
  }

  // 直接累加每个元素的高度，找到最佳分页点
  const elementHeights = children.map((child, idx) => {
    return {
      idx,
      height: child.offsetHeight  // 使用 offsetHeight
    }
  })

  // 计算源内容总高度
  const sourceHeight = container.scrollHeight

  // 计算需要的页数
  const estimatedPageCount = Math.max(1, Math.ceil(sourceHeight / pageContentHeight))

  // 累积分页算法
  const ranges = []
  let currentStart = 0
  let currentHeight = 0

  for (let i = 0; i < elementHeights.length; i++) {
    const elem = elementHeights[i]

    // 检查加上这个元素是否超出页面
    // 如果当前高度 + 这个元素高度 > 可用高度，需要分页
    // 留更大余量（约120px），因为 margin collapse 可能累积，且每个页面顶部会损失更多
    // 首行没有 margin-top，所以每个新页面会多出一些可用空间
    const wouldExceed = currentHeight + elem.height > (pageContentHeight - 120)

    if (currentStart === i && estimatedPageCount === 1) {
      // 只有一页的情况，直接包含所有元素
      currentHeight += elem.height
    } else if (wouldExceed && i > 0) {
      // 保存当前页
      ranges.push({ start: currentStart, end: i })

      // 开始新页面
      currentStart = i
      currentHeight = elem.height
    } else {
      currentHeight += elem.height
    }
  }

  // 保存最后一页
  if (currentStart < elementHeights.length) {
    ranges.push({ start: currentStart, end: elementHeights.length })
  }

  // 确保至少有一页
  if (ranges.length === 0 && elementHeights.length > 0) {
    ranges.push({ start: 0, end: elementHeights.length })
  }

  pageRanges.value = ranges
  pageCount.value = ranges.length

  // 验证：测量实际渲染的页面高度，如果溢出则调整
  await nextTick()
  await nextTick()

  const verifyAndFixPagination = async () => {
    const pageContents = document.querySelectorAll('.page-content')
    if (pageContents.length === 0) return

    let adjusted = false
    const availableHeight = pageContentHeight

    pageContents.forEach((el, idx) => {
      const actualHeight = el.scrollHeight
      if (actualHeight > availableHeight + 50) {
        // 标记需要重新计算
        adjusted = true
      }
    })

    // 如果有溢出，重新计算分页，使用更小的每页高度限制
    if (adjusted) {
      const newRanges = []
      let currentStart = 0
      let currentHeight = 0

      for (let i = 0; i < elementHeights.length; i++) {
        const elem = elementHeights[i]
        const wouldExceed = currentHeight + elem.height > (availableHeight - 150)

        if (wouldExceed && i > 0) {
          newRanges.push({ start: currentStart, end: i })
          currentStart = i
          currentHeight = elem.height
        } else {
          currentHeight += elem.height
        }
      }

      if (currentStart < elementHeights.length) {
        newRanges.push({ start: currentStart, end: elementHeights.length })
      }

      if (newRanges.length > ranges.length) {
        pageRanges.value = newRanges
        pageCount.value = newRanges.length
      }
    }
  }

  // 延迟验证，确保DOM已完全渲染
  setTimeout(verifyAndFixPagination, 200)
}

// ========== 监听变化 ==========
watch([() => props.data, marginVertical, marginHorizontal, moduleMargin, lineHeight, fontSize],
  () => {
    // 增加延迟时间，确保字体变化后浏览器有足够时间重新渲染
    if (window.requestAnimationFrame) {
      window.requestAnimationFrame(() => {
        setTimeout(calculatePagination, 300)  // 增加延迟
      })
    } else {
      setTimeout(calculatePagination, 300)
    }
  }, { deep: true })

// ========== 高亮模块滚动 ==========
watch(() => props.highlightedModule, async (newModule) => {
  if (newModule && props.data) {
    await nextTick()
    // 延迟执行滚动，确保DOM已完全渲染
    setTimeout(() => {
      // 在可见的 pages-wrapper 中查找对应模块
      const pagesWrapper = document.querySelector('.pages-wrapper')
      if (pagesWrapper) {
        // 根据模块类型查找对应的section标题
        const sectionTitle = pagesWrapper.querySelector(`[data-module="${newModule}"]`)
        if (sectionTitle) {
          sectionTitle.scrollIntoView({ behavior: 'smooth', block: 'center' })
        } else {
          // 如果没找到，尝试在 preview-content 中查找
          const previewContent = document.querySelector('.preview-content')
          if (previewContent) {
            const element = previewContent.querySelector(`[data-module="${newModule}"]`)
            if (element) {
              element.scrollIntoView({ behavior: 'smooth', block: 'center' })
            }
          }
        }
      }
    }, 200)
  }
})

// 调试方法：在控制台调用 testHighlight('education') 测试高亮效果
window.testHighlight = (moduleName) => {
  const previewContent = document.querySelector('.preview-content')
  if (previewContent) {
    const element = previewContent.querySelector(`[data-module="${moduleName}"]`)
    if (element) {
      // 添加高亮类测试动画
      element.classList.add('title-highlight')
      // 测试滚动
      element.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }
}

// 测试动画的独立方法
window.testAnimation = (moduleName) => {
  const element = document.querySelector(`[data-module="${moduleName}"]`)
  if (element) {
    element.classList.add('title-highlight')
    setTimeout(() => {
      element.classList.remove('title-highlight')
    }, 3000)
  }
}

// ========== 缩放计算 ==========
const calculateScale = () => {
  const container = containerRef.value || document.querySelector('.preview-content')
  if (!container) return

  const availableWidth = container.clientWidth - 40
  const widthScale = Math.min(1, Math.max(0.3, availableWidth / PAGE_WIDTH))
  fitWidthScale.value = widthScale

  let newScale = widthScale
  if (zoomMode.value === 'page') {
    const availableHeight = container.clientHeight - 40
    newScale = Math.min(widthScale, Math.max(0.3, availableHeight / PAGE_HEIGHT))
  } else if (zoomMode.value === 'manual') {
    newScale = widthScale * manualZoom.value
  }

  if (Math.abs(newScale - scale.value) > 0.01) {
    scale.value = newScale
  }
}

const setZoomMode = (mode, event) => {
  zoomMode.value = mode
  if (mode === 'width') manualZoom.value = 1
  calculateScale()
  event?.currentTarget?.blur()
}

const adjustZoom = (delta, event) => {
  const currentRatio = fitWidthScale.value
    ? scale.value / fitWidthScale.value
    : manualZoom.value
  manualZoom.value = Math.min(1, Math.max(0.4, currentRatio + delta))
  zoomMode.value = 'manual'
  calculateScale()
  event?.currentTarget?.blur()
}

// ========== 工具栏控制 ==========
const controlPanelTimeout = ref(null)

const showControlPanel = (event) => {
  const toolbarControls = event.currentTarget.querySelector('.toolbar-controls')
  if (toolbarControls) {
    clearTimeout(controlPanelTimeout.value)
    // 隐藏所有其他控制面板
    document.querySelectorAll('.toolbar-controls').forEach(panel => {
      if (panel !== toolbarControls) {
        panel.style.visibility = 'hidden'
        panel.style.opacity = '0'
      }
    })

    // 使用 fixed 定位，脱离所有层叠上下文
    const rect = event.currentTarget.getBoundingClientRect()
    toolbarControls.style.position = 'fixed'
    toolbarControls.style.left = `${rect.left + rect.width / 2}px`
    toolbarControls.style.transform = 'translateX(-50%)'
    toolbarControls.style.top = `${rect.bottom + window.scrollY}px`
    toolbarControls.style.visibility = 'visible'
    toolbarControls.style.opacity = '1'
  }
}

const hideControlPanel = (event) => {
  const toolbarControls = event.currentTarget.querySelector('.toolbar-controls')
  if (toolbarControls) {
    controlPanelTimeout.value = setTimeout(() => {
      toolbarControls.style.visibility = 'hidden'
      toolbarControls.style.opacity = '0'
    }, 150)
  }
}

// ========== 格式化文本 ==========
const formatText = (text) => {
  if (typeof text !== 'string') return text
  return text.trim().replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
}

// ========== 导出PDF（调用后端API，使用WeasyPrint生成矢量PDF）============
const showSuccessDialog = ref(false)
const exportError = ref('')
const isExportingPDF = ref(false)
const isExportingDOCX = ref(false)
const lastExportFormat = ref('PDF')

const exportDocument = async (format) => {
  if (!props.data) return

  const isPDF = format === 'pdf'
  if (isPDF) isExportingPDF.value = true
  else isExportingDOCX.value = true
  try {
    // 构建样式参数
    const style = {
      marginTop: marginVertical.value,
      marginBottom: marginVertical.value,
      marginLeft: marginHorizontal.value,
      marginRight: marginHorizontal.value,
      moduleMargin: moduleMargin.value,
      lineHeight: lineHeight.value,
      fontSize: fontSize.value
    }

    // 调用后端API
    const response = await fetch(isPDF ? '/export_pdf' : '/export_docx', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...buildAuthorizationHeaders(),
        ...(props.taskId ? { 'X-Task-ID': props.taskId } : {})
      },
      body: JSON.stringify({
        resume_data: props.data,
        style: style,
        lang: props.lang
      })
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => null)
      throw new Error(errorData?.detail || errorData || `${isPDF ? 'PDF' : 'Word'}生成失败`)
    }

    // 获取PDF二进制数据
    const documentBlob = await response.blob()

    // 创建下载链接
    const url = window.URL.createObjectURL(documentBlob)
    const a = document.createElement('a')
    a.href = url
    a.download = `resume_${props.data.basics?.name || 'export'}.${isPDF ? 'pdf' : 'docx'}`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)

    // 显示成功提示弹窗
    lastExportFormat.value = isPDF ? 'PDF' : 'Word'
    showSuccessDialog.value = true

  } catch (error) {
    console.error('简历导出错误:', error)
    exportError.value = error.message || '简历导出失败，请确认后端服务正常运行后重试。'
  } finally {
    if (isPDF) isExportingPDF.value = false
    else isExportingDOCX.value = false
  }
}

const exportPDF = () => exportDocument('pdf')
const exportWord = () => exportDocument('docx')

// ========== 生命周期 ==========
onMounted(async () => {
  await nextTick()
  setTimeout(async () => {
    await calculatePagination()
    calculateScale()
  }, 100)

  observer.value = new ResizeObserver(() => {
    clearTimeout(window.scaleTimeout)
    window.scaleTimeout = setTimeout(async () => {
      await calculatePagination()
      calculateScale()
    }, 100)
  })

  const container = document.querySelector('.preview-content')
  if (container) observer.value.observe(container)
  // 也监听隐藏内容的变化（字体变化会影响高度）
  if (contentRef.value) observer.value.observe(contentRef.value)
  observer.value.observe(document.body)
  window.addEventListener('resize', calculateScale)
  document.addEventListener('click', handleToolbarOutsideClick)
})

onUnmounted(() => {
  observer.value?.disconnect()
  window.removeEventListener('resize', calculateScale)
  document.removeEventListener('click', handleToolbarOutsideClick)
  clearTimeout(window.scaleTimeout)
})

// ========== 分页工具函数 ==========
const isItemVisible = (item, pageIndex) => {
  if (!pageRanges.value.length) return true
  const range = pageRanges.value[pageIndex]
  return range && item.index >= range.start && item.index < range.end
}

const getItemIndex = (type, dataIndex) => {
  const items = allItems.value
  if (!items.length) return 0

  const singleTypes = ['basics', 'education-title', 'work-title', 'projects-title', 'others-title', 'self-eval-title']
  if (singleTypes.includes(type)) {
    const found = items.find(item => item.type === type)
    return found ? found.index : 0
  }

  // 处理 cert-line、lang-line 和 skill-line（无 dataIndex 的特殊类型）
  if (type === 'cert-line' || type === 'lang-line' || type === 'skill-line') {
    const found = items.find(item => item.type === type)
    return found ? found.index : items.length
  }

  // 处理带 dataIndex 的类型
  const found = items.find(item => {
    if (item.type !== type) return false
    return item.dataIndex === dataIndex
  })
  return found ? found.index : 0
}
</script>

<template>
  <div class="resume-wrapper">
    <!-- 工具栏 - 始终显示 -->
    <div class="resume-toolbar-wrapper">
      <div class="resume-toolbar">
        <!-- 移动端：可展开的样式调整面板 -->
        <template v-if="isMobile">
          <button class="toolbar-icon reset-style-btn" @click="resetStyleSettings" title="恢复默认排版设置">🔧</button>
          <div class="zoom-controls" aria-label="简历缩放">
            <button :class="{ active: zoomMode === 'width' }" @click="setZoomMode('width', $event)" title="适应预览宽度">适宽</button>
            <button :class="{ active: zoomMode === 'page' }" @click="setZoomMode('page', $event)" title="完整显示一页">整页</button>
            <div class="zoom-readout">
              <span class="zoom-value">{{ zoomPercentage }}%</span>
              <span class="zoom-stepper">
                <button @click="adjustZoom(0.1, $event)" :disabled="zoomPercentage >= 100" title="放大">＋</button>
                <button @click="adjustZoom(-0.1, $event)" :disabled="zoomPercentage <= 40" title="缩小">−</button>
              </span>
            </div>
          </div>
          <div class="mobile-toolbar-row">
            <button class="mobile-style-btn" @click="toggleStylePanel" :class="{ active: isStylePanelExpanded }">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
              <span>{{ isStylePanelExpanded ? '收起' : '调整样式' }}</span>
            </button>
            
            <!-- 移动端操作按钮 - 始终显示 -->
            <button class="mobile-jd-btn" @click="emit('open-resume-edit')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
              <span>编辑简历</span>
            </button>
            <button class="mobile-jd-btn" @click="emit('open-jd-dialog')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
              </svg>
              <span>目标岗位</span>
            </button>
            <button class="mobile-export-btn" @click="exportPDF" :disabled="isExportingPDF || !data">
              <span v-if="isExportingPDF" class="spinner"></span>
              <span>{{ isExportingPDF ? '导出中...' : '导出PDF' }}</span>
            </button>
          </div>
          
          <!-- 可展开的样式控制面板 -->
          <Transition name="slide-down">
            <div v-if="isStylePanelExpanded" class="style-panel-mobile">
              <div class="style-control-row">
                <div class="style-control-item">
                  <label class="style-label">上下边距: {{ marginVertical }}rem</label>
                  <input type="range" v-model.number="marginVertical" min="3" max="12" step="0.25" class="slider">
                </div>
                <div class="style-control-item">
                  <label class="style-label">左右边距: {{ marginHorizontal }}rem</label>
                  <input type="range" v-model.number="marginHorizontal" min="3" max="12" step="0.25" class="slider">
                </div>
              </div>
              <div class="style-control-row">
                <div class="style-control-item">
                  <label class="style-label">模块间距: {{ moduleMargin }}rem</label>
                  <input type="range" v-model.number="moduleMargin" min="0.25" max="2" step="0.25" class="slider">
                </div>
                <div class="style-control-item">
                  <label class="style-label">行间距: {{ lineHeight }}</label>
                  <input type="range" v-model.number="lineHeight" min="1.1" max="2.2" step="0.1" class="slider">
                </div>
              </div>
              <div class="style-control-row single">
                <div class="style-control-item">
                  <label class="style-label">字体大小: {{ fontSize }}pt</label>
                  <input type="range" v-model.number="fontSize" min="9" max="14" step="0.5" class="slider">
                </div>
              </div>
            </div>
          </Transition>
        </template>
        
        <!-- PC端：合并同类功能，保留完整操作 -->
        <template v-else>
          <div class="compact-toolbar-cluster">
          <div class="compact-toolbar-group">
            <button
              class="compact-toolbar-btn"
              :class="{ active: activeToolbarMenu === 'zoom' }"
              :aria-expanded="activeToolbarMenu === 'zoom'"
              aria-label="打开页面缩放"
              @click="toggleToolbarMenu('zoom', $event)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3m18 0v3a2 2 0 0 1-2 2h-3"/>
              </svg>
              <span>{{ zoomPercentage }}%</span>
            </button>
            <button class="mobile-export-btn word-export-btn" @click="exportWord" :disabled="isExportingDOCX || !data">
              <span v-if="isExportingDOCX" class="spinner"></span>
              <span>{{ isExportingDOCX ? '导出中...' : '导出Word' }}</span>
            </button>
            <div v-if="activeToolbarMenu === 'zoom'" class="compact-popover zoom-popover" @click.stop>
              <div class="compact-popover-title">页面缩放</div>
              <div class="zoom-mode-grid">
                <button :class="{ active: zoomMode === 'width' }" @click="setZoomMode('width', $event)">适宽</button>
                <button :class="{ active: zoomMode === 'page' }" @click="setZoomMode('page', $event)">整页</button>
              </div>
              <div class="compact-zoom-stepper">
                <button @click="adjustZoom(-0.1, $event)" :disabled="zoomPercentage <= 40" aria-label="缩小">−</button>
                <button @click="manualZoom = 1; setZoomMode('manual', $event)" aria-label="恢复百分之百">100%</button>
                <button @click="adjustZoom(0.1, $event)" :disabled="zoomPercentage >= 100" aria-label="放大">＋</button>
              </div>
            </div>
          </div>

          <div class="compact-toolbar-group">
            <button
              class="compact-toolbar-btn"
              :class="{ active: activeToolbarMenu === 'layout' }"
              :aria-expanded="activeToolbarMenu === 'layout'"
              aria-label="打开排版设置"
              @click="toggleToolbarMenu('layout', $event)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <rect x="4" y="3" width="16" height="18" rx="2"/>
                <path d="M8 7h8M8 11h8M8 15h5"/>
              </svg>
              <span>排版</span>
            </button>
            <div v-if="activeToolbarMenu === 'layout'" class="compact-popover layout-popover" @click.stop>
              <div class="compact-popover-title">排版设置</div>
              <label class="compact-control">
                <span>上下页边距 <strong>{{ marginVertical }}mm</strong></span>
                <input type="range" v-model.number="marginVertical" min="3" max="12" step="0.25" class="slider">
              </label>
              <label class="compact-control">
                <span>左右页边距 <strong>{{ marginHorizontal }}mm</strong></span>
                <input type="range" v-model.number="marginHorizontal" min="3" max="12" step="0.25" class="slider">
              </label>
              <label class="compact-control">
                <span>模块间距 <strong>{{ moduleMargin }}rem</strong></span>
                <input type="range" v-model.number="moduleMargin" min="0.25" max="2" step="0.25" class="slider">
              </label>
              <label class="compact-control">
                <span>行间距 <strong>{{ lineHeight }}</strong></span>
                <input type="range" v-model.number="lineHeight" min="1.1" max="2.2" step="0.1" class="slider">
              </label>
              <label class="compact-control">
                <span>字体大小 <strong>{{ fontSize }}pt</strong></span>
                <input type="range" v-model.number="fontSize" min="9" max="14" step="0.5" class="slider">
              </label>
              <button class="compact-reset-btn" @click="resetStyleSettings">恢复默认排版</button>
            </div>
          </div>

          <button class="compact-toolbar-btn language-btn" @click="toggleLanguage" :aria-label="`切换为${lang === 'zh' ? '英文' : '中文'}简历`">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <circle cx="12" cy="12" r="9"/>
              <path d="M3 12h18M12 3c2.2 2.5 3.3 5.5 3.3 9S14.2 18.5 12 21c-2.2-2.5-3.3-5.5-3.3-9S9.8 5.5 12 3"/>
            </svg>
            <span>{{ lang === 'zh' ? '中 / EN' : 'EN / 中' }}</span>
          </button>

          <div class="compact-toolbar-group edit-toolbar-group">
            <button
              class="compact-toolbar-btn"
              :class="{ active: activeToolbarMenu === 'edit' }"
              :aria-expanded="activeToolbarMenu === 'edit'"
              aria-label="打开内容编辑菜单"
              @click="toggleToolbarMenu('edit', $event)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <path d="M12 20h9"/>
                <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L8 18l-4 1 1-4Z"/>
              </svg>
              <span>编辑</span>
            </button>
            <div v-if="activeToolbarMenu === 'edit'" class="compact-popover edit-popover" @click.stop>
              <div class="compact-popover-title">编辑内容</div>
              <button class="compact-menu-item" @click="openEditTarget('resume')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/>
                  <path d="M14 2v6h6M8 13h8M8 17h5"/>
                </svg>
                <span><strong>编辑简历</strong><small>修改个人信息与经历</small></span>
              </button>
              <button class="compact-menu-item" @click="openEditTarget('jd')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                  <rect x="3" y="7" width="18" height="13" rx="2"/>
                  <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18"/>
                </svg>
                <span><strong>目标岗位 JD</strong><small>{{ jdData ? '查看或修改岗位信息' : '添加岗位信息' }}</small></span>
              </button>
            </div>
          </div>
          </div>

          <button class="export-btn compact-export-btn" @click="exportPDF" :disabled="isExportingPDF || !data">
            <span v-if="isExportingPDF" class="spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M12 3v12M7 10l5 5 5-5"/>
              <path d="M5 21h14"/>
            </svg>
            <span>{{ isExportingPDF ? '导出中...' : '导出 PDF' }}</span>
          </button>
          <button class="export-btn compact-export-btn word-export-btn" @click="exportWord" :disabled="isExportingDOCX || !data">
            <span v-if="isExportingDOCX" class="spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M6 3h9l3 3v15H6z"/><path d="M15 3v4h4M9 11l2 6 2-4 2 4 2-6"/>
            </svg>
            <span>{{ isExportingDOCX ? '导出中...' : '导出 Word' }}</span>
          </button>
        </template>
      </div>
    </div>

    <!-- 有简历数据时显示预览 -->
    <template v-if="data">
      <!-- 预览内容区域 -->
      <div class="preview-content" ref="containerRef">
      <!-- 隐藏的完整内容（用于测量） -->
      <div ref="contentRef" class="content-source" :style="[pageStyles, pagePaddingStyle]">
      <!-- 个人信息 -->
      <div v-if="data.basics" class="pageable-item personal-info" :class="{ 'module-highlight': highlightedModule === 'basics' }" data-module="basics">
        <!-- 证件照绝对定位（不参与居中计算） -->
        <div v-if="data.basics.photo" class="photo-container">
          <img :src="data.basics.photo" class="profile-photo" alt="证件照" />
        </div>
        <h1 class="name">{{ data.basics.name || '姓名未填写' }}</h1>
        <div class="contact-info">
          <span v-if="data.basics?.gender" v-html="formatText(data.basics.gender)"></span>
          <span v-if="data.basics?.gender || data.basics?.phone" class="separator">|</span>
          <span v-if="data.basics?.phone" v-html="formatText(data.basics.phone)"></span>
          <span v-if="(data.basics?.gender || data.basics?.phone) && data.basics?.email" class="separator">|</span>
          <span v-if="data.basics?.email" v-html="formatText(data.basics.email)"></span>
        </div>
        <div v-if="data.basics?.target_position" class="target-position">
          {{ t.targetPosition }}：<span v-html="formatText(data.basics.target_position)"></span>
        </div>
      </div>

      <!-- {{ t.education }} -->
      <template v-if="data.education && data.education.length">
        <h2 class="pageable-item section-title" :class="{ 'title-highlight': highlightedModule === 'education' }" data-module="education">{{ t.education }}</h2>
        <div v-for="(item, idx) in data.education" :key="idx" class="pageable-item education-item">
          <div class="education-header">
            <div class="school-info">
              <span class="school" v-html="formatText(item.school_name || '学校未填写')"></span>
              <div v-if="item.school_tags?.length" class="school-tags">
                <span v-for="(tag, tIdx) in item.school_tags" :key="tIdx" class="school-tag" v-html="formatText(tag)"></span>
              </div>
            </div>
            <span class="graduation-date">{{ item.date_range?.[0] || '' }} - {{ item.date_range?.[1] || '至今' }}</span>
          </div>
          <div class="degree-major" v-html="formatText(`${item.degree || ''} ${item.major || ''}`)"></div>
          <div v-if="academicMetrics(item).length" class="academic-metrics">
            <span v-for="metric in academicMetrics(item)" :key="metric" v-html="formatText(metric)"></span>
          </div>
        </div>
        <template v-if="data.education">
          <template v-for="(item, idx) in data.education">
            <template v-if="item.theses?.length">
              <div v-for="(thesis, tIdx) in item.theses" :key="'thesis-'+idx+'-'+tIdx" class="pageable-item thesis-item">
                <h4 class="subfield-title">{{ t.thesis }}</h4>
                <div class="thesis-title" v-html="formatText(thesis.title)"></div>
                <ul v-if="thesis.details?.length" class="list-items">
                  <li v-for="(detail, dIdx) in thesis.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
                </ul>
              </div>
            </template>
          </template>
        </template>
      </template>

      <!-- {{ t.workExperience }} -->
      <template v-if="data.work_experience && data.work_experience.length">
        <h2 class="pageable-item section-title" :class="{ 'title-highlight': highlightedModule === 'work_experience' }" data-module="work_experience">{{ t.workExperience }}</h2>
        <div v-for="(item, idx) in data.work_experience" :key="idx" class="pageable-item work-item">
          <div class="work-header">
            <div class="work-main">
              <div class="company" v-html="formatText(item.company_name || '公司未填写')"></div>
              <div class="position" v-html="formatText(`${item.job_title || ''} ${item.job_type ? `(${item.job_type})` : ''}`)"></div>
            </div>
            <span class="work-period">{{ item.date_range?.[0] || '' }} - {{ item.date_range?.[1] || '至今' }}</span>
          </div>
        </div>
        <template v-if="data.work_experience">
          <template v-for="(item, idx) in data.work_experience">
            <div v-if="item.details" :key="'details-'+idx" class="pageable-item work-details">
              <ul class="list-items">
                <li v-for="(detail, dIdx) in item.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
              </ul>
            </div>
          </template>
        </template>
      </template>

      <!-- {{ t.projectExperience }} -->
      <template v-if="(data.project_experience || data.projects) && (data.project_experience || data.projects).length">
        <h2 class="pageable-item section-title" :class="{ 'title-highlight': highlightedModule === 'project_experience' }" data-module="project_experience">{{ t.projectExperience }}</h2>
        <div v-for="(item, idx) in (data.project_experience || data.projects)" :key="idx" class="pageable-item project-item">
          <div class="project-header">
            <div class="project-name" v-html="formatText(item.project_name || item.name || '项目未填写')"></div>
            <div class="project-role">
              <span v-if="item.date_range?.length" v-html="formatText(`${item.role || '角色'} | ${item.date_range[0]} - ${item.date_range[1] || '至今'}`)"></span>
              <span v-else-if="item.start_date || item.end_date" v-html="formatText(`${item.role || '角色'} | ${item.start_date || ''} - ${item.end_date || '至今'}`)"></span>
              <span v-else v-html="formatText(item.role || '项目')"></span>
            </div>
          </div>
        </div>
        <template v-if="data.project_experience || data.projects">
          <template v-for="(item, idx) in (data.project_experience || data.projects)">
            <div v-if="item.details" :key="'details-'+idx" class="pageable-item project-details">
              <ul class="list-items">
                <li v-for="(detail, dIdx) in item.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
              </ul>
            </div>
          </template>
        </template>
      </template>

      <!-- 其他 -->
      <template v-if="data.others && (data.others.skills?.length || data.others.certificates?.length || data.others.languages?.length)">
        <h2 class="pageable-item section-title" :class="{ 'title-highlight': highlightedModule === 'others' }" data-module="others">其他</h2>
        <!-- 技能一行显示 -->
        <template v-if="data.others.skills?.length">
          <div class="pageable-item cert-lang-line">
            <span class="cert-lang-label">{{ t.skills }}：</span>
            <template v-for="(skill, sIdx) in data.others.skills">
              <span v-html="formatText(skill)"></span><span v-if="sIdx < data.others.skills.length - 1" class="cert-lang-separator"> | </span>
            </template>
          </div>
        </template>
        <!-- 证书一行显示 -->
        <template v-if="data.others.certificates?.length">
          <div class="pageable-item cert-lang-line">
            <span class="cert-lang-label">{{ t.certificates }}：</span>
            <template v-for="(cert, cIdx) in data.others.certificates">
              <span v-html="formatText(cert)"></span><span v-if="cIdx < data.others.certificates.length - 1" class="cert-lang-separator"> | </span>
            </template>
          </div>
        </template>
        <!-- 语言一行显示 -->
        <template v-if="data.others.languages?.length">
          <div class="pageable-item cert-lang-line">
            <span class="cert-lang-label">{{ t.language }}：</span>
            <template v-for="(lang, lIdx) in data.others.languages">
              <span v-html="formatText(lang)"></span><span v-if="lIdx < data.others.languages.length - 1" class="cert-lang-separator"> | </span>
            </template>
          </div>
        </template>
      </template>

      <!-- {{ t.selfEvaluation }} -->
      <template v-if="data.self_evaluation && data.self_evaluation.length">
        <h2 class="pageable-item section-title" :class="{ 'title-highlight': highlightedModule === 'self_evaluation' }" data-module="self_evaluation">{{ t.selfEvaluation }}</h2>
        <!-- 每条{{ t.selfEvaluation }}独立分页 -->
        <template v-for="(item, idx) in data.self_evaluation">
          <div v-if="item" :key="'self-eval-'+idx" class="pageable-item self-eval-item">
            <span v-html="formatText(item)"></span>
          </div>
        </template>
      </template>
    </div>

    <!-- 打印专用容器 - 连续内容流，让浏览器自动分页 -->
    <div class="print-container" :style="[pageStyles, pagePaddingStyle]" v-if="data && data.work_experience">
      <!-- 个人信息 -->
      <div class="personal-info">
        <div v-if="data.basics?.photo" class="photo-container">
          <img :src="data.basics.photo" class="profile-photo" alt="证件照" />
        </div>
        <h1 class="name">{{ data.basics?.name || '姓名未填写' }}</h1>
        <div class="contact-info">
          <span v-if="data.basics?.gender" v-html="formatText(data.basics.gender)"></span>
          <span v-if="data.basics?.gender || data.basics?.phone" class="separator">|</span>
          <span v-if="data.basics?.phone" v-html="formatText(data.basics.phone)"></span>
          <span v-if="(data.basics?.gender || data.basics?.phone) && data.basics?.email" class="separator">|</span>
          <span v-if="data.basics?.email" v-html="formatText(data.basics.email)"></span>
        </div>
        <div v-if="data.basics?.target_position" class="target-position">
          {{ t.targetPosition }}：<span v-html="formatText(data.basics.target_position)"></span>
        </div>
      </div>

      <!-- {{ t.education }} -->
      <template v-if="data.education && data.education.length">
        <h2 class="section-title">{{ t.education }}</h2>
        <div v-for="(item, idx) in data.education" :key="idx" class="education-item">
          <div class="education-header">
            <div class="school-info">
              <span class="school" v-html="formatText(item.school_name || '学校未填写')"></span>
              <div v-if="item.school_tags?.length" class="school-tags">
                <span v-for="(tag, tIdx) in item.school_tags" :key="tIdx" class="school-tag" v-html="formatText(tag)"></span>
              </div>
            </div>
            <span class="graduation-date">{{ item.date_range?.[0] || '' }} - {{ item.date_range?.[1] || '至今' }}</span>
          </div>
          <div class="degree-major" v-html="formatText(`${item.degree || ''} ${item.major || ''}`)"></div>
          <div v-if="academicMetrics(item).length" class="academic-metrics">
            <span v-for="metric in academicMetrics(item)" :key="metric" v-html="formatText(metric)"></span>
          </div>
          <!-- 论文 -->
          <template v-if="item.theses?.length">
            <div v-for="(thesis, tIdx) in item.theses" :key="'thesis-'+idx+'-'+tIdx" class="thesis-item">
              <h4 class="subfield-title">{{ t.thesis }}</h4>
              <div class="thesis-title" v-html="formatText(thesis.title)"></div>
              <ul v-if="thesis.details?.length" class="list-items">
                <li v-for="(detail, dIdx) in thesis.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
              </ul>
            </div>
          </template>
        </div>
      </template>

      <!-- {{ t.workExperience }} -->
      <template v-if="data.work_experience && data.work_experience.length">
        <h2 class="section-title">{{ t.workExperience }}</h2>
        <div v-for="(item, idx) in data.work_experience" :key="idx" class="work-item">
          <div class="work-header">
            <div class="work-main">
              <div class="company" v-html="formatText(item.company_name || '公司未填写')"></div>
              <div class="position" v-html="formatText(`${item.job_title || ''} ${item.job_type ? `(${item.job_type})` : ''}`)"></div>
            </div>
            <span class="work-period">{{ item.date_range?.[0] || '' }} - {{ item.date_range?.[1] || '至今' }}</span>
          </div>
          <ul v-if="item.details?.length" class="list-items">
            <li v-for="(detail, dIdx) in item.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
          </ul>
        </div>
      </template>

      <!-- {{ t.projectExperience }} -->
      <template v-if="(data.project_experience || data.projects) && (data.project_experience || data.projects).length">
        <h2 class="section-title">{{ t.projectExperience }}</h2>
        <div v-for="(item, idx) in (data.project_experience || data.projects)" :key="idx" class="project-item">
          <div class="project-header">
            <div class="project-name" v-html="formatText(item.project_name || item.name || '项目未填写')"></div>
            <div class="project-role">
              <span v-if="item.date_range?.length" v-html="formatText(`${item.role || '角色'} | ${item.date_range[0]} - ${item.date_range[1] || '至今'}`)"></span>
              <span v-else-if="item.start_date || item.end_date" v-html="formatText(`${item.role || '角色'} | ${item.start_date || ''} - ${item.end_date || '至今'}`)"></span>
              <span v-else v-html="formatText(item.role || '项目')"></span>
            </div>
          </div>
          <ul v-if="item.details?.length" class="list-items">
            <li v-for="(detail, dIdx) in item.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
          </ul>
        </div>
      </template>

      <!-- 其他 -->
      <template v-if="data.others && (data.others.skills?.length || data.others.certificates?.length || data.others.languages?.length)">
        <h2 class="section-title">其他</h2>
        <div v-if="data.others.skills?.length" class="cert-lang-line">
          <span class="cert-lang-label">{{ t.skills }}：</span>
          <template v-for="(skill, sIdx) in data.others.skills" :key="'skill-'+sIdx">
            <span v-html="formatText(skill)"></span><span v-if="sIdx < data.others.skills.length - 1" class="cert-lang-separator"> | </span>
          </template>
        </div>
        <div v-if="data.others.certificates?.length" class="cert-lang-line">
          <span class="cert-lang-label">{{ t.certificates }}：</span>
          <template v-for="(cert, cIdx) in data.others.certificates" :key="'cert-'+cIdx">
            <span v-html="formatText(cert)"></span><span v-if="cIdx < data.others.certificates.length - 1" class="cert-lang-separator"> | </span>
          </template>
        </div>
        <div v-if="data.others.languages?.length" class="cert-lang-line">
          <span class="cert-lang-label">{{ t.language }}：</span>
          <template v-for="(lang, lIdx) in data.others.languages" :key="'lang-'+lIdx">
            <span v-html="formatText(lang)"></span><span v-if="lIdx < data.others.languages.length - 1" class="cert-lang-separator"> | </span>
          </template>
        </div>
      </template>

      <!-- {{ t.selfEvaluation }} -->
      <template v-if="data.self_evaluation && data.self_evaluation.length">
        <h2 class="section-title">{{ t.selfEvaluation }}</h2>
        <template v-for="(item, idx) in data.self_evaluation">
          <div v-if="item" :key="'self-eval-'+idx" class="self-eval-item" v-html="formatText(item)"></div>
        </template>
      </template>
    </div>

    <!-- 分页预览 -->
    <div class="pages-scale-shell" :style="pagesViewportStyle">
    <div class="pages-wrapper" :style="pagesContainerStyle">
      <div v-for="page in pageCount" :key="page" class="a4-page" :style="pageStyle">
        <div class="page-inner" :style="pagePaddingStyle">
          <div class="page-content" :style="pageStyles">
            <!-- 个人信息 -->
            <div v-if="data.basics && isItemVisible({index: getItemIndex('basics', 0)}, page - 1)" class="personal-info" :class="{ 'module-highlight': highlightedModule === 'basics' }" data-module="basics">
              <div v-if="data.basics.photo" class="photo-container">
                <img :src="data.basics.photo" class="profile-photo" alt="证件照" />
              </div>
              <h1 class="name">{{ data.basics.name || '姓名未填写' }}</h1>
              <div class="contact-info">
                <span v-if="data.basics.gender" v-html="formatText(data.basics.gender)"></span>
                <span v-if="data.basics.gender || data.basics.phone" class="separator">|</span>
                <span v-if="data.basics.phone" v-html="formatText(data.basics.phone)"></span>
                <span v-if="(data.basics.gender || data.basics.phone) && data.basics.email" class="separator">|</span>
                <span v-if="data.basics.email" v-html="formatText(data.basics.email)"></span>
              </div>
              <div v-if="data.basics.target_position" class="target-position">
                {{ t.targetPosition }}：<span v-html="formatText(data.basics.target_position)"></span>
              </div>
            </div>

            <!-- {{ t.education }} -->
            <template v-if="data.education && data.education.length">
              <h2 v-if="isItemVisible({index: getItemIndex('education-title', 0)}, page - 1)" class="section-title" :class="{ 'title-highlight': highlightedModule === 'education' }" data-module="education">{{ t.education }}</h2>
              <template v-for="(item, idx) in data.education">
                <div v-if="isItemVisible({index: getItemIndex('education-item', idx)}, page - 1)" :key="'edu-'+idx" class="education-item" :class="{ 'content-highlight': highlightedModule === 'education' }">
                  <div class="education-header">
                    <div class="school-info">
                      <span class="school" v-html="formatText(item.school_name || '学校未填写')"></span>
                      <div v-if="item.school_tags?.length" class="school-tags">
                        <span v-for="(tag, tIdx) in item.school_tags" :key="tIdx" class="school-tag" v-html="formatText(tag)"></span>
                      </div>
                    </div>
                    <span class="graduation-date">{{ item.date_range?.[0] || '' }} - {{ item.date_range?.[1] || '至今' }}</span>
                  </div>
                  <div class="degree-major" v-html="formatText(`${item.degree || ''} ${item.major || ''}`)"></div>
                  <div v-if="academicMetrics(item).length" class="academic-metrics">
                    <span v-for="metric in academicMetrics(item)" :key="metric" v-html="formatText(metric)"></span>
                  </div>
                </div>
                <!-- 论文（独立分页项） -->
                <template v-if="item.theses?.length">
                  <template v-for="(thesis, tIdx) in item.theses">
                    <div v-if="isItemVisible({index: getItemIndex('thesis-item', `${idx}-${tIdx}`)}, page - 1)" :key="'thesis-'+idx+'-'+tIdx" class="thesis-item">
                      <h4 class="subfield-title">{{ t.thesis }}</h4>
                      <div class="thesis-title" v-html="formatText(thesis.title)"></div>
                      <ul v-if="thesis.details?.length" class="list-items">
                        <li v-for="(detail, dIdx) in thesis.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
                      </ul>
                    </div>
                  </template>
                </template>
              </template>
            </template>

            <!-- {{ t.workExperience }} -->
            <template v-if="data.work_experience && data.work_experience.length">
              <h2 v-if="isItemVisible({index: getItemIndex('work-title', 0)}, page - 1)" class="section-title" :class="{ 'title-highlight': highlightedModule === 'work_experience' }" data-module="work_experience">{{ t.workExperience }}</h2>
              <template v-for="(item, idx) in data.work_experience">
                <div v-if="isItemVisible({index: getItemIndex('work-item', idx)}, page - 1)" :key="'work-'+idx" class="work-item" :class="{ 'content-highlight': highlightedModule === 'work_experience' }">
                  <div class="work-header">
                    <div class="work-main">
                      <div class="company" v-html="formatText(item.company_name || '公司未填写')"></div>
                      <div class="position" v-html="formatText(`${item.job_title || ''} ${item.job_type ? `(${item.job_type})` : ''}`)"></div>
                    </div>
                    <span class="work-period">{{ item.date_range?.[0] || '' }} - {{ item.date_range?.[1] || '至今' }}</span>
                  </div>
                </div>
                <!-- 工作详情（独立分页项） -->
                <div v-if="item.details && isItemVisible({index: getItemIndex('work-details', idx)}, page - 1)" :key="'work-details-'+idx" class="work-details">
                  <ul class="list-items">
                    <li v-for="(detail, dIdx) in item.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
                  </ul>
                </div>
              </template>
            </template>

            <!-- {{ t.projectExperience }} -->
            <template v-if="(data.project_experience || data.projects) && (data.project_experience || data.projects).length">
              <h2 v-if="isItemVisible({index: getItemIndex('projects-title', 0)}, page - 1)" class="section-title" :class="{ 'title-highlight': highlightedModule === 'project_experience' }" data-module="project_experience">{{ t.projectExperience }}</h2>
              <template v-for="(item, idx) in (data.project_experience || data.projects)">
                <div v-if="isItemVisible({index: getItemIndex('project-item', idx)}, page - 1)" :key="'proj-'+idx" class="project-item" :class="{ 'content-highlight': highlightedModule === 'project_experience' }">
                  <div class="project-header">
                    <div class="project-name" v-html="formatText(item.project_name || item.name || '项目未填写')"></div>
                    <div class="project-role">
                      <span v-if="item.date_range?.length" v-html="formatText(`${item.role || '角色'} | ${item.date_range[0]} - ${item.date_range[1] || '至今'}`)"></span>
                      <span v-else-if="item.start_date || item.end_date" v-html="formatText(`${item.role || '角色'} | ${item.start_date || ''} - ${item.end_date || '至今'}`)"></span>
                      <span v-else v-html="formatText(item.role || '项目')"></span>
                    </div>
                  </div>
                </div>
                <!-- 项目详情（独立分页项） -->
                <div v-if="item.details && isItemVisible({index: getItemIndex('project-details', idx)}, page - 1)" :key="'proj-details-'+idx" class="project-details">
                  <ul class="list-items">
                    <li v-for="(detail, dIdx) in item.details" :key="dIdx" class="list-item" v-html="formatText(detail)"></li>
                  </ul>
                </div>
              </template>
            </template>

            <!-- 其他 -->
            <template v-if="data.others && (data.others.skills?.length || data.others.certificates?.length || data.others.languages?.length)">
              <h2 v-if="isItemVisible({index: getItemIndex('others-title', 0)}, page - 1)" class="section-title" :class="{ 'title-highlight': highlightedModule === 'others' }" data-module="others">其他</h2>
              <!-- 技能一行显示 -->
              <template v-if="data.others.skills?.length">
                <div v-if="isItemVisible({index: getItemIndex('skill-line', 0)}, page - 1)" class="cert-lang-line">
                  <span class="cert-lang-label">{{ t.skills }}：</span>
                  <template v-for="(skill, sIdx) in data.others.skills">
                    <span v-html="formatText(skill)"></span><span v-if="sIdx < data.others.skills.length - 1" class="cert-lang-separator"> | </span>
                  </template>
                </div>
              </template>
              <!-- 证书一行显示 -->
              <template v-if="data.others.certificates?.length">
                <div v-if="isItemVisible({index: getItemIndex('cert-line', 0)}, page - 1)" class="cert-lang-line">
                  <span class="cert-lang-label">{{ t.certificates }}：</span>
                  <template v-for="(cert, cIdx) in data.others.certificates">
                    <span v-html="formatText(cert)"></span><span v-if="cIdx < data.others.certificates.length - 1" class="cert-lang-separator"> | </span>
                  </template>
                </div>
              </template>
              <!-- 语言一行显示 -->
              <template v-if="data.others.languages?.length">
                <div v-if="isItemVisible({index: getItemIndex('lang-line', 0)}, page - 1)" class="cert-lang-line">
                  <span class="cert-lang-label">{{ t.language }}：</span>
                  <template v-for="(lang, lIdx) in data.others.languages">
                    <span v-html="formatText(lang)"></span><span v-if="lIdx < data.others.languages.length - 1" class="cert-lang-separator"> | </span>
                  </template>
                </div>
              </template>
            </template>

            <!-- {{ t.selfEvaluation }} -->
            <template v-if="data.self_evaluation && data.self_evaluation.length">
              <h2 v-if="isItemVisible({index: getItemIndex('self-eval-title', 0)}, page - 1)" class="section-title" :class="{ 'title-highlight': highlightedModule === 'self_evaluation' }" data-module="self_evaluation">{{ t.selfEvaluation }}</h2>
              <!-- 每条{{ t.selfEvaluation }}独立分页 -->
              <template v-for="(item, idx) in data.self_evaluation">
                <div v-if="item && isItemVisible({index: getItemIndex('self-eval-item', idx)}, page - 1)" :key="'self-eval-'+idx" class="self-eval-item" :class="{ 'content-highlight': highlightedModule === 'self_evaluation' }">
                  <span v-html="formatText(item)"></span>
                </div>
              </template>
            </template>
          </div>
        </div>
        <div class="page-footer">{{ page }} / {{ pageCount }}</div>
      </div>
    </div>
    </div>
    <div v-if="pageCount > 1" class="page-indicator">共 {{ pageCount }} 页</div>
    </div>
    </template>

    <!-- 无简历数据时显示提示 -->
    <div v-if="!data" class="no-data">
      <p>暂无简历数据，请先编辑简历</p>
      <button class="jd-upload-btn" @click="emit('open-resume-edit')" title="编辑简历">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
        </svg>
        <span>编辑简历</span>
      </button>
    </div>
  </div>

  <!-- 成功提示弹窗 -->
  <div v-if="showSuccessDialog" class="success-dialog-overlay" @click.self="showSuccessDialog = false">
    <div class="success-dialog">
      <div class="success-icon">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h3>简历导出成功</h3>
      <p>{{ lastExportFormat }} 文件已成功下载。<br><br>{{ lastExportFormat === 'Word' ? 'DOCX 中的文字、段落和列表均可在 Word 或 WPS 中继续编辑。' : '网页预览与实际 PDF 文件在排版上可能有细微差异；可调整样式参数后重新导出。' }}</p>
      <button class="confirm-btn" @click="showSuccessDialog = false">我知道了</button>
    </div>
  </div>

  <div v-if="exportError" class="success-dialog-overlay" @click.self="exportError = ''">
    <div class="success-dialog error-dialog">
      <div class="success-icon error-icon">!</div>
      <h3>导出未完成</h3>
      <p>{{ exportError }}</p>
      <button class="confirm-btn" @click="exportError = ''">关闭</button>
    </div>
  </div>
</template>

<style scoped>
.resume-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
}
/* 工具栏包装器 - 为sticky提供正确的定位上下文 */
.resume-toolbar-wrapper {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(31, 32, 37, 0.97);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  flex-shrink: 0;
}
.resume-toolbar {
  height: 60px;
  min-height: 60px;
  box-sizing: border-box;
  background: transparent;
  padding: 0.55rem 0.65rem;
  box-shadow: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.4rem;
  flex-shrink: 0;
  flex-wrap: nowrap;
  overflow: visible;
}
.toolbar-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #303030;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
}
.reset-style-btn {
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  font-size: 17px;
  cursor: pointer;
  transition: background .15s, transform .15s;
}
.reset-style-btn:hover {
  background: #eee7df;
  transform: rotate(-12deg);
}
.reset-style-btn:focus,
.reset-style-btn:focus-visible,
.reset-style-btn:active {
  border: 0;
  outline: none;
  box-shadow: none;
}
.zoom-controls {
  display: flex;
  align-items: center;
  height: 30px;
  border: 1px solid #303030;
  flex-shrink: 0;
}
.zoom-controls button {
  height: 100%;
  min-width: 30px;
  padding: 0 .3rem;
  border: 0;
  border-right: 1px solid #303030;
  background: transparent;
  color: #303030;
  font-size: .625rem;
  cursor: pointer;
}
.zoom-controls button:hover:not(:disabled),
.zoom-controls button.active {
  background: #303030;
  color: #78a6ff;
}
.zoom-controls button:disabled {
  opacity: .35;
  cursor: default;
}
.zoom-controls button:focus,
.zoom-controls button:focus-visible {
  outline: none;
  box-shadow: none;
}
.zoom-value {
  min-width: 38px;
  padding: 0 .2rem;
  color: #303030;
  font-size: .625rem;
  line-height: 28px;
  text-align: center;
}
.zoom-readout {
  display: flex;
  height: 100%;
}
.zoom-stepper {
  display: flex;
  width: 15px;
  flex-direction: column;
  border-left: 1px solid #303030;
}
.zoom-stepper button {
  min-width: 0;
  width: 15px;
  height: 50%;
  padding: 0;
  border: 0;
  font-size: .55rem;
  line-height: 1;
}
.zoom-stepper button:first-child {
  border-bottom: 1px solid #303030;
}
.toolbar-controls-container {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  flex-shrink: 0;
}
.toolbar-section {
  display: flex;
  align-items: center;
  gap: 0;
  position: relative;
  flex-shrink: 0;
  z-index: 1;
}
.toolbar-section:last-child {
  margin-left: auto;
  flex-shrink: 0;
}
.toolbar-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.3rem;
}
.toolbar-title {
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.625rem;
  font-weight: 400;
  margin: 0;
  color: #303030;
  white-space: nowrap;
  cursor: pointer;
  padding: 0.35rem 0.45rem;
  border-radius: 0;
  background: transparent;
  border: 1px solid #303030;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  transition: all 0.2s ease;
}
.toolbar-title:hover {
  background: #303030;
  color: #78a6ff;
}
.toolbar-controls {
  visibility: hidden;
  opacity: 0;
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  background-color: #f9f5f0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='3.0' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
  background-blend-mode: overlay;
  border: 1px solid #303030;
  border-radius: 0;
  padding: 1rem;
  box-shadow: 4px 4px 0 #303030;
  gap: 0.8rem;
  flex-direction: column;
  z-index: 10000;
  min-width: 220px;
  white-space: nowrap;
  transition: visibility 0s linear 0.15s, opacity 0.15s ease;
}
.toolbar-section:hover > .toolbar-controls,
.toolbar-section:hover > .toolbar-title,
.toolbar-controls:hover {
  visibility: visible;
  opacity: 1;
  transition: visibility 0s linear 0s, opacity 0.15s ease;
}
.control-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  justify-content: space-between;
}
.control-label {
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  color: #303030;
  font-weight: 400;
  white-space: nowrap;
  width: 90px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.slider {
  -webkit-appearance: none;
  width: 120px;
  height: 4px;
  border-radius: 0;
  background: #e0e0e0;
  outline: none;
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 0;
  background: #303030;
  cursor: pointer;
  border: none;
  box-shadow: none;
}
.slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 0;
  background: #303030;
  cursor: pointer;
  border: none;
  box-shadow: none;
}
.export-btn {
  background: #5f8ff2;
  color: #303030;
  border: 1px solid #303030;
  padding: 0.38rem 0.55rem;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.625rem;
  font-weight: 400;
  border-radius: 0;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 0.2rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  box-shadow: 2px 2px 0 #303030;
}
.export-btn:hover {
  background: #303030;
  color: #78a6ff;
  box-shadow: none;
  transform: translate(2px, 2px);
}
.export-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}
/* 语言切换 */
.lang-toggle {
  display: flex;
  border: 1px solid #303030;
}
.lang-toggle span {
  padding: 0.35rem 0.4rem;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.625rem;
  cursor: pointer;
  transition: all 0.2s ease;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.lang-toggle span:first-child {
  border-right: 1px solid #303030;
}
.lang-toggle span.active {
  background: #303030;
  color: #78a6ff;
}
.lang-toggle span:not(.active):hover {
  background: #f0f0f0;
}
/* JD上传按钮 */
.jd-upload-btn {
  background: transparent;
  color: #303030;
  border: 1px solid #303030;
  padding: 0.35rem 0.5rem;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.625rem;
  font-weight: 400;
  border-radius: 0;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 0.2rem;
  position: relative;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.jd-upload-btn:hover {
  background: rgba(95, 143, 242, 0.16);
  border-color: #303030;
}
/* 桌面端 Apple 风格合并工具栏 */
.compact-toolbar-group {
  position: relative;
  flex: 0 0 auto;
}

.compact-toolbar-cluster {
  display: flex;
  align-items: center;
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: 0;
}

.compact-toolbar-cluster .compact-toolbar-btn {
  border-color: transparent;
  background: transparent;
  box-shadow: none;
}

.compact-toolbar-cluster .compact-toolbar-group + .compact-toolbar-group,
.compact-toolbar-cluster > .compact-toolbar-btn,
.compact-toolbar-cluster > .compact-toolbar-group + .compact-toolbar-btn,
.compact-toolbar-cluster > .compact-toolbar-btn + .compact-toolbar-group {
  border-left: 1px solid rgba(255, 255, 255, 0.065);
  border-top-left-radius: 0;
  border-bottom-left-radius: 0;
}

.compact-toolbar-btn {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.32rem;
  padding: 0.35rem 0.55rem;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 9px;
  color: #c9c9cf;
  background: rgba(255, 255, 255, 0.055);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
  cursor: pointer;
  white-space: nowrap;
  font-size: 0.68rem;
  font-weight: 500;
  transition: background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
}

.compact-toolbar-btn svg,
.compact-export-btn svg,
.compact-menu-item svg {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
}

.compact-toolbar-btn:hover,
.compact-toolbar-btn.active {
  color: #f5f5f7;
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.1);
}

.compact-toolbar-cluster .compact-toolbar-btn.active {
  border-color: transparent;
}

.compact-toolbar-btn:focus,
.compact-export-btn:focus,
.compact-menu-item:focus,
.compact-reset-btn:focus,
.compact-toolbar-btn:focus-visible,
.compact-export-btn:focus-visible,
.compact-menu-item:focus-visible,
.compact-reset-btn:focus-visible {
  outline: none;
  box-shadow: none;
}

.compact-popover {
  position: absolute;
  top: calc(100% + 9px);
  right: 0;
  z-index: 10020;
  min-width: 220px;
  padding: 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  color: #f5f5f7;
  background: rgba(35, 36, 42, 0.98);
  box-shadow: 0 20px 55px rgba(0, 0, 0, 0.48);
  backdrop-filter: blur(26px);
  -webkit-backdrop-filter: blur(26px);
}

.layout-popover {
  width: 255px;
}

.edit-popover {
  width: 240px;
}

.compact-popover-title {
  margin-bottom: 0.65rem;
  color: #f0f0f3;
  font-size: 0.72rem;
  font-weight: 500;
}

.zoom-mode-grid,
.compact-zoom-stepper {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.4rem;
}

.compact-zoom-stepper {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 0.45rem;
}

.zoom-mode-grid button,
.compact-zoom-stepper button,
.compact-reset-btn {
  min-height: 32px;
  padding: 0.3rem 0.45rem;
  border: 0;
  border-radius: 9px;
  color: #c7c7ce;
  background: rgba(255, 255, 255, 0.06);
  font-size: 0.68rem;
}

.zoom-mode-grid button:hover,
.zoom-mode-grid button.active,
.compact-zoom-stepper button:hover:not(:disabled),
.compact-reset-btn:hover {
  color: #f5f5f7;
  background: rgba(255, 255, 255, 0.11);
}

.compact-zoom-stepper button:disabled {
  opacity: 0.35;
  cursor: default;
}

.compact-control {
  display: grid;
  gap: 0.35rem;
  margin-top: 0.65rem;
}

.compact-control > span {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  color: #bdbdc5;
  font-size: 0.68rem;
}

.compact-control strong {
  color: #85858f;
  font-weight: 400;
}

.compact-control .slider {
  width: 100%;
  height: 3px;
  border-radius: 999px;
  background: #3b3c42;
}

.compact-control .slider::-webkit-slider-thumb {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: #e7eaf1;
}

.compact-control .slider::-moz-range-thumb {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: #e7eaf1;
}

.compact-reset-btn {
  width: 100%;
  margin-top: 0.8rem;
}

.compact-menu-item {
  width: 100%;
  min-height: 46px;
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.5rem 0.55rem;
  border: 0;
  border-radius: 9px;
  color: #d7d7dc;
  background: transparent;
  text-align: left;
}

.compact-menu-item:hover {
  color: #f5f5f7;
  background: rgba(255, 255, 255, 0.075);
}

.compact-menu-item > span {
  display: grid;
  gap: 0.12rem;
}

.compact-menu-item strong {
  font-size: 0.69rem;
  font-weight: 500;
}

.compact-menu-item small {
  color: #85858f;
  font-size: 0.62rem;
}

.language-btn {
  flex: 0 0 auto;
}

.compact-export-btn {
  min-height: 32px;
  padding: 0.35rem 0.7rem;
  border: 1px solid rgba(255, 255, 255, 0.7);
  border-radius: 9px;
  color: #0b0b0d;
  background: #f0f0f2;
  box-shadow: 0 5px 16px rgba(0, 0, 0, 0.2);
  font-size: 0.68rem;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
}

.compact-export-btn:hover {
  color: #0b0b0d;
  background: #ffffff;
  box-shadow: 0 7px 20px rgba(0, 0, 0, 0.28);
  transform: translateY(-1px);
}

.compact-export-btn:disabled {
  color: #0b0b0d;
  background: #a8a8ad;
  border-color: transparent;
  transform: none;
}
/* Spinner 转圈圈 */
.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(48, 48, 48, 0.3);
  border-radius: 0;
  border-top-color: #303030;
  animation: spin 0.8s linear infinite;
  margin-right: 6px;
  vertical-align: middle;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
/* 预览内容区域 - 处理滚动 */
.preview-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px;
  background:
    radial-gradient(circle at 50% 5%, rgba(91, 105, 145, 0.16), transparent 34%),
    #202126;
  width: 100%;
  box-sizing: border-box;
  overflow-y: auto;
  overflow-x: hidden;
  flex: 1;
  min-height: 0;
}
.content-source {
  /* 使用 opacity: 0 而非 visibility: hidden，确保可以准确测量高度 */
  position: fixed;
  left: 0;
  top: 0;
  opacity: 0;
  width: 794px;
  box-sizing: border-box;
  background: white;
  pointer-events: none;
}
.pages-wrapper {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.pages-scale-shell {
  position: relative;
  flex: 0 0 auto;
  align-self: center;
}

/* 打印容器默认隐藏，只在打印时显示 */
.print-container {
  display: none;
}
.a4-page {
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  position: relative;
  box-sizing: border-box;
  flex-shrink: 0;
}
.a4-page::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  border: 1px solid #e0e0e0;
  pointer-events: none;
  z-index: 1;
}
.page-inner {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
}
.page-content {
  width: 100%;
  box-sizing: border-box;
  word-wrap: break-word;
  overflow-wrap: break-word;
}
.personal-info {
  text-align: center;
  position: relative;
  min-height: 110px;
}

.personal-info .name {
  font-size: 1.5em;
  font-weight: 700;
  margin: 0 0 0.25em 0;
  color: #212529;
}

.contact-info {
  display: flex;
  justify-content: center;
  gap: 0.5em;
  flex-wrap: wrap;
  font-size: 0.8em;
  color: #6c757d;
}

.photo-container {
  position: absolute;
  top: 0;
  right: 0;
}

.profile-photo {
  width: 80px;
  height: 100px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
}

.target-position {
  font-size: 0.8em;
  color: #212529;
  font-weight: 600;
  margin-top: 0.25em;
}

.section-title {
  font-size: 1.1em;
  font-weight: 600;
  margin: 0 0 var(--module-margin, 0.5em) 0;
  color: #212529;
  padding-bottom: 0.25em;
  border-bottom: 2px solid #333;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.education-item,
.work-item,
.project-item {
  margin-bottom: var(--module-margin, 0.5em);
}
.education-header,
.work-header,
.project-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.5em;
}
.school,
.company,
.project-name {
  font-size: 1em;
  font-weight: 600;
  color: #212529;
}
.school-info {
  display: flex;
  align-items: baseline;
  gap: 0.5em;
  flex-wrap: wrap;
}
.school-tags {
  display: inline-flex;
  gap: 0.375em;
  flex-wrap: nowrap;
  white-space: nowrap;
}
.school-tag {
  display: inline-block;
  padding: 0.125em 0.5em;
  background: #333;
  color: white;
  font-size: 0.75em;
  border-radius: 4px;
  font-weight: 500;
}
.graduation-date,
.work-period {
  font-size: 0.8em;
  color: #95a5a6;
  white-space: nowrap;
  font-weight: 500;
}
.degree-major,
.position,
.project-role {
  font-size: 0.8em;
  color: #6c757d;
  font-weight: 500;
}
.academic-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25em 1em;
  margin-top: 0.125em;
  font-size: 0.8em;
  color: #6c757d;
  font-weight: 500;
}
.list-items {
  list-style: none;
  padding: 0;
  margin: 0;
}
.list-item {
  position: relative;
  padding-left: 1.25em;
  margin-bottom: 0.25em;
  font-size: 0.8em;
  line-height: var(--line-height, 1.6);
}
.list-item::before {
  content: '•';
  position: absolute;
  left: 0;
  color: #333;
  font-weight: bold;
}
.self-eval-item {
  font-size: 0.8em;
  line-height: var(--line-height, 1.6);
  color: #212529;
}
.others-title {
  font-size: 0.9em;
  font-weight: 600;
  color: #212529;
  margin: 0 0 0.25em 0;
}
.skill-section,
.cert-section,
.lang-section {
  margin-bottom: var(--module-margin, 0.5em);
}
.skill-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5em;
}
.skill-item,
.cert-lang-line,
.inline-item {
  font-size: 0.8em;
  color: #212529;
  word-wrap: break-word;
  overflow-wrap: break-word;
  max-width: 100%;
}
.cert-lang-label {
  font-weight: 600;
  margin-right: 0.25em;
}
.cert-lang-separator {
  color: #333;
  margin: 0 0.25em;
}
.skills-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5em;
}
.thesis-item {
  margin-top: 0.25em;
}
.thesis-title {
  font-weight: 600;
  font-size: 0.85em;
}
.subfield-title {
  font-size: 0.825em;
  font-weight: 600;
  color: #6c757d;
  margin-bottom: 0.25em;
  display: block;
}
.inline-list {
  display: inline;
}
.inline-item:not(:last-child)::after {
  content: '·';
  color: #333;
  font-weight: bold;
  margin-left: 0.5em;
  margin-right: 0.5em;
}
:deep(b) {
  font-weight: 600;
}
.page-footer {
  position: absolute;
  bottom: 15px;
  right: 20px;
  font-size: 10pt;
  color: #6c757d;
}
/* PC端页面指示器 - 保持原来的定位方式 */
@media (min-width: 1200px) {
  .page-indicator {
    position: absolute;
    right: 20px;
    bottom: 30px;
    color: #6c757d;
    font-size: 12px;
  }
}
.no-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  color: #6c757d;
  font-size: 1.1rem;
  gap: 1rem;
}

.no-data .jd-upload-btn {
  margin-top: 0.5rem;
}

/* 成功提示弹窗 */
.success-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.3s ease;
}

.success-dialog {
  background: white;
  border-radius: var(--radius-lg);
  padding: 32px;
  max-width: 420px;
  width: 90%;
  text-align: center;
  box-shadow: var(--shadow-lg);
  animation: slideUp 0.3s ease;
}

.success-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 20px;
  background: #f0f9f0;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.success-icon svg {
  width: 32px;
  height: 32px;
  color: #22c55e;
}

.success-icon.error-icon {
  color: #b64d52;
  font-size: 28px;
  font-weight: 600;
  background: #fff0f0;
}

.success-dialog h3 {
  margin: 0 0 16px;
  font-size: 1.25rem;
  font-weight: 600;
  color: #212529;
}

.success-dialog p {
  margin: 0 0 24px;
  font-size: 0.95rem;
  color: #6c757d;
  line-height: 1.6;
}

.success-dialog .confirm-btn {
  background: #212529;
  color: white;
  border: none;
  padding: 12px 32px;
  border-radius: var(--radius-md);
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.success-dialog .confirm-btn:hover {
  background: #495057;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ========== 模块高亮动画 - AI风格蓝紫色炫光 ========== */

/* 模块高亮边框脉冲动画 */
.module-highlight {
  position: relative;
  animation: borderPulse 2s ease-in-out infinite;
}

@keyframes borderPulse {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(6, 182, 212, 0);
  }
  25% {
    box-shadow: 0 0 0 2px rgba(6, 182, 212, 0.3), 0 0 10px rgba(139, 92, 246, 0.2);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(6, 182, 212, 0.2), 0 0 20px rgba(139, 92, 246, 0.3);
  }
  75% {
    box-shadow: 0 0 0 2px rgba(6, 182, 212, 0.3), 0 0 10px rgba(139, 92, 246, 0.2);
  }
}

/* 标题文字炫光动画 */
.title-highlight {
  position: relative;
  background: linear-gradient(
    90deg,
    #212529 0%,
    #06b6d4 25%,
    #8b5cf6 50%,
    #06b6d4 75%,
    #212529 100%
  );
  background-size: 200% 100%;
  background-clip: text;
  -webkit-background-clip: text;
  color: transparent;
  animation: titleShimmer 2.5s ease-in-out infinite;
  display: inline-block;
}

@keyframes titleShimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}
</style>

<!-- 全局样式 - 用于动态添加的高亮类 -->
<style>
/* ========== 模块高亮动画 - 全局样式（用于动态添加的类） ========== */

/* 模块高亮边框脉冲动画 */
:global(.module-highlight) {
  position: relative;
  animation: borderPulseGlobal 2s ease-in-out infinite;
}

@keyframes borderPulseGlobal {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(6, 182, 212, 0);
  }
  25% {
    box-shadow: 0 0 0 2px rgba(6, 182, 212, 0.3), 0 0 10px rgba(139, 92, 246, 0.2);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(6, 182, 212, 0.2), 0 0 20px rgba(139, 92, 246, 0.3);
  }
  75% {
    box-shadow: 0 0 0 2px rgba(6, 182, 212, 0.3), 0 0 10px rgba(139, 92, 246, 0.2);
  }
}

/* 标题文字炫光动画 - 使用 :global() 配合父选择器提高优先级 */
:global(.resume-wrapper .title-highlight),
:global(.preview-content .title-highlight),
:global(.pages-wrapper .title-highlight) {
  background: linear-gradient(
    90deg,
    #212529 0%,
    #06b6d4 25%,
    #8b5cf6 50%,
    #06b6d4 75%,
    #212529 100%
  ) !important;
  background-size: 200% 100% !important;
  -webkit-background-clip: text !important;
  background-clip: text !important;
  color: transparent !important;
  animation: titleShimmerGlobal 2.5s ease-in-out infinite;
  display: inline-block !important;
  background-repeat: repeat-y !important;
}

@keyframes titleShimmerGlobal {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}

/* 内容项动画 - 淡入闪烁效果 */
:global(.resume-wrapper .content-highlight),
:global(.preview-content .content-highlight),
:global(.pages-wrapper .content-highlight) {
  animation: contentPulseGlobal 2s ease-in-out infinite;
  border-radius: 4px;
}

@keyframes contentPulseGlobal {
  0%, 100% {
    background-color: transparent;
  }
  25% {
    background-color: rgba(6, 182, 212, 0.1);
  }
  50% {
    background-color: rgba(139, 92, 246, 0.15);
  }
  75% {
    background-color: rgba(6, 182, 212, 0.1);
  }
}

/* ==================== 移动端适配（0-1200px统一使用移动端样式） ==================== */
@media (max-width: 1200px) {
  .resume-wrapper {
    height: 100%;
    display: flex;
    flex-direction: column;
  }

  /* 移动端工具栏固定在底部 Tab 栏上方 */
  .resume-toolbar-wrapper {
    position: fixed;
    bottom: 60px;
    top: auto;
    left: 0;
    right: 0;
    z-index: 999;
    background-color: rgb(249, 245, 242);
    border-top: 1px solid #e0e0e0;
    border-bottom: none;
    box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.05);
  }

  /* 当样式面板展开时，工具栏高度增加 */
  .resume-toolbar-wrapper:has(.style-panel-mobile) {
    bottom: 60px;
  }

  .resume-toolbar {
    flex-wrap: wrap;
    padding: 6px 8px;
    gap: 6px;
    border-bottom: none;
  }

  /* 移动端隐藏 toolbar-icon */
  .toolbar-icon {
    display: none !important;
  }

  .toolbar-controls-container {
    gap: 6px;
    flex-wrap: wrap;
    justify-content: center;
  }

  .toolbar-title {
    padding: 5px 8px;
    font-size: 10px;
  }

  .toolbar-actions {
    gap: 6px;
  }

  .jd-upload-btn {
    padding: 6px 12px;
    font-size: 11px;
  }

  .export-btn {
    padding: 6px 12px;
    font-size: 11px;
  }

  /* 预览内容区域适配 */
  .preview-content {
    padding: 8px;
    flex: 1;
    overflow-y: auto;
    height: calc(100% - 60px);
    box-sizing: border-box;
  }

  /* 移动端页面指示器 */
  .page-indicator {
    position: fixed;
    bottom: 80px;
    right: 12px;
    background: rgba(255, 255, 255, 0.95);
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 10px;
    line-height: 1;
    z-index: 1001;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
    white-space: nowrap;
  }

  /* 移动端样式面板 */
  .style-panel-mobile {
    width: 100%;
    background: rgb(254, 253, 251);
    padding: 12px;
    border-top: 1px solid #e0e0e0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .style-control-row {
    display: flex;
    gap: 12px;
  }

  .style-control-row.single {
    justify-content: center;
  }

  .style-control-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .style-label {
    font-family: 'GTPressuraMono-Light', sans-serif;
    font-size: 0.625rem;
    color: #666;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .style-panel-mobile .slider {
    width: 100%;
    height: 4px;
    -webkit-appearance: none;
    appearance: none;
    background: #e0e0e0;
    outline: none;
    border-radius: 2px;
  }

  .style-panel-mobile .slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    background: #303030;
    cursor: pointer;
    border-radius: 0;
  }

  .style-panel-mobile .slider::-moz-range-thumb {
    width: 14px;
    height: 14px;
    background: #303030;
    cursor: pointer;
    border-radius: 0;
    border: none;
  }

  /* 移动端工具栏第一行 - 始终显示的按钮 */
  .mobile-toolbar-row {
    display: flex;
    gap: 6px;
    width: 100%;
    padding: 8px 12px;
  }

  /* 移动端样式调整按钮 */
  .mobile-style-btn {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 8px 6px;
    background: transparent;
    border: 1px solid #303030;
    border-radius: 0;
    color: #303030;
    font-family: 'GTPressuraMono-Light', sans-serif;
    font-size: 0.625rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 2px 2px 0 #303030;
    white-space: nowrap;
  }

  .mobile-style-btn:active {
    transform: translate(2px, 2px);
    box-shadow: none;
  }

  .mobile-style-btn.active {
    background: #5f8ff2;
  }

  /* 移动端JD按钮 - 跟PC端样式一致 */
  .mobile-jd-btn {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 8px 6px;
    background: transparent;
    color: #303030;
    border: 1px solid #303030;
    border-radius: 0;
    font-family: 'GTPressuraMono-Light', sans-serif;
    font-size: 0.625rem;
    font-weight: 400;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 2px 2px 0 #303030;
    white-space: nowrap;
  }

  .mobile-jd-btn:hover {
    background: rgba(95, 143, 242, 0.16);
    border-color: #303030;
  }

  .mobile-jd-btn:active {
    transform: translate(2px, 2px);
    box-shadow: none;
  }

  /* 移动端导出按钮 */
  .mobile-export-btn {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 8px 6px;
    background: #5f8ff2;
    color: #303030;
    border: 1px solid #303030;
    border-radius: 0;
    font-family: 'GTPressuraMono-Light', sans-serif;
    font-size: 0.625rem;
    font-weight: 400;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 2px 2px 0 #303030;
    white-space: nowrap;
  }

  .mobile-export-btn:hover:not(:disabled) {
    background: #303030;
    color: #78a6ff;
  }

  .mobile-export-btn:active:not(:disabled) {
    transform: translate(2px, 2px);
    box-shadow: none;
  }

  .mobile-export-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .mobile-jd-btn .spinner,
  .mobile-export-btn .spinner {
    width: 12px;
    height: 12px;
    border: 2px solid rgba(48, 48, 48, 0.3);
    border-top-color: #303030;
    border-radius: 0;
    animation: spin 0.8s linear infinite;
  }

  /* 展开收起动画 */
  .slide-down-enter-active,
  .slide-down-leave-active {
    transition: all 0.3s ease;
    overflow: hidden;
  }

  .slide-down-enter-from,
  .slide-down-leave-to {
    opacity: 0;
    max-height: 0;
    padding-top: 0;
    padding-bottom: 0;
  }

  .slide-down-enter-to,
  .slide-down-leave-from {
    opacity: 1;
    max-height: 300px;
  }
}
</style>
