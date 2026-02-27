import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const STORAGE_KEY = 'emailreader-ai-settings'

export const useSettingsStore = defineStore('settings', () => {
  const apiBaseUrl    = ref('https://api.openai.com/v1')
  const apiKey        = ref('')
  const selectedModel = ref('')
  const systemPrompt  = ref(
    '你是一个邮件助手，请用简洁、专业的语气帮助用户处理和理解邮件内容。'
  )
  /**
   * AI 回看天数：AI 只处理最近 N 天内的邮件
   * 0 = 不限（处理全部邮件，谨慎使用）
   */
  const aiDays = ref(7)

  /**
   * RAG 相关性阈值（0~100，整数百分比）
   * 筛选时，AI 评分 >= 此值的邮件才会被纳入上下文
   */
  const relevanceThreshold = ref(60)

  /**
   * 自动刷新间隔（分钟）
   * 0 = 关闭自动刷新
   */
  const refreshInterval = ref(5)

  /** 是否已完整配置（可发起 AI 请求） */
  const isConfigured = computed(
    () => !!apiBaseUrl.value.trim() && !!apiKey.value.trim() && !!selectedModel.value.trim()
  )

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const saved = JSON.parse(raw)
      if (saved.apiBaseUrl)    apiBaseUrl.value    = saved.apiBaseUrl
      if (saved.apiKey)        apiKey.value        = saved.apiKey
      if (saved.selectedModel) selectedModel.value = saved.selectedModel
      if (saved.systemPrompt)  systemPrompt.value  = saved.systemPrompt
                  if (saved.aiDays !== undefined) aiDays.value = saved.aiDays
                  if (saved.relevanceThreshold !== undefined) relevanceThreshold.value = saved.relevanceThreshold
                  if (saved.refreshInterval !== undefined) refreshInterval.value = saved.refreshInterval
    } catch { /* 忽略损坏的存储 */ }
  }

  function save() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      apiBaseUrl:    apiBaseUrl.value,
      apiKey:        apiKey.value,
      selectedModel: selectedModel.value,
      systemPrompt:  systemPrompt.value,
                  aiDays:           aiDays.value,
                  relevanceThreshold: relevanceThreshold.value,
                  refreshInterval:    refreshInterval.value,
    }))
  }

  // 初始化时立即读取
  load()

              return { apiBaseUrl, apiKey, selectedModel, systemPrompt, aiDays, relevanceThreshold, refreshInterval, isConfigured, save, load }
})
