<template>
  <div class="homepage">
    <header class="home-header">
      <BrandLogo />
      <div class="header-actions">
        <span v-if="isLocalMode" class="mode-pill">
          <i></i>
          本地模式
        </span>
        <button v-if="isLocalMode" class="quiet-btn" @click="openSettings">设置</button>
      </div>
    </header>

    <main class="home-main">
      <section class="workspace-intro">
        <div>
          <span class="eyebrow">Resume workspace</span>
          <h1>你的简历工作区</h1>
          <p>维护一份长期更新的主简历，针对不同 JD 创建独立岗位版本。</p>
        </div>
        <button class="primary-btn create-main-btn" @click="openCreateDialog">＋ 新建主简历</button>
      </section>

      <section v-if="canUseProjects" class="resume-library">
        <div class="section-heading">
          <h2>最近编辑</h2>
          <span>{{ projects.length }} 份主简历</span>
        </div>

        <div v-if="isLoadingProjects" class="loading-card">正在加载主简历…</div>

        <div v-else-if="projects.length" class="project-grid">
          <article
            v-for="(project, index) in projects"
            :key="project.id"
            :class="['project-card', { featured: index === 0 }]"
            @click="openProject(project)"
          >
            <button
              class="card-menu"
              type="button"
              aria-label="删除主简历"
              title="删除主简历"
              @click.stop="openDeleteDialog(project)"
            >
              •••
            </button>

            <div class="project-copy">
              <div class="project-meta">
                <i v-if="index === 0" class="live-dot"></i>
                {{ formatUpdatedAt(project.updated_at) }}
              </div>
              <h3>{{ project.title }}</h3>
              <p>
                {{ project.candidate_name || '姓名尚未填写' }}
                <span>·</span>
                {{ project.target_position || '目标岗位尚未填写' }}
              </p>
              <div class="project-stats">
                <div>
                  <strong>{{ Math.max((project.task_count || 1) - 1, 0) }}</strong>
                  <span>岗位版本</span>
                </div>
                <div>
                  <strong>{{ project.candidate_name ? '已建立' : '待完善' }}</strong>
                  <span>主简历状态</span>
                </div>
              </div>
            </div>

            <div v-if="index === 0" class="paper-thumbnail" aria-hidden="true">
              <strong>{{ project.candidate_name || '主简历' }}</strong>
              <i></i><i class="short"></i>
              <b></b>
              <i></i><i></i><i class="short"></i>
              <b></b>
              <i></i><i></i><i></i>
            </div>
          </article>
        </div>

        <button v-else class="empty-state" @click="openCreateDialog">
          <span class="empty-plus">＋</span>
          <strong>创建第一份主简历</strong>
          <small>从空白开始，或上传现有简历自动解析</small>
        </button>

      </section>

      <section v-else class="login-card">
        <h2>登录后开始管理简历</h2>
        <p>登录后可以创建主简历并为不同岗位建立独立版本。</p>
        <button class="primary-btn" @click="router.push('/login')">前往登录</button>
      </section>

      <section class="help-section" aria-label="产品帮助">
        <article>
          <span class="eyebrow">How it works</span>
          <h3>一份主简历，适配多个岗位</h3>
          <p>先沉淀完整经历，再为每个 JD 复制一份独立版本，后续修改互不干扰。</p>
        </article>
        <article>
          <span class="eyebrow">Resume assistant</span>
          <h3>通过对话梳理真实经历</h3>
          <p>补全信息、分析岗位匹配度，并将确认后的修改同步到右侧简历。</p>
        </article>
        <article>
          <span class="eyebrow">Help</span>
          <h3>解析、排版与 PDF</h3>
          <p>支持简历解析、页面排版、中英文版本和标准 PDF 导出。</p>
        </article>
      </section>

      <footer class="home-footer">
        <span>ResumeBranch · Local Resume Workspace</span>
        <span>数据仅保存在当前设备</span>
      </footer>
    </main>

    <Teleport to="body">
      <Transition name="modal-fade">
        <div v-if="showCreateDialog" class="internal-modal-mask" @click.self="closeCreateDialog">
          <section class="internal-modal" role="dialog" aria-modal="true" aria-labelledby="create-title">
            <header>
              <div>
                <span class="modal-kicker">New resume</span>
                <h2 id="create-title">新建主简历</h2>
              </div>
              <button class="modal-close" aria-label="关闭" @click="closeCreateDialog">×</button>
            </header>
            <div class="modal-body">
              <p>创建一份长期维护的主简历，之后可以针对不同 JD 建立独立岗位版本。</p>
              <label for="project-title">简历名称</label>
              <input
                id="project-title"
                ref="projectTitleInput"
                v-model="newProjectTitle"
                maxlength="120"
                placeholder="例如：郑梓锐的主简历"
                @keydown.enter="createProject"
              />
              <small>稍后可以随时重命名</small>
              <p v-if="createError" class="form-error">{{ createError }}</p>
            </div>
            <footer>
              <button class="secondary-btn" :disabled="isCreatingProject" @click="closeCreateDialog">取消</button>
              <button class="primary-btn" :disabled="isCreatingProject" @click="createProject">
                {{ isCreatingProject ? '创建中…' : '创建并进入' }}
              </button>
            </footer>
          </section>
        </div>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="modal-fade">
        <div v-if="projectToDelete" class="internal-modal-mask" @click.self="closeDeleteDialog">
          <section class="internal-modal danger-modal" role="alertdialog" aria-modal="true" aria-labelledby="delete-title">
            <header>
              <div>
                <span class="modal-kicker danger">Delete resume</span>
                <h2 id="delete-title">删除主简历？</h2>
              </div>
              <button class="modal-close" aria-label="关闭" @click="closeDeleteDialog">×</button>
            </header>
            <div class="modal-body">
              <p>
                “{{ projectToDelete.title }}”及其
                <strong>{{ Math.max((projectToDelete.task_count || 1) - 1, 0) }} 个岗位版本</strong>
                的 JD、对话和简历内容都会被永久删除。
              </p>
              <div class="danger-note">此操作无法撤销。</div>
              <p v-if="deleteError" class="form-error">{{ deleteError }}</p>
            </div>
            <footer>
              <button class="secondary-btn" :disabled="isDeletingProject" @click="closeDeleteDialog">取消</button>
              <button class="danger-btn" :disabled="isDeletingProject" @click="confirmDeleteProject">
                {{ isDeletingProject ? '删除中…' : '确认删除' }}
              </button>
            </footer>
          </section>
        </div>
      </Transition>
    </Teleport>

    <Teleport to="body">
      <Transition name="modal-fade">
        <div v-if="showSettingsDialog" class="internal-modal-mask" @click.self="closeSettings">
          <section class="internal-modal settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
            <header>
              <div>
                <span class="modal-kicker">Local settings</span>
                <h2 id="settings-title">模型与 API</h2>
              </div>
              <button class="modal-close" aria-label="关闭" @click="closeSettings">×</button>
            </header>
            <div class="modal-body">
              <p>在本地模式下接入自己的模型服务。密钥仅交给当前主机上的后端使用。</p>
              <div class="settings-grid">
                <div class="field">
                  <label id="provider-label">服务商</label>
                  <div ref="providerSelectRoot" class="provider-select">
                    <button
                      type="button"
                      class="provider-select-trigger"
                      aria-labelledby="provider-label"
                      :aria-expanded="showProviderMenu"
                      @click="showProviderMenu = !showProviderMenu"
                    >
                      <span>{{ selectedProvider?.label || '选择服务商' }}</span>
                      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5" /></svg>
                    </button>
                    <div v-if="showProviderMenu" class="provider-select-menu" role="listbox" aria-labelledby="provider-label">
                      <button
                        v-for="provider in providerCatalog"
                        :key="provider.id"
                        type="button"
                        role="option"
                        :aria-selected="provider.id === llmSettings.provider"
                        :class="['provider-select-option', { active: provider.id === llmSettings.provider }]"
                        @click="chooseProvider(provider.id)"
                      >
                        {{ provider.label }}
                      </button>
                    </div>
                  </div>
                </div>
                <div class="field">
                  <label for="model">模型</label>
                  <input id="model" v-model="llmSettings.model" placeholder="填写厂商当前模型 ID" @change="syncTemperatureForModel" />
                </div>
                <div class="field full">
                  <label for="base-url">Base URL</label>
                  <input id="base-url" v-model="llmSettings.base_url" placeholder="填写 OpenAI 兼容 Base URL" />
                </div>
                <div class="field full">
                  <label for="api-key">API Key</label>
                  <input
                    id="api-key"
                    v-model="llmSettings.api_key"
                    type="password"
                    :placeholder="llmSettings.configured ? '已配置，留空表示不更改' : '输入 API Key'"
                    autocomplete="off"
                  />
                </div>
                <div v-if="selectedTemperature?.supported" class="field full">
                  <label for="temperature">温度 Temperature</label>
                  <div class="temperature-field">
                    <input
                      id="temperature"
                      v-model.number="llmSettings.temperature"
                      type="range"
                      :min="selectedTemperature.min"
                      :max="selectedTemperature.max"
                      :step="selectedTemperature.step"
                    />
                    <input
                      v-model.number="llmSettings.temperature"
                      type="number"
                      :min="selectedTemperature.min"
                      :max="selectedTemperature.max"
                      :step="selectedTemperature.step"
                    />
                  </div>
                </div>
              </div>
              <div v-if="selectedProvider?.note" class="provider-note">
                {{ selectedProvider.note }}
                <a v-if="selectedProvider.docs_url" :href="selectedProvider.docs_url" target="_blank" rel="noreferrer">官方文档</a>
              </div>
              <div class="security-note">
                前端不会读取或回显完整密钥；保存后由本地后端更新配置。
              </div>
              <div v-if="settingsStatus.message" :class="['settings-status', settingsStatus.type]">
                <i></i>{{ settingsStatus.message }}
              </div>
            </div>
            <footer>
              <button class="secondary-btn" :disabled="isTestingSettings || isSavingSettings" @click="testSettings">
                {{ isTestingSettings ? '测试中…' : '测试连接' }}
              </button>
              <button class="primary-btn" :disabled="isTestingSettings || isSavingSettings" @click="saveSettings">
                {{ isSavingSettings ? '保存中…' : '保存设置' }}
              </button>
            </footer>
          </section>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import BrandLogo from '../components/BrandLogo.vue'
