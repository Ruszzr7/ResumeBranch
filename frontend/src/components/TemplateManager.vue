<script setup>
import { computed, ref, watch } from 'vue'
import {
  DEFAULT_LAYOUT_CONFIG,
  FONT_SIZE_LABELS,
  FONT_SIZE_LIMITS,
  normalizeLayoutConfig
} from '../utils/layoutConfig.js'

const props = defineProps({
  open: { type: Boolean, default: false },
  currentLayout: { type: Object, default: () => ({}) },
  activeTemplateId: { type: String, default: 'default' }
})

const emit = defineEmits(['close', 'apply', 'active-template-removed'])

const STORAGE_KEY = 'resume-assistant.custom-layout-templates.v1'
const clone = value => JSON.parse(JSON.stringify(value))
const sectionLabels = {
  education: '教育经历',
  skills: '专业技能',
  research_interests: '研究方向',
  honors: '主要荣誉',
  work_experience: '工作经历',
  internship_experience: '实习经历',
  project_experience: '项目经历',
  custom_sections: '自定义栏目',
  others: '证书与语言',
  self_evaluation: '自我评价'
}

function defaultTemplateLayout() {
  const layout = normalizeLayoutConfig(DEFAULT_LAYOUT_CONFIG)
  Object.assign(layout.global, {
    density: 'compact',
    fontSize: 9,
    lineHeight: 1.28,
    moduleMargin: 0.55,
    marginVertical: 8.5,
    marginHorizontal: 9,
    titleStyle: 'plain'
  })
  Object.assign(layout.basics, { preset: 'left-aligned', contactLayout: 'inline' })
  Object.assign(layout.education, { preset: 'compact', schoolTagStyle: 'outline', metricsPlacement: 'with-degree' })
  Object.assign(layout.work_experience, { preset: 'compact', detailsStyle: 'bullets', datePosition: 'right' })
  Object.assign(layout.project_experience, { preset: 'compact', detailsStyle: 'bullets', datePosition: 'right' })
  Object.assign(layout.others, { preset: 'tags', separator: 'dot' })
  Object.assign(layout.self_evaluation, { preset: 'compact' })
  return normalizeLayoutConfig(layout)
}

const defaultTemplate = Object.freeze({ id: 'default', name: '默认', layout: defaultTemplateLayout(), system: true })
const templates = ref([])
const view = ref('list')
const editingId = ref('')
const draftName = ref('')
const draftLayout = ref(defaultTemplateLayout())
const nameError = ref('')
const nameDialog = ref(null)
const deleteTarget = ref(null)

function loadTemplates() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    templates.value = Array.isArray(parsed)
      ? parsed.filter(item => item?.id && item?.name && item?.layout).map(item => ({
          id: String(item.id),
          name: String(item.name).slice(0, 20),
          layout: normalizeLayoutConfig(item.layout)
        }))
      : []
  } catch {
    templates.value = []
  }
}

function persistTemplates() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(templates.value))
}

watch(() => props.open, value => {
  if (!value) return
  loadTemplates()
  view.value = 'list'
  editingId.value = ''
  nameDialog.value = null
  deleteTarget.value = null
})

const displayedTemplates = computed(() => [...templates.value, defaultTemplate])
const fontSizeEntries = computed(() => Object.entries(FONT_SIZE_LABELS))

function previewStyle(layoutValue) {
  const layout = normalizeLayoutConfig(layoutValue)
  return {
    '--preview-font-size': `${Math.max(5.2, layout.typography.fontSizes.body * 0.64)}px`,
    '--preview-line-height': layout.global.lineHeight,
    '--preview-module-gap': `${Math.max(3, layout.global.moduleMargin * 7)}px`,
    '--preview-horizontal-padding': `${Math.max(8, layout.global.marginHorizontal * 1.05)}px`,
    '--preview-vertical-padding': `${Math.max(8, layout.global.marginVertical * 1.05)}px`,
    '--preview-title-size': `${Math.max(6.4, layout.typography.fontSizes.sectionTitle * 0.62)}px`,
    '--preview-name-size': `${Math.max(8, layout.typography.fontSizes.name * 0.62)}px`
  }
}

