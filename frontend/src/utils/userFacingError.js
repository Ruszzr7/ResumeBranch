const ERROR_MESSAGES = Object.freeze({
  RESUME_SAVE_FAILED: '简历保存失败，请稍后重试。',
  JD_LOAD_FAILED: '岗位信息加载失败，请稍后重试。',
  JD_SAVE_FAILED: '岗位信息保存失败，请稍后重试。',
  CONVERSATION_SAVE_FAILED: '对话保存失败，请稍后重试。',
  CONVERSATION_LOAD_FAILED: '对话加载失败，请稍后重试。',
  JD_PARSE_FAILED: '岗位描述识别失败，请稍后重试。',
  PDF_EXPORT_FAILED: 'PDF 导出失败，请稍后重试。',
  DOCX_EXPORT_FAILED: 'Word 导出失败，请稍后重试。',
  CHAT_FAILED: '本次请求未能安全完成，请稍后重试。',
  CONFIRM_FAILED: '确认操作处理失败，请重新加载后重试。'
})

const INTERNAL_ERROR_PATTERN = /(?:Traceback|Exception|sqlalchemy|pymysql|sqlite|\/app\/|\\backend\\|\.py:\d+|[A-Za-z_]+Error\b|\b(?:request_resume_edit|render_resume_pdf_images|layout_config|resume_data|session_id)\b)/i

export function userFacingApiError(payload, fallback = '操作失败，请稍后重试。') {
  if (payload && ERROR_MESSAGES[payload.code]) return ERROR_MESSAGES[payload.code]
  const candidate = typeof payload === 'string'
    ? payload
    : (payload?.message || payload?.detail || payload?.error || '')
  if (typeof candidate !== 'string' || !candidate.trim() || INTERNAL_ERROR_PATTERN.test(candidate)) {
    return fallback
  }
  return candidate.trim()
}