import { buildAuthorizationHeaders, loadAppConfig } from '../config/appMode.js'

const router = useRouter()
const projects = ref([])
const isLoadingProjects = ref(false)
const appConfig = ref(null)
const showCreateDialog = ref(false)
const newProjectTitle = ref('')
const projectTitleInput = ref(null)
const isCreatingProject = ref(false)
const createError = ref('')
const projectToDelete = ref(null)
const isDeletingProject = ref(false)
const deleteError = ref('')
const showSettingsDialog = ref(false)
const showProviderMenu = ref(false)
const providerSelectRoot = ref(null)
const isTestingSettings = ref(false)
const isSavingSettings = ref(false)
const settingsStatus = ref({ type: '', message: '' })
const providerCatalog = ref([])
const providerProfiles = ref({})
const llmSettings = ref({
  provider: 'kimi_api',
  model: '',
  base_url: '',
  api_key: '',
  temperature: null,
  configured: false
})

const selectedProvider = computed(() => providerCatalog.value.find(item => item.id === llmSettings.value.provider))
const selectedTemperature = computed(() => {
  const config = selectedProvider.value?.temperature
  if (!config) return null
  const model = llmSettings.value.model.toLowerCase()
  const modelDisablesTemperature =
    ['kimi_api', 'kimi_coding'].includes(llmSettings.value.provider) ||
    (llmSettings.value.provider === 'deepseek' && /(reasoner|thinking)/.test(model)) ||
    (llmSettings.value.provider === 'openai' && /^(gpt-5|o1|o3|o4)/.test(model))
  return { ...config, supported: config.supported && !modelDisablesTemperature }
})