function beginCreate() {
  editingId.value = ''
  draftName.value = ''
  draftLayout.value = defaultTemplateLayout()
  nameError.value = ''
  view.value = 'editor'
}

function beginEdit(template) {
  editingId.value = template.id
  draftName.value = template.name
  draftLayout.value = clone(template.layout)
  nameError.value = ''
  view.value = 'editor'
}

function validateName(name, excludedId = '') {
  const clean = String(name || '').trim().slice(0, 20)
  if (!clean) return { clean, error: '请输入模板名称' }
  if (templates.value.some(item => item.id !== excludedId && item.name === clean)) {
    return { clean, error: '模板名称已存在' }
  }
  return { clean, error: '' }
}

function saveDraft() {
  const { clean, error } = validateName(draftName.value, editingId.value)
  nameError.value = error
  if (error) return
  const normalized = normalizeLayoutConfig(draftLayout.value)
  if (editingId.value) {
    const target = templates.value.find(item => item.id === editingId.value)
    if (target) Object.assign(target, { name: clean, layout: normalized })
  } else {
    templates.value.push({
      id: `custom-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: clean,
      layout: normalized
    })
  }
  persistTemplates()
  view.value = 'list'
}

function applyTemplate(template) {
  if (template.id === props.activeTemplateId) return
  emit('apply', { id: template.id, layout: normalizeLayoutConfig(template.layout) })
}

function openNameDialog(mode, template) {
  nameDialog.value = {
    mode,
    id: template.id,
    value: mode === 'copy' ? `${template.name}副本`.slice(0, 20) : template.name,
    error: '',
    source: template
  }
}

function confirmNameDialog() {
  const dialog = nameDialog.value
  if (!dialog) return
  const excludedId = dialog.mode === 'rename' ? dialog.id : ''
  const { clean, error } = validateName(dialog.value, excludedId)
  dialog.error = error
  if (error) return
  if (dialog.mode === 'rename') {
    const target = templates.value.find(item => item.id === dialog.id)
    if (target) target.name = clean
  } else {
    templates.value.push({
      id: `custom-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: clean,
      layout: normalizeLayoutConfig(dialog.source.layout)
    })
  }
  persistTemplates()
  nameDialog.value = null
}

function requestDelete(template) {
  deleteTarget.value = template
}

function confirmDelete() {
  if (!deleteTarget.value) return
  const id = deleteTarget.value.id
  templates.value = templates.value.filter(item => item.id !== id)
  persistTemplates()
  if (props.activeTemplateId === id) emit('active-template-removed')
  deleteTarget.value = null
}

function moveDraftSection(index, direction) {
  const order = [...draftLayout.value.global.sectionOrder]
  const target = index + direction
  if (target < 0 || target >= order.length) return
  ;[order[index], order[target]] = [order[target], order[index]]
  draftLayout.value.global.sectionOrder = order
}
</script>

