const FIELD_LABELS = Object.freeze({
  basics: '基础信息',
  education: '教育经历',
  research_interests: '研究方向',
  honors: '主要荣誉',
  publications: '论文',
  work_experience: '工作经历',
  project_experience: '项目经历',
  custom_sections: '自定义模块',
  others: '专业技能与补充信息',
  self_evaluation: '自我评价',
  name: '姓名',
  gender: '性别',
  age: '年龄',
  birth_date: '出生年月',
  phone: '手机',
  email: '邮箱',
  location: '所在地',
  target_position: '目标岗位',
  photo: '头像',
  additional_fields: '补充信息',
  value: '内容',
  school: '学校',
  school_name: '学校名称',
  degree: '学历',
  major: '专业',
  date_range: '时间',
  start_date: '开始时间',
  end_date: '结束时间',
  graduation_date: '毕业时间',
  gpa: 'GPA',
  gpa_scale: 'GPA 满分',
  ranking: '排名',
  company_name: '公司',
  company: '公司',
  job_title: '职位',
  position: '职位',
  job_type: '工作类型',
  project_name: '项目名称',
  role: '角色',
  details: '详细内容',
  skills: '技能',
  certificates: '证书',
  languages: '语言',
  school_tags: '学校标签',
  theses: '论文',
  title: '标题',
  content: '内容',
  content_blocks: '内容结构',
  semantic_role: '内容用途',
  label: '小标题',
  label_bold: '小标题加粗',
  text: '正文',
  items: '条目',
  type: '内容类型',
  marginVertical: '上下页边距',
  marginHorizontal: '左右页边距',
  moduleMargin: '模块间距',
  lineHeight: '行间距',
  fontSize: '正文字号',
  titleStyle: '模块标题样式',
  sectionOrder: '模块顺序',
  hiddenSections: '隐藏模块',
  preset: '排版预设',
  separator: '分隔方式',
})

const INTERNAL_VALUE_LABELS = Object.freeze({
  paragraph: '段落',
  paragraphs: '分段',
  bullet: '分点',
  bullets: '分点',
  bullet_list: '分点',
  numbered: '编号',
  numbered_list: '编号',
  tech_stack: '技术栈',
  introduction: '项目简介',
  responsibilities: '项目职责',
  generic: '普通内容',
  standalone: '独立栏目',
})

const INTERNAL_FIELD_PATTERN = /^[a-z][a-z0-9_.\[\]-]*$/i

function mapFieldToken(token) {
  const clean = String(token || '').trim()
  if (!clean) return ''
  if (FIELD_LABELS[clean]) return FIELD_LABELS[clean]
  if (INTERNAL_VALUE_LABELS[clean]) return INTERNAL_VALUE_LABELS[clean]
  const pathParts = clean.replace(/\[\d+\]/g, '').split('.').filter(Boolean)
  const lastPart = pathParts[pathParts.length - 1]
  if (lastPart && FIELD_LABELS[lastPart]) return FIELD_LABELS[lastPart]
  return INTERNAL_FIELD_PATTERN.test(clean) ? '简历字段' : clean
}

export function userFacingFieldLabel(value) {
  const text = String(value || '').trim()
  if (!text) return '简历字段'
  if (FIELD_LABELS[text] || INTERNAL_FIELD_PATTERN.test(text)) return mapFieldToken(text)
  return text
    .split(/(\s*[·›]\s*)/)
    .map(part => /^[\s·›]+$/.test(part) ? part : mapFieldToken(part))
    .join('')
}

const INTERNAL_REFERENCES = Object.keys(FIELD_LABELS)
  .filter(key => /^[a-z][a-z0-9_]*$/i.test(key) && key.includes('_'))
  .sort((left, right) => right.length - left.length)

const INTERNAL_VALUE_REFERENCES = Object.keys(INTERNAL_VALUE_LABELS)
  .filter(key => /^[a-z][a-z0-9_]*$/i.test(key))
  .sort((left, right) => right.length - left.length)

export function localizeInternalFieldReferences(value) {
  let text = String(value || '')
  text = text
    .replace(/\[CONFIRM_REPLY:[^\]]+\]/g, '确认操作')
    .replace(/\b(?:request_resume_edit|render_resume_pdf_images)\b/g, '系统能力')
    .replace(/\b(?:layout_config|resume_data|jd_data|session_id|confirm_id|request_id)\b/g, '内部信息')
    .replace(/(?:Traceback[\s\S]*|[A-Za-z_]+Error:\s*[^\n]+)/g, '系统处理异常')
  for (const section of [
    'project_experience', 'work_experience', 'research_interests',
    'custom_sections', 'self_evaluation', 'education', 'honors', 'others', 'basics'
  ]) {
    text = text.replace(new RegExp(`(^|[^A-Za-z0-9_])${section}\\.`, 'g'), (match, prefix) => (
      `${prefix}${FIELD_LABELS[section]}中的`
    ))
    text = text.replace(new RegExp(`([（(\\[]\\s*)${section}(?=\\s*[）)\\]])`, 'g'), (match, prefix) => (
      `${prefix}${FIELD_LABELS[section]}`
    ))
  }
  for (const field of INTERNAL_REFERENCES) {
    const escaped = field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    text = text.replace(new RegExp(`(^|[^A-Za-z0-9_])${escaped}(?=$|[^A-Za-z0-9_])`, 'g'), (match, prefix) => (
      `${prefix}${FIELD_LABELS[field]}`
    ))
  }
  for (const field of INTERNAL_VALUE_REFERENCES) {
    const escaped = field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    text = text.replace(new RegExp(`(^|[^A-Za-z0-9_])${escaped}(?=$|[^A-Za-z0-9_])`, 'g'), (match, prefix) => (
      `${prefix}${INTERNAL_VALUE_LABELS[field]}`
    ))
  }
  return text
}

export { FIELD_LABELS }