const isLocalMode = computed(() => appConfig.value?.app_mode === 'local')
const canUseProjects = computed(() => isLocalMode.value || !!localStorage.getItem('access_token'))

function authHeaders() {
  return {
    'Content-Type': 'application/json',
    ...buildAuthorizationHeaders(localStorage.getItem('access_token') || '')
  }
}

function formatUpdatedAt(value) {
  if (!value) return '最近编辑'
  const date = new Date(value)
  const distance = Date.now() - date.getTime()
  if (distance < 60_000) return '刚刚编辑'
  if (distance < 3_600_000) return `${Math.max(1, Math.floor(distance / 60_000))} 分钟前编辑`
  if (distance < 86_400_000) return `${Math.max(1, Math.floor(distance / 3_600_000))} 小时前编辑`
  if (distance < 604_800_000) return `${Math.max(1, Math.floor(distance / 86_400_000))} 天前编辑`
  return date.toLocaleDateString('zh-CN')
}

async function loadProjects() {
  if (!canUseProjects.value) return
  isLoadingProjects.value = true
  try {
    const response = await fetch('/projects', { headers: authHeaders() })
    if (response.ok) projects.value = await response.json()
  } finally {
    isLoadingProjects.value = false
  }
}

async function openProject(project) {
  const response = await fetch(`/projects/${project.id}`, { headers: authHeaders() })
  if (!response.ok) return
  const detail = await response.json()
  const task = detail.tasks?.find(item => item.is_base) || detail.tasks?.[0]
  if (task) router.push(`/projects/${project.id}/tasks/${task.id}`)
}

