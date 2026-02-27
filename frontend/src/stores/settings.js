import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useSettingsStore = defineStore('settings', () => {
  const apiBaseUrl    = ref('https://api.openai.com/v1')
  const apiKey        = ref('')
  const selectedModel = ref('')
  const systemPrompt  = ref(
    '你是一个邮件助手，请用简洁、专业的语气帮助用户处理和理解邮件内容。'
  )
  const aiDays = ref(7)
  const relevanceThreshold = ref(60)
  const refreshInterval = ref(5)

  const isConfigured = computed(
    () => !!apiBaseUrl.value.trim() && !!apiKey.value.trim() && !!selectedModel.value.trim()
  )

  /** 从后端返回的 settings 对象写入 store（由 App 初始化时调用） */
  function loadFrom(saved) {
    if (!saved || typeof saved !== 'object') return
    if (saved.apiBaseUrl != null)    apiBaseUrl.value    = String(saved.apiBaseUrl)
    if (saved.apiKey != null)        apiKey.value        = String(saved.apiKey)
    if (saved.selectedModel != null) selectedModel.value = String(saved.selectedModel)
    if (saved.systemPrompt != null)  systemPrompt.value  = String(saved.systemPrompt)
    if (saved.aiDays !== undefined) aiDays.value = Number(saved.aiDays) || 0
    if (saved.relevanceThreshold !== undefined) relevanceThreshold.value = Number(saved.relevanceThreshold) || 0
    if (saved.refreshInterval !== undefined) refreshInterval.value = Number(saved.refreshInterval) ?? 5
  }

  /** 保存到后端（替代 localStorage） */
  async function save() {
    const payload = {
      apiBaseUrl:    apiBaseUrl.value,
      apiKey:        apiKey.value,
      selectedModel: selectedModel.value,
      systemPrompt:  systemPrompt.value,
      aiDays:        aiDays.value,
      relevanceThreshold: relevanceThreshold.value,
      refreshInterval:    refreshInterval.value,
    }
    const res = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings: payload }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || `保存失败 ${res.status}`)
    }
  }

  return { apiBaseUrl, apiKey, selectedModel, systemPrompt, aiDays, relevanceThreshold, refreshInterval, isConfigured, save, loadFrom }
})
