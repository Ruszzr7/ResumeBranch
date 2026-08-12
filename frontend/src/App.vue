<script setup>
import { ref, onMounted, watch, nextTick, computed, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ChatMessage from './components/ChatMessage.vue'
import ResumePreview from './components/ResumePreview.vue'
import RichTextEditor from './components/RichTextEditor.vue'
import MobileTabBar from './components/MobileTabBar.vue'
import BrandLogo from './components/BrandLogo.vue'
import { labels } from './utils/labels.js'
import { buildAuthorizationHeaders, loadAppConfig } from './config/appMode.js'
import { normalizeLayoutConfig, resolveContentBlockFlow, resolveLayoutTokens } from './utils/layoutConfig.js'
import { hasMeaningfulResumeContent } from './utils/resumePresence.js'
import { formatInlineHtml, plainInlineText } from './utils/inlineFormatting.js'

// 响应式布局状态
const isMobileView = ref(false)
const currentTab = ref('chat')
let resizeObserver = null

// 语言状态
const currentLang = ref('zh')
const showTranslateConfirm = ref(false)
const translationSourceData = ref(null)
const translationResultData = ref(null)
const translationApplied = ref(false)
const isTranslating = ref(false)
const TRANSLATION_SESSION_PREFIX = 'resumeTranslationSession:'
const TRANSLATION_CACHE_PREFIX = 'resumeTranslationCache:'
const WELCOME_MESSAGE = '你好！我是你的简历助手。你可以让我检查简历中的不足、进行深度打磨、结合 JD 分析匹配度，也可以直接修改简历内容和排版。告诉我你的目标岗位或具体需求，或者从下方选择一项开始。如原简历含头像，建议在“编辑简历”中自行上传清晰原图，避免自动裁剪造成模糊。'
const conversationMessagesForSave = () => messages.value.filter(message => !message.localOnly)
const assistantActions = [
  {
    label: '修改简历',
    prefillOnly: true,
    prompt: '请修改【模块或字段】：将【原内容】调整为【目标内容或具体要求】。'
  },
  {
    label: '排版建议',
    prompt: '请分析当前简历排版是否清晰、紧凑、重点突出，并给出可执行的排版建议。请说明建议涉及字号、间距、模块样式还是模块顺序；本轮只分析，不修改简历。'
  },
  {
    label: '全面诊断',
    mode: 'diagnosis',
    action: 'start',
    prompt: '请先对当前简历做一次全面诊断：指出最影响通过率的不足，按优先级给出具体改进建议；先不要修改简历，诊断后只追问我一个最关键的问题。'
  },
  {
    label: '深度打磨',
    mode: 'coaching',
    action: 'start',
    prompt: '请以严格面试官视角深度打磨我的简历：从最薄弱、最影响求职结果的一项经历开始，每次只问一个问题，持续追问到能形成真实、具体、可量化的简历表述；先不要修改简历。'
  },
  {
    label: '对照 JD',
    mode: 'jd_review',
    action: 'start',
    prompt: '请结合当前目标岗位 JD 分析简历匹配度：区分已经证明的匹配项、简历尚未证明的能力和确实缺失的条件，按优先级给建议；先不要修改简历，最后只问我一个最关键的问题。'
  }
]

// 检测是否为移动端视图
function checkMobileView() {
  isMobileView.value = window.innerWidth < 1200
}

// Tooltip 状态管理
const tooltipState = ref({ visible: false, text: '', x: 0, bottom: 0 })

function showTooltip(event, text) {
  const button = event.currentTarget
  const rect = button.getBoundingClientRect()
  const viewportHeight = window.innerHeight
  
  // 计算 tooltip 应该显示在按钮上方
  // 使用 bottom 属性：从视口底部向上计算
  tooltipState.value = {
    visible: true,
    text: text,
    x: rect.left + rect.width / 2,
    bottom: viewportHeight - rect.top
  }
}

function hideTooltip() {
  tooltipState.value.visible = false
}

function cloneResumeData(data) {
  return data ? JSON.parse(JSON.stringify(data)) : null
}

function translationSessionKey(taskId = currentTaskId.value) {
  return taskId ? `${TRANSLATION_SESSION_PREFIX}${taskId}` : ''
}

function translationCacheKey(taskId = currentTaskId.value) {
  return taskId ? `${TRANSLATION_CACHE_PREFIX}${taskId}` : ''
}

function resumeDataWithoutPhoto(data) {
  const snapshot = cloneResumeData(data)
  if (snapshot?.basics) delete snapshot.basics.photo
  return snapshot
}

function sameResumeSnapshot(left, right) {
  return JSON.stringify(resumeDataWithoutPhoto(left)) === JSON.stringify(resumeDataWithoutPhoto(right))
}

function persistTranslationSession() {
  const key = translationSessionKey()
  if (!key || !translationSourceData.value) return
  localStorage.setItem(key, JSON.stringify({
    source_data: resumeDataWithoutPhoto(translationSourceData.value),
    translated_data: resumeDataWithoutPhoto(translationResultData.value),
    language: currentLang.value,
    applied: translationApplied.value
  }))
}

function persistTranslationCache() {
  const key = translationCacheKey()
  if (!key || !translationSourceData.value || !translationResultData.value) return
  localStorage.setItem(key, JSON.stringify({
    source_data: resumeDataWithoutPhoto(translationSourceData.value),
    translated_data: resumeDataWithoutPhoto(translationResultData.value)
  }))
}

function loadCachedTranslation(sourceData) {
  const key = translationCacheKey()
  if (!key) return null
  try {
    const saved = JSON.parse(localStorage.getItem(key) || 'null')
    if (!saved?.source_data || !saved?.translated_data) return null
    return sameResumeSnapshot(saved.source_data, sourceData) ? saved.translated_data : null
  } catch (error) {
    console.warn('读取简历翻译缓存失败:', error)
    localStorage.removeItem(key)
    return null
  }
}

function clearTranslationSession() {
  const key = translationSessionKey()
  if (key) localStorage.removeItem(key)
  translationSourceData.value = null
  translationResultData.value = null
  translationApplied.value = false
}

function restoreTranslationSession() {
  const key = translationSessionKey()
  if (!key) return
  try {
    const saved = JSON.parse(localStorage.getItem(key) || 'null')
    if (!saved?.source_data || saved.language !== 'en') return
    translationSourceData.value = saved.source_data
    translationResultData.value = saved.translated_data || null
    translationApplied.value = Boolean(saved.applied)
    currentLang.value = 'en'
  } catch (error) {
    console.warn('恢复语言切换状态失败:', error)
    localStorage.removeItem(key)
  }
}

async function restoreChineseResume() {
  const sourceData = cloneResumeData(translationSourceData.value)
  showTranslateConfirm.value = false

  if (translationApplied.value && sourceData) {
    try {
      let response = await fetch('/restore_resume_translation', {
        method: 'POST',
        headers: getAuthHeaders()
      })
      let payload = await response.json().catch(() => ({}))
      let restoredData = payload.resume_data
      // 兼容功能升级前仅保存在浏览器中的翻译会话。
      if (!response.ok && sourceData) {
        response = await fetch('/save_resume', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ resume_data: sourceData })
        })
        restoredData = sourceData
      }
      if (!response.ok || !restoredData) throw new Error(payload.detail || '中文简历恢复失败')
      const currentPhoto = resumeData.value?.basics?.photo
      if (currentPhoto && restoredData.basics) restoredData.basics.photo = currentPhoto
      resumeData.value = restoredData
      currentLang.value = 'zh'
      previewResumeData.value = null
      previewLayoutConfig.value = null
      const undoIndex = [...messages.value].reverse().findIndex(
        message => message.type === 'undo' && !message.handled
      )
      if (undoIndex !== -1) {
        const actualIndex = messages.value.length - 1 - undoIndex
        messages.value[actualIndex] = {
          ...messages.value[actualIndex],
          handled: true,
          content: '已切回中文版本。'
        }
      }
    } catch (error) {
      persistTranslationSession()
      showNotice(error.message || '切换中文失败，请重试')
      return
    }
  }

  clearTranslationSession()
}

// 语言切换函数：进入英文先确认；英文返回中文时直接恢复中文基线。
async function switchLang(lang) {
  if (isTranslating.value) return
  if (lang === 'en') {
    if (currentLang.value === 'en') return
    showTranslateConfirm.value = true
    return
  }
  if (lang === 'zh' && currentLang.value === 'en') {
    await restoreChineseResume()
  }
}

// 确认翻译：专用接口直接返回结构化简历，不再进入普通聊天意图识别。
async function confirmTranslate() {
  if (isTranslating.value) return
  showTranslateConfirm.value = false
  const sourceData = cloneResumeData(resumeData.value)
  translationSourceData.value = sourceData
  translationResultData.value = null
  translationApplied.value = false
  isTranslating.value = true
  showNotice('正在生成英文简历，请稍候…')

  try {
    let translatedData = loadCachedTranslation(sourceData)
    let cacheHits = 0
    let reusedFullResult = Boolean(translatedData)

    if (translatedData) {
      const response = await fetch('/save_resume', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ resume_data: translatedData })
      })
      if (!response.ok) throw new Error('保存英文简历失败')
    } else {
      const response = await fetch('/translate_resume', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ source_language: 'zh', target_language: 'en' })
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || payload.error || '简历翻译失败，请重试')
      translatedData = payload.resume_data
      cacheHits = Number(payload.cache_hits || 0)
      reusedFullResult = Boolean(payload.full_snapshot_reused)
    }

    const currentPhoto = sourceData?.basics?.photo
    if (currentPhoto && translatedData?.basics) translatedData.basics.photo = currentPhoto
    translationResultData.value = cloneResumeData(translatedData)
    resumeData.value = cloneResumeData(translatedData)
    previewResumeData.value = null
    previewLayoutConfig.value = null
    translationApplied.value = true
    currentLang.value = 'en'
    persistTranslationSession()
    persistTranslationCache()
    const reuseHint = reusedFullResult
      ? '，已复用上次的完整翻译'
      : (cacheHits > 0 ? `，已复用 ${cacheHits} 项未变化内容` : '')
    showNotice(`英文简历已生成${reuseHint}`)
  } catch (error) {
    console.error('简历翻译失败:', error)
    currentLang.value = 'zh'
    translationSourceData.value = null
    translationResultData.value = null
    translationApplied.value = false
    showNotice(error?.message || String(error || '') || '简历翻译失败，请重试')
  } finally {
    isTranslating.value = false
  }
}

// 取消翻译
function cancelTranslate() {
  showTranslateConfirm.value = false
}

// 获取当前语言的标签
const t = computed(() => labels[currentLang.value] || labels.zh)

// 翻译弹窗始终使用中文
const translateLabels = computed(() => labels.zh)

// 认证状态
const isLoggedIn = ref(false)
const currentUser = ref(null)
const token = ref(localStorage.getItem('access_token') || '')
const appConfig = ref(null)
const router = useRouter()
const route = useRoute()
const isLocalMode = computed(() => appConfig.value?.app_mode === 'local')

// 计算属性：判断是否为管理页面路由
const isAdminRoute = computed(() => route.path === '/admin')
const isWorkspaceRoute = computed(() => route.name === 'TaskWorkspace')
const currentTaskId = computed(() => isWorkspaceRoute.value ? String(route.params.taskId || '') : '')
const currentProject = ref(null)
const projectTasks = ref([])
const currentTask = computed(() => projectTasks.value.find(task => task.id === currentTaskId.value) || null)
const workflowState = ref(null)
const workflowCompletedVisible = ref(false)
let workflowCompletedTimer = null
const pendingAssistantAction = ref(null)
const WORKFLOW_FOCUS_LABELS = Object.freeze({
  basics: '基本信息',
  'basics.name': '姓名',
  'basics.gender': '性别',
  'basics.birth_date': '出生年月',
  'basics.phone': '联系电话',
  'basics.email': '邮箱',
  'basics.target_position': '目标岗位',
  education: '教育经历',
  research_interests: '研究方向',
  honors: '主要荣誉',
  work_experience: '工作经历',
  project_experience: '项目经历',
  custom_sections: '自定义模块',
  others: '专业技能',
  'others.skills': '专业技能',
  'others.certificates': '证书与语言',
  'others.languages': '证书与语言',
  self_evaluation: '自我评价'
})

function formatWorkflowFocus(value) {
  const focus = String(value || '').trim()
  if (!focus) return ''
  const normalized = focus.replace(/\[(\d+)\]/g, '.$1')
  if (WORKFLOW_FOCUS_LABELS[normalized]) return WORKFLOW_FOCUS_LABELS[normalized]

  const parts = normalized.split('.').filter(part => part && !/^\d+$/.test(part))
  for (let length = parts.length; length > 0; length -= 1) {
    const candidate = parts.slice(0, length).join('.')
    if (WORKFLOW_FOCUS_LABELS[candidate]) return WORKFLOW_FOCUS_LABELS[candidate]
  }

  return /^[A-Za-z_][A-Za-z0-9_.]*$/.test(normalized) ? '简历内容' : focus
}

function updateWorkflowState(nextState, { showCompletedBriefly = false } = {}) {
  if (workflowCompletedTimer) {
    clearTimeout(workflowCompletedTimer)
    workflowCompletedTimer = null
  }
  workflowState.value = nextState || null
  const completed = workflowState.value?.phase === 'completed'
    || workflowState.value?.status === 'completed'
  workflowCompletedVisible.value = Boolean(completed && showCompletedBriefly)
  if (workflowCompletedVisible.value) {
    workflowCompletedTimer = setTimeout(() => {
      workflowCompletedVisible.value = false
      workflowCompletedTimer = null
    }, 2000)
  }
}

const workflowVisible = computed(() => (
  workflowState.value
  && ['diagnosis', 'coaching', 'jd_review'].includes(workflowState.value.interaction_mode)
  && workflowState.value.phase !== 'idle'
  && (
    (workflowState.value.phase !== 'completed' && workflowState.value.status !== 'completed')
    || workflowCompletedVisible.value
  )
))
const workflowFocusLabel = computed(() => formatWorkflowFocus(workflowState.value?.focus_section))
const workflowModeLabel = computed(() => ({
  diagnosis: '全面诊断',
  coaching: '深度打磨',
  jd_review: 'JD 对照'
}[workflowState.value?.interaction_mode] || '简历分析'))
const workflowStatusLabel = computed(() => ({
  active: '进行中',
  paused: '已暂停',
  awaiting_confirmation: '待确认',
  completed: '已结束',
  error: '需重试'
}[workflowState.value?.status] || '就绪'))
const previewLayoutConfig = ref(null)
const activeLayoutConfig = computed(() => normalizeLayoutConfig(
  previewLayoutConfig.value || currentTask.value?.layout_config || {}
))
const resumeEditorMetrics = computed(() => {
  const tokens = resolveLayoutTokens(activeLayoutConfig.value)
  return {
    fontSizePt: tokens.bodyFontSizePt,
    labelFontSizePt: tokens.labelFontSizePt,
    labelFontWeight: tokens.labelFontWeight,
    lineHeight: tokens.lineHeight,
    fontFamilyCss: tokens.fontFamilyCss,
    contentWidthPx: Math.max(1, (210 - tokens.marginLeftMm - tokens.marginRightMm) * (96 / 25.4))
  }
})
const projectIntroFlow = project => resolveContentBlockFlow({
  type: 'paragraph',
  label: project?._introLabel || '项目简介',
  label_bold: project?._introLabelBold !== false
})
const showTaskCreateDialog = ref(false)
const newTaskTitle = ref('')
const taskCreateMode = ref('copy')
const taskCreateStep = ref(1)
const taskSourceId = ref('')
const taskResumeSources = ref([])
const taskImportFile = ref(null)
const taskImportInput = ref(null)
const taskJDText = ref('')
const taskJDData = ref({})
const isParsingTaskJD = ref(false)
const isCreatingTask = ref(false)
const taskCreateError = ref('')
const taskToDelete = ref(null)
const isDeletingTask = ref(false)
const taskDeleteError = ref('')
const uiNotice = ref({ visible: false, type: 'error', message: '' })
let uiNoticeTimer = null

const currentProjectSources = computed(() => taskResumeSources.value.filter(
  source => source.project_id === String(route.params.projectId || '')
))
const otherProjectSourceGroups = computed(() => {
  const groups = new Map()
  taskResumeSources.value
    .filter(source => source.project_id !== String(route.params.projectId || ''))
    .forEach(source => {
      if (!groups.has(source.project_id)) {
        groups.set(source.project_id, { id: source.project_id, title: source.project_title, sources: [] })
      }
      groups.get(source.project_id).sources.push(source)
    })
  return [...groups.values()]
})
const selectedTaskSource = computed(() => taskResumeSources.value.find(
  source => source.id === taskSourceId.value
) || null)

// 聊天消息列表
const messages = ref([])
// 消息容器引用，用于自动滚动
const messagesContainer = ref(null)
// 文件输入引用
const fileInput = ref(null)
// 用户输入
const userInput = ref('')
// 上传的文件列表
const uploadedFiles = ref([])
// 简历数据
const resumeData = ref(null)
// 确认框出现期间使用的未保存简历候选，仅用于右侧临时预览
const previewResumeData = ref(null)
const activeResumeData = computed(() => previewResumeData.value || resumeData.value)
// JD数据（新增）
const jdData = ref(null)
// 加载状态
const isLoading = ref(false)
// 响应中状态（流式输出时）
const isResponding = ref(false)
// 确认区域状态（当有 confirm area 时，禁用输入）
const hasConfirmArea = ref(false)
// 加载文案状态
const loadingText = ref('正在处理中...')
let loadingTextInterval = null
const processingRequestId = ref('')
const processingPhase = ref('')
const processingText = ref('')
const confirmationProgressPhases = new Set(['building_preview', 'validating', 'ready'])
const showProcessingBar = computed(() => (
  isResponding.value
  && confirmationProgressPhases.has(processingPhase.value)
  && Boolean(processingText.value)
))

function beginProcessing(requestId) {
  processingRequestId.value = requestId
  processingPhase.value = ''
  processingText.value = ''
}

function updateProcessing(data) {
  if (data.request_id && data.request_id !== processingRequestId.value) return
  if (!confirmationProgressPhases.has(data.phase)) return
  isLoading.value = false
  processingPhase.value = data.phase
  processingText.value = '正在生成确认框，请勿离开或刷新当前页面…'
}

function finishProcessing(requestId = '') {
  if (requestId && processingRequestId.value && requestId !== processingRequestId.value) return
  processingRequestId.value = ''
  processingPhase.value = ''
  processingText.value = ''
}
// 全屏弹窗状态
const isFullscreenDialogOpen = ref(false)
const dialogUserInput = ref('')
// 会话ID - 用于保存对话历史（固定为 default，确保跨会话持久化）
const sessionId = ref('default')

// 图片预览状态
const showImagePreview = ref(false)
const previewImageUrl = ref('')

// 模块高亮状态
const highlightedModule = ref('')

// JD上传弹窗状态（新增）
const isJDDialogOpen = ref(false)
const jdInputMode = ref('input') // 'input' | 'form'
const jdInputText = ref('')
const jdInputImage = ref('') // base64
const isParsingJD = ref(false) // 解析中状态
const isSaving = ref(false) // 保存中状态
const jdFormData = ref({}) // 解析后的表单数据
const newSkill = ref('') // 用于添加技能标签

// 简历编辑弹窗状态（新增）
const isResumeEditDialogOpen = ref(false)
const resumeFormData = ref({
  basics: { name: '', gender: '', birth_date: '', phone: '', email: '', target_position: '', photo: '', additional_fields: [] },
  education: [],
  research_interests: [],
  honors: [],
  work_experience: [],
  project_experience: [],
  custom_sections: [],
  others: { skills: [], certificates: [], languages: [] },
  self_evaluation: []
})
// 简历照片错误信息
const photoError = ref('')
// 标签输入
const newResumeSkill = ref('')
const newResumeCert = ref('')
const newResumeLang = ref('')

// 多行文本编辑（临时存储）
const workDetailsText = ref('')
const projectDetailsText = ref('')
const researchInterestsText = ref('')
const honorsText = ref('')
const selfEvalText = ref('')

// 首次进入选择弹窗状态
const showStartDialog = ref(false)
const showUploadDialog = ref(false)
const resumeImageFile = ref(null) // 选择的图片文件
const resumeImagePreview = ref('') // 图片预览
const isResumePdf = ref(false) // 是否是PDF文件
const isParsingResume = ref(false) // 解析中状态
const resumeImportDraft = ref(null)
const resumeImportError = ref('')
const resumeFileInput = ref(null) // 简历文件输入元素引用
const startResumeFileInput = ref(null) // 开始创建弹窗中的直接文件选择
const hasResumeFileSelected = ref(false) // 是否已选择简历文件（上传流程已开始，不可返回）
const isLoadingInitialData = ref(false) // 防止 loadInitialData 重复调用
let parsingStatusPollInterval = null // 解析状态轮询定时器

// 身份选择弹窗状态
const showIdentityDialog = ref(false)
const selectedIdentity = ref(null) // 'intern' | 'campus' | 'jobhop' | 'custom'
const customIdentity = ref('') // 自定义身份输入

// 预设身份的 AI 首次提问消息
const IDENTITY_GREETINGS = {
  intern: {
    role: 'assistant',
    content: `你好！我是你的简历助手 👋  
为了帮你找到合适的**实习机会**，我们可以从你最熟悉的部分开始。

比如：  
你目前读什么**专业**？学到哪些和实习相关的课程或知识？  
或者，有没有做过让你觉得特别有收获的**课程项目**或小实践？  
又或者，你希望尝试哪个方向的**实习**？为什么对它感兴趣？

不用着急写完整简历，先随便聊聊其中一点就好～`
  },
  campus: {
    role: 'assistant',
    content: `你好！我是你的简历助手 👋  
校招竞争激烈，但每个人都有独特的故事。我们可以从你最有信心的一块开始梳理。

比如：  
你最想投递什么类型的**岗位**？为什么觉得它适合你？  
或者，有没有一段**项目/实习**经历，让你觉得自己"真的搞定了点东西"？  
又或者，你在学校里做过哪些别人可能没有的经历（**比赛**、**科研**、**创业**、**社团**等）？

选一个你愿意多说几句的方向，我来帮你理清楚怎么写进简历～`
  },
  jobhop: {
    role: 'assistant',
    content: `你好！我是你的简历助手 👋  
跳槽或转型的关键，是让新公司看到你过去经验的价值。我们可以从你最想突出的部分聊起。

比如：  
你现在主要做什么**工作**？最近半年最有成就感的一件事是什么？  
或者，你希望下一步往哪个方向发展？是什么让你决定要**转型**？  
又或者，有没有一个**项目**，让你觉得"这段经历绝对值得写在简历里"？

不用马上全部回答，先说说其中一点，我来帮你提炼亮点 💡`
  }
}

// 获取认证 headers
function getAuthorizationHeaders() {
  const headers = buildAuthorizationHeaders(token.value)
  if (currentTaskId.value) {
    headers['X-Task-ID'] = currentTaskId.value
  }
  return headers
}

function getAuthHeaders() {
  return {
    'Content-Type': 'application/json',
    ...getAuthorizationHeaders()
  }
}

// 检查登录状态
async function checkLoginStatus() {
  appConfig.value = await loadAppConfig()

  if (isLocalMode.value) {
    token.value = ''
    currentUser.value = {
      email: appConfig.value.local_user_email || 'local@localhost'
    }
    isLoggedIn.value = true
    return
  }

  const savedToken = localStorage.getItem('access_token')
  const savedUser = localStorage.getItem('user')

  if (savedToken && savedUser) {
    token.value = savedToken
    currentUser.value = JSON.parse(savedUser)
    isLoggedIn.value = true
    console.log('✅ 用户已登录:', currentUser.value?.email)
  } else {
    isLoggedIn.value = false
    currentUser.value = null
    console.log('❌ 用户未登录')
  }
}

// 监听 localStorage 变化（用于跨标签页同步登录状态）
function handleStorageChange(event) {
  if (event.key === 'access_token' || event.key === 'user') {
    console.log('📦 检测到登录状态变化，重新检查...')
    checkLoginStatus()
  }
}

// 初始化简历数据
onMounted(async () => {
  // 等待登录状态检查完成
  await checkLoginStatus()

  // 如果未登录，不加载数据
  if (!isLoggedIn.value) {
    return
  }

  if (isWorkspaceRoute.value) {
    await loadWorkspace()
  }
})

// 初始化响应式检测
onMounted(() => {
  // 初始检测
  checkMobileView()

  // 监听 localStorage 变化
  window.addEventListener('storage', handleStorageChange)

  // 使用 ResizeObserver 监听窗口大小变化
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      checkMobileView()
    })
    resizeObserver.observe(document.body)
  } else {
    // 降级方案：使用 window resize 事件
    window.addEventListener('resize', checkMobileView)
  }

  // 初始化页面滚动状态（直接访问 /admin 时）
  if (route.path === '/admin') {
    document.body.style.overflow = 'auto'
  } else {
    document.body.style.overflow = 'hidden'
  }
})

// 清理监听器
onUnmounted(() => {
  window.removeEventListener('storage', handleStorageChange)
  stopParsingStatusPoll()
  if (uiNoticeTimer) clearTimeout(uiNoticeTimer)
  if (workflowCompletedTimer) clearTimeout(workflowCompletedTimer)
  if (resizeObserver) {
    resizeObserver.disconnect()
  } else {
    window.removeEventListener('resize', checkMobileView)
  }
})

// 监听路由变化，自动更新登录状态
watch(() => route.fullPath, async () => {
  await checkLoginStatus()
  if (isLoggedIn.value && isWorkspaceRoute.value) {
    await loadWorkspace()
  }

  // /admin 页面启用滚动，其他页面禁用页面级滚动
  if (route.path === '/admin') {
    document.body.style.overflow = 'auto'
  } else {
    document.body.style.overflow = 'hidden'
  }
})

async function loadWorkspace() {
  currentLang.value = 'zh'
  showTranslateConfirm.value = false
  translationSourceData.value = null
  translationResultData.value = null
  translationApplied.value = false
  messages.value = []
  resumeData.value = null
  jdData.value = null
  showStartDialog.value = false
  hasConfirmArea.value = false
  previewLayoutConfig.value = null
  previewResumeData.value = null

  const response = await fetch(`/projects/${route.params.projectId}`, {
    headers: getAuthorizationHeaders()
  })
  if (!response.ok) {
    router.replace('/')
    return
  }
  currentProject.value = await response.json()
  projectTasks.value = currentProject.value.tasks || []
  const task = projectTasks.value.find(item => item.id === currentTaskId.value)
  if (!task) {
    router.replace('/')
    return
  }
  sessionId.value = task.session_id
  await loadInitialData()
  await loadWorkflowState()
  restoreTranslationSession()
}

async function createProjectTask() {
  newTaskTitle.value = ''
  taskCreateMode.value = 'copy'
  taskImportFile.value = null
  taskCreateStep.value = 1
  taskJDText.value = ''
  taskJDData.value = {}
  taskCreateError.value = ''
  showTaskCreateDialog.value = true
  try {
    const response = await fetch('/resume-sources', { headers: getAuthorizationHeaders() })
    if (!response.ok) throw new Error('无法加载简历列表')
    taskResumeSources.value = await response.json()
    const currentBase = taskResumeSources.value.find(
      source => source.project_id === String(route.params.projectId) && source.is_base
    )
    taskSourceId.value = currentBase?.id || currentTaskId.value || ''
  } catch (error) {
    taskCreateError.value = error.message || '无法加载简历列表'
  }
}

function closeTaskCreateDialog() {
  if (isCreatingTask.value) return
  showTaskCreateDialog.value = false
  taskImportFile.value = null
  taskCreateError.value = ''
}

function selectTaskImportFile() {
  taskImportInput.value?.click()
}

function handleTaskImportFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const allowedTypes = new Set(['application/pdf', 'image/jpeg', 'image/png'])
  if (!allowedTypes.has(file.type)) {
    taskCreateError.value = '仅支持 JPG、PNG 或 PDF 简历'
    return
  }
  if (file.size > 5 * 1024 * 1024) {
    taskCreateError.value = '文件大小不能超过 5MB'
    return
  }
  taskImportFile.value = file
  taskCreateError.value = ''
}

function goToTaskJDStep() {
  if (taskCreateMode.value === 'copy' && !taskSourceId.value) {
    taskCreateError.value = '请选择要复制的简历'
    return
  }
  if (taskCreateMode.value === 'import' && !taskImportFile.value) {
    taskCreateError.value = '请选择要导入的简历文件'
    return
  }
  taskCreateError.value = ''
  taskCreateStep.value = 2
}

async function goToTaskReview({ skipJD = false } = {}) {
  taskCreateError.value = ''
  if (skipJD || !taskJDText.value.trim()) {
    taskJDData.value = {}
    taskCreateStep.value = 3
    return
  }
  isParsingTaskJD.value = true
  try {
    const response = await fetch('/parse_jd', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ text: taskJDText.value.trim(), image: '' })
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok || data.error) throw new Error(data.error || 'JD 识别失败')
    taskJDData.value = { ...data, raw_text: taskJDText.value.trim() }
    if (!newTaskTitle.value.trim()) {
      newTaskTitle.value = [data.company, data.position].filter(Boolean).join(' · ') || '新岗位版本'
    }
    taskCreateStep.value = 3
  } catch (error) {
    taskCreateError.value = error.message || 'JD 识别失败，请重试或暂时跳过'
  } finally {
    isParsingTaskJD.value = false
  }
}

async function confirmCreateProjectTask() {
  const title = newTaskTitle.value.trim() || '新岗位版本'
  isCreatingTask.value = true
  taskCreateError.value = ''
  let createdTask = null
  try {
    const response = await fetch(`/projects/${route.params.projectId}/tasks`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        title,
        copy_base_resume: false,
        source_task_id: taskCreateMode.value === 'copy' ? taskSourceId.value : null,
        jd_data: taskJDData.value
      })
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || '创建岗位版本失败，请重试')
    }
    const task = await response.json()
    createdTask = task
    if (taskCreateMode.value === 'import') {
      const formData = new FormData()
      formData.append('file', taskImportFile.value)
      const importHeaders = buildAuthorizationHeaders(token.value)
      importHeaders['X-Task-ID'] = task.id
      const importResponse = await fetch('/api/resume/parse_and_save', {
        method: 'POST',
        headers: importHeaders,
        body: formData
      })
      const importData = await importResponse.json().catch(() => ({}))
      if (!importResponse.ok || !importData.success) {
        throw new Error(importData.error || importData.detail || '简历导入失败，请重试')
      }
    }
    isCreatingTask.value = false
    showTaskCreateDialog.value = false
    taskImportFile.value = null
    await router.push(`/projects/${task.project_id}/tasks/${task.id}`)
  } catch (error) {
    if (createdTask) {
      try {
        await fetch(`/tasks/${createdTask.id}`, {
          method: 'DELETE',
          headers: getAuthorizationHeaders()
        })
      } catch (rollbackError) {
        console.error('清理导入失败的版本时出错:', rollbackError)
      }
    }
    taskCreateError.value = error.message || '创建岗位版本失败，请重试'
  } finally {
    isCreatingTask.value = false
  }
}

async function deleteProjectTask(task, event) {
  if (task.is_base) return
  if (event?.detail > 0) {
    event.currentTarget?.blur()
  }
  taskToDelete.value = task
  taskDeleteError.value = ''
}

function closeTaskDeleteDialog() {
  if (isDeletingTask.value) return
  taskToDelete.value = null
  taskDeleteError.value = ''
}

async function confirmDeleteProjectTask() {
  if (!taskToDelete.value) return
  const deletingTask = taskToDelete.value
  isDeletingTask.value = true
  taskDeleteError.value = ''
  try {
    const response = await fetch(`/tasks/${deletingTask.id}`, {
      method: 'DELETE',
      headers: getAuthorizationHeaders()
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || '删除失败，请重试')
    }
    projectTasks.value = projectTasks.value.filter(item => item.id !== deletingTask.id)
    taskToDelete.value = null
    isDeletingTask.value = false
    if (deletingTask.id === currentTaskId.value) {
      const nextTask = projectTasks.value.find(item => item.is_base) || projectTasks.value[0]
      if (nextTask) {
        router.replace(`/projects/${nextTask.project_id}/tasks/${nextTask.id}`)
      } else {
        router.replace('/')
      }
    }
  } catch (error) {
    taskDeleteError.value = error.message || '删除失败，请重试'
  } finally {
    isDeletingTask.value = false
  }
}

function showNotice(message, type = 'error') {
  if (uiNoticeTimer) clearTimeout(uiNoticeTimer)
  uiNotice.value = { visible: true, type, message }
  uiNoticeTimer = setTimeout(() => {
    uiNotice.value.visible = false
  }, 3600)
}

function useLayoutPrompt(prompt) {
  userInput.value = prompt
  showNotice('排版示例已填入输入框，可修改后发送', 'success')
  nextTick(() => document.querySelector('.textarea-container textarea:not(:disabled)')?.focus())
}

function runAssistantAction(action) {
  if (isLoading.value || isResponding.value) return
  pendingAssistantAction.value = action.mode ? { mode: action.mode, action: action.action } : null
  userInput.value = action.prompt
  if (action.prefillOnly) {
    showNotice('修改需求模板已填入输入框，请补充具体内容后发送', 'success')
    nextTick(() => document.querySelector('.textarea-container textarea:not(:disabled)')?.focus())
    return
  }
  nextTick(() => sendMessage())
}

function runWorkflowAction(action) {
  if (isLoading.value || isResponding.value || !workflowState.value) return
  const prompts = {
    pause: '暂停本轮打磨',
    resume: '继续本轮打磨',
    end: '结束本轮打磨',
    apply: '应用当前改写建议'
  }
  pendingAssistantAction.value = {
    mode: workflowState.value.interaction_mode,
    action
  }
  userInput.value = prompts[action]
  nextTick(() => sendMessage())
}

async function loadWorkflowState() {
  if (!currentTaskId.value) {
    updateWorkflowState(null)
    return
  }
  try {
    const response = await fetch(`/tasks/${currentTaskId.value}/workflow`, {
      headers: getAuthorizationHeaders()
    })
    if (!response.ok) return
    const data = await response.json()
    // 已结束的历史工作流不在刷新后重新闪现；仅实时结束动作短暂展示。
    updateWorkflowState(data.state || null)
  } catch (error) {
    console.warn('恢复深度打磨状态失败:', error)
  }
}

function requestLayoutTemplate(prompt) {
  userInput.value = prompt
  nextTick(() => sendMessage())
}

function handleLayoutUpdated(layoutConfig) {
  if (currentTask.value) currentTask.value.layout_config = normalizeLayoutConfig(layoutConfig)
  previewLayoutConfig.value = null
}

// 加载初始数据的函数（同时检查首次访问）
async function loadInitialData() {
  // 防止重复调用
  if (isLoadingInitialData.value) {
    console.log('[DEBUG] loadInitialData: 已在加载中，跳过重复调用')
    return
  }
  isLoadingInitialData.value = true
  console.log('[DEBUG] loadInitialData: 开始加载...')

  try {
    const response = await fetch('/load_resume', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({})
    })

    // 如果认证失败，跳转登录
    if (response.status === 401) {
      logout()
      return
    }

    const data = await response.json()
    resumeData.value = data

    // 检查解析状态
    const parsingStatus = data.parsing_status || 'none'
    console.log(`[DEBUG] loadInitialData: parsingStatus="${parsingStatus}"`)

    // 如果正在解析中，显示上传弹窗并启动轮询
    if (parsingStatus === 'parsing') {
      console.log('📋 检测到简历正在解析中，启动轮询...')
      showUploadDialog.value = true
      hasResumeFileSelected.value = true
      isParsingResume.value = true
      resumeImagePreview.value = ''
      resumeImageFile.value = null
      isResumePdf.value = false
      // 启动轮询检查解析状态
      startParsingStatusPoll()
      return
    }

    // 停止轮询（如果之前在轮询中）
    stopParsingStatusPoll()

    // 加载JD数据
    try {
      const jdResponse = await fetch('/load_jd', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({})
      })
      if (jdResponse.status === 401) {
        logout()
        return
      }
      const jdResult = await jdResponse.json()
      if (jdResult && Object.keys(jdResult).length > 0) {
        jdData.value = jdResult
      }
    } catch (jdError) {
      console.log('暂无岗位数据')
    }

    // 检查是否首次进入（无简历且无聊天记录）
    // 修正判断逻辑：检查basics中是否有有效字段
    const hasResume = hasMeaningfulResumeContent(data)
    console.log(`[DEBUG] loadInitialData: hasResume=${hasResume}`)

    // 加载对话历史
    try {
      const convResponse = await fetch('/load_conversation', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ session_id: sessionId.value })
      })
      if (convResponse.status === 401) {
        logout()
        return
      }
      const convData = await convResponse.json()
      const hasChatHistory = Array.isArray(convData) && convData.length > 0
      console.log(`[DEBUG] loadInitialData: hasChatHistory=${hasChatHistory}`)

      // 首次进入检测：无简历且无聊天记录
      if (!hasResume && (!hasChatHistory || route.query.new === '1')) {
        console.log('[DEBUG] 首次进入，显示开始选择弹窗')
        showStartDialog.value = true
        return
      }

      if (hasChatHistory) {
        messages.value = convData
      } else {
        messages.value = [{
          id: Date.now(),
          role: 'assistant',
          content: WELCOME_MESSAGE,
          localOnly: true
        }]
      }
    } catch (convError) {
      messages.value = [{
        id: Date.now(),
        role: 'assistant',
        content: WELCOME_MESSAGE,
        localOnly: true
      }]
    }
  } catch (error) {
    console.error('加载数据失败:', error)
    messages.value = [{
      id: Date.now(),
      role: 'assistant',
      content: '抱歉，加载简历失败。请确保MCP服务已启动。'
    }]
  } finally {
    isLoadingInitialData.value = false
    console.log('[DEBUG] loadInitialData: 完成')
  }
}

// 轮询检查解析状态
async function pollParsingStatus() {
  try {
    const response = await fetch('/api/resume/parsing_status', {
      method: 'GET',
      headers: getAuthHeaders()
    })

    if (response.status === 401) {
      logout()
      return
    }

    const data = await response.json()
    const status = data.parsing_status || 'none'
    console.log(`[DEBUG] pollParsingStatus: status="${status}"`)

    if (status === 'completed') {
      // 解析完成，重新加载简历数据
      console.log('✅ 解析完成，重新加载数据...')
      stopParsingStatusPoll()
      isParsingResume.value = false
      showUploadDialog.value = false
      // 重新加载简历
      await loadResumeData()

      // 导入完成只更新简历，不触发 LLM、不改变聊天记录。用户明确提问
      // 或点击快捷入口后，助手才开始工作。
      if (messages.value.length === 0) {
        messages.value = [{ id: Date.now(), role: 'assistant', content: WELCOME_MESSAGE, localOnly: true }]
      }
    } else if (status === 'failed') {
      // 解析失败
      console.error('❌ 解析失败')
      stopParsingStatusPoll()
      isParsingResume.value = false
      showNotice('简历解析失败，请重新上传')
    }
    // 如果还是 'parsing'，继续轮询
  } catch (error) {
    console.error('检查解析状态失败:', error)
  }
}

// 启动解析状态轮询
function startParsingStatusPoll() {
  // 先清除之前的轮询
  stopParsingStatusPoll()
  // 立即检查一次
  pollParsingStatus()
  // 每3秒检查一次
  parsingStatusPollInterval = setInterval(pollParsingStatus, 3000)
}

// 停止解析状态轮询
function stopParsingStatusPoll() {
  if (parsingStatusPollInterval) {
    clearInterval(parsingStatusPollInterval)
    parsingStatusPollInterval = null
  }
}

// 加载简历数据（不检查解析状态）
async function loadResumeData() {
  try {
    const response = await fetch('/load_resume', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({})
    })

    if (response.status === 401) {
      logout()
      return
    }

    const data = await response.json()
    resumeData.value = data
    // 更新简历内容
    const { parsing_status, ...resumeContent } = data
    if (resumeContent && Object.keys(resumeContent).length > 0) {
      console.log('✅ 简历数据已加载')
    }
  } catch (error) {
    console.error('加载简历数据失败:', error)
  }
}

// 登出
function logout() {
  if (isLocalMode.value) {
    return
  }
  localStorage.removeItem('access_token')
  localStorage.removeItem('user')
  token.value = ''
  currentUser.value = null
  isLoggedIn.value = false
  // 刷新页面
  window.location.reload()
}

// 发送消息
async function sendMessage() {
  // 检查登录状态
  if (!isLoggedIn.value) {
    showNotice('请先登录')
    return
  }
  if ((!userInput.value.trim() && uploadedFiles.value.length === 0) || isLoading.value) return

  // 如果有未处理的 confirm area，取消它（用户发送了新消息）
  const hadPendingConfirmation = messages.value.some(m => m.type === 'confirm' && !m.handled)
  if (hadPendingConfirmation) {
    messages.value = messages.value.map(message => (
      message.type === 'confirm' && !message.handled
        ? { ...message, handled: true }
        : message
    ))
    hasConfirmArea.value = false
    previewResumeData.value = null
    previewLayoutConfig.value = null
  }

  const input = userInput.value.trim()
  const structuredAction = pendingAssistantAction.value
  pendingAssistantAction.value = null
  userInput.value = ''

  // 先保存附件
  const currentAttachments = [...uploadedFiles.value]

  // 清空上传的文件列表
  uploadedFiles.value = []

  // 创建消息ID - 使用更可靠的方式确保唯一性
  const baseId = Date.now() * 1000 + Math.floor(Math.random() * 1000)
  const userMessageId = baseId
  const streamMessageId = baseId + 1
  const requestId = globalThis.crypto?.randomUUID?.() || `request-${baseId}`

  // 添加用户消息
  const userMessage = {
    id: userMessageId,
    role: 'user',
    content: input,
    attachments: currentAttachments
  }
  messages.value.push(userMessage)

  // 预先添加一个流式消息占位符 - 确保role属性始终为assistant
  const streamingMessage = {
    id: streamMessageId,
    role: 'assistant',
    content: '',
    streaming: true
  }
  messages.value.push(streamingMessage)
  nextTick(() => scrollToBottom('auto'))

  isLoading.value = true
  isResponding.value = true
  beginProcessing(requestId)
  // 启动加载文案切换
  loadingText.value = '正在处理中...'
  let textIndex = 0
  const loadingTexts = ['正在处理中...', '正在思考中...', '正在总结提炼回答...']
  const textDelays = [8000, 10000] // 第一个8秒，第二个10秒，之后一直显示第三个

  // 使用setTimeout实现不同时长的文案切换
  const runTextCycle = () => {
    textIndex++
    if (textIndex < loadingTexts.length) {
      loadingText.value = loadingTexts[textIndex]
      const delay = textIndex < textDelays.length ? textDelays[textIndex] : 0
      if (delay > 0) {
        loadingTextInterval = setTimeout(runTextCycle, delay)
      }
    }
  }
  loadingTextInterval = setTimeout(runTextCycle, textDelays[0])
  
  try {
    // 创建FormData对象
    const formData = new FormData()
    formData.append('message', input)
    formData.append('session_id', sessionId.value)
    formData.append('request_id', requestId)
    if (structuredAction?.mode) formData.append('interaction_mode', structuredAction.mode)
    if (structuredAction?.action) formData.append('interaction_action', structuredAction.action)

    // 添加上传的文件
    // 注意：uploadedFiles 在函数开头已被清空，这里附件信息已保存在 currentAttachments 中
    currentAttachments.forEach((fileObj) => {
      formData.append('files', fileObj.file)
    })

    // 使用fetch API处理SSE流式响应
    const response = await fetch('/chat', {
      method: 'POST',
      headers: getAuthorizationHeaders(),
      body: formData
    })
    
    if (!response.ok) {
      throw new Error(`HTTP错误! 状态: ${response.status}`)
    }
    
    // 检查是否支持流式响应
    if (!response.body) {
      throw new Error('不支持流式响应')
    }
    
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    
    while (true) {
      const { done, value } = await reader.read()
      
      if (done) break
      
      // 解码接收到的数据
      buffer += decoder.decode(value, { stream: true })
      
      // 处理接收到的SSE消息
      let newlineIndex
      while ((newlineIndex = buffer.indexOf('\n\n')) !== -1) {
        const message = buffer.substring(0, newlineIndex)
        buffer = buffer.substring(newlineIndex + 2)
        
        // 处理SSE消息格式（data: {...}）
        if (message.startsWith('data: ')) {
          const jsonData = message.substring(6).trim()
          if (jsonData) {
            try {
              const data = JSON.parse(jsonData)

              if (data.type === 'progress') {
                updateProcessing(data)
              } else if (data.type === 'stream') {
                // 停止加载文案切换
                if (loadingTextInterval) {
                  clearTimeout(loadingTextInterval)
                  loadingTextInterval = null
                }
                // 收到第一个流式数据时，立即隐藏加载指示器
                isLoading.value = false

                // 实时流式更新内容
                const index = messages.value.findIndex(m => m.id === streamMessageId)
                if (index !== -1) {
                  // 创建新对象触发 Vue 响应式更新
                  messages.value[index] = {
                    ...messages.value[index],
                    content: data.content,
                    streaming: true
                  }
                }
              } else if (data.type === 'final') {
                console.log('[前端] 收到 final 事件, isLoading before:', isLoading.value, 'isResponding:', isResponding.value)
                // 停止加载文案切换
                if (loadingTextInterval) {
                  clearTimeout(loadingTextInterval)
                  loadingTextInterval = null
                }
                // 更新流式消息为最终内容
                const index = messages.value.findIndex(m => m.id === streamMessageId)
                if (index !== -1) {
                  // 使用对象展开语法，确保role属性不会被修改
                  messages.value[index] = {
                    ...messages.value[index],
                    content: data.content,
                    streaming: false
                  }
                }
                // 收到第一个流式输出后，隐藏加载指示器
                isLoading.value = false
                finishProcessing(data.request_id)
                // 更新会话ID并保存到localStorage
                if (data.session_id) {
                  sessionId.value = data.session_id
                  localStorage.setItem('resumeAssistantSessionId', data.session_id)
                }
              } else if (data.type === 'tool_call') {
                // 停止加载文案切换
                if (loadingTextInterval) {
                  clearTimeout(loadingTextInterval)
                  loadingTextInterval = null
                }
                // 收到工具调用通知，隐藏加载指示器，显示正在调用工具
                isLoading.value = false
                // 更新流式消息，显示正在调用工具
                const index = messages.value.findIndex(m => m.id === streamMessageId)
                if (index !== -1) {
                  messages.value[index] = {
                    ...messages.value[index],
                    content: data.content,
                    streaming: true
                  }
                }
              } else if (data.type === 'confirm') {
                // 停止加载文案切换
                if (loadingTextInterval) {
                  clearTimeout(loadingTextInterval)
                  loadingTextInterval = null
                }
                isLoading.value = false
                isResponding.value = false
                finishProcessing(data.request_id)
                // 一个任务同时只能有一个活动确认框。先失效旧确认，再按
                // confirm_id 更新或插入，避免重复 SSE 事件生成双确认框。
                messages.value = messages.value.map(message => (
                  message.type === 'confirm' && !message.handled
                    ? { ...message, handled: true }
                    : message
                ))
                const confirmationMessage = {
                  id: data.id || Date.now(),
                  role: 'assistant',
                  type: 'confirm',
                  content: data.content,
                  options: data.options,
                  changes: data.changes || [],
                  confirm_id: data.confirm_id,
                  handled: false,
                  streaming: false
                }
                previewResumeData.value = data.resume_candidate || null
                previewLayoutConfig.value = data.layout_candidate
                  ? normalizeLayoutConfig(data.layout_candidate)
                  : null
                const existingConfirmIndex = messages.value.findIndex(
                  message => message.type === 'confirm' && message.confirm_id === data.confirm_id
                )
                if (existingConfirmIndex === -1) {
                  messages.value.push(confirmationMessage)
                } else {
                  messages.value[existingConfirmIndex] = confirmationMessage
                }
                // 标记有 confirm area，禁用输入
                hasConfirmArea.value = true
              } else if (data.type === 'proposal_error') {
                previewResumeData.value = null
                previewLayoutConfig.value = null
                if (loadingTextInterval) {
                  clearTimeout(loadingTextInterval)
                  loadingTextInterval = null
                }
                const index = messages.value.findIndex(m => m.id === streamMessageId)
                if (index !== -1) {
                  messages.value[index] = {
                    ...messages.value[index],
                    content: data.message || '本次修改无法安全生成确认预览，系统未对简历做任何更改。',
                    streaming: false
                  }
                }
                isLoading.value = false
                isResponding.value = false
                finishProcessing(data.request_id)
              } else if (data.type === 'persistence_error') {
                showNotice(data.message || '对话状态未能安全保存，请重新发送上一条消息。')
              } else if (data.type === 'workflow_error') {
                showNotice(data.message || '工作流进度未能保存，本轮对话内容仍已处理。')
              } else if (data.type === 'workflow_state') {
                updateWorkflowState(data.state || null, { showCompletedBriefly: true })
              } else if (data.type === 'end') {
                console.log('[前端] 收到 end 事件, isResponding before:', isResponding.value, 'isLoading:', isLoading.value)
                // 结束信号，关闭连接
                isResponding.value = false
                finishProcessing(data.request_id)
                console.log('[前端] isResponding 已设置为 false')
                // 只在流式响应结束时调用一次updateResumeData()
                updateResumeData()
                // 更新会话ID并保存到localStorage
                if (data.session_id) {
                  sessionId.value = data.session_id
                  localStorage.setItem('resumeAssistantSessionId', data.session_id)
                }
                break
              }
            } catch (e) {
              console.error('解析JSON失败:', e)
              // 记录原始消息以便调试
              console.error('原始消息:', jsonData)
            }
          }
        }
      }
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    let errorMessage = '抱歉，发送消息失败。'
    if (error.name === 'AbortError') {
      errorMessage = '请求超时，请稍后重试。'
    } else if (error.message) {
      errorMessage = `抱歉，发送消息失败: ${error.message}`
    }
    messages.value.push({
      id: Date.now(),
      role: 'assistant',
      content: errorMessage
    })
  } finally {
    isLoading.value = false
    isResponding.value = false

    // 保存对话历史（过滤掉未处理的 confirm 消息，已处理的 confirm 消息保留 handled 状态）
    try {
      const messagesToSave = conversationMessagesForSave().filter(m => !(m.type === 'confirm' && m.confirm_id && !m.handled))
      await fetch('/save_conversation', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          session_id: sessionId.value,
          messages: messagesToSave
        })
      })
    } catch (saveError) {
      console.error('保存对话历史失败:', saveError)
    }
  }
}

