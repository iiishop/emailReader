/**
 * stores/dashboardData.js
 * Dashboard 工作台数据：事件提取、Todo 持久化、今日简报、话题、联系人。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useSettingsStore } from './settings.js'

function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2)
}

export const useDashboardDataStore = defineStore('dashboardData', () => {
  const settings = useSettingsStore()

  // ── Dashboard 数据（来自后端 dashboard.json）────────────────────────────────
  const events          = ref([])
  const topics          = ref([])
  const people          = ref([])
  const brief           = ref('')                // 全局简报
  const accountBriefs   = ref({})               // 各账号简报 { email: text }
  const accountStats    = ref({})               // 各账号统计 { email: {email_count, event_count} }
  const accEvents       = ref({})               // 各账号事件 { email: [...] }
  const stats           = ref({})
  const extractedAt     = ref(null)
  const isExtracting    = ref(false)
  const extractError    = ref('')
  const extractProgress = ref(null)  // { current, total, message } 或 null

  // ── 账号 Tab 过滤 ─────────────────────────────────────────────────────────
  // 'all' 或某个 email 字符串
  const selectedAccount = ref('all')

  // ── 简报历史 ───────────────────────────────────────────────────────────────
  const briefs       = ref([])   // 列表（含 preview）
  const briefsLoaded = ref(false)

  // ── Todo 列表 ──────────────────────────────────────────────────────────────
  const todos = ref([])
  const todosLoaded = ref(false)

  // ── 过滤后的数据（随 selectedAccount 变化） ─────────────────────────────────
  /** 当前视图显示的事件列表 */
  const filteredEvents = computed(() => {
    if (selectedAccount.value === 'all') return events.value
    return accEvents.value[selectedAccount.value] ?? []
  })

  /** 当前视图的今日简报文本 */
  const currentBrief = computed(() => {
    if (selectedAccount.value === 'all') return brief.value
    return accountBriefs.value[selectedAccount.value] ?? ''
  })

  /** 当前视图的统计信息 */
  const currentStats = computed(() => {
    if (selectedAccount.value === 'all') return stats.value
    const as = accountStats.value[selectedAccount.value]
    return as ? {
      total_emails:   as.email_count,
      total_events:   as.event_count,
      accounts_count: 1,
      ai_days:        stats.value.ai_days,
    } : stats.value
  })

  /** 当前视图的话题（从 filteredEvents 重新聚合） */
  const filteredTopics = computed(() => {
    if (selectedAccount.value === 'all') return topics.value
    // 从过滤后的事件重新聚合 tags
    const map = {}
    for (const ev of filteredEvents.value) {
      for (const tag of (ev.tags ?? [])) {
        if (!map[tag]) map[tag] = { name: tag, count: 0, events: [] }
        map[tag].count++
        if (map[tag].events.length < 3) map[tag].events.push(ev.title ?? '')
      }
    }
    return Object.values(map).sort((a, b) => b.count - a.count).slice(0, 20)
  })

  /** 当前视图的联系人（从 filteredEvents 的 source_from 聚合） */
  const filteredPeople = computed(() => {
    if (selectedAccount.value === 'all') return people.value
    // 只保留与当前账号相关的人
    const emailSet = new Set(filteredEvents.value.map(e => e.source_from).filter(Boolean))
    return people.value.filter(p => emailSet.has(p.from) || p.account === selectedAccount.value)
  })

  /** 当前账号的历史简报列表（含过滤） */
  const filteredBriefs = computed(() => {
    if (selectedAccount.value === 'all') return briefs.value
    return briefs.value.map(b => {
      const accBrief = b.account_briefs?.[selectedAccount.value]
      if (!accBrief) return null
      return {
        ...b,
        brief:   accBrief,
        preview: accBrief.slice(0, 120),
      }
    }).filter(Boolean)
  })

  // ── 计算属性 ───────────────────────────────────────────────────────────────
  const todosByStatus = computed(() => ({
    todo:  todos.value.filter(t => t.status === 'todo'),
    doing: todos.value.filter(t => t.status === 'doing'),
    done:  todos.value.filter(t => t.status === 'done'),
  }))

  /** 未来 7 天内的倒计时事件（deadline / milestone，有明确日期） */
  const countdowns = computed(() => {
    const now   = Date.now()
    return filteredEvents.value
      .filter(e => (e.type === 'deadline' || e.type === 'milestone') && e.datetime)
      .map(e => {
        const ts = new Date(e.datetime).getTime()
        return { ...e, _ts: ts, _diffMs: ts - now }
      })
      .filter(e => e._ts > now - 86400000)
      .sort((a, b) => a._ts - b._ts)
      .slice(0, 10)
  })

  /** 今天的事件 */
  const todayEvents = computed(() => {
    const today = new Date().toISOString().slice(0, 10)
    return filteredEvents.value.filter(e => e.datetime?.startsWith(today))
  })

  /** 本周的事件（用于 Weekly Schedule） */
  const weekEvents = computed(() => {
    const now   = new Date()
    const day   = now.getDay() || 7
    const mon   = new Date(now); mon.setDate(now.getDate() - day + 1); mon.setHours(0,0,0,0)
    const sun   = new Date(mon); sun.setDate(mon.getDate() + 6); sun.setHours(23,59,59,999)
    return filteredEvents.value.filter(e => {
      if (!e.datetime) return false
      const t = new Date(e.datetime).getTime()
      return t >= mon.getTime() && t <= sun.getTime()
    })
  })

  // ── 加载简报历史列表 ────────────────────────────────────────────────────────
  async function loadBriefs() {
    try {
      const res  = await fetch('/api/dashboard/briefs')
      const data = await res.json()
      briefs.value  = data.briefs ?? []
      briefsLoaded.value = true
    } catch { /* ignore */ }
  }

  /** 获取某条简报完整内容 */
  async function fetchBriefDetail(id) {
    try {
      const res  = await fetch(`/api/dashboard/briefs/${id}`)
      const data = await res.json()
      return data.success ? data.brief : null
    } catch { return null }
  }

  // ── 加载 Dashboard 数据 ────────────────────────────────────────────────────
  async function loadData() {
    try {
      // 禁止缓存，否则 PyWebView/浏览器可能一直返回旧的 is_extracting: true
      const res  = await fetch('/api/dashboard/data?t=' + Date.now(), { cache: 'no-store' })
      const data = await res.json()
      events.value         = data.events         ?? []
      topics.value         = data.topics         ?? []
      people.value         = data.people         ?? []
      brief.value          = data.brief          ?? ''
      accountBriefs.value  = data.account_briefs ?? {}
      accountStats.value   = data.account_stats  ?? {}
      accEvents.value      = data.acc_events     ?? {}
      stats.value          = data.stats          ?? {}
      extractedAt.value    = data.extracted_at     ?? null
      isExtracting.value   = data.is_extracting    ?? false
      extractError.value   = data.extract_error    ?? ''
      extractProgress.value = data.extract_progress ?? null
      // 调试：提取状态变化时打 log，便于确认是否收到「已完成」
      if (data.is_extracting || data.extract_progress) {
        console.log('[Dashboard] loadData 提取中:', data.is_extracting, data.extract_progress)
      } else if (data.extracted_at || (data.events && data.events.length)) {
        console.log('[Dashboard] loadData 已完成:', data.events?.length, 'events', !!data.brief)
      }
    } catch (e) {
      isExtracting.value = false
      extractError.value = e.message
    }
  }

  // ── 触发 AI 提取 ───────────────────────────────────────────────────────────
  async function triggerExtract() {
    if (!settings.isConfigured) return
    isExtracting.value = true
    extractError.value = ''
    _pollCount = 0
    try {
      await fetch('/api/dashboard/extract', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: settings.apiBaseUrl,
          api_key:  settings.apiKey,
          model:    settings.selectedModel,
          ai_days:  settings.aiDays,
          max_emails_per_folder: 500,
          max_chars_per_email:   1200,
        }),
      })
      // 立即拉一次，让界面尽快显示「提取中」并拿到进度
      await loadData()
      _pollExtract()
    } catch (e) {
      isExtracting.value = false
      extractError.value = e.message
    }
  }

  let _pollTimer = null
  let _pollCount = 0
  function _pollExtract() {
    clearTimeout(_pollTimer)
    // 前几次快轮询，便于进度条更新
    const delay = _pollCount < 5 ? 1500 : 5000
    _pollTimer = setTimeout(async () => {
      _pollCount++
      await loadData()
      if (isExtracting.value) {
        _pollExtract()  // 仍在提取中，继续轮询
      } else {
        // 提取完成，再拉一次确保拿到最终数据
        await loadData()
        _pollCount = 0
      }
    }, delay)
  }

  // ── 已加入 Todo 的事件 source_key 集合（纯前端状态，用于标记） ──────────────
  const addedEventKeys = ref(new Set())

  // ── Todo CRUD ──────────────────────────────────────────────────────────────
  async function loadTodos() {
    try {
      const res  = await fetch('/api/dashboard/todos')
      const data = await res.json()
      if (data.success) {
        todos.value  = data.todos
        todosLoaded.value = true
        // 从已有 todos 恢复已加入标记
        const keys = new Set()
        for (const t of data.todos) {
          if (t.source_key) keys.add(t.source_key)
        }
        addedEventKeys.value = keys
      }
    } catch { /* ignore */ }
  }

  async function addTodo(fields = {}) {
    const item = {
      id:          uid(),
      title:       fields.title       ?? '新任务',
      status:      fields.status      ?? 'todo',
      priority:    fields.priority    ?? 'medium',
      due:         fields.due         ?? null,
      tags:        fields.tags        ?? [],
      source_key:  fields.source_key  ?? null,
      source_from: fields.source_from ?? null,
      note:        fields.note        ?? '',
      created_at:  '',
      updated_at:  '',
    }
    try {
      const res  = await fetch('/api/dashboard/todos', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(item),
      })
      const data = await res.json()
      if (data.success) todos.value.push(data.todo)
      return data.todo
    } catch { return null }
  }

  async function updateTodo(id, fields) {
    const idx = todos.value.findIndex(t => t.id === id)
    if (idx === -1) return
    const updated = { ...todos.value[idx], ...fields }
    try {
      const res  = await fetch(`/api/dashboard/todos/${id}`, {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(updated),
      })
      const data = await res.json()
      if (data.success) todos.value[idx] = data.todo
    } catch { /* ignore */ }
  }

  async function deleteTodo(id) {
    todos.value = todos.value.filter(t => t.id !== id)
    try {
      await fetch(`/api/dashboard/todos/${id}`, { method: 'DELETE' })
    } catch { /* ignore */ }
  }

  /** 从事件快速创建 Todo（并标记该事件已加入） */
  async function addTodoFromEvent(event, extraFields = {}) {
    const todo = await addTodo({
      title:       event.title,
      priority:    event.priority ?? 'medium',
      due:         event.datetime?.slice(0, 10) ?? null,
      tags:        event.tags ?? [],
      source_key:  event.source_key ?? null,
      source_from: event.source_from ?? null,
      note:        event.description ?? '',
      ...extraFields,
    })
    if (todo && event.source_key) {
      addedEventKeys.value = new Set([...addedEventKeys.value, event.source_key])
    }
    return todo
  }

  /** 检查某个事件是否已加入 Todo */
  function isEventAdded(event) {
    if (!event?.source_key) return false
    return addedEventKeys.value.has(event.source_key)
  }

  /** 拖拽后批量保存顺序 */
  async function saveTodosOrder() {
    try {
      await fetch('/api/dashboard/todos/reorder', {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ todos: todos.value }),
      })
    } catch { /* ignore */ }
  }

  return {
    // raw data
    events, topics, people, brief, stats,
    accountBriefs, accountStats, accEvents,
    extractedAt, isExtracting, extractError, extractProgress,
    // account filter
    selectedAccount,
    // filtered computed
    filteredEvents, currentBrief, currentStats, filteredTopics, filteredPeople, filteredBriefs,
    // original computed (still used internally)
    countdowns, todayEvents, weekEvents, todosByStatus,
    // todos
    todos, todosLoaded, addedEventKeys,
    // briefs history
    briefs, briefsLoaded,
    // actions
    loadData, triggerExtract,
    loadTodos, addTodo, updateTodo, deleteTodo, addTodoFromEvent, isEventAdded, saveTodosOrder,
    loadBriefs, fetchBriefDetail,
  }
})