function openCreateDialog() {
  if (!canUseProjects.value) {
    router.push('/register')
    return
  }
  newProjectTitle.value = ''
  createError.value = ''
  showCreateDialog.value = true
  nextTick(() => projectTitleInput.value?.focus())
}

function closeCreateDialog() {
  if (isCreatingProject.value) return
  showCreateDialog.value = false
  createError.value = ''
}

async function createProject() {
  if (isCreatingProject.value) return
  const title = newProjectTitle.value.trim()
  if (!title) {
    createError.value = '请输入主简历名称'
    projectTitleInput.value?.focus()
    return
  }

  isCreatingProject.value = true
  createError.value = ''
  try {
    const response = await fetch('/projects', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ title })
    })
    if (!response.ok) throw new Error((await response.json()).detail || '创建失败')
    const project = await response.json()
    showCreateDialog.value = false
    await router.push({
      path: `/projects/${project.id}/tasks/${project.base_task_id}`,
      query: { new: '1' }
    })
  } catch (error) {
    createError.value = error.message || '创建失败，请稍后重试'
  } finally {
    isCreatingProject.value = false
  }
}

function openDeleteDialog(project) {
  projectToDelete.value = project
  deleteError.value = ''
}

function closeDeleteDialog() {
  if (isDeletingProject.value) return
  projectToDelete.value = null
  deleteError.value = ''
}

async function confirmDeleteProject() {
  if (!projectToDelete.value || isDeletingProject.value) return
  isDeletingProject.value = true
  deleteError.value = ''
  try {
    const response = await fetch(`/projects/${projectToDelete.value.id}`, {
      method: 'DELETE',
      headers: authHeaders()
    })
    if (!response.ok) throw new Error((await response.json()).detail || '删除失败')
    projects.value = projects.value.filter(item => item.id !== projectToDelete.value.id)
    projectToDelete.value = null
  } catch (error) {
    deleteError.value = error.message || '删除失败，请稍后重试'
  } finally {
    isDeletingProject.value = false
  }
}

async function openSettings() {
  showSettingsDialog.value = true
  settingsStatus.value = { type: '', message: '' }
  try {
    const response = await fetch('/settings/llm', { headers: authHeaders() })
    if (!response.ok) throw new Error((await response.json()).detail || '无法读取配置')
    const data = await response.json()
    providerCatalog.value = data.providers || []
    providerProfiles.value = data.profiles || {}
    llmSettings.value.provider = data.active_provider || providerCatalog.value[0]?.id || 'kimi_api'
    selectProvider()
  } catch (error) {
    settingsStatus.value = { type: 'error', message: error.message || '无法读取配置' }
  }
}

function selectProvider() {
  const provider = selectedProvider.value
  const profile = providerProfiles.value[llmSettings.value.provider] || {}
  llmSettings.value = {
    provider: llmSettings.value.provider,
    model: profile.model || '',
    base_url: profile.base_url || '',
    api_key: '',
    temperature: profile.temperature_supported === false
      ? null
      : (profile.temperature ?? provider?.temperature?.default ?? null),
    configured: !!profile.configured
  }
  settingsStatus.value = { type: '', message: '' }
}

function chooseProvider(providerId) {
  llmSettings.value.provider = providerId
  showProviderMenu.value = false
  selectProvider()
}

function syncTemperatureForModel() {
  if (selectedTemperature.value?.supported && llmSettings.value.temperature === null) {
    llmSettings.value.temperature = selectedProvider.value?.temperature?.default ?? 0.2
  } else if (!selectedTemperature.value?.supported) {
    llmSettings.value.temperature = null
  }
}

function closeSettings() {
  if (isTestingSettings.value || isSavingSettings.value) return
  showSettingsDialog.value = false
  showProviderMenu.value = false
  llmSettings.value.api_key = ''
}