// 处理确认按钮点击
async function handleOptionClick({ confirm_id, value, selected_change_ids = [] }) {
  const confirmMsgIndex = messages.value.findIndex(m => m.type === 'confirm' && m.confirm_id === confirm_id)
  if (confirmMsgIndex !== -1) {
    messages.value[confirmMsgIndex] = {
      ...messages.value[confirmMsgIndex],
      handled: true
    }
  }
  hasConfirmArea.value = false
  if (value === 'cancel') {
    previewResumeData.value = null
    previewLayoutConfig.value = null
  }

  const selectedSuffix = selected_change_ids.length ? `:${selected_change_ids.join(',')}` : ''
  const confirmMessage = `[CONFIRM_REPLY:${confirm_id}:${value}${selectedSuffix}]`
  const isAccepting = value !== 'cancel'
  const baseId = Date.now() * 1000 + Math.floor(Math.random() * 1000)
  const streamMessageId = baseId + 1
  const requestId = globalThis.crypto?.randomUUID?.() || `confirm-${baseId}`

  messages.value.push({
    id: baseId,
    role: 'user',
    content: value === 'cancel'
      ? '全部拒绝'
      : (value === 'confirm_selected' ? `应用已选 ${selected_change_ids.length} 项修改` : '全部接受')
  })
  messages.value.push({
    id: streamMessageId,
    role: 'assistant',
    content: '',
    streaming: true
  })

  try {
    isLoading.value = true
    isResponding.value = true

    const formData = new FormData()
    formData.append('message', confirmMessage)
    formData.append('session_id', sessionId.value)
    formData.append('request_id', requestId)

    // 恢复原版确认链路：确认回复进入 /chat，由 LangGraph tool_node 处理。
    const response = await fetch('/chat', {
      method: 'POST',
      headers: getAuthorizationHeaders(),
      body: formData
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.error || errorData.detail || `HTTP错误! 状态: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let resumeRefreshed = false
    let confirmationProcessed = false
    let confirmationSucceeded = false

    while (true) {
      const { done, value: chunk } = await reader.read()
      if (done) break
      buffer += decoder.decode(chunk, { stream: true })

      let newlineIndex
      while ((newlineIndex = buffer.indexOf('\n\n')) !== -1) {
        const eventText = buffer.substring(0, newlineIndex)
        buffer = buffer.substring(newlineIndex + 2)
        if (!eventText.startsWith('data: ')) continue

        const jsonData = eventText.substring(6).trim()
        if (!jsonData) continue

        const data = JSON.parse(jsonData)
        if (data.type === 'stream') {
          isLoading.value = false
          const index = messages.value.findIndex(m => m.id === streamMessageId)
          if (index !== -1) {
            messages.value[index] = { ...messages.value[index], content: data.content, streaming: true }
          }
        } else if (data.type === 'final') {
          isLoading.value = false
          confirmationProcessed = Boolean(data.confirmation_processed)
          confirmationSucceeded = Boolean(data.confirmation_success)
          const index = messages.value.findIndex(m => m.id === streamMessageId)
          if (index !== -1) {
            messages.value[index] = { ...messages.value[index], content: data.content, streaming: false }
          }
          if (data.session_id) sessionId.value = data.session_id
          if (isAccepting && confirmationSucceeded) {
            await updateResumeData()
            resumeRefreshed = true
          }
        } else if (data.type === 'persistence_error') {
          showNotice(data.message || '对话状态未能安全保存，请重新发送上一条消息。')
        } else if (data.type === 'workflow_error') {
          showNotice(data.message || '工作流进度未能保存，本轮对话内容仍已处理。')
        } else if (data.type === 'end') {
          confirmationProcessed = confirmationProcessed || Boolean(data.confirmation_processed)
          confirmationSucceeded = confirmationSucceeded || Boolean(data.confirmation_success)
          if (data.session_id) sessionId.value = data.session_id
          if (isAccepting && confirmationSucceeded && !resumeRefreshed) {
            await updateResumeData()
            resumeRefreshed = true
          }
        }
      }
    }
    if (isAccepting && confirmationProcessed && confirmationSucceeded && resumeRefreshed) {
      messages.value.push({
        id: Date.now() * 1000 + 9,
        role: 'assistant',
        type: 'undo',
        content: '本次修改已应用。',
        handled: false
      })
    }
  } catch (error) {
    console.error('确认操作失败:', error)
    if (confirmMsgIndex !== -1) {
      messages.value[confirmMsgIndex] = {
        ...messages.value[confirmMsgIndex],
        handled: false
      }
    }
    hasConfirmArea.value = true
    const index = messages.value.findIndex(m => m.id === streamMessageId)
    if (index !== -1) {
      messages.value[index] = {
        ...messages.value[index],
        content: `处理确认请求失败：${error.message || '请重试。'}`,
        streaming: false
      }
    }
  } finally {
    isLoading.value = false
    isResponding.value = false
    finishProcessing(requestId)
    try {
      await fetch('/save_conversation', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ session_id: sessionId.value, messages: conversationMessagesForSave() })
      })
    } catch (saveError) {
      console.error('保存确认消息失败:', saveError)
    }
  }
}

async function handleUndoClick({ message_id }) {
  const index = messages.value.findIndex(message => message.id === message_id)
  try {
    const response = await fetch(`/tasks/${currentTaskId.value}/undo`, {
      method: 'POST',
      headers: getAuthorizationHeaders()
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || '撤回失败，请重试')
    if (index !== -1) {
      messages.value[index] = { ...messages.value[index], handled: true, content: '已撤回本次修改。' }
    }
    messages.value = messages.value.map(message => (
      message.type === 'confirm' && !message.handled
        ? { ...message, handled: true }
        : message
    ))
    hasConfirmArea.value = false
    previewResumeData.value = null
    previewLayoutConfig.value = null
    await updateResumeData()
    showNotice('已撤回本次修改', 'success')
    await fetch('/save_conversation', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ session_id: sessionId.value, messages: conversationMessagesForSave() })
    })
  } catch (error) {
    showNotice(error.message || '撤回失败，请重试')
  }
}

// 检测哪个模块发生了变化
function detectChangedModule(oldData, newData) {
  if (!oldData || !newData) return ''

  const modules = ['basics', 'education', 'research_interests', 'honors', 'work_experience', 'project_experience', 'custom_sections', 'others', 'self_evaluation']

  for (const module of modules) {
    const oldVal = JSON.stringify(oldData[module] || {})
    const newVal = JSON.stringify(newData[module] || {})

    if (oldVal !== newVal) {
      return module
    }
  }

  return ''
}

// 更新简历数据
async function updateResumeData() {
  try {
    // 先从服务器获取新数据
    const response = await fetch('/load_resume', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({})
    })
    const newData = await response.json()

    // 保存旧数据用于比较
    const oldData = resumeData.value ? JSON.parse(JSON.stringify(resumeData.value)) : null

    // 先更新数据
    resumeData.value = newData

    if (currentTaskId.value) {
      const layoutResponse = await fetch(`/tasks/${currentTaskId.value}/layout`, {
        headers: getAuthorizationHeaders()
      })
      if (layoutResponse.ok) {
        const layoutPayload = await layoutResponse.json()
        const normalizedLayout = normalizeLayoutConfig(layoutPayload.layout_config)
        projectTasks.value = projectTasks.value.map(task => (
          task.id === currentTaskId.value
            ? { ...task, layout_config: normalizedLayout }
            : task
        ))
      }
    }
    if (!hasConfirmArea.value) {
      previewResumeData.value = null
      previewLayoutConfig.value = null
    }

    // 检测变化并触发高亮
    const changedModule = detectChangedModule(oldData, newData)

    if (changedModule) {
      highlightedModule.value = changedModule

      // 3秒后清除高亮
      setTimeout(() => {
        highlightedModule.value = ''
      }, 3000)
    }
  } catch (error) {
    console.error('更新简历数据失败:', error)
  }
}

// 处理键盘事件
function handleKeyDown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

// 处理粘贴事件
function handlePaste(event) {
  // 检查剪贴板是否有图片
  const clipboardItems = (event.clipboardData || event.originalEvent.clipboardData).items
  for (let item of clipboardItems) {
    if (item.kind === 'file' && item.type.startsWith('image/')) {
      // 获取图片文件
      const file = item.getAsFile()
      if (file) {
        // 创建文件对象，包含文件信息和缩略图URL
        const fileObj = {
          id: Date.now(),
          file: file,
          name: `pasted_image_${Date.now()}.${file.type.split('/')[1]}`,
          type: file.type,
          thumbnail: ''
        }
        
        // 生成缩略图
        const reader = new FileReader()
        reader.onload = (e) => {
          fileObj.thumbnail = e.target.result
        }
        reader.readAsDataURL(file)
        
        uploadedFiles.value.push(fileObj)
      }
      break
    }
  }
}

// 处理文件选择
function handleFileSelect(event) {
  const files = event.target.files
  if (files.length > 0) {
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      // 检查文件类型
      if (file.type.match(/(image\/(png|jpeg|jpg)|application\/pdf)/)) {
        // 创建文件对象，包含文件信息和缩略图URL
        const fileObj = {
          id: Date.now() + i,
          file: file,
          name: file.name,
          type: file.type,
          thumbnail: ''
        }
        
        // 生成缩略图
        if (file.type.startsWith('image/')) {
          const reader = new FileReader()
          reader.onload = (e) => {
            fileObj.thumbnail = e.target.result
          }
          reader.readAsDataURL(file)
        } else if (file.type === 'application/pdf') {
          // PDF文件使用默认图标
          fileObj.thumbnail = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0iTTMgN2MwLTEuMS45LTIgMi0yaDE2YzEuMSAwIDIgLjkgMiAydjEwYzAgMS4xLS45IDItMiAyaC0zLjVjLS42IDAtMS4yLjItMS41LjV2LS41SDV2NkgzbTIgOWguNXYxLjVoLTJ6TTUgMTBoMTZ2Mi41SDV6TTUgMTZoMTR2Mi41SDV6Ii8+PC9zdmc+'
        }
        
        uploadedFiles.value.push(fileObj)
      }
    }
  }
}

// 删除上传的文件
function deleteFile(fileId) {
  uploadedFiles.value = uploadedFiles.value.filter(file => file.id !== fileId)
}

// 打开图片预览
function openImagePreview(file) {
  if (file.thumbnail) {
    previewImageUrl.value = file.thumbnail
    showImagePreview.value = true
  }
}

// 关闭图片预览
function closeImagePreview() {
  showImagePreview.value = false
  previewImageUrl.value = ''
}

// ==================== JD 上传功能（新增） ====================

// 打开岗位信息弹窗
function openJDDialog() {
  isJDDialogOpen.value = true
  // 如果已有岗位信息，直接显示编辑表单
  if (jdData.value && Object.keys(jdData.value).length > 0) {
    jdInputMode.value = 'form'
    jdFormData.value = {
      ...jdData.value,
      preferred_qualifications_text: arrayToCommaSeparated(jdData.value.preferred_qualifications),
      highlights_text: arrayToCommaSeparated(jdData.value.highlights)
    }
  } else {
    jdInputMode.value = 'input'
    jdInputText.value = ''
    jdInputImage.value = ''
    jdFormData.value = {
      company: '',
      position: '',
      department: '',
      location: '',
      job_type: '',
      salary: '',
      description: '',
      requirements: {
        education: '',
        experience: '',
        skills: [],
        language: ''
      },
      preferred_qualifications: [],
      highlights: [],
      preferred_qualifications_text: '',
      highlights_text: ''
    }
  }
  newSkill.value = ''
}

// 退回上一步
function backToInputMode() {
  jdInputMode.value = 'input'
}

// 关闭JD弹窗
function closeJDDialog() {
  isJDDialogOpen.value = false
}

// ==================== 简历编辑功能（新增） ====================

function initializeProjectContentEditor(proj) {
  const blocks = Array.isArray(proj.content_blocks) ? proj.content_blocks : []
  const intro = blocks.find(block => block?.type === 'paragraph' && /简介|背景|概述|说明/.test(block.label || ''))
  const duties = blocks.find(block => block?.type === 'numbered_list' && /职责|负责内容/.test(block.label || ''))
  const extraBlocks = blocks.filter(block => block !== intro && block !== duties)
  proj._introLabel = intro?.label || '项目简介'
  proj._dutiesLabel = duties?.label || '项目职责'
  proj._introLabelBold = intro?.label_bold !== false
  proj._dutiesLabelBold = duties?.label_bold !== false
  proj._introText = intro?.text || ''
  proj._dutiesText = arrayToMultiline(duties?.items || [])
  proj._extraDetailsText = arrayToMultiline(extraBlocks.flatMap(block => block?.items?.length ? block.items : (block?.text ? [block.text] : [])))

  if (!blocks.length && Array.isArray(proj.details)) {
    let dutyMode = false
    const extras = []
    const dutiesFromLegacy = []
    for (const raw of proj.details) {
      const text = String(raw || '').trim()
      const introMatch = text.match(/^(项目简介|项目背景|项目概述|项目说明)\s*[：:]\s*(.*)$/)
      const dutyMatch = text.match(/^(项目职责|主要职责|个人职责|负责内容)\s*[：:]?\s*(.*)$/)
      if (introMatch) {
        proj._introLabel = introMatch[1]
        proj._introText = introMatch[2]
        dutyMode = false
      } else if (dutyMatch) {
        proj._dutiesLabel = dutyMatch[1]
        dutyMode = true
        if (dutyMatch[2]) dutiesFromLegacy.push(dutyMatch[2].replace(/^\s*[（(]?\d+[）).、]\s*/, ''))
      } else if (dutyMode || /^\s*[（(]?\d+[）).、]/.test(text)) {
        dutiesFromLegacy.push(text.replace(/^\s*[（(]?\d+[）).、]\s*/, ''))
      } else if (text) {
        extras.push(text)
      }
    }
    proj._dutiesText = arrayToMultiline(dutiesFromLegacy)
    proj._extraDetailsText = arrayToMultiline(extras)
  }
}

function contentBlocksToEditableLines(item, { labelsAsContent = false } = {}) {
  const blocks = Array.isArray(item?.content_blocks) ? item.content_blocks : []
  if (!blocks.length) return item?.details || []
  const lines = []
  blocks.forEach(block => {
    const label = String(block?.label || '').trim()
    const editableLabel = labelsAsContent && label
      ? (block?.label_bold === false ? plainInlineText(label) : `**${plainInlineText(label)}**`)
      : label
    if (block?.type === 'paragraph') {
      const text = String(block?.text || '').trim()
      if (label || text) lines.push(label ? `${editableLabel}：${text}` : text)
      return
    }
    if (label) lines.push(`${editableLabel}：`)
    ;(block?.items || []).forEach((detail, index) => {
      const text = String(detail || '').trim()
      if (!text) return
      lines.push(block.type === 'numbered_list' ? `(${index + 1}) ${text}` : text)
    })
  })
  return lines
}

function initializeWorkContentEditor(work) {
  work._detailsText = arrayToMultiline(contentBlocksToEditableLines(work, { labelsAsContent: true }))
}

function editableWorkLinesToContentBlocks(work) {
  const lines = multilineToArray(work?._detailsText)
  const blocks = []
  let activeBlock = null
  for (const raw of lines) {
    const line = String(raw || '').trim()
    const numbered = /^\s*[（(]?\d+[）).、]/.test(plainInlineText(line))
    const type = numbered ? 'numbered_list' : 'bullet_list'
    if (!activeBlock || activeBlock.type !== type) {
      activeBlock = { type, label: '', label_bold: true, text: '', items: [] }
      blocks.push(activeBlock)
    }
    activeBlock.items.push(numbered ? line.replace(/^(\*\*)?\s*[（(]?\d+[）).、]\s*/, '$1') : line)
  }
  return blocks.filter(block => block.items.length)
}

// 打开简历编辑弹窗
function openResumeEditDialog() {
  // 深拷贝当前简历数据
  if (resumeData.value && Object.keys(resumeData.value).length > 0) {
    resumeFormData.value = JSON.parse(JSON.stringify(resumeData.value))
  } else {
    // 使用空结构
    resumeFormData.value = {
      basics: { name: '', gender: '', birth_date: '', phone: '', email: '', target_position: '', photo: '', additional_fields: [] },
      education: [],
      research_interests: [],
      honors: [],
      work_experience: [],
      project_experience: [],
      custom_sections: [],
      others: { skills: [], certificates: [], languages: [] },
      self_evaluation: []
    }
  }

  // 确保所有必要字段都存在（防御性编程）
  resumeFormData.value.basics = resumeFormData.value.basics || {}
  resumeFormData.value.basics.birth_date = resumeFormData.value.basics.birth_date || ''
  resumeFormData.value.basics.additional_fields = resumeFormData.value.basics.additional_fields || []
  resumeFormData.value.education = resumeFormData.value.education || []
  resumeFormData.value.research_interests = resumeFormData.value.research_interests || []
  resumeFormData.value.honors = resumeFormData.value.honors || []
  resumeFormData.value.work_experience = resumeFormData.value.work_experience || []
  resumeFormData.value.project_experience = resumeFormData.value.project_experience || []
  resumeFormData.value.custom_sections = resumeFormData.value.custom_sections || []
  resumeFormData.value.others = resumeFormData.value.others || { skills: [], certificates: [], languages: [] }
  resumeFormData.value.self_evaluation = resumeFormData.value.self_evaluation || []

  // 初始化日期范围和"至今"标志
  const initDateRange = (item) => {
    if (!item.date_range) {
      item.date_range = ['', '']
    }
    // 设置临时日期范围数组（用于 el-date-picker）
    const start = item.date_range[0] ? item.date_range[0].replace('.', '-') : null
    const end = item.date_range[1] && item.date_range[1] !== '至今'
      ? item.date_range[1].replace('.', '-')
      : null
    item._dateRange = start && end ? [start, end] : (start ? [start, null] : null)
    item._isPresent = item.date_range[1] === '至今'
  }

  // 为每项工作经历初始化日期
  resumeFormData.value.work_experience.forEach(work => {
    initDateRange(work)
    initializeWorkContentEditor(work)
  })

  // 为每项项目经历初始化日期
  resumeFormData.value.project_experience.forEach(proj => {
    initDateRange(proj)
    initializeProjectContentEditor(proj)
  })

  // 为每项教育经历初始化日期
  resumeFormData.value.education.forEach(edu => {
    initDateRange(edu)
    edu.gpa = edu.gpa || ''
    edu.gpa_scale = edu.gpa_scale || ''
    edu.ranking = edu.ranking || ''
    edu.average_score = edu.average_score || ''
  })

  resumeFormData.value.custom_sections.forEach(section => {
    section._itemsText = arrayToMultiline(section.items || [])
  })

  researchInterestsText.value = arrayToMultiline(resumeFormData.value.research_interests)
  honorsText.value = arrayToMultiline(resumeFormData.value.honors)
  // 转换自我评价为多行文本
  selfEvalText.value = arrayToMultiline(resumeFormData.value.self_evaluation || [])

  isResumeEditDialogOpen.value = true
}

// 处理"至今"复选框变化
function onPresentChange(item) {
  if (item._isPresent) {
    // 如果选中"至今"，保留开始日期，清空结束日期
    if (item._dateRange && item._dateRange.length === 2) {
      item._dateRange[1] = null
    }
  } else {
    // 如果取消"至今"，需要恢复结束日期选择
    if (item._dateRange && item._dateRange.length === 2) {
      // 如果原来有结束日期，恢复它
      if (item.date_range && item.date_range[1] && item.date_range[1] !== '至今') {
        item._dateRange[1] = item.date_range[1].replace('.', '-')
      } else {
        // 没有结束日期时，设置一个默认值（当前月）
        const now = new Date()
        item._dateRange[1] = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
      }
    }
  }
}

// 将日期范围转换为保存格式
function convertDateRangeToSave(item) {
  if (item._dateRange && item._dateRange.length === 2) {
    const start = item._dateRange[0] ? item._dateRange[0].replace('-', '.') : ''
    const end = item._isPresent ? '至今' : (item._dateRange[1] ? item._dateRange[1].replace('-', '.') : '')
    item.date_range = [start, end]
  } else if (item._dateRange && item._dateRange.length === 1) {
    item.date_range = [item._dateRange[0].replace('-', '.'), item._isPresent ? '至今' : '']
  } else {
    item.date_range = ['', item._isPresent ? '至今' : '']
  }
  // 清理临时字段
  delete item._dateRange
  delete item._isPresent
}

// 关闭简历编辑弹窗
function closeResumeEditDialog() {
  isResumeEditDialogOpen.value = false
  photoError.value = ''
}

// 处理证件照上传
function handlePhotoUpload(event) {
  const file = event.target.files[0]
  photoError.value = ''
  
  if (!file) return
  
  // 1. 验证文件类型
  if (!file.type.startsWith('image/')) {
    photoError.value = '请选择图片文件（jpg、png 等）'
    return
  }
  
  // 2. 验证文件大小（限制 2MB）
  if (file.size > 2 * 1024 * 1024) {
    photoError.value = '照片大小不能超过 2MB，请选择更小的图片'
    event.target.value = ''
    return
  }
  
  // 3. 读取并验证图片尺寸
  const reader = new FileReader()
  reader.onload = (e) => {
    const img = new Image()
    img.onload = () => {
      const width = img.width
      const height = img.height
      
      // 1寸照片比例约 3:3.5，允许误差 ±20%
      const ratio = width / height
      const targetRatio = 3 / 3.5  // 约 0.857
      const minRatio = targetRatio * 0.8
      const maxRatio = targetRatio * 1.2
      
      // 像素尺寸限制
      const minPixels = 200
      
      if (width < minPixels || height < minPixels) {
        photoError.value = `照片像素太低，请选择至少 ${minPixels}x${minPixels} 像素的图片`
        return
      }
      
      // 比例提示（非强制）
      if (ratio < minRatio || ratio > maxRatio) {
        console.warn('照片比例偏离 1 寸标准')
      }
      
      // 4. 压缩图片
      compressAndSave(img)
    }
    img.src = e.target.result
  }
  reader.readAsDataURL(file)
}

// 压缩并保存图片
function compressAndSave(img) {
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  
  // 限制最大尺寸
  const MAX_SIZE = 400
  let width = img.width
  let height = img.height
  
  if (width > height) {
    if (width > MAX_SIZE) {
      height = height * (MAX_SIZE / width)
      width = MAX_SIZE
    }
  } else {
    if (height > MAX_SIZE) {
      width = width * (MAX_SIZE / height)
      height = MAX_SIZE
    }
  }
  
  canvas.width = width
  canvas.height = height
  ctx.drawImage(img, 0, 0, width, height)
  
  // 转换为 Base64（质量 0.8）
  resumeFormData.value.basics.photo = canvas.toDataURL('image/jpeg', 0.8)
}

// 删除证件照
function removePhoto() {
  resumeFormData.value.basics.photo = ''
  photoError.value = ''
  // 清空文件输入
  const input = document.querySelector('.photo-input')
  if (input) input.value = ''
}

// 添加学历
function addEducation() {
  resumeFormData.value.education.push({
    school_name: '',
    major: '',
    degree: '',
    date_range: ['', ''],
    school_tags: [],
    gpa: '',
    gpa_scale: '',
    ranking: '',
    average_score: '',
    theses: []
  })
}

// 删除学历
function removeEducation(index) {
  resumeFormData.value.education.splice(index, 1)
}

// 添加学校标签
function addSchoolTag(edu) {
  if (edu.newSchoolTag && edu.newSchoolTag.trim()) {
    edu.school_tags.push(edu.newSchoolTag.trim())
    edu.newSchoolTag = ''
  }
}

// 添加工作经历
function addWork() {
  resumeFormData.value.work_experience.push({
    company_name: '',
    job_title: '',
    date_range: ['', ''],
    job_type: '全职',
    details: ['']
  })
}

// 删除工作经历
function removeWork(index) {
  resumeFormData.value.work_experience.splice(index, 1)
}

// 添加工作内容
function addWorkDetail(work) {
  work.details.push('')
}

// 删除工作内容
function removeWorkDetail(work, index) {
  work.details.splice(index, 1)
}

// 添加项目经历
function addProject() {
  resumeFormData.value.project_experience.push({
    project_name: '',
    role: '',
    date_range: ['', ''],
    content_blocks: [],
    details: [],
    _introLabel: '项目简介',
    _dutiesLabel: '项目职责',
    _introLabelBold: true,
    _dutiesLabelBold: true,
    _introText: '',
    _dutiesText: '',
    _extraDetailsText: ''
  })
}

// 删除项目经历
function removeProject(index) {
  resumeFormData.value.project_experience.splice(index, 1)
}

// 标签添加方法
function addResumeSkill() {
  if (newResumeSkill.value.trim()) {
    resumeFormData.value.others.skills.push(newResumeSkill.value.trim())
    newResumeSkill.value = ''
  }
}

function addResumeCert() {
  if (newResumeCert.value.trim()) {
    resumeFormData.value.others.certificates.push(newResumeCert.value.trim())
    newResumeCert.value = ''
  }
}

function addResumeLang() {
  if (newResumeLang.value.trim()) {
    resumeFormData.value.others.languages.push(newResumeLang.value.trim())
    newResumeLang.value = ''
  }
}

// 加载简历数据
async function loadResume() {
  try {
    const response = await fetch('/load_resume', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({})
    })
    const data = await response.json()
    resumeData.value = data
  } catch (error) {
    console.error('加载简历失败:', error)
  }
}

// 辅助函数：日期格式转换 YYYY-MM -> YYYY.MM
function formatDateForSave(dateStr) {
  if (!dateStr) return ''
  // 如果已经是 YYYY.MM 格式，直接返回
  if (dateStr.includes('.')) return dateStr
  // YYYY-MM 转换为 YYYY.MM
  return dateStr.replace('-', '.')
}

// 将数组转换为多行文本（用于编辑）
function arrayToMultiline(arr) {
  if (!arr || !Array.isArray(arr)) return ''
  return arr.filter(item => item.trim()).join('\n')
}

// 将多行文本转换为数组（用于保存）
function multilineToArray(text) {
  if (!text) return []
  return text.split('\n').map(line => line.trim()).filter(line => line)
}

function addCustomSection() {
  resumeFormData.value.custom_sections.push({ title: '', items: [], _itemsText: '' })
}

function removeCustomSection(index) {
  resumeFormData.value.custom_sections.splice(index, 1)
}

function addBasicAdditionalField() {
  resumeFormData.value.basics.additional_fields.push({ label: '', value: '' })
}

function removeBasicAdditionalField(index) {
  resumeFormData.value.basics.additional_fields.splice(index, 1)
}

// 保存简历
async function saveResume() {
  isSaving.value = true
  try {
    // 复制数据进行处理
    const dataToSave = JSON.parse(JSON.stringify(resumeFormData.value))

    // 处理性别：保密 -> 空字符串
    if (dataToSave.basics.gender === '保密') {
      dataToSave.basics.gender = ''
    }

    // 处理日期格式：确保是 YYYY.MM 格式
    dataToSave.education?.forEach(edu => {
      convertDateRangeToSave(edu)
    })
    dataToSave.work_experience?.forEach(work => {
      convertDateRangeToSave(work)
      if (work._detailsText !== undefined) {
        work.content_blocks = editableWorkLinesToContentBlocks(work)
        work.details = []
        delete work._detailsText
      }
    })
    dataToSave.project_experience?.forEach(proj => {
      convertDateRangeToSave(proj)
      const introText = String(proj._introText || '').trim()
      const duties = multilineToArray(proj._dutiesText)
      const extras = multilineToArray(proj._extraDetailsText)
      proj.content_blocks = []
      if (introText) proj.content_blocks.push({ type: 'paragraph', label: proj._introLabel || '项目简介', label_bold: proj._introLabelBold !== false, text: introText, items: [] })
      if (duties.length) proj.content_blocks.push({ type: 'numbered_list', label: proj._dutiesLabel || '项目职责', label_bold: proj._dutiesLabelBold !== false, text: '', items: duties })
      if (extras.length) proj.content_blocks.push({ type: 'bullet_list', label: '', label_bold: true, text: '', items: extras })
      proj.details = []
      delete proj._introLabel
      delete proj._dutiesLabel
      delete proj._introLabelBold
      delete proj._dutiesLabelBold
      delete proj._introText
      delete proj._dutiesText
      delete proj._extraDetailsText
    })

    dataToSave.research_interests = multilineToArray(researchInterestsText.value)
    dataToSave.honors = multilineToArray(honorsText.value)
    dataToSave.custom_sections = (dataToSave.custom_sections || [])
      .map(section => ({
        title: String(section.title || '').trim(),
        items: multilineToArray(section._itemsText !== undefined ? section._itemsText : arrayToMultiline(section.items || []))
      }))
      .filter(section => section.title && section.items.length)

    // 将自我评价多行文本转换回数组
    dataToSave.self_evaluation = multilineToArray(selfEvalText.value)

    const response = await fetch('/save_resume', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ resume_data: dataToSave })
    })

    if (response.ok) {
      closeResumeEditDialog()
      // 刷新简历渲染
      loadResume()
    } else {
      showNotice('保存失败，请重试')
    }
  } catch (error) {
    console.error('保存简历失败:', error)
    showNotice('保存失败，请重试')
  } finally {
    isSaving.value = false
  }
}

// 解析岗位信息
async function parseJD() {
  if (!jdInputText.value.trim() && !jdInputImage.value) {
    showNotice('请输入职位描述或粘贴图片')
    return
  }

  isParsingJD.value = true
  try {
    const response = await fetch('/parse_jd', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        text: jdInputText.value,
        image: jdInputImage.value
      })
    })

    if (!response.ok) {
      throw new Error('识别失败')
    }

    const result = await response.json()

    if (result.error) {
      showNotice('识别失败: ' + result.error)
      return
    }

    // 确保所有字段都存在
    jdFormData.value = {
      company: result.company || '',
      position: result.position || '',
      department: result.department || '',
      location: result.location || '',
      job_type: result.job_type || '',
      salary: result.salary || '',
      description: result.description || '',
      requirements: {
        education: result.requirements?.education || '',
        experience: result.requirements?.experience || '',
        skills: result.requirements?.skills || [],
        language: result.requirements?.language || ''
      },
      preferred_qualifications: result.preferred_qualifications || [],
      highlights: result.highlights || []
    }

    jdInputMode.value = 'form'
  } catch (error) {
    console.error('识别失败:', error)
    showNotice('识别失败，请重试')
  } finally {
    isParsingJD.value = false
  }
}

// 保存岗位信息
async function saveJD() {
  isSaving.value = true
  try {
    const response = await fetch('/save_jd', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        jd_data: jdFormData.value,
        session_id: sessionId.value
      })
    })

    const result = await response.json()

    if (result.success) {
      jdData.value = { ...jdFormData.value }
      isJDDialogOpen.value = false
    } else {
      showNotice('保存失败: ' + (result.error || '未知错误'))
    }
  } catch (error) {
    console.error('保存失败:', error)
    showNotice('保存失败，请重试')
  } finally {
    isSaving.value = false
  }
}

// 添加技能标签
function addSkill() {
  const skill = newSkill.value.trim()
  if (skill && !jdFormData.value.requirements.skills.includes(skill)) {
    jdFormData.value.requirements.skills.push(skill)
    newSkill.value = ''
  }
}

// 删除技能标签
function removeSkill(index) {
  jdFormData.value.requirements.skills.splice(index, 1)
}

// 处理图片上传
function handleJDImageUpload(event) {
  const file = event.target.files[0]
  if (file) {
    const reader = new FileReader()
    reader.onload = (e) => {
      jdInputImage.value = e.target.result
    }
    reader.readAsDataURL(file)
  }
}

// 处理粘贴事件（支持图片粘贴）
function handleJDPaste(event) {
  const items = event.clipboardData?.items
  if (!items) return

  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.type.startsWith('image/')) {
      event.preventDefault()
      const file = item.getAsFile()
      const reader = new FileReader()
      reader.onload = (e) => {
        jdInputImage.value = e.target.result
      }
      reader.readAsDataURL(file)
      break
    }
  }
}

// 辅助函数：将逗号分隔的文本转换为数组
function parseCommaSeparated(text) {
  if (!text) return []
  return text.split(',').map(s => s.trim()).filter(s => s)
}

// 将数组转换为逗号分隔的文本（用于表单绑定）
function arrayToCommaSeparated(arr) {
  if (!arr || !Array.isArray(arr)) return ''
  return arr.join(', ')
}

// 更新优先条件数组
function updatePreferredQualifications() {
  jdFormData.value.preferred_qualifications = parseCommaSeparated(jdFormData.value.preferred_qualifications_text)
}

// 更新亮点数组
function updateHighlights() {
  jdFormData.value.highlights = parseCommaSeparated(jdFormData.value.highlights_text)
}

// 在解析后初始化文本字段
function initFormTexts() {
  jdFormData.value.preferred_qualifications_text = arrayToCommaSeparated(jdFormData.value.preferred_qualifications)
  jdFormData.value.highlights_text = arrayToCommaSeparated(jdFormData.value.highlights)
}

// 在解析成功后调用初始化
const originalParseJD = parseJD
parseJD = async function() {
  await originalParseJD()
  if (jdInputMode.value === 'form') {
    initFormTexts()
  }
}

// 打开全屏弹窗
function openFullscreenDialog() {
  dialogUserInput.value = userInput.value
  isFullscreenDialogOpen.value = true
  nextTick(() => {
    const dialogTextarea = document.querySelector('.dialog-textarea')
    if (dialogTextarea) {
      dialogTextarea.focus()
    }
  })
}

// 关闭全屏弹窗（不保存内容）
function closeFullscreenDialog() {
  isFullscreenDialogOpen.value = false
}

// 保存弹窗内容到输入框
function saveDialogContent() {
  userInput.value = dialogUserInput.value
  isFullscreenDialogOpen.value = false
}

// 提交弹窗内容
function submitFullscreenDialog() {
  if (dialogUserInput.value.trim()) {
    userInput.value = dialogUserInput.value.trim()
    isFullscreenDialogOpen.value = false
    sendMessage()
  }
}

// 监听ESC键关闭弹窗
function handleDialogKeydown(event) {
  if (event.key === 'Escape') {
    closeFullscreenDialog()
  } else if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    submitFullscreenDialog()
  }
}

// ==================== 首次进入选择弹窗 ====================

// 打开开始选择弹窗（首次进入且无简历时）
function openStartDialog() {
  showStartDialog.value = true
}

// 关闭开始弹窗
function closeStartDialog() {
  showStartDialog.value = false
}

async function cancelNewProjectOnboarding() {
  showStartDialog.value = false
  showIdentityDialog.value = false
  showUploadDialog.value = false

  if (route.query.new === '1' && currentProject.value?.id) {
    try {
      const response = await fetch(`/projects/${currentProject.value.id}`, {
        method: 'DELETE',
        headers: getAuthorizationHeaders()
      })
      if (!response.ok) {
        throw new Error('删除未完成的简历失败')
      }
    } catch (error) {
      showNotice(error.message || '取消创建失败，请重试')
      showStartDialog.value = true
      return
    }
  }
  await router.push('/')
}

async function completeNewProjectOnboarding() {
  if (route.query.new !== '1') return
  await router.replace({
    name: route.name,
    params: route.params
  })
}

// 从空白创建简历 - 打开身份选择弹窗
function startFromBlank() {
  closeStartDialog()
  // 打开身份选择弹窗
  showIdentityDialog.value = true
  selectedIdentity.value = null
  customIdentity.value = ''
}

// 关闭身份选择弹窗
function closeIdentityDialog() {
  showIdentityDialog.value = false
  selectedIdentity.value = null
  customIdentity.value = ''
}

// 从身份选择返回上一步（回到开始选择弹窗）
function backToStartFromIdentity() {
  showIdentityDialog.value = false
  selectedIdentity.value = null
  customIdentity.value = ''
  showStartDialog.value = true
}

// 处理预设身份选择
function selectIdentity(identity) {
  selectedIdentity.value = identity
  customIdentity.value = ''
}

// 确认身份选择
async function confirmIdentitySelection() {
  if (!selectedIdentity.value) {
    showNotice('请选择一个身份类型')
    return
  }

  if (selectedIdentity.value === 'custom' && !customIdentity.value.trim()) {
    showNotice('请输入你的身份描述')
    return
  }

  // 先保存选择的身份，因为 closeIdentityDialog 会重置 selectedIdentity
  const identity = selectedIdentity.value
  const customDesc = customIdentity.value.trim()

  closeIdentityDialog()
  closeStartDialog()
  await completeNewProjectOnboarding()

  if (identity === 'custom') {
    // 自定义身份：调用后端 API 获取首次提问
    isLoading.value = true
    try {
      const response = await fetch('/api/chat/first_message', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          user_type: 'custom',
          custom_identity: customDesc,
          session_id: sessionId.value || ''
        })
      })

      const data = await response.json()
      
      isLoading.value = false

      if (data.error) {
        showNotice(data.error)
        return
      }

      const aiMessage = data.message || data.content

      messages.value = [{
        id: Date.now(),
        role: 'assistant',
        content: aiMessage
      }]

      // 保存 session_id 到全局
      if (data.session_id) {
        sessionId.value = data.session_id
      }

      // 保存对话到数据库（后端已保存，但确保前端也保存一次）
      try {
        await fetch('/save_conversation', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            session_id: sessionId.value,
            messages: [
              { type: 'human', content: `我的身份描述：${customDesc}` },
              { type: 'ai', content: aiMessage }
            ]
          })
        })
      } catch (saveError) {
        console.error('保存对话失败:', saveError)
      }

      // 调用后端保存 AI 消息（保存到数据库和上下文）
      try {
        await fetch('/api/chat/save_ai_message', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            message: aiMessage,
            session_id: sessionId.value || ''
          })
        })
      } catch (saveAiError) {
        console.error('保存 AI 消息失败:', saveAiError)
      }
    } catch (error) {
      isLoading.value = false
      console.error('获取首次提问失败:', error)
      showNotice('获取首次提问失败，请重试')
    }
  } else {
    // 预设身份：直接使用预制消息并保存到数据库
    isLoading.value = true
    const greeting = IDENTITY_GREETINGS[identity]
    const aiMessage = greeting.content

    messages.value = [{
      id: Date.now(),
      role: greeting.role,
      content: aiMessage
    }]

    // 保存对话到数据库
    try {
      await fetch('/save_conversation', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          session_id: sessionId.value,
          messages: [{ type: 'ai', content: aiMessage }]
        })
      })
    } catch (saveError) {
      console.error('保存对话失败:', saveError)
    }

    isLoading.value = false

    // 调用后端保存 AI 消息
    try {
      const saveResponse = await fetch('/api/chat/save_ai_message', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          message: greeting.content,
          session_id: sessionId.value || ''
        })
      })

      const saveData = await saveResponse.json()
      if (saveData.session_id) {
        sessionId.value = saveData.session_id
      }
    } catch (saveError) {
      console.error('保存消息失败:', saveError)
    }
  }
}

// 显示上传弹窗
function showUploadResumeDialog() {
  closeStartDialog()
  showUploadDialog.value = true
  resumeImagePreview.value = ''
  resumeImageFile.value = null
  isResumePdf.value = false
  hasResumeFileSelected.value = false  // 重置，允许返回
  resumeImportDraft.value = null
  resumeImportError.value = ''
}

// 触发文件选择器
function triggerResumeFileSelect() {
  resumeFileInput.value?.click()
}

// 从创建方式弹窗直接打开系统文件选择器；取消选择时仍停留在当前弹窗。
function selectResumeFileFromStart() {
  resumeImagePreview.value = ''
  resumeImageFile.value = null
  isResumePdf.value = false
  hasResumeFileSelected.value = false
  resumeImportDraft.value = null
  resumeImportError.value = ''
  startResumeFileInput.value?.click()
}

// 关闭上传弹窗
async function discardPendingResumeSource() {
  const token = resumeImportDraft.value?.source_document_token
  if (!token) return
  try {
    await fetch(`/api/resume/import_drafts/${token}`, {
      method: 'DELETE',
      headers: getAuthorizationHeaders()
    })
  } catch (error) {
    console.warn('清理待确认原稿失败:', error)
  }
}

async function closeUploadDialog() {
  await discardPendingResumeSource()
  showUploadDialog.value = false
  resumeImagePreview.value = ''
  resumeImageFile.value = null
  isResumePdf.value = false
  hasResumeFileSelected.value = false
  resumeImportDraft.value = null
  resumeImportError.value = ''
}

// 返回上一步（回到开始选择弹窗）
async function backToStartDialog() {
  await discardPendingResumeSource()
  showUploadDialog.value = false
  resumeImagePreview.value = ''
  resumeImageFile.value = null
  isResumePdf.value = false
  hasResumeFileSelected.value = false
  showStartDialog.value = true
}

// 重新选择文件
async function reselectResumeFile() {
  await discardPendingResumeSource()
  resumeImagePreview.value = ''
  resumeImageFile.value = null
  isResumePdf.value = false
  hasResumeFileSelected.value = false  // 重置，允许返回
  resumeImportDraft.value = null
  resumeImportError.value = ''
}

// 处理简历图片选择
function handleResumeImageSelect(event) {
  const file = event.target.files[0]
  if (!file) return
  const selectedFromStart = showStartDialog.value

  // 验证文件类型
  if (!file.type.startsWith('image/') && file.type !== 'application/pdf') {
    showNotice('请上传图片文件（JPG、PNG）或 PDF')
    event.target.value = ''
    return
  }

  // 验证文件大小（5MB）
  if (file.size > 5 * 1024 * 1024) {
    showNotice('文件大小不能超过 5MB')
    event.target.value = ''
    return
  }

  resumeImageFile.value = file
  hasResumeFileSelected.value = true  // 已选择文件，不可返回上一步

  // 检测是否是PDF文件
  isResumePdf.value = file.type === 'application/pdf'

  // 生成预览（PDF不生成图片预览，只显示图标）
  if (isResumePdf.value) {
    resumeImagePreview.value = 'pdf'  // 设置为非空值以触发界面切换
    if (selectedFromStart) {
      closeStartDialog()
      showUploadDialog.value = true
    }
  } else {
    const reader = new FileReader()
    reader.onload = (e) => {
      resumeImagePreview.value = e.target.result
      if (selectedFromStart) {
        closeStartDialog()
        showUploadDialog.value = true
      }
    }
    reader.readAsDataURL(file)
  }
  event.target.value = ''
}

// 解析并保存简历
async function parseAndSaveResume(confirmedData = null) {
  if (!confirmedData || confirmedData.success !== true) confirmedData = null
  if (!confirmedData && !resumeImageFile.value) {
    showNotice('请先选择简历图片')
    return
  }

  isParsingResume.value = true
  resumeImportError.value = ''

  try {
    let data = confirmedData
    if (!data) {
      const formData = new FormData()
      formData.append('file', resumeImageFile.value)
      formData.append('draft_only', 'true')
      const response = await fetch('/api/resume/parse_and_save', {
        method: 'POST', headers: getAuthorizationHeaders(), body: formData
      })
      data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.error || data.detail || '解析失败')
    }

    if (data.success && data.draft) {
      resumeImportDraft.value = data
    } else if (data.success) {
      // 更新简历数据
      resumeData.value = data.resume_data
      const task = projectTasks.value.find(item => item.id === currentTaskId.value)
      if (task) {
        if (data.source_page_count) task.source_page_count = data.source_page_count
        if (data.has_source_document) task.has_source_document = true
      }
      closeUploadDialog()
      await completeNewProjectOnboarding()

      if (messages.value.length === 0) {
        messages.value = [{ id: Date.now(), role: 'assistant', content: WELCOME_MESSAGE, localOnly: true }]
      }
      showNotice('简历已成功导入', 'success')
    } else {
      resumeImportError.value = data.error || '解析失败'
      showNotice('解析失败：' + resumeImportError.value)
      // 解析失败，保留状态让用户可以重试
    }
  } catch (error) {
    console.error('解析简历失败:', error)
    resumeImportError.value = error.message || '解析简历失败，请稍后重试'
    showNotice(resumeImportError.value)
  } finally {
    // 失败时保留文件和预览，便于用户切换模型后直接重试。
    // 成功时 closeUploadDialog 已经完整重置这些状态。
    isParsingResume.value = false
  }
}

async function confirmResumeImport() {
  if (!resumeImportDraft.value || isParsingResume.value) return
  isParsingResume.value = true
  resumeImportError.value = ''
  try {
    const response = await fetch('/api/resume/confirm_import', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        resume_data: resumeImportDraft.value.resume_data,
        source_page_count: resumeImportDraft.value.source_page_count || 1,
        source_document_token: resumeImportDraft.value.source_document_token || null
      })
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok || !data.success) throw new Error(data.detail || '保存导入结果失败')
    resumeImportDraft.value = null
    await parseAndSaveResume(data)
  } catch (error) {
    resumeImportError.value = error.message || '保存导入结果失败'
  } finally {
    isParsingResume.value = false
  }
}

// 自动滚动到底部，添加丝滑过渡效果
function scrollToBottom(behavior = 'smooth') {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTo({
      top: messagesContainer.value.scrollHeight,
      behavior
    })
    isChatNearBottom.value = true
    showScrollToBottomButton.value = false
  }
}

// 滑动至底部按钮状态
const showScrollToBottomButton = ref(false)
const isChatNearBottom = ref(true)
let scrollThrottleTimer = null

// 检查是否需要显示滑动至底部按钮
function checkScrollPosition() {
  if (!messagesContainer.value) return
  
  const { scrollTop, scrollHeight, clientHeight } = messagesContainer.value
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight
  
  isChatNearBottom.value = distanceFromBottom <= 120
  showScrollToBottomButton.value = !isChatNearBottom.value
}

// 滚动事件节流处理（100ms间隔）
function handleScroll() {
  if (scrollThrottleTimer) return
  
  scrollThrottleTimer = setTimeout(() => {
    scrollThrottleTimer = null
    checkScrollPosition()
  }, 100)
}

// 点击滑动至底部按钮
function handleScrollToBottomClick() {
  scrollToBottom()
}

// 监听消息列表变化，自动滚动到底部
// 使用deep: true监听消息内容的变化，确保流式输出时也能自动滚动
watch(
  () => messages.value,
  () => {
    const shouldFollowLatest = isChatNearBottom.value
    nextTick(() => {
      if (shouldFollowLatest) scrollToBottom('auto')
      else checkScrollPosition()
    })
  },
  { deep: true }
)
</script>

<template>
  <Teleport to="body">
    <Transition name="toast">
      <div v-if="uiNotice.visible" :class="['app-toast', `is-${uiNotice.type}`]" role="status">
        {{ uiNotice.message }}
      </div>
    </Transition>
  </Teleport>

  <!-- 新建岗位版本弹窗 -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="showTaskCreateDialog" class="workspace-modal-mask" @click.self="closeTaskCreateDialog">
        <form class="workspace-modal" @submit.prevent="confirmCreateProjectTask">
          <div class="workspace-modal-header">
            <div>
              <span class="workspace-modal-kicker">岗位版本</span>
              <h2>新建岗位版本</h2>
            </div>
            <button type="button" class="modal-close-btn" aria-label="关闭" @click="closeTaskCreateDialog">×</button>
          </div>
          <div class="task-create-steps" aria-label="创建进度">
            <span v-for="step in 3" :key="step" :class="{ active: taskCreateStep >= step }">{{ step }}</span>
          </div>

          <section v-if="taskCreateStep === 1" class="task-create-panel">
            <div class="task-step-heading">
              <strong>选择简历来源</strong>
              <small>只复制简历内容和照片，不复制原 JD 或对话。</small>
            </div>
            <fieldset class="copy-mode-fieldset">
              <label :class="['copy-mode-card', { active: taskCreateMode === 'copy' }]">
                <input v-model="taskCreateMode" type="radio" value="copy" />
                <span class="copy-mode-icon">⎘</span>
                <span><strong>复制现有简历</strong><small>创建独立副本，后续修改互不影响。</small></span>
              </label>
              <label :class="['copy-mode-card', { active: taskCreateMode === 'blank' }]">
                <input v-model="taskCreateMode" type="radio" value="blank" />
                <span class="copy-mode-icon">＋</span>
                <span><strong>创建空白版本</strong><small>不带入任何简历内容。</small></span>
              </label>
              <label :class="['copy-mode-card', { active: taskCreateMode === 'import' }]">
                <input v-model="taskCreateMode" type="radio" value="import" />
                <span class="copy-mode-icon">⇧</span>
                <span><strong>导入现有简历</strong><small>上传 JPG、PNG 或 PDF，自动解析为新版本。</small></span>
              </label>
            </fieldset>

            <div v-if="taskCreateMode === 'copy'" class="resume-source-picker">
              <strong class="source-group-title">当前主简历</strong>
              <label v-for="source in currentProjectSources" :key="source.id" class="resume-source-row">
                <input v-model="taskSourceId" type="radio" :value="source.id" />
                <span><b>{{ source.is_base ? '基础简历' : source.title }}</b><small>{{ source.target_position || source.candidate_name || '未填写目标岗位' }}</small></span>
              </label>
              <details v-if="otherProjectSourceGroups.length" class="other-resume-sources">
                <summary>其他主简历</summary>
                <div v-for="group in otherProjectSourceGroups" :key="group.id" class="source-project-group">
                  <strong>{{ group.title }}</strong>
                  <label v-for="source in group.sources" :key="source.id" class="resume-source-row">
                    <input v-model="taskSourceId" type="radio" :value="source.id" />
                    <span><b>{{ source.is_base ? '基础简历' : source.title }}</b><small>{{ source.target_position || source.candidate_name || '未填写目标岗位' }}</small></span>
                  </label>
                </div>
              </details>
            </div>
            <div v-else-if="taskCreateMode === 'import'" class="task-import-picker">
              <input
                ref="taskImportInput"
                type="file"
                accept="image/jpeg,image/png,application/pdf"
                class="hidden-input"
                @change="handleTaskImportFile"
              />
              <button type="button" class="task-import-button" @click="selectTaskImportFile">
                <strong>{{ taskImportFile ? taskImportFile.name : '选择简历文件' }}</strong>
                <small>{{ taskImportFile ? '点击可重新选择' : '支持 JPG、PNG、PDF，最大 5MB' }}</small>
              </button>
            </div>
          </section>

          <section v-else-if="taskCreateStep === 2" class="task-create-panel">
            <div class="task-step-heading">
              <strong>添加目标岗位 JD</strong>
              <small>粘贴岗位描述后自动识别；暂时没有 JD 也可以跳过。</small>
            </div>
            <textarea v-model="taskJDText" class="task-jd-input" rows="10" placeholder="在这里粘贴完整的职位描述（JD）…"></textarea>
          </section>

          <section v-else class="task-create-panel task-review-panel">
            <div class="task-step-heading">
              <strong>确认新版本</strong>
              <small>创建后仍可继续编辑简历和岗位信息。</small>
            </div>
            <label class="workspace-field">
              <span>版本名称</span>
              <input v-model="newTaskTitle" maxlength="80" placeholder="例如：字节跳动 · 后端开发" />
            </label>
            <dl class="task-review-list">
              <div><dt>简历来源</dt><dd>{{ taskCreateMode === 'blank' ? '空白简历' : taskCreateMode === 'import' ? `导入：${taskImportFile?.name || ''}` : `${selectedTaskSource?.project_title || ''} / ${selectedTaskSource?.is_base ? '基础简历' : selectedTaskSource?.title || ''}` }}</dd></div>
              <div><dt>目标岗位</dt><dd>{{ taskJDData.position || '暂未添加 JD' }}</dd></div>
              <div v-if="taskJDData.company"><dt>公司</dt><dd>{{ taskJDData.company }}</dd></div>
            </dl>
          </section>
          <p v-if="taskCreateError" class="workspace-modal-error">{{ taskCreateError }}</p>
          <div class="workspace-modal-footer">
            <button v-if="taskCreateStep === 1" type="button" class="workspace-btn secondary" @click="closeTaskCreateDialog">取消</button>
            <button v-else type="button" class="workspace-btn secondary" :disabled="isCreatingTask || isParsingTaskJD" @click="taskCreateStep--">上一步</button>
            <button v-if="taskCreateStep === 1" type="button" class="workspace-btn primary" @click="goToTaskJDStep">下一步</button>
            <template v-else-if="taskCreateStep === 2">
              <button type="button" class="workspace-btn secondary" :disabled="isParsingTaskJD" @click="goToTaskReview({ skipJD: true })">暂不添加 JD</button>
              <button type="button" class="workspace-btn primary" :disabled="isParsingTaskJD || !taskJDText.trim()" @click="goToTaskReview()">
                {{ isParsingTaskJD ? '识别中…' : '识别并继续' }}
              </button>
            </template>
            <button v-else type="submit" class="workspace-btn primary" :disabled="isCreatingTask">
              {{ isCreatingTask ? (taskCreateMode === 'import' ? '导入并创建中…' : '创建中…') : '创建版本' }}
            </button>
          </div>
        </form>
      </div>
    </Transition>
  </Teleport>

  <!-- 删除岗位版本弹窗 -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="taskToDelete" class="workspace-modal-mask" @click.self="closeTaskDeleteDialog">
        <div class="workspace-modal compact">
          <div class="workspace-modal-header">
            <div>
              <span class="workspace-modal-kicker danger">删除岗位版本</span>
              <h2>删除岗位版本？</h2>
            </div>
            <button type="button" class="modal-close-btn" aria-label="关闭" @click="closeTaskDeleteDialog">×</button>
          </div>
          <p class="workspace-modal-copy">
            “{{ taskToDelete.title }}”及其 JD、对话记录会一并删除。主简历不受影响，此操作无法撤销。
          </p>
          <p v-if="taskDeleteError" class="workspace-modal-error">{{ taskDeleteError }}</p>
          <div class="workspace-modal-footer">
            <button type="button" class="workspace-btn secondary" :disabled="isDeletingTask" @click="closeTaskDeleteDialog">取消</button>
            <button type="button" class="workspace-btn danger" :disabled="isDeletingTask" @click="confirmDeleteProjectTask">
              {{ isDeletingTask ? '删除中…' : '确认删除' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 首次进入选择弹窗 -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="showStartDialog" class="modal-mask" @click.self="cancelNewProjectOnboarding">
        <div class="modal-container start-modal" @click.stop>
          <div class="modal-header">
            <div class="header-badge">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
              </svg>
            </div>
            <h2>创建简历</h2>
            <button type="button" class="modal-close-btn light" aria-label="取消创建" @click="cancelNewProjectOnboarding">×</button>
          </div>
          <p class="modal-desc">选择一种方式开始创建你的简历</p>
          <input
            ref="startResumeFileInput"
            type="file"
            accept="image/jpeg,image/png,application/pdf"
            class="hidden-input"
            @change="handleResumeImageSelect"
          />
          <div class="option-list">
            <button @click="startFromBlank" class="option-item">
              <div class="optionGraphic graphic-plus">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="12" y1="5" x2="12" y2="19"></line>
                  <line x1="5" y1="12" x2="19" y2="12"></line>
                </svg>
              </div>
              <div class="option-content">
                <span class="option-label">从空白创建</span>
                <span class="option-sublabel">手动填写，逐步完善</span>
              </div>
              <svg class="option-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="9 18 15 12 9 6"></polyline>
              </svg>
            </button>
            <button @click="selectResumeFileFromStart" class="option-item">
              <div class="optionGraphic graphic-upload">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
              </div>
              <div class="option-content">
                <span class="option-label">导入现有简历</span>
                <span class="option-sublabel">支持图片或 PDF，自动解析</span>
              </div>
              <svg class="option-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="9 18 15 12 9 6"></polyline>
              </svg>
            </button>
          </div>
          <div class="modal-footer start-modal-footer">
            <button type="button" class="btn-secondary full-width" @click="cancelNewProjectOnboarding">取消</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 身份选择弹窗 -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="showIdentityDialog" class="modal-mask">
        <div class="modal-container start-modal identity-selection" @click.stop>
          <div class="modal-header">
            <div class="header-badge">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                <circle cx="12" cy="7" r="4"></circle>
              </svg>
            </div>
            <h2>选择你的身份</h2>
            <div class="modal-actions">
              <button @click="backToStartFromIdentity" class="modal-back">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="19" y1="12" x2="5" y2="12"></line>
                  <polyline points="12 19 5 12 12 5"></polyline>
                </svg>
                返回
              </button>
            </div>
          </div>
          <p class="modal-desc">选择最符合你当前情况的身份类型</p>
          
          <div class="identity-cards-container">
            <!-- 四个身份卡片竖排 -->
            <div class="identity-cards-row">
              <!-- 寻找实习 -->
              <button 
                @click="selectIdentity('intern')" 
                :class="['identity-card', { active: selectedIdentity === 'intern' }]"
              >
                <div class="identity-icon">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M22 10v6M2 10l10-5 10 5-10 5z"/>
                    <path d="M6 12v5c3 3 9 3 12 0v-5"/>
                  </svg>
                </div>
                <div class="identity-card-content">
                  <div class="identity-title">寻找实习</div>
                  <div class="identity-desc">正在寻找实习机会的学生</div>
                </div>
              </button>
              
              <!-- 校招应届 -->
              <button 
                @click="selectIdentity('campus')" 
                :class="['identity-card', { active: selectedIdentity === 'campus' }]"
              >
                <div class="identity-icon pink">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M22 10v6M2 10l10-5 10 5-10 5z"/>
                    <path d="M6 12v5c3 3 9 3 12 0v-5"/>
                    <path d="M12 16v4"/>
                  </svg>
                </div>
                <div class="identity-card-content">
                  <div class="identity-title">校招应届</div>
                  <div class="identity-desc">准备参加校园招聘的应届毕业生</div>
                </div>
              </button>
              
              <!-- 跳槽转型 -->
              <button 
                @click="selectIdentity('jobhop')" 
                :class="['identity-card', { active: selectedIdentity === 'jobhop' }]"
              >
                <div class="identity-icon">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/>
                    <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
                  </svg>
                </div>
                <div class="identity-card-content">
                  <div class="identity-title">跳槽转型</div>
                  <div class="identity-desc">计划跳槽的职场白领</div>
                </div>
              </button>

              <!-- 自定义 -->
              <button 
                @click="selectIdentity('custom')" 
                :class="['identity-card', { active: selectedIdentity === 'custom' }]"
              >
                <div class="identity-icon pink">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </div>
                <div class="identity-card-content">
                  <div class="identity-title">自定义</div>
                  <div class="identity-desc">不符合上述选项，描述你的情况</div>
                </div>
              </button>
            </div>

            <!-- 自定义身份输入框 -->
            <div v-if="selectedIdentity === 'custom'" class="custom-identity-input">
              <textarea 
                v-model="customIdentity" 
                placeholder="请简单描述你的情况，例如：我是工作3年的产品经理，想转行做技术..."
                rows="3"
              ></textarea>
            </div>
          </div>

          <div class="modal-footer">
            <button @click="confirmIdentitySelection" :disabled="!selectedIdentity || (selectedIdentity === 'custom' && !customIdentity.trim())" class="btn-primary full-width">
              开始创建简历
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 简历上传弹窗 -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="showUploadDialog" class="modal-mask">
        <div class="modal-container upload-modal" @click.stop>
          <div class="modal-header">
            <div class="header-badge">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
            </div>
            <h2>导入简历</h2>
            <div class="modal-actions">
              <!-- 未选择文件且不在解析中时显示返回按钮 -->
              <button v-if="!hasResumeFileSelected && !isParsingResume" @click="backToStartDialog" class="modal-back">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="19" y1="12" x2="5" y2="12"></line>
                  <polyline points="12 19 5 12 12 5"></polyline>
                </svg>
                返回
              </button>
            </div>
          </div>
          <div class="modal-body">
            <!-- 未选择文件且不在解析中时显示上传框 -->
            <div v-if="!resumeImagePreview && !isParsingResume" class="upload-box" @click="triggerResumeFileSelect()">
              <input type="file" accept="image/*,.pdf" @change="handleResumeImageSelect" ref="resumeFileInput" class="hidden-input" />
              <div class="upload-graphic">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
              </div>
              <p class="upload-title">点击上传简历</p>
              <p class="upload-hint">自动解析并生成结构化简历</p>
              <span class="upload-formats">支持 JPG、PNG、PDF</span>
            </div>
            <!-- 解析中状态显示 -->
            <div v-if="isParsingResume" class="parsing-status">
              <div class="parsing-spinner"></div>
              <p class="parsing-text">简历正在解析中...</p>
              <p class="parsing-hint">请稍候，解析完成后将自动显示结果</p>
            </div>
            <div v-else-if="resumeImportDraft" class="import-draft-review">
              <h3>请确认解析结果</h3>
              <p>姓名：{{ resumeImportDraft.resume_data?.basics?.name || '未识别' }}</p>
              <p>教育 {{ resumeImportDraft.resume_data?.education?.length || 0 }} 段 · 工作 {{ resumeImportDraft.resume_data?.work_experience?.length || 0 }} 段 · 项目 {{ resumeImportDraft.resume_data?.project_experience?.length || 0 }} 段</p>
              <small>为避免裁剪后模糊或误识别，系统不自动提取头像。导入后可在“编辑简历”中上传清晰原图。</small>
            </div>
            <div v-else-if="resumeImagePreview" class="preview-box">
              <!-- PDF文件预览 -->
              <div v-if="isResumePdf" class="pdf-preview">
                <div class="pdf-icon-wrapper">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                    <line x1="16" y1="13" x2="8" y2="13"></line>
                    <line x1="16" y1="17" x2="8" y2="17"></line>
                    <polyline points="10 9 9 9 8 9"></polyline>
                  </svg>
                </div>
                <p class="pdf-filename">{{ resumeImageFile?.name }}</p>
                <p class="pdf-hint">PDF文件准备解析</p>
              </div>
              <!-- 图片预览 -->
              <img v-else :src="resumeImagePreview" alt="简历预览" class="preview-img" />
              <button @click="reselectResumeFile" class="btn-reselect">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
                重新选择
              </button>
            </div>
          </div>
          <p v-if="resumeImportError" class="import-persistent-error">{{ resumeImportError }}</p>
          <div class="modal-footer" v-if="resumeImagePreview || isParsingResume">
            <button v-if="resumeImportDraft" @click="confirmResumeImport" :disabled="isParsingResume" class="btn-primary full-width">
              {{ isParsingResume ? '保存中...' : '确认并导入' }}
            </button>
            <button v-else @click="parseAndSaveResume" :disabled="isParsingResume" class="btn-primary full-width">
              {{ isParsingResume ? '解析中...' : '开始解析' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 顶部导航栏（全屏宽度） -->
  <header v-if="isWorkspaceRoute" class="app-header">
    <div class="header-content">
      <h1>
        <router-link to="/" class="header-brand-link" aria-label="返回 ResumeBranch 首页">
          <BrandLogo />
        </router-link>
      </h1>
      <div class="header-info">
        <span class="workspace-project-title">{{ currentProject?.title || '主简历' }}</span>
      </div>
    </div>
  </header>

  <!-- 主内容区（居中显示） -->
  <div class="app-container">
    <!-- 路由视图：登录/注册/管理页面 -->
    <router-view v-if="!isLoggedIn || isAdminRoute || !isWorkspaceRoute"></router-view>

    <!-- 已登录且非管理页面：显示主内容（聊天界面） -->
    <div v-if="isLoggedIn && isWorkspaceRoute" class="workspace-shell">
      <aside class="task-sidebar">
        <div class="task-sidebar-title">岗位版本</div>
        <div v-for="task in projectTasks" :key="task.id" class="task-row">
          <router-link
            :to="`/projects/${task.project_id}/tasks/${task.id}`"
            :class="['task-link', { active: task.id === currentTaskId }]"
            :title="task.is_base ? '基础简历' : task.title"
          >
            <span>{{ task.is_base ? '基础简历' : task.title }}</span>
          </router-link>
          <button
            v-if="!task.is_base"
            class="task-delete-btn"
            title="删除岗位版本"
            @click="deleteProjectTask(task, $event)"
          >×</button>
        </div>
        <button class="new-task-btn" @click="createProjectTask">＋ 新建版本</button>
      </aside>
      <div class="main-content">
      <!-- 桌面端：并排显示 -->
      <template v-if="!isMobileView">
        <!-- 左侧聊天区 -->
      <div class="chat-section">
        <div class="chat-panel-header">
          <div class="assistant-orb" aria-hidden="true"></div>
          <div class="chat-panel-title">
            <strong>简历助手</strong>
            <span>{{ currentTask?.is_base ? '基础简历' : (currentTask?.title || '岗位版本') }}</span>
          </div>
        </div>
        <div class="chat-container">
          <div class="messages-container" ref="messagesContainer" @scroll="handleScroll">
            <ChatMessage
              v-for="message in messages"
              :key="message.id + '_' + (message.content?.length || 0)"
              :message="message"
              @optionClick="handleOptionClick"
              @undoClick="handleUndoClick"
            />
            <!-- 只有当没有过程消息且正在加载时才显示默认加载指示器 -->
          <div v-if="isLoading" class="loading-indicator">
            <div class="loading-spinner">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="32" stroke-dashoffset="10" opacity="0.3"/>
                <path d="M10 3 A 7 7 0 0 1 10 17 A 7 7 0 0 1 10 3" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
              </svg>
            </div>
            <span class="loading-text">{{ loadingText }}</span>
          </div>
          </div>
          
          <!-- 滑动至底部按钮 -->
          <Transition name="fade">
            <button
              v-if="showScrollToBottomButton"
              type="button"
              class="scroll-to-bottom-btn"
              aria-label="返回最新消息"
              title="返回最新消息"
              @click="handleScrollToBottomClick"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M12 5v14M6.5 13.5 12 19l5.5-5.5"/>
              </svg>
            </button>
          </Transition>
        </div>
        
        <!-- 悬浮输入容器 -->
        <div class="floating-input-container">
          <div v-if="showProcessingBar" class="processing-status" role="status" aria-live="polite">
            <span class="processing-track" aria-hidden="true"><span></span></span>
            <span>{{ processingText }}</span>
          </div>
          <div v-if="workflowVisible" class="workflow-status" aria-live="polite">
            <div class="workflow-status-main">
              <strong>{{ workflowModeLabel }}</strong>
              <span>{{ workflowStatusLabel }}</span>
              <span v-if="workflowFocusLabel">聚焦：{{ workflowFocusLabel }}</span>
              <span>已确认 {{ workflowState.fact_count || 0 }} 条补充信息</span>
            </div>
            <div class="workflow-status-actions">
              <button v-if="workflowState.status === 'active'" type="button" :disabled="isLoading || isResponding" @click="runWorkflowAction('pause')">暂停</button>
              <button v-if="workflowState.status === 'paused'" type="button" :disabled="isLoading || isResponding" @click="runWorkflowAction('resume')">继续</button>
              <button v-if="workflowState.has_suggestion && workflowState.status !== 'completed'" type="button" :disabled="isLoading || isResponding" @click="runWorkflowAction('apply')">应用建议</button>
              <button v-if="workflowState.status !== 'completed'" type="button" :disabled="isLoading || isResponding" @click="runWorkflowAction('end')">结束</button>
            </div>
          </div>
          <div class="assistant-actions" aria-label="简历分析快捷操作">
            <button
              v-for="action in assistantActions"
              :key="action.label"
              type="button"
              :disabled="isLoading || isResponding"
              :title="action.prompt"
              @click="runAssistantAction(action)"
            >{{ action.label }}</button>
          </div>
          <!-- 文件上传区域 -->
          <div v-if="uploadedFiles.length > 0" class="uploaded-files">
            <div v-for="file in uploadedFiles" :key="file.id" class="file-thumbnail">
              <!-- 图片类型 - 支持点击预览 -->
              <div
                v-if="file.type.startsWith('image/')"
                class="file-icon image-icon"
                :style="{ cursor: 'pointer' }"
                @click="openImagePreview(file)"
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
              </div>
              <!-- PDF类型 - 不支持点击 -->
              <div v-else-if="file.type === 'application/pdf'" class="file-icon pdf-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
              </div>
              <div class="file-name">{{ file.name }}</div>
              <div @click="deleteFile(file.id)" class="delete-file-btn">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
          </div>
            </div>
          </div>
          
          <div class="input-wrapper">
            <input
              type="file"
              ref="fileInput"
              multiple
              accept="image/png, image/jpeg, image/jpg, application/pdf"
              @change="handleFileSelect"
              style="display: none;"
            />
            <div class="textarea-container">
              <textarea
                v-model="userInput"
                @keydown="handleKeyDown"
                @paste="handlePaste"
                placeholder="输入你的问题或请求..."
                rows="1"
                :disabled="isLoading || isResponding"
              ></textarea>
              <!-- 底部工具栏 -->
              <div class="toolbar">
                <!-- 上传按钮 -->
                <button
                  @click="fileInput?.click()"
                  class="icon-btn"
                  :disabled="isLoading || isResponding"
                  @mouseenter="(e) => showTooltip(e, '上传文件')"
                  @mouseleave="hideTooltip"
                  @mousemove="(e) => { tooltipState.x = e.currentTarget.getBoundingClientRect().left + e.currentTarget.getBoundingClientRect().width / 2; tooltipState.y = e.currentTarget.getBoundingClientRect().bottom + 8 }"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="17 8 12 3 7 8"></polyline>
                    <line x1="12" y1="3" x2="12" y2="15"></line>
                  </svg>
                </button>
                <!-- 全屏按钮 -->
                <button
                  @click="openFullscreenDialog"
                  class="icon-btn"
                  :disabled="isLoading || isResponding"
                  @mouseenter="(e) => showTooltip(e, '全屏输入')"
                  @mouseleave="hideTooltip"
                  @mousemove="(e) => { tooltipState.x = e.currentTarget.getBoundingClientRect().left + e.currentTarget.getBoundingClientRect().width / 2; tooltipState.y = e.currentTarget.getBoundingClientRect().bottom + 8 }"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                  </svg>
                </button>
                <!-- 发送按钮 - 预留空间避免高度突变 -->
                <div class="send-btn-placeholder" v-if="!(userInput.trim() || uploadedFiles.length > 0)"></div>
                <button
                  v-if="userInput.trim() || uploadedFiles.length > 0"
                  @click="sendMessage"
                  class="icon-btn send-btn"
                  :disabled="isLoading || isResponding"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13"></line>
                    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧简历预览区 -->
      <div class="resume-section">
        <div class="resume-content">
          <ResumePreview :data="activeResumeData" :layout-config="activeLayoutConfig" :task-id="currentTaskId" :source-page-count="currentTask?.source_page_count || 1" :has-source-document="!!currentTask?.has_source_document" :highlighted-module="highlightedModule" :jd-data="jdData" :lang="currentLang" :translation-busy="isTranslating" @open-jd-dialog="openJDDialog" @open-resume-edit="openResumeEditDialog" @open-resume-import="showUploadResumeDialog" @toggle-lang="switchLang" @use-layout-prompt="useLayoutPrompt" @request-layout-template="requestLayoutTemplate" @layout-updated="handleLayoutUpdated" />
        </div>
      </div>
      </template>

      <!-- 移动端：Tab 切换显示 -->
      <template v-else>
        <!-- 聊天 Tab 内容 -->
        <Transition name="tab-content" mode="out-in">
          <div v-if="currentTab === 'chat'" class="mobile-chat-view" key="chat">
            <div class="chat-container">
              <div class="messages-container" ref="messagesContainer" @scroll="handleScroll">
                <ChatMessage
                  v-for="message in messages"
                  :key="message.id + '_' + (message.content?.length || 0)"
                  :message="message"
                  @optionClick="handleOptionClick"
                  @undoClick="handleUndoClick"
                />
                <div v-if="isLoading" class="loading-indicator">
                  <div class="loading-spinner">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="32" stroke-dashoffset="10" opacity="0.3"/>
                      <path d="M10 3 A 7 7 0 0 1 10 17 A 7 7 0 0 1 10 3" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
                    </svg>
                  </div>
                  <span class="loading-text">{{ loadingText }}</span>
                </div>
              </div>
              
              <!-- 滑动至底部按钮 -->
              <Transition name="fade">
                <button
                  v-if="showScrollToBottomButton"
                  type="button"
                  class="scroll-to-bottom-btn"
                  aria-label="返回最新消息"
                  title="返回最新消息"
                  @click="handleScrollToBottomClick"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M12 5v14M6.5 13.5 12 19l5.5-5.5"/>
                  </svg>
                </button>
              </Transition>
            </div>
            
            <!-- 悬浮输入容器 -->
            <div class="floating-input-container mobile-input">
              <div v-if="showProcessingBar" class="processing-status" role="status" aria-live="polite">
                <span class="processing-track" aria-hidden="true"><span></span></span>
                <span>{{ processingText }}</span>
              </div>
              <div v-if="workflowVisible" class="workflow-status" aria-live="polite">
                <div class="workflow-status-main">
                  <strong>{{ workflowModeLabel }}</strong>
                  <span>{{ workflowStatusLabel }}</span>
                  <span v-if="workflowFocusLabel">聚焦：{{ workflowFocusLabel }}</span>
                  <span>已确认 {{ workflowState.fact_count || 0 }} 条补充信息</span>
                </div>
                <div class="workflow-status-actions">
                  <button v-if="workflowState.status === 'active'" type="button" :disabled="isLoading || isResponding" @click="runWorkflowAction('pause')">暂停</button>
                  <button v-if="workflowState.status === 'paused'" type="button" :disabled="isLoading || isResponding" @click="runWorkflowAction('resume')">继续</button>
                  <button v-if="workflowState.has_suggestion && workflowState.status !== 'completed'" type="button" :disabled="isLoading || isResponding" @click="runWorkflowAction('apply')">应用建议</button>
                  <button v-if="workflowState.status !== 'completed'" type="button" :disabled="isLoading || isResponding" @click="runWorkflowAction('end')">结束</button>
                </div>
              </div>
              <div class="assistant-actions" aria-label="简历分析快捷操作">
                <button
                  v-for="action in assistantActions"
                  :key="action.label"
                  type="button"
                  :disabled="isLoading || isResponding"
                  @click="runAssistantAction(action)"
                >{{ action.label }}</button>
              </div>
              <div v-if="uploadedFiles.length > 0" class="uploaded-files">
                <div v-for="file in uploadedFiles" :key="file.id" class="file-thumbnail">
                  <div v-if="file.type.startsWith('image/')" class="file-icon image-icon" :style="{ cursor: 'pointer' }" @click="openImagePreview(file)">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
                  </div>
                  <div v-else-if="file.type === 'application/pdf'" class="file-icon pdf-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
                  </div>
                  <div class="file-name">{{ file.name }}</div>
                  <div @click="deleteFile(file.id)" class="delete-file-btn">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                  </div>
                </div>
              </div>
              
              <div class="input-wrapper">
                <input type="file" ref="fileInput" multiple accept="image/png, image/jpeg, image/jpg, application/pdf" @change="handleFileSelect" style="display: none;" />
                <div class="textarea-container">
                  <textarea v-model="userInput" @keydown="handleKeyDown" @paste="handlePaste" placeholder="输入你的问题或请求..." rows="1" :disabled="isLoading || isResponding"></textarea>
                  <div class="toolbar mobile-toolbar">
                    <button @click="fileInput?.click()" class="icon-btn" :disabled="isLoading || isResponding">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                    </button>
                    <button @click="openFullscreenDialog" class="icon-btn" :disabled="isLoading || isResponding">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path></svg>
                    </button>
                    <div class="send-btn-placeholder" v-if="!(userInput.trim() || uploadedFiles.length > 0)"></div>
                    <button v-if="userInput.trim() || uploadedFiles.length > 0" @click="sendMessage" class="icon-btn send-btn" :disabled="isLoading || isResponding">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 简历 Tab 内容 -->
          <div v-else-if="currentTab === 'resume'" class="mobile-resume-view" key="resume">
            <ResumePreview :data="activeResumeData" :layout-config="activeLayoutConfig" :task-id="currentTaskId" :source-page-count="currentTask?.source_page_count || 1" :has-source-document="!!currentTask?.has_source_document" :highlighted-module="highlightedModule" :jd-data="jdData" :is-mobile-view="isMobileView" :lang="currentLang" :translation-busy="isTranslating" @open-jd-dialog="openJDDialog" @open-resume-edit="openResumeEditDialog" @open-resume-import="showUploadResumeDialog" @toggle-lang="switchLang" @use-layout-prompt="useLayoutPrompt" @request-layout-template="requestLayoutTemplate" @layout-updated="handleLayoutUpdated" />
          </div>
        </Transition>

        <!-- 移动端底部 Tab 栏 -->
        <MobileTabBar :active-tab="currentTab" @update:activeTab="currentTab = $event" />
      </template>
      </div>
    </div> <!-- 闭合 workspace-shell -->
  </div>

  <!-- 图片预览弹窗 -->
  <Teleport to="body">
    <div v-if="showImagePreview" class="image-preview-modal" @click="closeImagePreview">
      <div class="image-preview-content" @click.stop>
        <button class="image-preview-close" @click="closeImagePreview">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
        <img :src="previewImageUrl" class="image-preview-image" alt="图片预览" />
      </div>
    </div>
  </Teleport>

  <!-- 自定义 Tooltip -->
  <Teleport to="body">
    <Transition name="tooltip-fade">
      <div 
        v-if="tooltipState.visible" 
        class="custom-tooltip"
        :style="{ left: tooltipState.x + 'px', bottom: tooltipState.bottom + 'px' }"
      >
        {{ tooltipState.text }}
      </div>
    </Transition>
  </Teleport>

  <!-- 全屏输入弹窗 -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="isFullscreenDialogOpen" class="fullscreen-dialog-overlay" @click.self="closeFullscreenDialog">
        <div class="fullscreen-dialog" @keydown="handleDialogKeydown">
          <div class="dialog-header">
            <h3>输入你的请求</h3>
            <button class="dialog-close-btn" @click="closeFullscreenDialog" title="关闭 (ESC)">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
          </div>
          <div class="dialog-body">
            <textarea
              v-model="dialogUserInput"
              class="dialog-textarea"
              placeholder="输入你的问题或请求...（按Enter换行）"
              rows="15"
              autofocus
            ></textarea>
          </div>
          <div class="dialog-footer">
            <button class="dialog-save-btn" @click="saveDialogContent">保存</button>
            <button
              class="dialog-submit-btn"
              @click="submitFullscreenDialog"
              :disabled="!dialogUserInput.trim()"
            >
              发送 (Ctrl+Enter)
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 翻译确认弹窗 -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="showTranslateConfirm" class="translate-dialog-overlay" @click.self="cancelTranslate">
        <div class="translate-dialog">
          <div class="dialog-header">
            <h3>{{ translateLabels.translateConfirmTitle }}</h3>
            <button class="dialog-close-btn" @click="cancelTranslate" title="关闭">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
          </div>
          <div class="dialog-body">
            <p>{{ translateLabels.translateConfirmMessage }}</p>
          </div>
          <div class="dialog-footer">
            <button class="cancel-btn" @click="cancelTranslate">{{ translateLabels.cancel }}</button>
            <button class="confirm-btn" @click="confirmTranslate">{{ translateLabels.confirm }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- JD上传弹窗（新增） -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="isJDDialogOpen" class="jd-dialog-overlay">
        <div class="jd-dialog">
          <div class="dialog-header">
            <h3>{{ jdInputMode === 'input' ? '上传目标岗位信息' : '编辑岗位信息' }}</h3>
            <button class="dialog-close-btn" @click="closeJDDialog" title="关闭">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
          </div>

          <!-- 输入模式 -->
          <div v-if="jdInputMode === 'input'" class="jd-input-section">
            <!-- 有图片时：显示图片预览 -->
            <div v-if="jdInputImage" class="input-group">
              <label>目标岗位描述（图片）</label>
              <img :src="jdInputImage" class="jd-image-preview" alt="图片预览" />
              <button class="remove-image-btn" @click="jdInputImage = ''">移除图片</button>
            </div>
            <!-- 没有图片时：显示输入框 -->
            <div v-else class="input-group">
              <label>粘贴职位描述</label>
              <textarea
                v-model="jdInputText"
                @paste="handleJDPaste"
                placeholder="粘贴招聘要求内容，支持直接粘贴图片（Ctrl+V）..."
                rows="10"
              ></textarea>
            </div>
          </div>

          <!-- 表单模式 -->
          <div v-if="jdInputMode === 'form'" class="jd-form-section">
            <div class="form-header">
              <button class="back-btn" @click="backToInputMode">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M19 12H5M12 19l-7-7 7-7"/>
                </svg>
                退回上一步
              </button>
            </div>

            <!-- 基本信息（双列：3行×2列） -->
            <h4 class="section-title">基本信息</h4>
            <div class="form-grid">
              <div class="field-group">
                <label>公司名称</label>
                <input v-model="jdFormData.company" placeholder="请输入" />
              </div>
              <div class="field-group">
                <label>职位名称</label>
                <input v-model="jdFormData.position" placeholder="请输入" />
              </div>
              <div class="field-group">
                <label>部门/团队</label>
                <input v-model="jdFormData.department" placeholder="请输入" />
              </div>
              <div class="field-group">
                <label>工作地点</label>
                <input v-model="jdFormData.location" placeholder="请输入" />
              </div>
              <div class="field-group">
                <label>工作类型</label>
                <select v-model="jdFormData.job_type">
                  <option value="">请选择</option>
                  <option value="全职">全职</option>
                  <option value="实习">实习</option>
                </select>
              </div>
              <div class="field-group">
                <label>薪资范围</label>
                <input v-model="jdFormData.salary" placeholder="如：30k-50k" />
              </div>
            </div>

            <!-- 职位描述（单列） -->
            <h4 class="section-title">职位描述</h4>
            <div class="form-grid">
              <div class="field-group full-width">
                <textarea v-model="jdFormData.description" rows="3" placeholder="请输入"></textarea>
              </div>
            </div>

            <!-- 任职要求（双列） -->
            <h4 class="section-title">任职要求</h4>
            <div class="form-grid">
              <div class="field-group">
                <label>学历要求</label>
                <input v-model="jdFormData.requirements.education" placeholder="如：本科及以上" />
              </div>
              <div class="field-group">
                <label>经验要求</label>
                <input v-model="jdFormData.requirements.experience" placeholder="如：3年以上" />
              </div>
              <div class="field-group">
                <label>语言要求</label>
                <input v-model="jdFormData.requirements.language" placeholder="如：普通话流利" />
              </div>
            </div>

            <!-- 其他信息（单列） -->
            <h4 class="section-title">其他信息</h4>
            <div class="form-grid">
              <div class="field-group full-width">
                <label>技能要求</label>
                <div class="tags-input">
                  <span v-for="(skill, i) in jdFormData.requirements.skills" :key="i" class="tag">
                    {{ skill }}
                    <button @click="removeSkill(i)" class="tag-remove">×</button>
                  </span>
                  <input
                    v-model="newSkill"
                    @keydown.enter="addSkill"
                    placeholder="回车添加技能"
                    class="tag-input"
                  />
                </div>
              </div>
              <div class="field-group full-width">
                <label>优先条件</label>
                <textarea v-model="jdFormData.preferred_qualifications_text" rows="2" placeholder="请输入（用逗号分隔）" @blur="updatePreferredQualifications"></textarea>
              </div>
              <div class="field-group full-width">
                <label>亮点/核心关键词</label>
                <textarea v-model="jdFormData.highlights_text" rows="2" placeholder="请输入（用逗号分隔）" @blur="updateHighlights"></textarea>
              </div>
            </div>
          </div>

          <!-- 底部按钮（固定在底部，不随内容滚动） -->
          <div class="dialog-actions">
            <template v-if="jdInputMode === 'input'">
              <button class="parse-btn" @click="parseJD" :disabled="!jdInputText.trim() && !jdInputImage || isParsingJD">
                <span v-if="isParsingJD" class="spinner"></span>
                <span>{{ isParsingJD ? '识别中...' : '智能识别' }}</span>
              </button>
            </template>
            <template v-else>
              <button class="cancel-btn" @click="closeJDDialog">取消</button>
              <button class="save-btn" @click="saveJD" :disabled="isSaving">
                <span v-if="isSaving" class="spinner"></span>
                <span>{{ isSaving ? '保存中...' : '保存' }}</span>
              </button>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 简历编辑弹窗（新增） -->
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="isResumeEditDialogOpen" class="resume-dialog-overlay">
        <div class="resume-dialog">
          <div class="dialog-header">
            <h3>编辑简历</h3>
            <button class="dialog-close-btn" @click="closeResumeEditDialog" title="关闭">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
          </div>

          <div class="resume-form-section">
            <div class="resume-format-hint" role="note">
              <span>选中文字后按</span>
              <kbd>Ctrl+B</kbd>
              <span>加粗或取消加粗；内容框右下方显示按当前正文设置预计在简历中所占行数</span>
            </div>

            <!-- 基本信息 -->
            <h4 class="section-title">基本信息</h4>
            
            <!-- 证件照上传 -->
            <div class="field-group photo-upload-group">
              <label>证件照</label>
              <div class="photo-upload-area" :class="{ 'has-error': photoError }">
                <img v-if="resumeFormData.basics.photo" :src="resumeFormData.basics.photo" class="photo-preview" />
                <div v-else class="photo-placeholder" @click="$refs.photoInput.click()">
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                  </svg>
                  <span>点击上传证件照</span>
                  <small>（1寸照片，不超过2MB）</small>
                </div>
                <input 
                  ref="photoInput"
                  type="file" 
                  accept="image/jpeg,image/png"
                  @change="handlePhotoUpload"
                  class="photo-input" 
                />
                <button v-if="resumeFormData.basics.photo" @click="removePhoto" class="remove-photo-btn">×</button>
              </div>
              <div v-if="photoError" class="photo-error">{{ photoError }}</div>
            </div>
            
            <div class="form-grid">
              <div class="field-group">
                <label>姓名</label>
                <RichTextEditor v-model="resumeFormData.basics.name" placeholder="请输入" compact />
              </div>
              <div class="field-group">
                <label>性别</label>
                <el-select v-model="resumeFormData.basics.gender" placeholder="请选择" class="element-select" popper-class="resume-dark-select-popper">
                  <el-option label="男" value="男" />
                  <el-option label="女" value="女" />
                  <el-option label="保密" value="保密" />
                </el-select>
              </div>
              <div class="field-group">
                <label>出生年月</label>
                <input v-model="resumeFormData.basics.birth_date" placeholder="例如 2002.06" class="element-input" />
              </div>
              <div class="field-group">
                <label>手机</label>
                <RichTextEditor v-model="resumeFormData.basics.phone" placeholder="请输入" compact />
              </div>
              <div class="field-group">
                <label>邮箱</label>
                <RichTextEditor v-model="resumeFormData.basics.email" placeholder="请输入" compact />
              </div>
              <div class="field-group full-width">
                <label>期望岗位</label>
                <RichTextEditor v-model="resumeFormData.basics.target_position" placeholder="请输入" compact />
              </div>
              <div class="field-group full-width">
                <label>其他基本信息</label>
                <div v-for="(field, fieldIndex) in resumeFormData.basics.additional_fields" :key="`basic-extra-${fieldIndex}`" class="inline-edit-row">
                  <RichTextEditor v-model="field.label" placeholder="字段名，如籍贯" compact />
                  <RichTextEditor v-model="field.value" placeholder="字段内容" compact />
                  <button type="button" class="remove-btn" @click="removeBasicAdditionalField(fieldIndex)">删除</button>
                </div>
                <button type="button" class="add-btn" @click="addBasicAdditionalField">+ 添加基本信息</button>
              </div>
            </div>

            <!-- 教育背景 -->
            <h4 class="section-title">教育背景</h4>
            <div v-for="(edu, i) in resumeFormData.education" :key="i" class="array-item">
              <div class="array-item-header">
                <span>学历 {{ i + 1 }}</span>
                <button @click="removeEducation(i)" class="remove-btn">删除</button>
              </div>
              <div class="form-grid">
                <div class="field-group">
                  <label>学校</label>
                  <RichTextEditor v-model="edu.school_name" placeholder="请输入" compact />
                </div>
                <div class="field-group">
                  <label>专业</label>
                  <RichTextEditor v-model="edu.major" placeholder="请输入" compact />
                </div>
                <div class="field-group">
                  <label>学历</label>
                  <el-select v-model="edu.degree" placeholder="请选择" class="element-select" popper-class="resume-dark-select-popper">
                    <el-option label="博士" value="博士" />
                    <el-option label="硕士" value="硕士" />
                    <el-option label="本科" value="本科" />
                    <el-option label="大专" value="大专" />
                    <el-option label="中专" value="中专" />
                    <el-option label="高中" value="高中" />
                    <el-option label="初中及以下" value="初中及以下" />
                  </el-select>
                </div>
                <div class="field-group">
                  <label>GPA / 绩点</label>
                  <RichTextEditor v-model="edu.gpa" placeholder="例如 3.72" compact />
                </div>
                <div class="field-group">
                  <label>绩点满分</label>
                  <RichTextEditor v-model="edu.gpa_scale" placeholder="例如 4.0" compact />
                </div>
                <div class="field-group">
                  <label>专业 / 年级排名</label>
                  <RichTextEditor v-model="edu.ranking" placeholder="例如 前 10%" compact />
                </div>
                <div class="field-group">
                  <label>平均分 / 加权平均分</label>
                  <RichTextEditor v-model="edu.average_score" placeholder="例如 88/100" compact />
                </div>
                <div class="field-group full-width">
                  <label>时间范围</label>
                  <div class="date-range-wrapper">
                    <template v-if="!edu._isPresent">
                      <el-date-picker
                        v-model="edu._dateRange"
                        type="monthrange"
                        range-separator="至"
                        start-placeholder="开始时间"
                        end-placeholder="结束时间"
                        format="YYYY.MM"
                        value-format="YYYY-MM"
                        class="element-date-picker"
                        popper-class="resume-dark-date-popper"
                      />
                    </template>
                    <template v-else>
                      <div class="present-date-display">
                        <span class="present-start-date">{{ edu._dateRange?.[0]?.replace('-', '.') || '' }}</span>
                        <span class="present-separator">至</span>
                        <span class="present-end-text">至今</span>
                      </div>
                    </template>
                    <label class="present-label">
                      <input type="checkbox" v-model="edu._isPresent" @change="onPresentChange(edu)" />
                      至今
                    </label>
                  </div>
                </div>
                <div class="field-group full-width">
                  <label>学校标签</label>
                  <div class="tags-input">
                    <span v-for="(tag, j) in edu.school_tags" :key="j" class="tag">
                      <span v-html="formatInlineHtml(tag)"></span>
                      <button @click="edu.school_tags.splice(j, 1)" class="tag-remove">×</button>
                    </span>
                    <input v-model="edu.newSchoolTag" @keydown.enter="addSchoolTag(edu)" placeholder="回车添加标签" class="tag-input" />
                  </div>
                </div>
              </div>
            </div>
            <button @click="addEducation" class="add-btn">+ 添加学历</button>

            <h4 class="section-title">研究方向</h4>
            <RichTextEditor
              v-model="researchInterestsText"
              placeholder="每行一条研究方向，导入内容会按原文保留"
              class="rich-editor-field"
              :resume-metrics="resumeEditorMetrics"
            />

            <h4 class="section-title">主要荣誉</h4>
            <RichTextEditor
              v-model="honorsText"
              placeholder="每行一项奖学金、竞赛奖项或荣誉"
              class="rich-editor-field"
              :resume-metrics="resumeEditorMetrics"
            />

            <!-- 工作经历 -->
            <h4 class="section-title">工作经历</h4>
            <div v-for="(work, i) in resumeFormData.work_experience" :key="i" class="array-item">
              <div class="array-item-header">
                <span>工作 {{ i + 1 }}</span>
                <button @click="removeWork(i)" class="remove-btn">删除</button>
              </div>
              <div class="form-grid">
                <div class="field-group">
                  <label>公司</label>
                  <RichTextEditor v-model="work.company_name" placeholder="请输入" compact />
                </div>
                <div class="field-group">
                  <label>职位</label>
                  <RichTextEditor v-model="work.job_title" placeholder="请输入" compact />
                </div>
                <div class="field-group">
                  <label>工作类型</label>
                  <el-select v-model="work.job_type" placeholder="请选择" class="element-select" popper-class="resume-dark-select-popper">
                    <el-option label="全职" value="全职" />
                    <el-option label="实习" value="实习" />
                  </el-select>
                </div>
                <div class="field-group full-width">
                  <label>时间范围</label>
                  <div class="date-range-wrapper">
                    <template v-if="!work._isPresent">
                      <el-date-picker
                        v-model="work._dateRange"
                        type="monthrange"
                        range-separator="至"
                        start-placeholder="开始时间"
                        end-placeholder="结束时间"
                        format="YYYY.MM"
                        value-format="YYYY-MM"
                        class="element-date-picker"
                        popper-class="resume-dark-date-popper"
                      />
                    </template>
                    <template v-else>
                      <div class="present-date-display">
                        <span class="present-start-date">{{ work._dateRange?.[0]?.replace('-', '.') || '' }}</span>
                        <span class="present-separator">至</span>
                        <span class="present-end-text">至今</span>
                      </div>
                    </template>
                    <label class="present-label">
                      <input type="checkbox" v-model="work._isPresent" @change="onPresentChange(work)" />
                      至今
                    </label>
                  </div>
                </div>
              </div>
              <!-- 工作内容 -->
              <div class="array-item-nested">
                <label>工作内容</label>
                <RichTextEditor
                  v-model="work._detailsText"
                  placeholder="请输入工作内容，支持换行"
                  class="rich-editor-field"
                  :resume-metrics="resumeEditorMetrics"
                />
              </div>
            </div>
            <button @click="addWork" class="add-btn">+ 添加工作经历</button>

            <!-- 项目经历 -->
            <h4 class="section-title">项目经历</h4>
            <div v-for="(proj, i) in resumeFormData.project_experience" :key="i" class="array-item">
              <div class="array-item-header">
                <span>项目 {{ i + 1 }}</span>
                <button @click="removeProject(i)" class="remove-btn">删除</button>
              </div>
              <div class="form-grid">
                <div class="field-group">
                  <label>项目名称</label>
                  <RichTextEditor v-model="proj.project_name" placeholder="请输入" compact />
                </div>
                <div class="field-group">
                  <label>角色</label>
                  <RichTextEditor v-model="proj.role" placeholder="请输入" compact />
                </div>
                <div class="field-group full-width">
                  <label>时间范围</label>
                  <div class="date-range-wrapper">
                    <template v-if="!proj._isPresent">
                      <el-date-picker
                        v-model="proj._dateRange"
                        type="monthrange"
                        range-separator="至"
                        start-placeholder="开始时间"
                        end-placeholder="结束时间"
                        format="YYYY.MM"
                        value-format="YYYY-MM"
                        class="element-date-picker"
                        popper-class="resume-dark-date-popper"
                      />
                    </template>
                    <template v-else>
                      <div class="present-date-display">
                        <span class="present-start-date">{{ proj._dateRange?.[0]?.replace('-', '.') || '' }}</span>
                        <span class="present-separator">至</span>
                        <span class="present-end-text">至今</span>
                      </div>
                    </template>
                    <label class="present-label">
                      <input type="checkbox" v-model="proj._isPresent" @change="onPresentChange(proj)" />
                      至今
                    </label>
                  </div>
                </div>
              </div>
              <!-- 项目内容 -->
              <div class="array-item-nested">
                <div class="semantic-label-heading">
                  <span :class="{ 'is-bold': proj._introLabelBold }">{{ proj._introLabel || '项目简介' }}</span>
                  <button type="button" @click="proj._introLabelBold = !proj._introLabelBold">
                    {{ proj._introLabelBold ? '取消加粗' : '设为加粗' }}
                  </button>
                </div>
                <RichTextEditor
                  v-model="proj._introText"
                  placeholder="简要说明项目背景和目标"
                  class="rich-editor-field"
                  :resume-metrics="resumeEditorMetrics"
                  :resume-flow="projectIntroFlow(proj)"
                />
              </div>
              <div class="array-item-nested">
                <div class="semantic-label-heading">
                  <span :class="{ 'is-bold': proj._dutiesLabelBold }">{{ proj._dutiesLabel || '项目职责' }}（每行一条，模板自动编号）</span>
                  <button type="button" @click="proj._dutiesLabelBold = !proj._dutiesLabelBold">
                    {{ proj._dutiesLabelBold ? '取消加粗' : '设为加粗' }}
                  </button>
                </div>
                <RichTextEditor
                  v-model="proj._dutiesText"
                  placeholder="每行填写一项职责，不需要手动输入序号"
                  class="rich-editor-field"
                  :resume-metrics="resumeEditorMetrics"
                />
              </div>
              <div class="array-item-nested">
                <label>其他项目内容（可选）</label>
                <RichTextEditor
                  v-model="proj._extraDetailsText"
                  placeholder="不属于项目简介或项目职责的补充内容，每行一条"
                  class="rich-editor-field"
                  :resume-metrics="resumeEditorMetrics"
                />
              </div>
            </div>
            <button @click="addProject" class="add-btn">+ 添加项目经历</button>

            <h4 class="section-title">其他原始栏目</h4>
            <div v-for="(section, sectionIndex) in resumeFormData.custom_sections" :key="`custom-section-${sectionIndex}`" class="array-item">
              <div class="array-item-header">
                <span>自定义栏目 {{ sectionIndex + 1 }}</span>
                <button type="button" @click="removeCustomSection(sectionIndex)" class="remove-btn">删除</button>
              </div>
              <div class="field-group full-width">
                <label>栏目标题</label>
                <RichTextEditor v-model="section.title" placeholder="保留原简历栏目标题" compact />
              </div>
              <div class="array-item-nested">
                <label>栏目内容</label>
                <RichTextEditor
                  v-model="section._itemsText"
                  placeholder="每行一条，按原简历阅读顺序保留"
                  class="rich-editor-field"
                  :resume-metrics="resumeEditorMetrics"
                />
              </div>
            </div>
            <button type="button" @click="addCustomSection" class="add-btn">+ 添加自定义栏目</button>

            <!-- 专业技能 -->
            <h4 class="section-title">专业技能</h4>
            <div class="others-section">
              <div class="field-group full-width">
                <label>技能条目</label>
                <div class="tags-input">
                  <span v-for="(skill, i) in resumeFormData.others.skills" :key="i" class="tag">
                    <span v-html="formatInlineHtml(skill)"></span>
                    <button @click="resumeFormData.others.skills.splice(i, 1)" class="tag-remove">×</button>
                  </span>
                  <input v-model="newResumeSkill" @keydown.enter="addResumeSkill" placeholder="回车添加技能" class="tag-input" />
                </div>
              </div>
            </div>

            <!-- 补充信息 -->
            <h4 class="section-title">证书与语言</h4>
            <div class="others-section">
              <div class="field-group full-width">
                <label>证书</label>
                <div class="tags-input">
                  <span v-for="(cert, i) in resumeFormData.others.certificates" :key="i" class="tag">
                    <span v-html="formatInlineHtml(cert)"></span>
                    <button @click="resumeFormData.others.certificates.splice(i, 1)" class="tag-remove">×</button>
                  </span>
                  <input v-model="newResumeCert" @keydown.enter="addResumeCert" placeholder="回车添加证书" class="tag-input" />
                </div>
              </div>
              <div class="field-group full-width">
                <label>语言</label>
                <div class="tags-input">
                  <span v-for="(lang, i) in resumeFormData.others.languages" :key="i" class="tag">
                    <span v-html="formatInlineHtml(lang)"></span>
                    <button @click="resumeFormData.others.languages.splice(i, 1)" class="tag-remove">×</button>
                  </span>
                  <input v-model="newResumeLang" @keydown.enter="addResumeLang" placeholder="回车添加语言" class="tag-input" />
                </div>
              </div>
            </div>

            <!-- 自我评价 -->
            <h4 class="section-title">自我评价</h4>
            <RichTextEditor
              v-model="selfEvalText"
              placeholder="请输入自我评价，支持换行"
              class="rich-editor-field"
              :resume-metrics="resumeEditorMetrics"
            />
          </div>

          <div class="dialog-actions">
            <button class="cancel-btn" @click="closeResumeEditDialog">取消</button>
            <button class="save-btn" @click="saveResume" :disabled="isSaving">
              <span v-if="isSaving" class="spinner"></span>
              <span>{{ isSaving ? '保存中...' : '保存' }}</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  color: #f5f5f7;
  background:
    radial-gradient(circle at 64% -20%, rgba(100, 130, 220, 0.12), transparent 36%),
    #050506;
  width: 100%;
  margin: 0;
  max-width: none;
}

.app-header + .app-container {
  height: calc(100vh - 52px);
}

.app-header {
  width: 100%;
  height: 52px;
  min-height: 52px;
  background: rgba(8, 8, 10, 0.94);
  color: #f5f5f7;
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  box-shadow: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  position: sticky;
  top: 0;
  z-index: 9999;
  margin: 0;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 100%;
  min-height: 0;
  padding: 0.45rem 1.6rem;
  width: 100%;
  box-sizing: border-box;
  margin: 0;
}

.app-header h1 {
  margin: 0;
  display: flex;
  align-items: center;
  height: 22px;
  line-height: 1;
}

.app-header h1 .header-brand-link {
  display: inline-flex;
  align-items: center;
  height: 22px;
  line-height: 1;
}

.app-logo {
  height: 26px;
  width: auto;
  filter: grayscale(1) brightness(0) invert(1);
  opacity: 0.92;
}

.header-info {
  display: flex;
  gap: 1rem;
  font-size: 0.8rem;
  color: #8f8f98;
  align-items: center;
}

.workspace-project-title {
  color: #d8d8dd;
  font-size: 0.9rem;
  font-weight: 560;
  letter-spacing: 0.03em;
}

.logout-btn {
  padding: 0.45rem 0.8rem;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.055);
  color: #c9c9cf;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.25em;
  cursor: pointer;
  transition: all 0.2s ease;
}

.logout-btn:hover {
  border-color: rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.auth-link {
  color: #c9c9cf;
  text-decoration: none;
  padding: 0.5rem 1rem;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 9px;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.25em;
  transition: all 0.2s ease;
}

.auth-link:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

/* 未登录提示样式 */
.not-logged-in {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: white;
}

.not-logged-in-content {
  text-align: center;
  padding: 3rem;
}

.not-logged-in-content svg {
  color: var(--text-secondary);
  margin-bottom: 1rem;
}

.not-logged-in-content h2 {
  margin: 0 0 0.5rem 0;
  color: var(--text-primary);
  font-size: 1.5rem;
}

.not-logged-in-content p {
  margin: 0 0 1.5rem 0;
  color: var(--text-secondary);
}

.auth-buttons {
  display: flex;
  gap: 1rem;
  justify-content: center;
}

.auth-btn {
  padding: 0.75rem 2rem;
  border-radius: var(--radius-md);
  text-decoration: none;
  font-weight: 500;
  transition: all 0.2s ease;
}

.login-btn {
  background: white;
  border: 1px solid var(--border-color);
  color: var(--text-primary);
}

.login-btn:hover {
  background: var(--secondary-color);
}

.register-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  color: white;
}

.register-btn:hover {
  opacity: 0.9;
}

.message-count {
  background-color: var(--accent-color);
  padding: 0.25rem 0.75rem;
  border-radius: var(--radius-full);
  font-size: 0.8rem;
}

.workspace-shell {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: #08090b;
}

.task-sidebar {
  flex: 0 0 156px;
  padding: 1rem .65rem;
  overflow-y: auto;
  background: rgba(8, 8, 10, 0.88);
  border-right: 1px solid rgba(255, 255, 255, 0.065);
}

.task-sidebar-title {
  padding: .25rem .6rem .75rem;
  color: #74747d;
  font-size: .8rem;
  font-weight: 500;
  letter-spacing: .1em;
}

.task-link {
  display: flex;
  flex-direction: column;
  gap: .2rem;
  margin-bottom: 0;
  padding: .58rem .65rem;
  border-radius: 0;
  color: #a7a7af;
  text-decoration: none;
  min-width: 0;
  flex: 1;
  font-size: .8rem;
}

.task-link > span {
  position: relative;
  display: block;
  padding-left: 0;
  overflow: visible;
  line-height: 1.35;
  white-space: normal;
  overflow-wrap: anywhere;
}

.task-link:hover,
.task-link.active {
  background: transparent;
  box-shadow: none;
}

.task-link.active {
  color: #f5f5f7;
  font-weight: 600;
}

.task-link.active span {
  display: block;
  padding-left: .8rem;
}

.task-link.active span::before {
  position: absolute;
  top: .48em;
  left: 0;
  width: 5px;
  height: 5px;
  content: '';
  background: #78a6ff;
  border-radius: 50%;
  box-shadow: 0 0 8px rgba(120, 166, 255, .55);
}

.new-task-btn {
  width: 100%;
  margin-top: .6rem;
  padding: .65rem;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: #8d8d96;
  font-size: .8rem;
  text-align: left;
  cursor: pointer;
}

.new-task-btn:hover {
  color: #dbe6ff;
  background: transparent;
}

.task-row {
  display: flex;
  align-items: center;
  gap: .25rem;
  margin-bottom: .2rem;
}

.task-delete-btn {
  width: 26px;
  height: 26px;
  flex: 0 0 26px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #686871;
  cursor: pointer;
}

.task-delete-btn:hover {
  background: transparent;
  color: #ff8e8e;
}

.main-content {
  display: flex;
  flex: 1;
  overflow: hidden; /* 关键：让子元素处理滚动 */
  margin: 0;
  padding: 0;
  min-width: 0;
}

@media (max-width: 1199px) {
  .workspace-shell {
    flex-direction: column;
  }

  .task-sidebar {
    display: flex;
    flex: 0 0 auto;
    gap: .4rem;
    padding: .5rem;
    overflow-x: auto;
    border-right: 0;
    border-bottom: 1px solid #ddd8d2;
  }

  .task-sidebar-title {
    display: none;
  }

  .task-link {
    flex: 0 0 auto;
    margin: 0;
  }

  .task-row {
    flex: 0 0 auto;
  }

  .task-delete-btn {
    display: none;
  }

  .new-task-btn {
    flex: 0 0 auto;
    width: auto;
    margin: 0;
  }

}

.chat-section {
  flex: 0 0 39%;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(circle at 40% 10%, rgba(79, 105, 160, 0.09), transparent 31%),
    #0c0c0e;
  margin: 0;
  padding: 0;
  overflow: hidden;
  position: relative;
  border-right: 1px solid rgba(255, 255, 255, 0.065);
  height: 100%; /* 确保高度填满 */
}

.chat-panel-header {
  height: 54px;
  min-height: 54px;
  box-sizing: border-box;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.45rem 0.9rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.055);
  background: rgba(12, 12, 14, 0.76);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.assistant-orb {
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  border-radius: 50%;
  background:
    radial-gradient(circle at 34% 32%, #fff 0 7%, #a9c0ff 16%, #576fb3 42%, #171926 68%);
  box-shadow: 0 0 22px rgba(106, 141, 235, 0.32);
}

.chat-panel-title {
  min-width: 0;
  display: grid;
  gap: 0.08rem;
}

.chat-panel-title strong {
  color: #eeeeF1;
  font-size: 0.78rem;
  font-weight: 500;
}

.chat-panel-title span {
  overflow: hidden;
  color: #7f7f88;
  font-size: 0.66rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 简洁的滚动条样式 - 应用于所有可滚动区域 */
.messages-container::-webkit-scrollbar,
.preview-content::-webkit-scrollbar {
  width: 8px;
}

.messages-container::-webkit-scrollbar-track,
.preview-content::-webkit-scrollbar-track {
  background: transparent;
  border-radius: 4px;
}

.messages-container::-webkit-scrollbar-thumb,
.preview-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.14);
  border-radius: 4px;
  min-height: 30px;
}

.messages-container::-webkit-scrollbar-thumb:hover,
.preview-content::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.24);
}

/* 聊天区域容器 */
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  flex: 1;
  overflow: hidden;
  padding: 0;
  background-color: transparent;
  position: relative;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 1.35rem 1.15rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  color: #d8d8dd;
  font-size: 14px;
}

/* 滑动至底部按钮 */
.scroll-to-bottom-btn {
  position: absolute;
  left: 50%;
  bottom: 14px;
  transform: translateX(-50%);
  width: 32px;
  height: 32px;
  padding: 0;
  border-radius: 50%;
  background: rgba(43, 44, 50, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.24);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #e4e4e8;
  transition: background-color 0.16s ease, border-color 0.16s ease, color 0.16s ease, transform 0.16s ease;
  z-index: 10;
  backdrop-filter: blur(4px);
}

.scroll-to-bottom-btn:hover {
  background: rgba(57, 58, 65, 0.98);
  border-color: rgba(255, 255, 255, 0.22);
  color: #fff;
  transform: translateX(-50%) translateY(-1px);
}

.scroll-to-bottom-btn:active {
  transform: translateX(-50%) translateY(0);
}

.scroll-to-bottom-btn svg {
  width: 19px;
  height: 19px;
  stroke-width: 2.25;
}

.scroll-to-bottom-btn:focus-visible {
  outline: 2px solid #8eb1ff;
  outline-offset: 2px;
}

/* 按钮淡入淡出动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.floating-input-container {
  position: relative;
  padding: 0.75rem 0.85rem 0.85rem;
  background: linear-gradient(to top, #0c0c0e 72%, rgba(12, 12, 14, 0));
  border-top: 1px solid rgba(255, 255, 255, 0.025);
  flex-shrink: 0;
}

.workflow-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0 2px 8px;
  padding: 7px 9px;
  color: #cbd6ed;
  background: rgba(83, 125, 202, 0.1);
  border: 1px solid rgba(126, 164, 234, 0.2);
  border-radius: 9px;
  font-size: 11px;
}

.workflow-status-main,
.workflow-status-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}

.workflow-status-main strong {
  color: #f3f6ff;
}

.workflow-status-actions {
  justify-content: flex-end;
}

.workflow-status-actions button {
  padding: 3px 7px;
  color: #dce6ff;
  background: rgba(126, 164, 234, 0.13);
  border: 1px solid rgba(126, 164, 234, 0.25);
  border-radius: 6px;
  font: inherit;
  cursor: pointer;
}

.workflow-status-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.assistant-actions {
  display: flex;
  gap: 7px;
  margin: 0 2px 8px;
  overflow-x: auto;
  scrollbar-width: none;
}

.assistant-actions::-webkit-scrollbar {
  display: none;
}

.assistant-actions button {
  flex: 0 0 auto;
  min-height: 29px;
  padding: 5px 10px;
  color: #cbd6ed;
  background: rgba(113, 151, 222, 0.09);
  border: 1px solid rgba(126, 164, 234, 0.2);
  border-radius: 999px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.assistant-actions button:hover:not(:disabled) {
  color: #fff;
  background: rgba(113, 151, 222, 0.18);
  border-color: rgba(139, 177, 247, 0.4);
}

.assistant-actions button:focus-visible {
  outline: 2px solid #8eb1ff;
  outline-offset: 2px;
}

.assistant-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.processing-status {
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr);
  align-items: center;
  gap: 9px;
  min-height: 25px;
  margin: -2px 3px 7px;
  color: #aeb2bd;
  font-size: 12px;
  line-height: 1.35;
}

.processing-track {
  position: relative;
  height: 2px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.09);
  border-radius: 999px;
}

.processing-track > span {
  position: absolute;
  inset: 0 auto 0 0;
  width: 45%;
  background: linear-gradient(90deg, transparent, #8bb0ff, transparent);
  border-radius: inherit;
  animation: processing-slide 1.15s ease-in-out infinite;
}

@keyframes processing-slide {
  from { transform: translateX(-110%); }
  to { transform: translateX(245%); }
}

.input-wrapper {
  display: flex;
  max-width: 100%;
  background-color: transparent;
}

.input-wrapper:focus-within {
}

/* 文本域容器 - 模仿模板风格 */
.textarea-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.045);
  border: 1px solid rgba(255, 255, 255, 0.09);
  transition: all 0.2s ease;
  overflow: hidden;
  border-radius: 15px;
  box-shadow: 0 14px 35px rgba(0, 0, 0, 0.24);
}

.textarea-container:focus-within {
  background: rgba(255, 255, 255, 0.065);
  border-color: rgba(120, 166, 255, 0.48);
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.3), 0 0 0 3px rgba(120, 166, 255, 0.08);
}

.textarea-container textarea {
  flex: 1;
  width: 100%;
  padding: 1.125rem;
  border: none;
  resize: none;
  font-size: 0.875rem;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background-color: transparent;
  transition: all 0.2s ease;
  min-height: 4.0625rem;
  max-height: 150px;
  overflow-y: auto;
  line-height: 1.5;
  color: #f1f1f4;
}

.textarea-container textarea::-webkit-scrollbar {
  display: none;
}

.textarea-container textarea {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

.textarea-container textarea:focus {
  outline: none;
}

.textarea-container textarea::placeholder {
  color: #73737c;
}

/* 底部工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 0.5rem;
  border-top: none;
  background-color: transparent;
}

/* 图标按钮 - 模仿模板风格 */
.icon-btn {
  background: transparent;
  border: none;
  padding: 0.5rem;
  border-radius: 9px;
  color: #8f8f98;
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.07);
  color: #f5f5f7;
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.icon-btn svg {
  width: 1.25rem;
  height: 1.25rem;
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 发送按钮 - 模仿模板风格 */
.send-btn {
  color: #0b0b0d;
  margin-left: auto;
  background: #e9e9ec;
  border: none;
  border-radius: 10px;
  padding: 0.65rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.send-btn:hover:not(:disabled) {
  background: #fff;
  color: #0b0b0d;
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.send-btn svg {
  width: 1.25rem;
  height: 1.25rem;
}

/* 发送按钮占位符 - 预留空间避免高度突变 */
.send-btn-placeholder {
  width: 2.75rem;
  height: 2.75rem;
  flex-shrink: 0;
}

/* 自定义 Tooltip 样式 - 使用 Teleport 渲染到 body */
.custom-tooltip {
  position: fixed;
  transform: translateX(-50%);
  background-color: #303030;
  color: white;
  padding: 0.375rem 0.625rem;
  border-radius: 4px;
  font-size: 0.75rem;
  white-space: nowrap;
  pointer-events: none;
  z-index: 9999;
}

/* Tooltip 淡入淡出动画 */
.tooltip-fade-enter-active,
.tooltip-fade-leave-active {
  transition: opacity 0.15s ease;
}

.tooltip-fade-enter-from,
.tooltip-fade-leave-to {
  opacity: 0;
}

/* 上传文件展示区域 */
.uploaded-files {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-bottom: 1rem;
  padding: 0.25rem;
}

.file-thumbnail {
  position: relative;
  width: 60px;
  height: 60px;
  border-radius: var(--radius-md);
  /* 移除overflow: hidden，确保删除按钮完全可见 */
  overflow: visible;
  border: 1px solid var(--border-color);
  background-color: white;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0.5rem;
  box-shadow: var(--shadow-sm);
  transition: all 0.3s ease;
  /* 确保容器能正确显示绝对定位的删除按钮 */
  z-index: 1;
}

.file-thumbnail:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.thumbnail-image {
  width: 32px;
  height: 32px;
  object-fit: contain;
  margin-bottom: 0.125rem;
}

.file-name {
  font-size: 0.6rem;
  color: var(--text-secondary);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
  max-height: 12px;
}

.delete-file-btn {
  position: absolute;
  top: -8px;
  right: -8px;
  background-color: rgba(255, 0, 0, 0.8);
  border: 2px solid white;
  border-radius: 50%;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: all 0.3s ease;
  /* 确保是完美圆形 */
  min-width: 24px;
  min-height: 24px;
  max-width: 24px;
  max-height: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  /* 确保图标可见 */
  color: white;
  /* 确保div样式正确 */
  padding: 0;
  margin: 0;
  box-sizing: border-box;
  /* 确保图标显示正确 */
  overflow: hidden;
}

.file-thumbnail:hover .delete-file-btn {
  opacity: 1;
}

.delete-file-btn:hover {
  background-color: rgba(255, 0, 0, 1);
  transform: scale(1.1);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.delete-file-btn svg {
  width: 10px;
  height: 10px;
  stroke-width: 3;
  stroke: white;
}

/* 调整上传文件区域的间距 */
.uploaded-files {
  margin-bottom: 0.5rem;
}

.resume-section {
  flex: 1;
  min-width: 0;
  max-width: none;
  background: #0d0e11;
  margin: 0;
  padding: 0;
  position: relative;
  overflow: visible;
  border-left: none;
  min-height: 0; /* 关键：允许flex子元素收缩 */
  box-shadow: none;
  border-radius: 0;
  display: flex;
  flex-direction: column;
}

.resume-content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: hidden;
  overflow-x: hidden;
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  color: #a9abb4;
  font-size: 0.9rem;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  margin: 0.5rem 0;
  box-shadow: none;
}

.loading-spinner {
  animation: spin 1s linear infinite;
  color: #78a6ff;
  transform-origin: center;
}

.loading-text {
  font-weight: 500;
  background: linear-gradient(
    90deg,
    #8fa6d6 0%,
    #eef3ff 50%,
    #8fa6d6 100%
  );
  background-size: 200% 100%;
  background-clip: text;
  -webkit-background-clip: text;
  color: transparent;
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}

/* 图片预览弹窗样式 */
.image-preview-modal {
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

.image-preview-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.image-preview-image {
  max-width: 100%;
  max-height: 85vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.image-preview-close {
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

.image-preview-close:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* 全屏弹窗样式 */
.fullscreen-dialog-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.fullscreen-dialog {
  background-color: rgb(254, 253, 251);
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='3.0' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
  background-blend-mode: overlay;
  background-repeat: repeat;
  border: 1px solid #303030;
  border-radius: 0;
  box-shadow: none;
  width: 90%;
  max-width: 720px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #303030;
  background-color: transparent;
}

.dialog-header h3 {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 400;
  font-family: 'GTPressuraMono-Light', sans-serif;
  color: #303030;
  text-transform: uppercase;
  letter-spacing: 0.2em;
}

.dialog-close-btn {
  padding: 0.5rem;
  border: 1px solid #303030;
  background: transparent;
  color: #303030;
  cursor: pointer;
  border-radius: 0;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.dialog-close-btn:hover {
  background: #303030;
  color: #78a6ff;
}

.dialog-body {
  flex: 1;
  padding: 1.5rem;
  overflow: hidden;
}

.dialog-textarea {
  width: 100%;
  height: 100%;
  min-height: 280px;
  background-color: #f5f4f2;
  border: 1px solid #e0e0e0;
  border-radius: 0;
  padding: 1rem;
  font-size: 0.875rem;
  line-height: 1.6;
  resize: none;
  font-family: 'GTPressuraMono-Light', sans-serif;
  transition: all 0.2s ease;
  color: #303030;
}

.dialog-textarea:focus {
  outline: none;
  background-color: white;
  border-color: #303030;
}

.dialog-textarea::placeholder {
  color: #999;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid #303030;
  background-color: transparent;
}

.dialog-cancel-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #303030;
  border-radius: 0;
  background: transparent;
  color: #303030;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.25em;
  cursor: pointer;
  transition: all 0.2s ease;
}

.dialog-cancel-btn:hover {
  background: #303030;
  color: #78a6ff;
}

.dialog-save-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #303030;
  border-radius: 0;
  background: transparent;
  color: #303030;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.25em;
  cursor: pointer;
  transition: all 0.2s ease;
}

.dialog-save-btn:hover {
  background: #5f8ff2;
  border-color: #303030;
}

.dialog-submit-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #303030;
  border-radius: 0;
  background: #5f8ff2;
  color: #303030;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.25em;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 2px 2px 0 #303030;
}

.dialog-submit-btn:hover:not(:disabled) {
  background: #303030;
  color: #78a6ff;
  box-shadow: none;
  transform: translate(2px, 2px);
}

.dialog-submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 弹窗过渡动画 */
.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 0.2s ease;
}

.dialog-fade-enter-active .fullscreen-dialog,
.dialog-fade-leave-active .fullscreen-dialog {
  transition: transform 0.3s ease, opacity 0.2s ease;
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}

.dialog-fade-enter-from .fullscreen-dialog,
.dialog-fade-leave-to .fullscreen-dialog {
  transform: scale(0.95);
}

/* ==================== 翻译确认弹窗样式 ==================== */
.translate-dialog-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.translate-dialog {
  background-color: rgb(254, 253, 251);
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='3.0' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
  background-blend-mode: overlay;
  background-repeat: repeat;
  border: 1px solid #303030;
  border-radius: 0;
  width: 100%;
  max-width: 400px;
  display: flex;
  flex-direction: column;
  box-shadow: none;
}

.translate-dialog .dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #303030;
  background-color: transparent;
}

.translate-dialog .dialog-header h3 {
  font-size: 0.875rem;
  font-weight: 400;
  font-family: 'GTPressuraMono-Light', sans-serif;
  color: #303030;
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.2em;
}

.translate-dialog .dialog-body {
  padding: 1.5rem;
}

.translate-dialog .dialog-body p {
  margin: 0;
  font-size: 0.875rem;
  color: #303030;
  line-height: 1.6;
}

.translate-dialog .dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid #303030;
}

.translate-dialog .confirm-btn {
  background: #303030;
  color: #78a6ff;
  border: 1px solid #303030;
  padding: 0.5rem 1rem;
  font-size: 0.75rem;
  font-family: 'GTPressuraMono-Light', sans-serif;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: all 0.2s ease;
}

.translate-dialog .confirm-btn:hover {
  background: #4a4a4a;
}

/* ==================== JD上传弹窗样式（新增） ==================== */
.jd-dialog-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.jd-dialog {
  background-color: rgb(254, 253, 251);
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='3.0' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
  background-blend-mode: overlay;
  background-repeat: repeat;
  border: 1px solid #303030;
  border-radius: 0;
  width: 100%;
  max-width: 600px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  box-shadow: none;
}

.jd-dialog .dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #303030;
  background-color: transparent;
}

.jd-dialog .dialog-header h3 {
  font-size: 0.875rem;
  font-weight: 400;
  font-family: 'GTPressuraMono-Light', sans-serif;
  color: #303030;
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.2em;
}

.jd-dialog .dialog-close-btn {
  background: transparent;
  border: 1px solid #303030;
  cursor: pointer;
  padding: 0.5rem;
  border-radius: 0;
  color: #303030;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.jd-dialog .dialog-close-btn:hover {
  background: #303030;
  color: #78a6ff;
}

.jd-input-section {
  padding: 1.5rem;
  overflow-y: auto;
}

.jd-input-section .input-group {
  margin-bottom: 1rem;
}

.jd-input-section .input-group label {
  display: block;
  font-size: 0.75rem;
  font-weight: 400;
  font-family: 'GTPressuraMono-Light', sans-serif;
  color: #303030;
  margin-bottom: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.jd-input-section .input-group textarea {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid #e0e0e0;
  border-radius: 0;
  font-size: 0.875rem;
  line-height: 1.5;
  resize: vertical;
  font-family: 'GTPressuraMono-Light', sans-serif;
  background-color: #f5f4f2;
  transition: all 0.2s ease;
  color: #303030;
}

.jd-input-section .input-group textarea:focus {
  outline: none;
  border-color: #303030;
  background-color: white;
}

.jd-input-section .image-upload-input {
  display: block;
  width: 100%;
  padding: 0.5rem;
  border: 1px dashed #303030;
  border-radius: 0;
  font-size: 0.875rem;
  font-family: 'GTPressuraMono-Light', sans-serif;
}

.jd-image-preview {
  width: 100%;
  max-height: 200px;
  object-fit: contain;
  border-radius: 0;
  margin-top: 0.5rem;
  border: 1px solid #303030;
}

.jd-input-section .image-tip {
  font-size: 0.875rem;
  color: #666;
  margin-top: 0.75rem;
  line-height: 1.5;
  padding: 0.5rem;
  background: rgba(48, 48, 48, 0.04);
  border-left: 2px solid #78a6ff;
}

.remove-image-btn {
  margin-top: 0.5rem;
  padding: 0.4rem 0.8rem;
  background: transparent;
  color: #303030;
  border: 1px solid #303030;
  border-radius: 0;
  cursor: pointer;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  transition: all 0.2s ease;
}

.remove-image-btn:hover {
  background: rgba(95, 143, 242, 0.16);
}

.jd-dialog .dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid #303030;
  background-color: transparent;
  flex-shrink: 0;
}

.parse-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #303030;
  border-radius: 0;
  background: #5f8ff2;
  color: #303030;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  box-shadow: 2px 2px 0 #303030;
}

.parse-btn:hover:not(:disabled) {
  background: #303030;
  color: #78a6ff;
  box-shadow: none;
  transform: translate(2px, 2px);
}

.parse-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Spinner 动效 */
.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(48, 48, 48, 0.3);
  border-top-color: #303030;
  border-radius: 0;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.cancel-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #303030;
  border-radius: 0;
  background: transparent;
  color: #303030;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: all 0.2s ease;
}

.cancel-btn:hover {
  background: #303030;
  color: #78a6ff;
}

.save-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #303030;
  border-radius: 0;
  background: #5f8ff2;
  color: #303030;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 2px 2px 0 #303030;
}

.save-btn:hover {
  background: #303030;
  color: #78a6ff;
  box-shadow: none;
  transform: translate(2px, 2px);
}

/* JD表单样式 */
.jd-form-section {
  padding: 1.5rem;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.form-header {
  display: flex;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border-color);
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.4rem 0.75rem;
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.back-btn:hover {
  background: #e9ecef;
  color: var(--text-primary);
}

/* 分组标题 */
.section-title {
  font-size: 1rem;
  font-weight: 600;
  color: #212529;
  margin: 1.5rem 0 0.75rem 0;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #e9ecef;
}

/* 子项标题（学历1、工作1、项目1） */
.array-item-header span {
  font-size: 0.75rem;
  color: #6c757d;
  font-weight: 500;
}

/* 表单布局 */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem 0.75rem;
  margin-bottom: 0.75rem;
}

.form-grid + .form-grid {
  margin-top: 0.5rem;
}

/* 字段容器 */
.field-group {
  display: flex;
  flex-direction: column;
}

.field-group.full-width {
  grid-column: 1 / -1;
}

.field-group label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 0.2rem;
}

.field-group input,
.field-group select,
.field-group textarea {
  width: 100%;
  padding: 0.5rem 0.6rem;
  border: 1px solid #e9ecef;
  border-radius: var(--radius-sm);
  font-size: 0.8rem;
  font-family: inherit;
  background: #fafafa;
  transition: all 0.2s ease;
}

.field-group input:hover,
.field-group select:hover,
.field-group textarea:hover {
  border-color: #dee2e6;
}

.field-group input:focus,
.field-group select:focus,
.field-group textarea:focus {
  outline: none;
  border-color: var(--primary-color);
  background: #fff;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.08);
}

.field-group input::placeholder,
.field-group textarea::placeholder {
  color: #adb5bd;
}

.field-group textarea {
  resize: vertical;
  min-height: 56px;
  line-height: 1.5;
}

.tags-input {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.5rem;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  align-items: center;
}

.tags-input.full-width {
  grid-column: 1 / -1;
}

.tags-input .tag {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  background-color: var(--secondary-color);
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  color: var(--text-primary);
}

.tags-input .tag-remove {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  font-size: 1rem;
  line-height: 1;
  color: var(--text-secondary);
}

.tags-input .tag-remove:hover {
  color: var(--error-color);
}

/* 证件照上传样式 */
.photo-upload-group {
  grid-column: 1 / -1;
  margin-bottom: 1rem;
}

.photo-upload-area {
  width: 80px;
  height: 100px;
  border: 2px dashed #e0e0e0;
  border-radius: 8px;
  overflow: hidden;
  position: relative;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #fafafa;
  transition: all 0.2s ease;
}

.photo-upload-area:hover {
  border-color: #999;
  background-color: #f5f5f5;
}

.photo-upload-area.has-error {
  border-color: #dc3545;
}

.photo-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: #999;
  font-size: 10px;
  text-align: center;
  padding: 6px;
}

.photo-placeholder svg {
  width: 24px;
  height: 24px;
  color: #ccc;
}

.photo-placeholder small {
  display: none;
}

.photo-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.photo-input {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.remove-photo-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(0,0,0,0.6);
  color: white;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  line-height: 1;
  transition: background 0.2s ease;
  padding: 0;
}

.remove-photo-btn:hover {
  background: rgba(0,0,0,0.7);
}

.photo-error {
  color: #dc3545;
  font-size: 12px;
  margin-top: 4px;
}

.tags-input .tag-input {
  flex: 1;
  min-width: 100px;
  border: none;
  padding: 0.25rem;
  font-size: 0.875rem;
}

.tags-input .tag-input:focus {
  outline: none;
  box-shadow: none;
}

/* ==================== 简历编辑弹窗样式（新增） ==================== */
.resume-dialog-overlay {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.resume-dialog {
  background-color: rgb(254, 253, 251);
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='3.0' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
  background-blend-mode: overlay;
  background-repeat: repeat;
  border: 1px solid #303030;
  border-radius: 0;
  width: 100%;
  max-width: 700px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: none;
}

.resume-dialog .dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid #303030;
  background-color: transparent;
}

.resume-dialog .dialog-header h3 {
  font-size: 0.875rem;
  font-weight: 400;
  font-family: 'GTPressuraMono-Light', sans-serif;
  color: #303030;
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.2em;
}

.resume-dialog .dialog-close-btn {
  background: transparent;
  border: 1px solid #303030;
  cursor: pointer;
  padding: 0.5rem;
  border-radius: 0;
  color: #303030;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.resume-dialog .dialog-close-btn:hover {
  background: #303030;
  color: #78a6ff;
}

.resume-form-section {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

.resume-format-hint {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0 0 1.25rem;
  padding: 0;
  color: #aeb0b9;
  font-size: 0.78rem;
  line-height: 1.4;
  background: transparent;
  border: 0;
  border-radius: 0;
}

.resume-format-hint::before {
  content: '提示：';
  color: #d9dae0;
}

.resume-format-hint kbd {
  display: inline-block;
  padding: 0.12rem 0.38rem;
  color: #e8e9ed;
  font: inherit;
  font-size: 0.72rem;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 4px;
}

.array-item {
  border: 1px solid #303030;
  border-radius: 0;
  padding: 1rem;
  margin-bottom: 1rem;
}

.array-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  font-weight: 400;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.75rem;
  color: #303030;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.array-item-nested {
  margin-top: 0.75rem;
}

.array-item-nested > label {
  display: block;
  font-size: 0.75rem;
  font-weight: 400;
  font-family: 'GTPressuraMono-Light', sans-serif;
  color: #303030;
  margin-bottom: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.semantic-label-heading,
.semantic-label-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 7px;
  color: #ededf1;
  font-size: 0.75rem;
}

.semantic-label-heading .is-bold,
.semantic-label-toggle .is-bold { font-weight: 700; }

.semantic-label-heading button,
.semantic-label-toggle {
  padding: 3px 8px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  color: #c9cbd2;
  background: rgba(255, 255, 255, 0.045);
  cursor: pointer;
}

.semantic-label-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.semantic-label-toggle small { color: #8f929d; }

.nested-item {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.nested-item input {
  flex: 1;
}

.add-btn {
  width: 100%;
  padding: 0.5rem;
  border: 1px dashed #303030;
  background: none;
  cursor: pointer;
  border-radius: 0;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  color: #303030;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  transition: all 0.2s ease;
}

.add-btn:hover {
  background: rgba(95, 143, 242, 0.16);
  border-color: #303030;
}

.add-nested-btn {
  padding: 0.4rem 0.75rem;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  border: 1px dashed #303030;
  background: none;
  cursor: pointer;
  border-radius: 0;
  color: #303030;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  transition: all 0.2s ease;
}

.add-nested-btn:hover {
  background: rgba(95, 143, 242, 0.16);
  border-color: #303030;
}

.remove-btn {
  color: #303030;
  background: none;
  border: 1px solid #303030;
  cursor: pointer;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  padding: 0.25rem 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.remove-btn:hover {
  background: rgba(255, 91, 91, 0.08);
  color: #303030;
  border-color: #303030;
}

/* 日期选择器样式 */
.date-range-wrapper {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.element-date-picker {
  flex: 1;
}

.element-date-picker :deep(.el-input__wrapper) {
  background: #fafafa;
  border-color: #e9ecef;
}

.element-date-picker :deep(.el-input__wrapper:hover) {
  border-color: #dee2e6;
}

.element-date-picker :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.08);
}

.present-label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}

.present-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.present-text {
  color: var(--primary-color);
  font-weight: 500;
  font-size: 0.9rem;
  padding: 0.4rem 0.8rem;
  background: rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-sm);
}

.present-date-display {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: #fafafa;
  border: 1px solid #e9ecef;
  border-radius: var(--radius-sm);
  flex: 1;
}

.present-start-date {
  color: var(--text-primary);
  font-size: 0.85rem;
}

.present-separator {
  color: #adb5bd;
  font-size: 0.85rem;
}

.present-end-text {
  color: var(--primary-color);
  font-weight: 500;
  font-size: 0.85rem;
}

/* Element UI 组件样式 */
.element-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid #e9ecef;
  border-radius: var(--radius-sm);
  font-size: 0.8rem;
  font-family: inherit;
  background: #fafafa;
  transition: all 0.2s ease;
}

.element-input:hover {
  border-color: #dee2e6;
}

.element-input:focus {
  outline: none;
  border-color: var(--primary-color);
  background: #fff;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.08);
}

.element-select {
  width: 100%;
}

.element-select :deep(.el-input__wrapper) {
  background: #fafafa;
  border-color: #e9ecef;
  border-radius: var(--radius-sm);
}

.element-select :deep(.el-input__wrapper:hover) {
  border-color: #dee2e6;
}

.element-select :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.08);
}

.element-date-picker {
  width: 100%;
}

.element-date-picker :deep(.el-input__wrapper) {
  background: #fafafa;
  border-color: #e9ecef;
  border-radius: var(--radius-sm);
}

.element-date-picker :deep(.el-input__wrapper:hover) {
  border-color: #dee2e6;
}

.element-date-picker :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.08);
}

/* 其他信息单列布局 */
.others-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

/* 嵌套项全宽布局 */
.nested-item.full-width {
  flex-direction: column;
}

.nested-item.full-width :deep(.bold-textarea) {
  width: 100%;
}

.nested-item.full-width :deep(.content-area) {
  min-height: 80px;
}

/* 按钮布局优化 */
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid #303030;
  background-color: transparent;
  flex-shrink: 0;
}

.cancel-btn, .save-btn {
  min-width: 80px;
  padding: 0.5rem 1rem;
}

.save-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.save-btn:disabled .spinner {
  margin-right: 0.4rem;
}

/* 字段组的样式 */
.field-group label {
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  font-weight: 400;
  color: #303030;
  margin-bottom: 0.2rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.field-group input,
.field-group select,
.field-group textarea {
  width: 100%;
  padding: 0.5rem 0.6rem;
  border: 1px solid #e0e0e0;
  border-radius: 0;
  font-size: 0.8rem;
  font-family: 'GTPressuraMono-Light', sans-serif;
  background: #f5f4f2;
  transition: all 0.2s ease;
  color: #303030;
}

.field-group input:hover,
.field-group select:hover,
.field-group textarea:hover {
  border-color: #303030;
}

.field-group input:focus,
.field-group select:focus,
.field-group textarea:focus {
  outline: none;
  border-color: #303030;
  background: #fff;
  box-shadow: none;
}

.field-group input::placeholder,
.field-group textarea::placeholder {
  color: #999;
}

.field-group textarea {
  resize: vertical;
  min-height: 56px;
  line-height: 1.5;
}

.tags-input {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.5rem;
  border: 1px solid #e0e0e0;
  border-radius: 0;
  align-items: center;
  background: #f5f4f2;
}

.tags-input .tag {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  background-color: #e6e2dd;
  border-radius: 0;
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.6875rem;
  color: #303030;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tags-input .tag-remove {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  font-size: 1rem;
  line-height: 1;
  color: #303030;
}

.tags-input .tag-remove:hover {
  color: #78a6ff;
}

.tags-input .tag-input {
  flex: 1;
  min-width: 100px;
  border: none;
  padding: 0.25rem;
  font-size: 0.875rem;
  background: transparent;
}

.tags-input .tag-input:focus {
  outline: none;
  box-shadow: none;
}

/* 字段组的 select 样式 */
.field-group select {
  width: 100%;
  padding: 0.5rem 0.6rem;
  border: 1px solid #e0e0e0;
  border-radius: 0;
  font-size: 0.8rem;
  font-family: 'GTPressuraMono-Light', sans-serif;
  background: #f5f4f2;
  cursor: pointer;
  transition: all 0.2s ease;
  color: #303030;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23303030' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0.5rem center;
  padding-right: 1.5rem;
}

.field-group select:hover {
  border-color: #303030;
}

.field-group select:focus {
  outline: none;
  border-color: #303030;
  background-color: #fff;
}

.field-group select:hover {
  border-color: #dee2e6;
}

.field-group select:focus {
  outline: none;
  border-color: var(--primary-color);
  background: #fff;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.08);
}

/* 多行文本域样式 */
.multiline-textarea {
  width: 100%;
  min-height: 100px;
  max-height: 300px;
  padding: 0.75rem;
  border: 1px solid #e9ecef;
  border-radius: var(--radius-sm);
  font-size: 0.8rem;
  font-family: inherit;
  line-height: 1.6;
  resize: vertical;
  background: #fafafa;
  transition: all 0.2s ease;
}

.multiline-textarea:hover {
  border-color: #dee2e6;
}

.multiline-textarea:focus {
  outline: none;
  border-color: var(--primary-color);
  background: #fff;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.08);
}

/* 富文本编辑器样式 */
.rich-editor-field {
  width: 100%;
}

.rich-editor-field :deep(.rich-editor) {
  border: 1px solid #e9ecef;
  background: #fafafa;
}

.rich-editor-field :deep(.rich-editor:focus-within) {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.08);
}

.rich-editor-field :deep(.editor-content) {
  min-height: 100px;
  max-height: 200px;
  font-size: 0.85rem;
}

/* ==================== 移动端响应式布局 ==================== */
@media (max-width: 1199px) {
  /* 主内容区域 */
  .main-content {
    flex-direction: column;
    height: calc(100vh - 48px);
    overflow: hidden;
  }

  .chat-section,
  .resume-section {
    flex: none;
    width: 100%;
    height: 100%;
    border-right: none;
  }

  /* 移动端聊天视图 */
  .mobile-chat-view {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    background-color: rgb(254, 253, 251); /* 与PC端聊天区域背景色一致 */
    padding-bottom: 60px; /* 为底部导航栏留出空间 */
    position: relative;
  }

  .mobile-chat-view .chat-container {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .mobile-chat-view .messages-container {
    flex: 1;
    padding: 1rem;
    font-size: 14px;
  }

  /* 移动端输入区域 */
  .floating-input-container.mobile-input {
    padding: 12px 16px;
    padding-bottom: calc(12px + env(safe-area-inset-bottom, 0));
    background: #f9f5f0;
    border-top: 1px solid #e0e0e0;
    flex-shrink: 0;
  }

  .mobile-input .textarea-container {
    background-color: #fff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
  }

  .mobile-input .textarea-container textarea {
    min-height: 48px;
    padding: 14px;
    font-size: 16px;
  }

  .mobile-toolbar {
    height: 52px;
    padding: 0 4px;
  }

  .mobile-toolbar .icon-btn {
    width: 44px;
    height: 44px;
  }

  .mobile-toolbar .send-btn-placeholder {
    width: 44px;
    height: 44px;
  }

  /* 移动端简历视图 */
  .mobile-resume-view {
    height: 100%;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    padding-bottom: 60px; /* 为底部导航栏留出空间 */
  }

  /* 移动端设置视图 */
  .mobile-settings-view {
    padding: 2rem 1.5rem;
    overflow-y: auto;
  }

  .settings-content {
    max-width: 400px;
    margin: 0 auto;
  }

  .settings-content h2 {
    font-size: 1.25rem;
    margin-bottom: 1.5rem;
    font-weight: 600;
  }

  .settings-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 0;
    border-bottom: 1px solid #e0e0e0;
  }

  .settings-value {
    color: #666;
    font-size: 0.875rem;
  }

  .settings-logout {
    width: 100%;
    margin-top: 2rem;
    padding: 0.875rem;
    font-size: 0.875rem;
  }

  /* Tab 内容切换动画 */
  .tab-content-enter-active,
  .tab-content-leave-active {
    transition: opacity 0.2s ease, transform 0.2s ease;
  }

  .tab-content-enter-from {
    opacity: 0;
    transform: translateX(20px);
  }

  .tab-content-leave-to {
    opacity: 0;
    transform: translateX(-20px);
  }

  .tab-content-enter-to,
  .tab-content-leave-from {
    opacity: 1;
    transform: translateX(0);
  }

  /* 上传文件区域适配 */
  .uploaded-files {
    padding: 8px 12px;
    gap: 8px;
  }

  .file-thumbnail {
    padding: 6px;
  }

  .file-name {
    font-size: 11px;
    max-width: 80px;
  }
}

/* 小屏幕适配 */
@media (max-width: 480px) {
  .mobile-tab-bar {
    height: 56px;
  }

  .mobile-tab-label {
    font-size: 10px;
  }

  .mobile-tab-icon {
    width: 20px;
    height: 20px;
  }

  .floating-input-container.mobile-input {
    padding: 10px 12px;
  }

  .mobile-input .textarea-container textarea {
    padding: 12px;
    font-size: 15px;
  }

  .mobile-toolbar .icon-btn {
    width: 40px;
    height: 40px;
  }

  .mobile-toolbar .send-btn-placeholder {
    width: 40px;
    height: 40px;
  }

  .messages-container {
    padding: 0.75rem;
    font-size: 13px;
  }
}

/* Apple 风格暗色弹窗：保留所有原表单和保存逻辑 */
:is(.fullscreen-dialog-overlay, .translate-dialog-overlay, .jd-dialog-overlay, .resume-dialog-overlay) {
  background: rgba(0, 0, 0, 0.72);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
}

:is(.fullscreen-dialog, .translate-dialog, .jd-dialog, .resume-dialog) {
  color: #ededf1;
  background: #15161a;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 18px;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
}

:is(.fullscreen-dialog, .translate-dialog, .jd-dialog, .resume-dialog) .dialog-header {
  color: #f5f5f7;
  background: rgba(255, 255, 255, 0.02);
  border-bottom-color: rgba(255, 255, 255, 0.075);
}

:is(.fullscreen-dialog, .translate-dialog, .jd-dialog, .resume-dialog) .dialog-header h3 {
  color: #f5f5f7;
}

:is(.fullscreen-dialog, .translate-dialog, .jd-dialog, .resume-dialog) .dialog-close-btn {
  color: #9b9ba4;
  background: rgba(255, 255, 255, 0.055);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 9px;
}

:is(.fullscreen-dialog, .translate-dialog, .jd-dialog, .resume-dialog) .dialog-close-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
}

:is(.jd-dialog, .resume-dialog) label,
:is(.jd-dialog, .resume-dialog) .section-title,
:is(.jd-dialog, .resume-dialog) .form-header {
  color: #cfcfd5;
}

:is(.jd-dialog, .resume-dialog) :is(input, textarea, select),
.fullscreen-dialog .dialog-textarea {
  color: #ededf1;
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.1);
  border-radius: 10px;
}

:is(.jd-dialog, .resume-dialog) select {
  color-scheme: dark;
}

:is(.jd-dialog, .resume-dialog) select option {
  color: #ededf1;
  background: #292a30;
}

:is(.jd-dialog, .resume-dialog) select option:checked {
  color: #fff;
  background: #454750;
}

:is(.jd-dialog, .resume-dialog) :is(input, textarea, select):focus,
.fullscreen-dialog .dialog-textarea:focus {
  color: #f5f5f7;
  background: #25262c !important;
  border-color: rgba(120, 166, 255, 0.55);
  box-shadow: 0 0 0 3px rgba(120, 166, 255, 0.09);
}

:is(.jd-dialog, .resume-dialog) :is(input, textarea)::placeholder,
.fullscreen-dialog .dialog-textarea::placeholder {
  color: #6f6f78;
}

:is(.jd-dialog, .resume-dialog) .dialog-actions,
:is(.fullscreen-dialog, .translate-dialog) .dialog-footer {
  background: rgba(255, 255, 255, 0.015);
  border-top-color: rgba(255, 255, 255, 0.075);
}

.translate-dialog .dialog-body p,
.translate-dialog .cancel-btn,
.translate-dialog .confirm-btn {
  color: #f5f5f7;
}

.translate-dialog .cancel-btn {
  border-color: rgba(255, 255, 255, 0.14);
}

.translate-dialog .confirm-btn {
  background: #5f8ff2;
  border-color: #78a6ff;
}

:is(.dialog-save-btn, .dialog-submit-btn) {
  color: #fff;
  background: #5f8ff2;
  border-color: #78a6ff;
  border-radius: 9px;
  box-shadow: none;
}

:is(.dialog-save-btn, .dialog-submit-btn):hover:not(:disabled) {
  color: #fff;
  background: #78a6ff;
  border-color: #8eb5ff;
  transform: translateY(-1px);
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.25);
}

:is(.jd-dialog, .resume-dialog) :deep(.el-input__wrapper),
:is(.jd-dialog, .resume-dialog) :deep(.el-select__wrapper),
:is(.jd-dialog, .resume-dialog) :deep(.el-date-editor) {
  color: #ededf1;
  background: rgba(255, 255, 255, 0.05) !important;
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
}

.resume-dialog .element-select {
  --el-component-size: 46px;
}

.resume-dialog .field-group input.element-input,
.resume-dialog .field-group > input:not([type='checkbox']):not([type='file']) {
  height: 46px;
  min-height: 46px;
  padding-block: 0;
  box-sizing: border-box;
}

.resume-dialog .element-select :deep(.el-select__wrapper),
.resume-dialog .element-select :deep(.el-input__wrapper),
.resume-dialog .element-date-picker :deep(.el-input__wrapper),
.resume-dialog :deep(.element-date-picker.el-input__wrapper) {
  height: 46px !important;
  min-height: 46px !important;
  padding: 0 0.75rem;
  box-sizing: border-box !important;
}

.resume-dialog .present-date-display {
  height: 46px;
  min-height: 46px;
  box-sizing: border-box;
  color: #ededf1;
  background: rgba(255, 255, 255, 0.045);
  border-color: rgba(255, 255, 255, 0.1);
  border-radius: 10px;
}

.resume-dialog .present-start-date {
  color: #ededf1;
}

.resume-dialog .present-separator {
  color: #777780;
}

.resume-dialog .present-end-text {
  color: #78a6ff;
}

.resume-dialog .present-label {
  color: #d5d5da;
}

.resume-dialog .present-label input[type='checkbox'] {
  position: relative;
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  margin: 0;
  padding: 0;
  appearance: none;
  background: #25262c;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 4px;
  box-shadow: none;
}

.resume-dialog .present-label input[type='checkbox']:checked {
  background: #5f8ff2;
  border-color: #78a6ff;
}

.resume-dialog .present-label input[type='checkbox']:checked::after {
  position: absolute;
  top: 2px;
  left: 5px;
  width: 5px;
  height: 9px;
  content: '';
  border: solid #fff;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

.resume-dialog :deep(.element-date-picker) {
  gap: 8px;
}

.resume-dialog :deep(.element-date-picker .el-range-input) {
  height: auto;
  min-height: 0;
  padding: 0 4px;
  color: #ededf1;
  background: transparent !important;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.resume-dialog :deep(.element-date-picker .el-range-input:focus) {
  background: transparent !important;
  border: 0;
  box-shadow: none;
}

.resume-dialog :deep(.element-date-picker .el-range__icon) {
  width: 18px;
  margin: 0 2px 0 0;
  flex: 0 0 18px;
}

.resume-dialog :deep(.element-date-picker .el-range-separator) {
  width: 22px;
  flex: 0 0 22px;
  color: #777780;
}

.resume-dialog :deep(.element-date-picker .el-range__close-icon) {
  width: 18px;
  margin-left: 2px;
  flex: 0 0 18px;
}

.resume-dialog .element-select :deep(.el-select__placeholder),
.resume-dialog .element-select :deep(.el-select__selected-item),
.resume-dialog .element-select :deep(.el-input__inner) {
  font-family: 'GTPressuraMono-Light', sans-serif;
  font-size: 0.8rem !important;
  font-weight: 400;
  line-height: 1.2;
}

:is(.jd-dialog, .resume-dialog) :deep(.el-input__wrapper:hover),
:is(.jd-dialog, .resume-dialog) :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.18) inset !important;
}

:is(.jd-dialog, .resume-dialog) :deep(.is-focus .el-input__wrapper),
:is(.jd-dialog, .resume-dialog) :deep(.el-input__wrapper.is-focus),
:is(.jd-dialog, .resume-dialog) :deep(.el-select__wrapper.is-focused) {
  color: #f5f5f7 !important;
  background: #25262c !important;
  box-shadow: 0 0 0 1px rgba(120, 166, 255, 0.6) inset,
    0 0 0 3px rgba(120, 166, 255, 0.09) !important;
}

:is(.jd-dialog, .resume-dialog) :deep(.el-input__inner),
:is(.jd-dialog, .resume-dialog) :deep(.el-select__selected-item),
:is(.jd-dialog, .resume-dialog) :deep(.el-select__placeholder) {
  color: #ededf1 !important;
}

:is(.jd-dialog, .resume-dialog) :deep(.el-select__caret),
:is(.jd-dialog, .resume-dialog) :deep(.el-input__icon) {
  color: #8d8d96;
}

:global(.resume-dark-select-popper.el-popper) {
  background: #25262c !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
  box-shadow: 0 18px 45px rgba(0, 0, 0, 0.42) !important;
}

:global(.resume-dark-select-popper .el-popper__arrow::before) {
  background: #25262c !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
}

:global(.resume-dark-select-popper .el-select-dropdown__item) {
  color: #d8d8dd !important;
  background: transparent !important;
}

:global(.resume-dark-select-popper .el-select-dropdown__item:hover),
:global(.resume-dark-select-popper .el-select-dropdown__item.is-hovering) {
  color: #fff !important;
  background: rgba(255, 255, 255, 0.08) !important;
}

:global(.resume-dark-select-popper .el-select-dropdown__item.is-selected) {
  color: #a9c5ff !important;
  background: rgba(95, 143, 242, 0.12) !important;
}

:global(.resume-dark-date-popper.el-picker__popper) {
  --el-bg-color-overlay: #25262c;
  --el-border-color-light: rgba(255, 255, 255, 0.1);
  --el-border-color-lighter: rgba(255, 255, 255, 0.075);
  --el-fill-color-light: rgba(95, 143, 242, 0.12);
  --el-fill-color: rgba(255, 255, 255, 0.06);
  --el-text-color-primary: #ededf1;
  --el-text-color-regular: #c8cad2;
  --el-text-color-secondary: #8d8f98;
  color: #ededf1;
  background: #25262c !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
  box-shadow: 0 22px 60px rgba(0, 0, 0, 0.48) !important;
}

:global(.resume-dark-date-popper .el-picker-panel),
:global(.resume-dark-date-popper .el-picker-panel__body-wrapper),
:global(.resume-dark-date-popper .el-picker-panel__body),
:global(.resume-dark-date-popper .el-date-range-picker__content) {
  color: #d8d9de;
  background: #25262c !important;
}

:global(.resume-dark-date-popper .el-date-range-picker__content.is-left) {
  border-right-color: rgba(255, 255, 255, 0.09);
}

:global(.resume-dark-date-popper .el-date-range-picker__header),
:global(.resume-dark-date-popper .el-picker-panel__icon-btn) {
  color: #f1f1f4;
}

:global(.resume-dark-date-popper .el-month-table td) {
  color: #c9cad0;
}

:global(.resume-dark-date-popper .el-month-table td .el-date-table-cell) {
  background: transparent;
}

:global(.resume-dark-date-popper .el-month-table td:hover .el-date-table-cell__text) {
  color: #fff;
  background: rgba(120, 166, 255, 0.16);
}

:global(.resume-dark-date-popper .el-month-table td.in-range .el-date-table-cell) {
  background: rgba(95, 143, 242, 0.14);
}

:global(.resume-dark-date-popper .el-month-table td.start-date .el-date-table-cell__text),
:global(.resume-dark-date-popper .el-month-table td.end-date .el-date-table-cell__text) {
  color: #fff;
  background: #5f8ff2;
}

:global(.resume-dark-date-popper .el-month-table td.disabled .el-date-table-cell) {
  color: #5f616a;
  background: rgba(255, 255, 255, 0.02);
}

:global(.resume-dark-date-popper .el-popper__arrow::before) {
  background: #25262c !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
}

:is(.jd-dialog, .resume-dialog) .save-btn {
  color: #fff;
  background: #5f8ff2;
  border-color: #78a6ff;
  border-radius: 9px;
  box-shadow: none;
}

:is(.jd-dialog, .resume-dialog) .save-btn:hover:not(:disabled) {
  color: #fff;
  background: #78a6ff;
  border-color: #8eb5ff;
  transform: translateY(-1px);
}

:is(.jd-dialog, .resume-dialog) .cancel-btn {
  color: #d5d5da;
  background: rgba(255, 255, 255, 0.055);
  border-color: rgba(255, 255, 255, 0.1);
  border-radius: 9px;
}

:is(.jd-dialog, .resume-dialog) .cancel-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.16);
}

.resume-dialog .photo-upload-area,
.resume-dialog .array-item,
.resume-dialog .tags-input {
  color: #d5d5da;
  background: rgba(255, 255, 255, 0.035);
  border-color: rgba(255, 255, 255, 0.09);
}

.resume-dialog .array-item-header {
  color: #ededf1;
}

.resume-dialog .remove-btn {
  color: #9b9da6;
  background: transparent;
  border-color: rgba(255, 255, 255, 0.12);
  border-radius: 7px;
}

.resume-dialog .remove-btn:hover,
.resume-dialog .remove-btn:focus-visible {
  color: #ff9b9b;
  background: rgba(255, 91, 91, 0.08);
  border-color: rgba(255, 123, 123, 0.35);
  outline: none;
}

.resume-dialog .tags-input {
  min-height: 46px;
  padding: 0.5rem;
  box-sizing: border-box;
}

.resume-dialog .tags-input .tag {
  color: #dbe6ff;
  background: rgba(95, 143, 242, 0.13);
  border-radius: 6px;
}

.resume-dialog .tags-input .tag-remove {
  color: #9fb7e9;
}

.resume-dialog .tags-input .tag-remove:hover {
  color: #fff;
}

.resume-dialog .tags-input .tag-input {
  height: 28px;
  min-height: 28px;
  padding: 0.25rem;
  color: #ededf1;
  background: transparent !important;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.resume-dialog .tags-input .tag-input:focus {
  background: transparent !important;
  border: 0;
  box-shadow: none;
}

.resume-dialog .add-btn,
.resume-dialog .add-nested-btn {
  color: #a9abb4;
  background: rgba(255, 255, 255, 0.025);
  border-color: rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  outline: none;
}

.resume-dialog .add-btn:hover,
.resume-dialog .add-btn:focus-visible,
.resume-dialog .add-nested-btn:hover,
.resume-dialog .add-nested-btn:focus-visible {
  color: #eef3ff;
  background: rgba(95, 143, 242, 0.1);
  border-color: rgba(120, 166, 255, 0.48);
  box-shadow: 0 0 0 3px rgba(120, 166, 255, 0.08);
}

.resume-dialog .add-btn:active,
.resume-dialog .add-nested-btn:active {
  color: #fff;
  background: rgba(95, 143, 242, 0.16);
  border-color: rgba(120, 166, 255, 0.62);
}

.resume-dialog .photo-upload-area:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(120, 166, 255, 0.45);
}

.resume-dialog .array-item-header span,
.resume-dialog .array-item-nested > label {
  color: #ededf1;
}

.jd-input-section .input-group label {
  color: #b5b5bd;
}

.jd-input-section .input-group textarea {
  color: #ededf1;
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.1);
  border-radius: 10px;
}

.jd-input-section .input-group textarea::placeholder {
  color: #777780;
}

.jd-input-section .input-group textarea:focus {
  color: #fff;
  background: rgba(255, 255, 255, 0.065);
  border-color: rgba(120, 166, 255, 0.55);
  box-shadow: 0 0 0 3px rgba(120, 166, 255, 0.09);
}

.jd-dialog .parse-btn {
  color: #fff;
  background: #5f8ff2;
  border-color: #78a6ff;
  border-radius: 9px;
  box-shadow: none;
}

.jd-dialog .parse-btn:hover:not(:disabled) {
  color: #fff;
  background: #78a6ff;
  border-color: #8eb5ff;
  box-shadow: none;
  transform: translateY(-1px);
}

.jd-dialog .parse-btn:disabled {
  color: #777780;
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.08);
  opacity: 1;
}

@media (max-width: 1199px) {
  .workspace-shell,
  .mobile-chat-view,
  .mobile-resume-view {
    background: #0c0c0e;
  }

  .task-sidebar {
    background: #0d0e11;
    border-bottom-color: rgba(255, 255, 255, 0.065);
  }

  .floating-input-container.mobile-input {
    background: #0c0c0e;
    border-top-color: rgba(255, 255, 255, 0.065);
  }

  .mobile-input .textarea-container {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.09);
  }
}

/* ResumeBranch workspace finish */
.app-header {
  background: #1b1c20;
  border-bottom-color: rgba(255, 255, 255, 0.075);
}

.header-brand-link {
  display: inline-flex;
  text-decoration: none;
}

.app-header h1 {
  margin: 0;
}

.workspace-shell {
  background: #1b1c20;
}

.task-sidebar {
  background: #202126;
  border-right-color: rgba(255, 255, 255, 0.075);
}

.main-content,
.chat-section,
.chat-container,
.floating-input-container {
  background: #222329;
}

.chat-panel-header {
  background: #1e1f24;
  border-bottom-color: rgba(255, 255, 255, 0.075);
}

.textarea-container {
  background: #292a30;
  border-color: rgba(255, 255, 255, 0.095);
}

.textarea-container:focus-within {
  background: #2c2d34;
}

.workspace-modal-mask {
  position: fixed;
  inset: 0;
  z-index: 2200;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(8, 9, 12, 0.68);
  backdrop-filter: blur(18px);
}

.workspace-modal {
  width: min(520px, 100%);
  padding: 26px;
  color: #f4f4f5;
  background: #23242a;
  border: 1px solid rgba(255, 255, 255, 0.11);
  border-radius: 20px;
  box-shadow: 0 28px 80px rgba(0, 0, 0, 0.42);
}

.workspace-modal.compact {
  width: min(440px, 100%);
}

.workspace-modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 22px;
}

.workspace-modal-header h2 {
  margin: 5px 0 0;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.workspace-modal-kicker {
  color: #92b4ff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.18em;
}

.workspace-modal-kicker.danger {
  color: #ff9d9d;
}

.modal-close-btn {
  width: 32px;
  height: 32px;
  padding: 0;
  color: #a6a6ae;
  font-size: 23px;
  line-height: 28px;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 50%;
  cursor: pointer;
}

.modal-close-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.07);
}

.modal-close-btn:focus-visible {
  outline: 2px solid #89aefc;
  outline-offset: 2px;
}

.modal-close-btn.light {
  flex: 0 0 auto;
  margin-left: auto;
  color: #555861;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.start-modal .modal-close-btn.light:hover {
  color: #f1f1f3;
  background: transparent;
}

.workspace-field {
  display: grid;
  gap: 8px;
  margin-bottom: 20px;
  color: #b8b8c0;
  font-size: 13px;
}

.workspace-field input {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  box-sizing: border-box;
  padding: 12px 14px;
  color: #f5f5f7;
  font: inherit;
  background: #2b2c32;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 11px;
  outline: none;
}

.workspace-field input:focus {
  border-color: #7fa8ff;
  box-shadow: 0 0 0 3px rgba(90, 137, 238, 0.14);
}

.copy-mode-fieldset {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  border: 0;
}

.copy-mode-fieldset legend {
  margin-bottom: 9px;
  color: #b8b8c0;
  font-size: 13px;
}

.copy-mode-card {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: center;
  gap: 12px;
  padding: 14px;
  color: #ececef;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 13px;
  cursor: pointer;
}

.copy-mode-card:hover {
  background: rgba(255, 255, 255, 0.045);
}

.copy-mode-card.active {
  background: rgba(91, 139, 242, 0.1);
  border-color: rgba(125, 167, 255, 0.65);
}

.copy-mode-card input {
  accent-color: #86aaff;
}

.copy-mode-icon {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  color: #dce7ff;
  background: rgba(124, 165, 255, 0.13);
  border-radius: 9px;
}

.copy-mode-card strong,
.copy-mode-card small {
  display: block;
}

.task-create-steps {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: -4px 0 20px;
}

.task-create-steps span {
  display: grid;
  height: 24px;
  place-items: center;
  color: #777983;
  font-size: 11px;
  border-bottom: 2px solid rgba(255, 255, 255, 0.08);
}

.task-create-steps span.active {
  color: #cbd9ff;
  border-color: #7fa8ff;
}

.task-create-panel {
  max-height: min(55vh, 520px);
  overflow-y: auto;
}

.task-step-heading {
  display: grid;
  gap: 5px;
  margin-bottom: 16px;
}

.task-step-heading strong { font-size: 15px; }
.task-step-heading small { color: #999ba4; font-size: 12px; line-height: 1.55; }

.resume-source-picker {
  display: grid;
  gap: 7px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.task-import-picker {
  margin-top: 16px;
}

.task-import-button {
  display: grid;
  width: 100%;
  gap: 5px;
  padding: 18px;
  color: #e8edfa;
  text-align: left;
  background: rgba(124, 165, 255, 0.07);
  border: 1px dashed rgba(125, 167, 255, 0.55);
  border-radius: 12px;
  cursor: pointer;
}

.task-import-button:hover {
  background: rgba(124, 165, 255, 0.12);
}

.task-import-button small {
  color: #999ba4;
}

.source-group-title,
.other-resume-sources summary,
.source-project-group > strong {
  color: #aeb0ba;
  font-size: 12px;
}

.resume-source-row {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px 11px;
  border-radius: 9px;
  cursor: pointer;
}

.resume-source-row:hover { background: rgba(255, 255, 255, 0.045); }
.resume-source-row input { accent-color: #86aaff; }
.resume-source-row span,
.resume-source-row b,
.resume-source-row small { display: block; }
.resume-source-row span { min-width: 0; }
.resume-source-row b { color: #e6e6ea; font-size: 13px; }
.resume-source-row small { margin-top: 3px; color: #8f919a; font-size: 11px; }

.other-resume-sources { margin-top: 5px; }
.other-resume-sources summary { padding: 8px 0; cursor: pointer; }
.source-project-group { margin: 8px 0 12px 12px; }
.source-project-group > strong { display: block; margin-bottom: 5px; }

.task-jd-input {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  padding: 13px 14px;
  color: #eeeef2;
  font: inherit;
  font-size: 13px;
  line-height: 1.65;
  background: #2b2c32;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 11px;
  outline: none;
}

.task-jd-input:focus { border-color: #7fa8ff; }

.task-review-list {
  display: grid;
  gap: 10px;
  margin: 0;
}

.task-review-list div {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 12px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.025);
  border-radius: 9px;
}

.task-review-list dt { color: #94969f; font-size: 12px; }
.task-review-list dd { margin: 0; color: #e1e1e5; font-size: 13px; }

.copy-mode-card strong {
  margin-bottom: 3px;
  font-size: 14px;
}

.copy-mode-card small {
  color: #9b9ba4;
  font-size: 12px;
  line-height: 1.45;
}

.workspace-modal-copy {
  margin: 0;
  color: #b9b9c1;
  font-size: 14px;
  line-height: 1.75;
}

.workspace-modal-error {
  margin: 14px 0 0;
  color: #ffaaaa;
  font-size: 13px;
}

.workspace-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 24px;
}

.workspace-btn {
  min-width: 92px;
  padding: 10px 15px;
  color: #ececf0;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  cursor: pointer;
}

.workspace-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.07);
}

.workspace-btn.primary {
  color: #fff;
  background: #5f8ff2;
  border-color: #78a6ff;
}

.workspace-btn.danger {
  color: #fff;
  background: #a64649;
  border-color: #b9565a;
}

.workspace-btn:disabled {
  cursor: wait;
  opacity: 0.55;
}

.start-modal-footer {
  margin-top: 18px;
}

.modal-mask {
  background: rgba(8, 9, 12, 0.68);
  backdrop-filter: blur(18px);
}

.modal-container {
  color: #f2f2f4;
  background: #23242a;
  border: 1px solid rgba(255, 255, 255, 0.11);
  border-radius: 20px;
  box-shadow: 0 28px 80px rgba(0, 0, 0, 0.42);
}

.modal-container .modal-header {
  border-bottom-color: rgba(255, 255, 255, 0.08);
}

.modal-container .modal-header h2,
.modal-container .option-label,
.modal-container .identity-title,
.modal-container .upload-title,
.modal-container .pdf-filename {
  color: #f1f1f3;
}

.modal-container .modal-desc,
.modal-container .option-sublabel,
.modal-container .identity-desc,
.modal-container .upload-hint,
.modal-container .upload-formats,
.modal-container .pdf-hint {
  color: #9c9ca5;
}

.modal-container .header-badge,
.modal-container .optionGraphic,
.modal-container .identity-icon,
.modal-container .upload-graphic,
.modal-container .pdf-icon-wrapper {
  color: #d9e5ff;
  background: rgba(124, 165, 255, 0.12);
  border-color: rgba(124, 165, 255, 0.22);
}

.modal-container .option-item,
.modal-container .identity-card,
.modal-container .upload-box,
.modal-container .preview-box {
  color: #ededf0;
  background: rgba(255, 255, 255, 0.028);
  border-color: rgba(255, 255, 255, 0.09);
}

.import-draft-review {
  padding: 20px;
  border: 1px solid rgba(117, 162, 255, 0.28);
  border-radius: 12px;
  background: rgba(117, 162, 255, 0.07);
}

.import-draft-review h3 { margin: 0 0 12px; font-size: 15px; }
.import-draft-review p { margin: 7px 0; color: #d6d9e2; font-size: 13px; }
.import-draft-review .import-source-fingerprint { color: #8f93a0; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; }
.import-draft-review small { display: block; margin-top: 12px; color: #9699a4; line-height: 1.55; }

.import-persistent-error {
  margin: 0 20px 16px;
  padding: 10px 12px;
  color: #ffb0b0;
  background: rgba(255, 93, 93, 0.08);
  border: 1px solid rgba(255, 112, 112, 0.22);
  border-radius: 9px;
  font-size: 12px;
  line-height: 1.5;
}

.modal-container .option-item:hover,
.modal-container .identity-card:hover,
.modal-container .upload-box:hover {
  background: rgba(255, 255, 255, 0.055);
  border-color: rgba(255, 255, 255, 0.16);
}

.start-modal .option-item,
.start-modal .optionGraphic {
  color: #c8cad1;
  background: rgba(255, 255, 255, 0.028);
  border-color: rgba(255, 255, 255, 0.09);
}

.start-modal .option-item:hover {
  background: rgba(96, 139, 232, 0.11);
  border-color: rgba(126, 167, 255, 0.55);
}

.start-modal .option-item:hover .optionGraphic {
  color: #d9e5ff;
  background: rgba(124, 165, 255, 0.12);
  border-color: rgba(124, 165, 255, 0.55);
}

.modal-container .option-item.primary,
.modal-container .identity-card.active {
  background: rgba(96, 139, 232, 0.11);
  border-color: rgba(126, 167, 255, 0.55);
}

.modal-container .identity-card.active .identity-icon,
.modal-container .identity-card.active .identity-icon.pink {
  color: #202126;
  background: #f5f5f7;
  border-color: #f5f5f7;
}

.modal-container .option-item.primary .option-label,
.modal-container .option-item.primary .option-sublabel {
  color: inherit;
}

.modal-container .option-arrow,
.modal-container .modal-back {
  color: #a6a6af;
}

.modal-container .modal-back {
  background: transparent;
  border-color: rgba(255, 255, 255, 0.1);
}

.modal-container .modal-footer {
  border-top-color: rgba(255, 255, 255, 0.08);
}

.modal-container .btn-primary {
  color: #fff;
  background: #5f8ff2;
  border-color: #78a6ff;
  box-shadow: none;
}

.modal-container .btn-primary:hover:not(:disabled) {
  color: #fff;
  background: #78a6ff;
}

.modal-container .btn-secondary {
  color: #d0d0d5;
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
}

.modal-container .custom-identity-input textarea {
  color: #eeeeF1;
  background: #2b2c32;
  border-color: rgba(255, 255, 255, 0.1);
}

.modal-container .custom-identity-input textarea::placeholder {
  color: #777780;
}

.app-toast {
  position: fixed;
  top: 84px;
  left: 50%;
  z-index: 3000;
  max-width: min(460px, calc(100vw - 32px));
  padding: 11px 16px;
  color: #f4f4f5;
  font-size: 13px;
  background: #292a30;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 11px;
  box-shadow: 0 16px 42px rgba(0, 0, 0, 0.3);
  transform: translateX(-50%);
}

.app-toast.is-error {
  border-color: rgba(255, 139, 139, 0.35);
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, -8px);
}

.inline-edit-row {
  display: grid;
  grid-template-columns: minmax(120px, 0.7fr) minmax(180px, 1.3fr) auto;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
}

@media (max-width: 640px) {
  .inline-edit-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1199px) {
  .workspace-shell,
  .mobile-chat-view,
  .mobile-resume-view {
    background: #222329;
  }

  .task-sidebar {
    background: #202126;
  }

  .floating-input-container.mobile-input {
    background: #222329;
  }
}

@media (max-width: 640px) {
  .workspace-modal {
    padding: 20px;
    border-radius: 16px;
  }

  .copy-mode-card {
    grid-template-columns: auto 1fr;
  }

  .copy-mode-card input {
    grid-row: 1;
  }

  .copy-mode-icon {
    display: none;
  }
}
</style>
