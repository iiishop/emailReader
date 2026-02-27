/**
 * stores/prompts.js
 * 从后端 /api/prompts 拉取 prompts.yaml 内容并缓存。
 * 提供 getPrompt(section, key, vars) 工具函数，与后端 prompts.py 行为一致。
 *
 * 使用示例：
 *   const promptsStore = usePromptsStore()
 *   await promptsStore.ensure()
 *   const text = promptsStore.get('chat', 'rules')
 *   const text = promptsStore.get('chat', 'context_header', { count: 5, threshold_pct: 60 })
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

export const usePromptsStore = defineStore('prompts', () => {
  const data    = ref(null)   // 完整的 prompts 对象
  const loading = ref(false)
  const error   = ref('')

  /** 拉取（若已缓存则直接返回） */
  async function ensure() {
    if (data.value) return
    if (loading.value) {
      // 等待已在进行中的请求
      await new Promise(resolve => {
        const stop = setInterval(() => {
          if (!loading.value) { clearInterval(stop); resolve() }
        }, 50)
      })
      return
    }
    loading.value = true
    error.value   = ''
    try {
      const res = await fetch('/api/prompts')
      const json = await res.json()
      if (json.success) {
        data.value = json.prompts
      } else {
        error.value = json.error ?? '加载 prompts 失败'
      }
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取指定 section.key 的文本，并用 vars 进行模板插值。
   * 缺少的变量保持原样 {varName}。
   * 若 prompts 尚未加载，返回空字符串（调用方应先 await ensure()）。
   */
  function get(section, key, vars = {}) {
    const text = data.value?.[section]?.[key]
    if (text == null) return ''
    return _interpolate(String(text).trimEnd(), vars)
  }

  /** 简单模板插值：{varName} → vars[varName]，缺失时保留原样 */
  function _interpolate(template, vars) {
    return template.replace(/\{(\w+)\}/g, (match, name) =>
      Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match
    )
  }

  return { data, loading, error, ensure, get }
})