function settingsPayload() {
  return {
    provider: llmSettings.value.provider,
    model: llmSettings.value.model.trim(),
    base_url: llmSettings.value.base_url.trim(),
    api_key: llmSettings.value.api_key.trim() || null,
    temperature: llmSettings.value.temperature
  }
}

async function testSettings() {
  if (isTestingSettings.value) return
  isTestingSettings.value = true
  settingsStatus.value = { type: '', message: '' }
  try {
    const response = await fetch('/settings/llm/test', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(settingsPayload())
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || '连接失败')
    settingsStatus.value = { type: 'success', message: `连接成功 · ${data.model}` }
  } catch (error) {
    settingsStatus.value = { type: 'error', message: error.message || '连接失败' }
  } finally {
    isTestingSettings.value = false
  }
}

async function saveSettings() {
  if (isSavingSettings.value) return
  isSavingSettings.value = true
  settingsStatus.value = { type: '', message: '' }
  try {
    const response = await fetch('/settings/llm', {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify(settingsPayload())
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || '保存失败')
    providerCatalog.value = data.providers || providerCatalog.value
    providerProfiles.value = data.profiles || providerProfiles.value
    selectProvider()
    settingsStatus.value = { type: 'success', message: '设置已保存，后续请求立即生效' }
  } catch (error) {
    settingsStatus.value = { type: 'error', message: error.message || '保存失败' }
  } finally {
    isSavingSettings.value = false
  }
}

function handleKeydown(event) {
  if (event.key !== 'Escape') return
  if (showProviderMenu.value) {
    showProviderMenu.value = false
    return
  }
  if (showCreateDialog.value) closeCreateDialog()
  if (projectToDelete.value) closeDeleteDialog()
  if (showSettingsDialog.value) closeSettings()
}

function handleDocumentClick(event) {
  if (providerSelectRoot.value && !providerSelectRoot.value.contains(event.target)) {
    showProviderMenu.value = false
  }
}

onMounted(async () => {
  appConfig.value = await loadAppConfig()
  await loadProjects()
  window.addEventListener('keydown', handleKeydown)
  document.addEventListener('click', handleDocumentClick)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('click', handleDocumentClick)
})
</script>

<style scoped>
.homepage {
  --home-bg: #191a1f;
  --home-surface: #202126;
  --home-surface-soft: #25262c;
  --home-line: rgba(255, 255, 255, 0.085);
  --home-line-strong: rgba(255, 255, 255, 0.14);
  --home-text: #f3f3f5;
  --home-muted: #96979f;
  --home-action: #5f8ff2;
  --home-action-hover: #75a2ff;
  --home-action-soft: rgba(95, 143, 242, 0.14);
  --home-control-font-size: 0.8rem;
  min-height: 100vh;
  color: var(--home-text);
  background:
    radial-gradient(circle at 78% -8%, rgba(114, 141, 209, 0.09), transparent 34%),
    var(--home-bg);
  overflow: auto;
}

.home-header {
  position: sticky;
  top: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  padding: 0 2.1rem;
  border-bottom: 1px solid var(--home-line);
  background: rgba(25, 26, 31, 0.9);
  backdrop-filter: blur(20px);
}

.header-actions,
.mode-pill {
  display: flex;
  align-items: center;
}

.header-actions {
  gap: 0.65rem;
}

.mode-pill {
  gap: 0.45rem;
  padding: 0.48rem 0.2rem;
  border: 0;
  border-radius: 0;
  color: var(--home-muted);
  background: transparent;
  font-size: var(--home-control-font-size);
}

.mode-pill i,
.live-dot,
.settings-status i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #6ed69b;
  box-shadow: 0 0 10px rgba(110, 214, 155, 0.7);
}

.quiet-btn,
.secondary-btn {
  border: 1px solid var(--home-line);
  color: #d4d4d9;
  background: rgba(255, 255, 255, 0.045);
}

.quiet-btn {
  padding: 0.5rem 0.3rem;
  border: 0;
  border-radius: 0;
  background: transparent;
  font-size: var(--home-control-font-size);
  cursor: pointer;
}

.quiet-btn:hover {
  color: #fff;
  background: transparent;
}

.home-main {
  width: min(1120px, calc(100% - 4.5rem));
  margin: 0 auto;
  padding: 4.5rem 0 6.5rem;
}

.workspace-intro {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 2rem;
  margin-bottom: 2.6rem;
}

