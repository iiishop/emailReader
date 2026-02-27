import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { useMailStore }     from './mail.js'
import { useSettingsStore } from './settings.js'

export const useRefreshStore = defineStore('refresh', () => {
  const lastRefreshed = ref(null)   // Date | null
  const isRefreshing  = ref(false)

  let _timerId = null

  /** 格式化为 HH:MM:SS */
  function formatTime(d) {
    if (!(d instanceof Date)) return ''
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    return `${hh}:${mm}:${ss}`
  }

  /** 仅更新上次刷新时间（不触发网络请求），供"打开文件夹"场景使用 */
  function markRefreshed() {
    lastRefreshed.value = new Date()
  }

  /**
   * 执行一次增量刷新：新邮件会滑入列表顶部，不重置整个列表。
   */
  async function doRefresh() {
    const mailStore = useMailStore()
    if (!mailStore.selectedFolder) return
    if (isRefreshing.value) return

    isRefreshing.value = true
    try {
      await mailStore.refreshEmails()
      lastRefreshed.value = new Date()
    } finally {
      isRefreshing.value = false
    }
  }

  /** 停止自动刷新定时器 */
  function stopAutoRefresh() {
    if (_timerId !== null) {
      clearInterval(_timerId)
      _timerId = null
    }
  }

  /** 根据 settings.refreshInterval 启动（或停止）定时器 */
  function startAutoRefresh() {
    stopAutoRefresh()
    const settings = useSettingsStore()
    const mins = settings.refreshInterval
    if (mins <= 0) return
    _timerId = setInterval(() => doRefresh(true), mins * 60 * 1000)
  }

  /** 在 App.vue 挂载时调用一次，完成初始化并监听间隔变化 */
  function init() {
    const settings = useSettingsStore()
    startAutoRefresh()
    watch(
      () => settings.refreshInterval,
      () => startAutoRefresh(),
    )
  }

  return {
    lastRefreshed,
    isRefreshing,
    formatTime,
    markRefreshed,
    doRefresh,
    startAutoRefresh,
    stopAutoRefresh,
    init,
  }
})