<template>
  <div v-if="open" class="template-manager-overlay" @click.self="emit('close')">
    <section class="template-manager" role="dialog" aria-modal="true" aria-labelledby="template-manager-title">
      <header class="template-manager-header">
        <div class="template-manager-heading">
          <button v-if="view === 'editor'" class="back-button" type="button" @click="view = 'list'">←</button>
          <h3 id="template-manager-title">{{ view === 'editor' ? (editingId ? '编辑模板' : '新建模板') : '模板管理' }}</h3>
        </div>
        <button class="close-button" type="button" aria-label="关闭模板窗口" @click="emit('close')">×</button>
      </header>

      <div v-if="view === 'list'" class="template-grid">
        <article v-for="template in displayedTemplates" :key="template.id" class="template-card">
          <h4>{{ template.name }}</h4>
          <div class="template-sheet-frame">
            <div class="template-sheet-preview" :class="[`basics-${template.layout.basics.preset}`, `title-${template.layout.global.titleStyle}`]" :style="previewStyle(template.layout)">
              <header><strong>示例姓名</strong><span>求职方向 · 138****8888 · example@email.com</span></header>
              <section><h5>教育经历</h5><p><b>示例大学</b><span>硕士 · 电子信息 · 3.8/5.0 (前10%)</span><i>2022—2025</i></p></section>
              <section><h5>专业技能</h5><p>1. Python、Vue、FastAPI、MySQL</p></section>
              <section><h5>工作经历</h5><p><b>示例科技有限公司</b><i>2024—至今</i></p><p>• 负责核心服务与交付效率优化</p></section>
              <section><h5>项目经历</h5><p><b>智能简历助手</b><i>2023—2024</i></p><p>• 项目简介：完成编辑、预览与导出</p><p>• 项目职责：(1) 设计统一排版协议</p></section>
            </div>
          </div>
          <button class="apply-button" type="button" :class="{ current: template.id === activeTemplateId }" :disabled="template.id === activeTemplateId" @click="applyTemplate(template)">
            {{ template.id === activeTemplateId ? '当前模板' : '应用模板' }}
          </button>
          <div v-if="!template.system" class="template-action-row">
            <button type="button" @click="beginEdit(template)">编辑</button>
            <button type="button" @click="openNameDialog('copy', template)">复制</button>
            <button type="button" @click="openNameDialog('rename', template)">重命名</button>
            <button class="danger" type="button" @click="requestDelete(template)">删除</button>
          </div>
          <div v-else class="template-action-row default-action-row">
            <button type="button" @click="openNameDialog('copy', template)">复制</button>
          </div>
        </article>

        <article class="template-card create-card">
          <h4>自定义</h4>
          <button class="create-sheet" type="button" aria-label="新建自定义模板" @click="beginCreate"><span>+</span></button>
          <button class="apply-button" type="button" @click="beginCreate">新建模板</button>
        </article>
      </div>

      <div v-else class="template-editor">
        <aside class="template-controls">
          <label class="name-control">
            <span>模板名称</span>
            <input v-model="draftName" maxlength="20" placeholder="请输入模板名称">
            <small v-if="nameError">{{ nameError }}</small>
          </label>

          <fieldset>
            <legend>页面设置</legend>
            <label><span>上下页边距 <b>{{ draftLayout.global.marginVertical }}mm</b></span><input v-model.number="draftLayout.global.marginVertical" type="range" min="3" max="12" step="0.25"></label>
            <label><span>左右页边距 <b>{{ draftLayout.global.marginHorizontal }}mm</b></span><input v-model.number="draftLayout.global.marginHorizontal" type="range" min="3" max="12" step="0.25"></label>
            <label><span>模块间距 <b>{{ draftLayout.global.moduleMargin }}</b></span><input v-model.number="draftLayout.global.moduleMargin" type="range" min="0.25" max="2" step="0.25"></label>
            <label><span>行间距 <b>{{ draftLayout.global.lineHeight }}</b></span><input v-model.number="draftLayout.global.lineHeight" type="range" min="1.1" max="2.2" step="0.1"></label>
          </fieldset>

          <fieldset>
            <legend>字体大小</legend>
            <label v-for="([role, label]) in fontSizeEntries" :key="role">
              <span>{{ label }} <b>{{ draftLayout.typography.fontSizes[role] }}pt</b></span>
              <input v-model.number="draftLayout.typography.fontSizes[role]" type="range" :min="FONT_SIZE_LIMITS[role][0]" :max="FONT_SIZE_LIMITS[role][1]" step="0.5">
            </label>
          </fieldset>

          <fieldset>
            <legend>模块样式</legend>
            <label class="select-control"><span>基本信息</span><select v-model="draftLayout.basics.preset"><option value="left-aligned">左对齐</option><option value="centered">居中</option></select></label>
            <label class="select-control"><span>模块标题</span><select v-model="draftLayout.global.titleStyle"><option value="plain">简洁</option><option value="underline">下划线</option></select></label>
            <label class="select-control"><span>教育经历</span><select v-model="draftLayout.education.preset"><option value="compact">紧凑</option><option value="classic">经典</option><option value="three-column">三列</option></select></label>
            <label class="select-control"><span>工作经历</span><select v-model="draftLayout.work_experience.preset"><option value="compact">紧凑</option><option value="classic">经典</option></select></label>
            <label class="select-control"><span>项目经历</span><select v-model="draftLayout.project_experience.preset"><option value="compact">紧凑</option><option value="classic">经典</option></select></label>
          </fieldset>

          <fieldset>
            <legend>模块顺序</legend>
            <div v-for="(section, index) in draftLayout.global.sectionOrder" :key="section" class="section-order-row">
              <span>{{ sectionLabels[section] || section }}</span>
              <button type="button" :disabled="index === 0" @click="moveDraftSection(index, -1)">↑</button>
              <button type="button" :disabled="index === draftLayout.global.sectionOrder.length - 1" @click="moveDraftSection(index, 1)">↓</button>
            </div>
          </fieldset>
        </aside>

        <main class="editor-preview-area">
          <div class="editor-sheet" :style="previewStyle(draftLayout)">
            <div class="template-sheet-preview editor-sheet-content" :class="[`basics-${draftLayout.basics.preset}`, `title-${draftLayout.global.titleStyle}`]">
              <header><strong>示例姓名</strong><span>出生年月：2000.01　|　138****8888　|　example@email.com</span></header>
              <section><h5>教育经历</h5><p><b>示例大学</b><span>硕士 · 电子信息 · 3.8/5.0 (前10%)</span><i>2022.09—2025.06</i></p></section>
              <section><h5>专业技能</h5><p>1. 编程与工程工具：Python、Vue、FastAPI、MySQL</p><p>2. 熟悉服务端开发与文档导出流程</p></section>
              <section><h5>工作经历</h5><p><b>示例科技有限公司 · 开发工程师</b><i>2024.01—至今</i></p><p>• 项目简介：负责核心服务和自动化工具开发</p><p>• 项目职责：</p><p class="numbered">(1) 优化接口性能并完善测试。</p><p class="numbered">(2) 提升团队交付效率。</p></section>
              <section><h5>项目经历</h5><p><b>智能简历助手</b><i>2023.06—2024.06</i></p><p>• 项目简介：实现结构化编辑与三端导出</p><p>• 项目职责：</p><p class="numbered">(1) 设计共享排版协议。</p></section>
            </div>
          </div>
        </main>
      </div>

      <footer v-if="view === 'editor'" class="template-editor-footer">
        <button type="button" class="secondary" @click="view = 'list'">取消</button>
        <button type="button" class="primary" @click="saveDraft">保存模板</button>
      </footer>
    </section>

    <div v-if="nameDialog" class="nested-dialog-overlay" @click.self="nameDialog = null">
      <div class="name-dialog" role="dialog" aria-modal="true">
        <h4>{{ nameDialog.mode === 'copy' ? '复制模板' : '重命名模板' }}</h4>
        <label><span>新模板名称</span><input v-model="nameDialog.value" maxlength="20" @keydown.enter="confirmNameDialog"></label>
        <small v-if="nameDialog.error">{{ nameDialog.error }}</small>
        <div><button type="button" @click="nameDialog = null">取消</button><button class="primary" type="button" @click="confirmNameDialog">确认</button></div>
      </div>
    </div>

    <div v-if="deleteTarget" class="nested-dialog-overlay" @click.self="deleteTarget = null">
      <div class="name-dialog" role="alertdialog" aria-modal="true">
        <h4>删除模板</h4>
        <p>确定删除“{{ deleteTarget.name }}”吗？</p>
        <div><button type="button" @click="deleteTarget = null">取消</button><button class="danger-confirm" type="button" @click="confirmDelete">删除</button></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.template-manager-overlay { position: fixed; inset: 0; z-index: 1800; display: grid; place-items: center; padding: 24px; background: rgba(7, 8, 11, .74); }