.eyebrow,
.modal-kicker {
  color: var(--home-muted);
  font-size: 0.68rem;
  font-weight: 650;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.workspace-intro h1 {
  margin: 0.7rem 0 0;
  font-size: clamp(2.35rem, 4.5vw, 3.45rem);
  font-weight: 590;
  line-height: 1.05;
  letter-spacing: -0.05em;
}

.workspace-intro p {
  margin: 1rem 0 0;
  color: var(--home-muted);
  font-size: 0.92rem;
}

.primary-btn,
.secondary-btn,
.danger-btn {
  min-height: 39px;
  padding: 0.62rem 0.9rem;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 620;
  transition: 0.16s ease;
}

.primary-btn {
  border: 1px solid #5f8ff2 !important;
  color: #fff !important;
  background: #5f8ff2 !important;
}

.primary-btn:hover:not(:disabled) {
  border-color: #75a2ff !important;
  background: #75a2ff !important;
  transform: translateY(-1px);
}

.create-main-btn {
  flex: 0 0 auto;
  padding-inline: 1.1rem;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.85rem;
}

.section-heading h2 {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 620;
}

.section-heading span {
  color: #70717a;
  font-size: 0.7rem;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.project-card {
  position: relative;
  min-height: 238px;
  overflow: hidden;
  border: 1px solid var(--home-line);
  border-radius: 19px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.035), transparent 55%),
    var(--home-surface);
  cursor: pointer;
  transition: 0.18s ease;
}

.project-card:hover {
  border-color: var(--home-line-strong);
  transform: translateY(-2px);
}

.project-card.featured {
  grid-column: span 2;
  min-height: 286px;
}

.project-copy {
  position: relative;
  z-index: 2;
  display: flex;
  width: calc(100% - 1px);
  height: 100%;
  min-height: inherit;
  padding: 1.7rem;
  flex-direction: column;
}

.featured .project-copy {
  width: calc(100% - 245px);
}

.project-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--home-muted);
  font-size: 0.7rem;
}

.project-card h3 {
  margin: 1.5rem 0 0.5rem;
  font-size: 1.45rem;
  font-weight: 580;
  letter-spacing: -0.035em;
}

.project-card p {
  margin: 0;
  color: var(--home-muted);
  font-size: 0.78rem;
  line-height: 1.6;
}

.project-card p span {
  margin: 0 0.3rem;
  color: #666771;
}

.project-stats {
  display: flex;
  gap: 2.1rem;
  margin-top: auto;
  padding-top: 2rem;
}

.project-stats strong,
.project-stats span {
  display: block;
}

.project-stats strong {
  margin-bottom: 0.25rem;
  font-size: 0.92rem;
  font-weight: 620;
}

.project-stats span {
  color: #70717a;
  font-size: 0.65rem;
}

.card-menu {
  position: absolute;
  top: 1.15rem;
  right: 1.15rem;
  z-index: 5;
  display: grid;
  width: 40px;
  height: 32px;
  padding: 0;
  box-sizing: border-box;
  place-items: center;
  border: 0;
  border-radius: 0;
  color: #fff;
  background: transparent;
  font-size: 1.1rem;
  line-height: 1;
  letter-spacing: 0.08em;
  opacity: 0.82;
  cursor: pointer;
}

.featured .card-menu {
  right: 2rem;
}

.card-menu:hover {
  color: #fff;
  background: transparent;
  opacity: 1;
}

.card-menu:focus,
.card-menu:focus-visible {
  outline: none;
  background: transparent;
}

.paper-thumbnail {
  position: absolute;
  right: 2rem;
  bottom: -1.5rem;
  width: 205px;
  height: 255px;
  padding: 1.5rem 1.15rem;
  border-radius: 8px 8px 0 0;
  color: #26272a;
  background: #fff;
  box-shadow: -18px 20px 48px rgba(0, 0, 0, 0.22);
  transform: rotate(1.2deg);
}

.paper-thumbnail strong {
  display: block;
  margin-bottom: 1rem;
  font-size: 0.68rem;
  text-align: center;
}

.paper-thumbnail i,
.paper-thumbnail b {
  display: block;
  height: 3px;
  margin-bottom: 6px;
  border-radius: 2px;
  background: rgba(38, 39, 42, 0.16);
}

.paper-thumbnail i.short {
  width: 62%;
}