.template-manager { position: relative; display: flex; flex-direction: column; width: min(980px, 94vw); max-height: 86vh; overflow: hidden; color: #f2f3f7; background: #202229; border: 1px solid #3e424d; border-radius: 14px; box-shadow: 0 24px 70px rgba(0, 0, 0, .46); }
.template-manager-header { display: flex; align-items: center; justify-content: space-between; min-height: 56px; padding: 0 18px; border-bottom: 1px solid #363942; }
.template-manager-heading { display: flex; align-items: center; gap: 10px; }
.template-manager-header h3 { margin: 0; font-size: 18px; }
.close-button, .back-button { display: grid; place-items: center; width: 36px; height: 36px; padding: 0; color: #c7cad3; background: #2d3037; border: 1px solid #41454f; border-radius: 9px; cursor: pointer; font-size: 23px; }
.back-button { width: 32px; height: 32px; font-size: 18px; }
.template-grid { display: flex; gap: 14px; padding: 18px 18px 20px; overflow-x: auto; overflow-y: hidden; scrollbar-gutter: stable; }
.template-card { position: relative; flex: 0 0 218px; padding: 10px; background: #2b2e36; border: 1px solid #3e424d; border-radius: 11px; }
.template-card h4 { margin: 0 0 9px; overflow: hidden; font-size: 14px; text-align: center; text-overflow: ellipsis; white-space: nowrap; }
.template-sheet-frame, .create-sheet { overflow: hidden; width: 100%; aspect-ratio: 210 / 297; background: #fff; border: 1px solid #4b505c; border-radius: 7px; }
.template-sheet-preview { box-sizing: border-box; width: 100%; height: 100%; padding: var(--preview-vertical-padding) var(--preview-horizontal-padding); color: #111; background: #fff; font-family: Arial, 'Microsoft YaHei', sans-serif; font-size: var(--preview-font-size); line-height: var(--preview-line-height); }
.template-sheet-preview header { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; margin-bottom: var(--preview-module-gap); }
.template-sheet-preview.basics-centered header { align-items: center; text-align: center; }
.template-sheet-preview header strong { font-size: var(--preview-name-size); }
.template-sheet-preview section { margin-top: var(--preview-module-gap); }
.template-sheet-preview h5 { margin: 0 0 2px; padding-bottom: 1px; font-size: var(--preview-title-size); }
.template-sheet-preview.title-underline h5 { border-bottom: 1px solid #555; }
.template-sheet-preview p { display: flex; gap: 5px; margin: 1px 0; }
.template-sheet-preview p span { flex: 1; text-align: center; }
.template-sheet-preview p i { margin-left: auto; font-style: normal; white-space: nowrap; }
.apply-button { display: block; width: 120px; min-height: 30px; margin: 9px auto 0; padding: 0 12px; color: #fff; background: #3f67aa; border: 0; border-radius: 6px; cursor: pointer; font-size: 13px; }
.apply-button.current { color: #9ea3af; background: #3a3d45; cursor: default; }
.template-action-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; margin-top: 8px; }
.template-action-row button { min-width: 0; height: 26px; padding: 0 4px; color: #cfd4df; background: #353941; border: 1px solid #4b505c; border-radius: 5px; cursor: pointer; font-size: 11px; }
.template-action-row button:hover { color: #fff; background: #414650; }
.template-action-row .danger { color: #f0aaaa; }
.default-action-row { display: flex; justify-content: center; }
.default-action-row button { width: 56px; }
.create-sheet { display: grid; place-items: center; color: #8990a1; border: 1px dashed #6a7080; cursor: pointer; }
.create-sheet span { font-size: 56px; font-weight: 200; }
.template-editor { display: grid; grid-template-columns: 330px minmax(0, 1fr); min-height: 0; overflow: hidden; }
.template-controls { padding: 18px; overflow-y: auto; border-right: 1px solid #363942; }
.template-controls fieldset { display: grid; gap: 12px; margin: 0 0 18px; padding: 14px; border: 1px solid #41454f; border-radius: 10px; }
.template-controls legend { padding: 0 6px; color: #e6e8ee; font-size: 14px; font-weight: 700; }
.template-controls label { display: grid; gap: 6px; color: #bfc3ce; font-size: 12px; }
.template-controls label > span { display: flex; justify-content: space-between; gap: 10px; }
.template-controls input, .template-controls select, .name-dialog input { box-sizing: border-box; width: 100%; color: #f2f3f7; background: #292c33; border: 1px solid #474b56; border-radius: 7px; }
.template-controls input[type='text'], .template-controls input:not([type]), .template-controls select, .name-dialog input { min-height: 36px; padding: 0 10px; }
.template-controls input[type='range'] { accent-color: #7399e8; }
.name-control { margin-bottom: 18px; }
.name-control small, .name-dialog small { color: #ff9999; }
.select-control { grid-template-columns: 1fr 132px; align-items: center; }
.select-control > span { display: block !important; }
.section-order-row { display: grid; grid-template-columns: 1fr 28px 28px; gap: 5px; align-items: center; font-size: 12px; }
.section-order-row button { width: 28px; height: 26px; color: #d7d9e0; background: #343840; border: 1px solid #4b505c; border-radius: 5px; cursor: pointer; }
.editor-preview-area { display: grid; place-items: start center; min-width: 0; padding: 24px; overflow: auto; background: #17191e; }
.editor-sheet { width: min(560px, 100%); aspect-ratio: 210 / 297; background: #fff; box-shadow: 0 10px 34px rgba(0,0,0,.35); }
.editor-sheet-content { font-size: calc(var(--preview-font-size) * 1.65); }
.editor-sheet-content header strong { font-size: calc(var(--preview-name-size) * 1.65); }
.editor-sheet-content h5 { font-size: calc(var(--preview-title-size) * 1.65); }
.editor-sheet-content .numbered { padding-left: 16px; }
.template-editor-footer { display: flex; justify-content: flex-end; gap: 10px; padding: 13px 20px; border-top: 1px solid #363942; }
.template-editor-footer button, .name-dialog button { min-width: 64px; min-height: 32px; padding: 0 14px; border: 0; border-radius: 6px; cursor: pointer; }
.template-editor-footer .secondary, .name-dialog button { color: #e3e5eb; background: #383c45; }
.template-editor-footer .primary, .name-dialog .primary { color: #fff; background: #416db7; }
.nested-dialog-overlay { position: fixed; inset: 0; z-index: 1900; display: grid; place-items: center; background: rgba(7,8,11,.6); }
.name-dialog { width: min(330px, calc(100vw - 40px)); padding: 18px; color: #f1f2f5; background: #282b32; border: 1px solid #484c57; border-radius: 11px; box-shadow: 0 18px 50px rgba(0,0,0,.45); }
.name-dialog h4 { margin: 0 0 16px; }
.name-dialog p { color: #c9ccd4; }
.name-dialog label { display: grid; gap: 7px; color: #c9ccd4; font-size: 13px; }
.name-dialog > div { display: flex; justify-content: flex-end; gap: 9px; margin-top: 18px; }
.name-dialog .danger-confirm { color: #fff; background: #b94a4a; }

@media (max-width: 900px) {
  .template-editor { grid-template-columns: 280px minmax(0, 1fr); }
}
@media (max-width: 650px) {
  .template-manager-overlay { padding: 8px; }
  .template-manager { width: 100%; max-height: 96vh; }
  .template-grid { padding: 14px; }
  .template-card { flex-basis: min(230px, 78vw); }
  .template-editor { display: block; overflow-y: auto; }
  .template-controls { border-right: 0; border-bottom: 1px solid #363942; }
  .editor-preview-area { min-height: 420px; }
}
</style>