.paper-thumbnail b {
  width: 38%;
  height: 4px;
  margin: 0.9rem 0 0.5rem;
  background: rgba(38, 39, 42, 0.48);
}

.loading-card,
.empty-state,
.login-card {
  width: 100%;
  border: 1px dashed var(--home-line-strong);
  border-radius: 17px;
  color: var(--home-muted);
  background: rgba(255, 255, 255, 0.018);
}

.loading-card {
  padding: 3rem;
  text-align: center;
}

.empty-state {
  display: grid;
  min-height: 210px;
  place-items: center;
  align-content: center;
  gap: 0.5rem;
  cursor: pointer;
}

.empty-state strong {
  color: #e4e4e7;
}

.empty-state small {
  color: #74757d;
}

.empty-plus {
  display: grid;
  width: 38px;
  height: 38px;
  margin-bottom: 0.25rem;
  place-items: center;
  border: 1px solid var(--home-line-strong);
  border-radius: 12px;
  color: #a9c5ff;
  background: var(--home-action-soft);
  font-size: 1.2rem;
}

.help-section {
  display: grid;
  margin-top: 4.6rem;
  overflow: hidden;
  grid-template-columns: 1.1fr 1fr 1fr;
  gap: 1px;
  border: 1px solid var(--home-line);
  border-radius: 19px;
  background: var(--home-line);
}

.help-section article {
  min-height: 168px;
  padding: 1.5rem;
  background: #1d1e23;
}

.help-section h3 {
  margin: 0.7rem 0 0.65rem;
  font-size: 0.92rem;
}

.help-section p {
  margin: 0;
  color: var(--home-muted);
  font-size: 0.72rem;
  line-height: 1.65;
}

.home-footer {
  display: flex;
  justify-content: space-between;
  padding-top: 1.25rem;
  color: #696a72;
  font-size: 0.66rem;
}

.login-card {
  padding: 3rem;
  text-align: center;
}

.internal-modal-mask {
  position: fixed;
  inset: 0;
  z-index: 20000;
  display: grid;
  padding: 1rem;
  place-items: center;
  background: rgba(6, 7, 9, 0.72);
  backdrop-filter: blur(16px);
}

.internal-modal {
  width: min(440px, 100%);
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 19px;
  color: #f1f1f3;
  background: #24252b;
  box-shadow: 0 28px 80px rgba(0, 0, 0, 0.46);
}

.internal-modal.settings-modal {
  --settings-control-font-size: 0.8rem;
  width: min(520px, 100%);
}

.internal-modal > header,
.internal-modal > footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.1rem 1.3rem;
}

.internal-modal > header {
  border-bottom: 1px solid rgba(255, 255, 255, 0.075);
}

.internal-modal > footer {
  justify-content: flex-end;
  gap: 0.6rem;
  border-top: 1px solid rgba(255, 255, 255, 0.075);
  background: rgba(255, 255, 255, 0.015);
}

.internal-modal h2 {
  margin: 0.28rem 0 0;
  font-size: 1.08rem;
}

.modal-close {
  width: 31px;
  height: 31px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 9px;
  color: #96979f;
  background: rgba(255, 255, 255, 0.045);
  cursor: pointer;
  font-size: 1.15rem;
}

.modal-body {
  padding: 1.2rem 1.3rem 1.35rem;
}

.modal-body > p {
  margin: 0 0 1.15rem;
  color: #9d9ea6;
  font-size: 0.78rem;
  line-height: 1.6;
}

.modal-body label,
.field label {
  display: block;
  margin-bottom: 0.45rem;
  color: #cfcfd4;
  font-size: 0.72rem;
}

.modal-body input,
.modal-body select {
  width: 100%;
  height: 42px;
  padding: 0 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  outline: 0;
  border-radius: 10px;
  color: #f2f2f4;
  background: rgba(255, 255, 255, 0.05);
}

.settings-modal .modal-body input,
.settings-modal .provider-select-trigger,
.settings-modal .provider-select-option,
.settings-modal > footer .primary-btn,
.settings-modal > footer .secondary-btn {
  font-family: inherit;
  font-size: var(--settings-control-font-size);
  font-weight: 400;
}

.modal-body input:focus,
.modal-body select:focus {
  border-color: rgba(120, 166, 255, 0.6);
  box-shadow: 0 0 0 3px rgba(120, 166, 255, 0.09);
}

.provider-select {
  position: relative;
}

.provider-select-trigger {
  display: flex;
  width: 100%;
  height: 42px;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  color: #f2f2f4;
  background: rgba(255, 255, 255, 0.05);
  font: inherit;
  text-align: left;
}

.provider-select-trigger:hover,
.provider-select-trigger[aria-expanded='true'] {
  color: #fff;
  background: #303138;
  border-color: rgba(120, 166, 255, 0.6);
  box-shadow: 0 0 0 3px rgba(120, 166, 255, 0.09);
}

.provider-select-trigger svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: #bfc0c7;
  stroke-width: 2;
}

.provider-select-menu {
  position: absolute;
  z-index: 30;
  top: calc(100% + 6px);
  right: 0;
  left: 0;
  max-height: 260px;
  padding: 5px;
  overflow-y: auto;
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 10px;
  background: #292a30;
  box-shadow: 0 18px 45px rgba(0, 0, 0, 0.45);
  color-scheme: dark;
}

.provider-select-option {
  display: block;
  width: 100%;
  padding: 0.62rem 0.7rem;
  border: 0;
  border-radius: 7px;
  color: #d6d7dc;
  background: transparent;
  font: inherit;
  text-align: left;
}

.provider-select-option:hover,
.provider-select-option:focus-visible {
  color: #fff;
  background: #393a42;
}

.provider-select-option.active {
  color: #fff;
  background: #454750;
}

.provider-select-menu::-webkit-scrollbar-track {
  background: #24252a;
}

.provider-select-menu::-webkit-scrollbar-thumb {
  background: #555761;
}

.modal-body > small {
  display: block;
  margin-top: 0.45rem;
  color: #71727a;
  font-size: 0.66rem;
}

.form-error {
  margin: 0.75rem 0 0 !important;
  color: #ff9b9b !important;
}

.danger-note,
.security-note {
  padding: 0.7rem 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: #9d9ea6;
  background: rgba(255, 255, 255, 0.025);
  font-size: 0.7rem;
}

.danger-note {
  color: #ffaaaa;
  border-color: rgba(255, 95, 95, 0.17);
  background: rgba(255, 95, 95, 0.055);
}

.danger-btn {
  border: 1px solid #c84f57;
  color: #fff;
  background: #b9444c;
}

.danger-btn:hover:not(:disabled) {
  border-color: #e06a71;
  background: #cf525a;
}

.danger-modal .secondary-btn,
.danger-modal .danger-btn {
  min-height: 36px;
  padding: 0.5rem 0.78rem;
  font-size: 0.74rem;
}

.modal-kicker.danger {
  color: #ff9292;
}

.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.9rem;
}

.field.full {
  grid-column: 1 / -1;
}

.security-note {
  margin-top: 1rem;
}

.provider-note {
  margin-top: 0.8rem;
  color: #b8b8c0;
  font-size: 0.7rem;
  line-height: 1.55;
}

.provider-note a {
  margin-left: 0.45rem;
  color: #91b6ff;
}

.temperature-field {
  display: grid;
  grid-template-columns: 1fr 84px;
  gap: 0.75rem;
  align-items: center;
}

.temperature-field input[type="number"] {
  width: 100%;
}

.settings-status {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin-top: 0.85rem;
  color: #aaaab2;
  font-size: 0.7rem;
}

.settings-status.error {
  color: #ff9b9b;
}

.settings-status.error i {
  background: #ff7373;
  box-shadow: 0 0 10px rgba(255, 115, 115, 0.55);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

button:focus {
  outline: none;
}

button:focus-visible {
  outline: 2px solid #75a2ff;
  outline-offset: 2px;
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.18s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

@media (max-width: 760px) {
  .home-header {
    padding: 0 1rem;
  }

  .mode-pill {
    display: none;
  }

  .home-main {
    width: calc(100% - 2rem);
    padding-top: 3rem;
  }

  .workspace-intro {
    align-items: stretch;
    flex-direction: column;
  }

  .project-grid {
    grid-template-columns: 1fr;
  }

  .project-card.featured {
    grid-column: auto;
  }

  .featured .project-copy {
    width: 100%;
  }

  .paper-thumbnail {
    display: none;
  }

  .help-section {
    grid-template-columns: 1fr;
  }

  .home-footer {
    gap: 0.5rem;
    flex-direction: column;
  }

  .settings-grid {
    grid-template-columns: 1fr;
  }

  .field.full {
    grid-column: auto;
  }
}
</style>
