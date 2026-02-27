import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useSettingsStore } from './settings.js'
import { usePromptsStore }  from './prompts.js'

export const useDashboardStore = defineStore('dashboard', () => {
  const settingsStore = useSettingsStore()
  const promptsStore  = usePromptsStore()

  // ─── 对话消息 ──────────────────────────────────────────────────────────────
  /**
   * messages 里除了 user/assistant，还有 role='status' 的进度消息
   * status 消息仅在流程进行中展示，完成后自动替换为 assistant 消息
   */
  const messages  = ref([])
  const thinking  = ref(false)
  const chatError = ref('')

  /** RAG 进度阶段：null | 'screening' | 'loading' | 'answering' */
  const ragPhase  = ref(null)
  /** 当前正在进行的步骤的人读文本 */
  const ragStatus = ref('')

  // ─── 邮件上下文 ────────────────────────────────────────────────────────────
  const contextAccountId = ref('')
  const contextFolderId  = ref('')
  /** 元数据列表（metadata_only=true 加载，速度快） */
  const contextEmails    = ref([])
  const contextLoading   = ref(false)
  const contextError     = ref('')
  const contextLoaded    = ref(false)

  /** 手动勾选的邮件 key 集合（null = 全选） */
  const selectedKeys     = ref(null)

  /**
   * 从 Reader 页面跳转过来时携带的预选邮件信息
   * { accountId, folderId, key }
   */
  const pendingJump = ref(null)

  const contextSummary = computed(() => {
    if (!contextLoaded.value) return null
    return {
      total:   contextEmails.value.length,
      unread:  contextEmails.value.filter(e => !e.is_read).length,
      aiDays:  settingsStore.aiDays,
    }
  })

  // ─── 加载元数据（快速，只取标题/发件人/日期）──────────────────────────────
  async function loadContext(accountId, folderId) {
    if (!accountId || !folderId) return
    contextLoading.value = true
    contextError.value   = ''
    contextLoaded.value  = false
    selectedKeys.value   = null

    try {
      const res = await fetch('/api/ai/prepare-emails', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          account_id:    accountId,
          folder_id:     folderId,
          ai_days:       settingsStore.aiDays,
          max_emails:    300,
          metadata_only: true,   // ← 只拉元数据，快速
        }),
      })
      const data = await res.json()
      if (data.success) {
        contextAccountId.value = accountId
        contextFolderId.value  = folderId
        contextEmails.value    = data.emails
        contextLoaded.value    = true
      } else {
        contextError.value = data.error ?? '加载失败'
      }
    } catch (e) {
      contextError.value = e.message
    } finally {
      contextLoading.value = false
    }
  }

  // ─── 辅助：生成消息唯一 ID ─────────────────────────────────────────────────
  function _uid() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2)
  }

  function _addMessage(role, content, extra = {}) {
    messages.value.push({ role, content, id: _uid(), ...extra })
  }

  function _removeLastStatus() {
    const idx = [...messages.value].reverse().findIndex(m => m.role === 'status')
    if (idx !== -1) messages.value.splice(messages.value.length - 1 - idx, 1)
  }

  // ─── 核心：发送消息（两阶段 RAG）──────────────────────────────────────────
  /**
   * @param {string} userText    用户输入的文字
   * @param {Set<string>|null}  keysOverride  指定要考虑的邮件 key 集合（null = 用 selectedKeys）
   */
  async function sendMessage(userText, keysOverride = null) {
    if (!userText.trim() || thinking.value) return
    chatError.value = ''

    await promptsStore.ensure()

    _addMessage('user', userText.trim())
    thinking.value = true
    ragPhase.value = null

    let emailContextText = ''

    try {
      const candidateEmails = _getCandidateEmails(keysOverride)

      if (candidateEmails.length > 0 && settingsStore.isConfigured) {
        // ── 阶段 1：相关性筛选 ─────────────────────────────────────────────
        ragPhase.value  = 'screening'
        ragStatus.value = `正在分析 ${candidateEmails.length} 封邮件的相关性…`
        _addMessage('status', ragStatus.value, { phase: 'screening' })

        const threshold = (settingsStore.relevanceThreshold ?? 60) / 100
        const screenRes = await _screenEmails(userText.trim(), candidateEmails, threshold)

        _removeLastStatus()

        if (!screenRes.success) {
          // 筛选失败时降级：不带邮件上下文直接回答
          _addMessage('status', `⚠️ 相关性筛选失败（${screenRes.error}），将不带邮件上下文回答`, { phase: 'warn' })
        } else if (screenRes.relevant.length === 0) {
          _addMessage('status', `未找到相关邮件（相关性均低于阈值 ${settingsStore.relevanceThreshold}%），AI 将如实告知`, { phase: 'info' })
        } else {
          // ── 阶段 2：拉取相关邮件正文 ──────────────────────────────────
          ragPhase.value  = 'loading'
          const relevantKeys = screenRes.relevant.map(r => r.key)
          ragStatus.value = `找到 ${relevantKeys.length} 封相关邮件，正在加载内容…`
          _addMessage('status', ragStatus.value, { phase: 'loading' })

          const bodiesRes = await _fetchBodies(relevantKeys)
          _removeLastStatus()

          if (bodiesRes.success) {
            emailContextText = _buildEmailContext(screenRes.relevant, bodiesRes.bodies, threshold)
            _addMessage('status',
              `已加载 ${relevantKeys.length} 封相关邮件（相关性 ≥ ${settingsStore.relevanceThreshold}%）`,
              { phase: 'info', count: relevantKeys.length }
            )
          }
        }
      }

      // ── 阶段 3：调用主 AI 回答 ────────────────────────────────────────────
      ragPhase.value  = 'answering'
      ragStatus.value = '正在生成回复…'

      const systemContent = _buildSystemPrompt(emailContextText)
      const historyMsgs = messages.value
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .slice(-20)
        .map(m => ({ role: m.role, content: m.content }))

      const apiMessages = [
        { role: 'system', content: systemContent },
        ...historyMsgs,
      ]

      const res = await fetch('/api/ai/chat', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          base_url: settingsStore.apiBaseUrl,
          api_key:  settingsStore.apiKey,
          model:    settingsStore.selectedModel,
          messages: apiMessages,
        }),
      })
      const data = await res.json()

      if (data.success) {
        _addMessage('assistant', data.content, { usage: data.usage })
      } else {
        chatError.value = data.error ?? 'AI 请求失败'
        _addMessage('assistant', `⚠️ 请求失败：${chatError.value}`)
      }
    } catch (e) {
      chatError.value = e.message
      _addMessage('assistant', `⚠️ 网络错误：${e.message}`)
    } finally {
      thinking.value  = false
      ragPhase.value  = null
      ragStatus.value = ''
    }
  }

  // ─── 内部：获取候选邮件（手动选中 or 全部）──────────────────────────────
  function _getCandidateEmails(keysOverride) {
    if (!contextLoaded.value) return []
    const keys = keysOverride ?? selectedKeys.value
    if (keys === null) return contextEmails.value
    return contextEmails.value.filter(e => keys.has(e.key))
  }

  // ─── 内部：调用 screen-emails 端点 ───────────────────────────────────────
  async function _screenEmails(query, emails, threshold) {
    try {
      const res = await fetch('/api/ai/screen-emails', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          base_url:         settingsStore.apiBaseUrl,
          api_key:          settingsStore.apiKey,
          model:            settingsStore.selectedModel,
          query,
          emails,
          threshold,
        }),
      })
      return await res.json()
    } catch (e) {
      return { success: false, error: e.message }
    }
  }

  // ─── 内部：批量拉取正文 ────────────────────────────────────────────────────
  async function _fetchBodies(keys) {
    try {
      const res = await fetch('/api/ai/fetch-bodies', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          account_id:          contextAccountId.value,
          folder_id:           contextFolderId.value,
          keys,
          max_chars_per_email: 2000,
        }),
      })
      return await res.json()
    } catch (e) {
      return { success: false, error: e.message }
    }
  }

  // ─── 内部：构建邮件上下文文本 ─────────────────────────────────────────────
  function _buildEmailContext(relevantList, bodies, threshold) {
    if (!relevantList.length) return ''

    const thresholdPct = Math.round(threshold * 100)
    const lines = [
      `以下是与本次对话相关的邮件（共 ${relevantList.length} 封，相关性 ≥ ${thresholdPct}%，按相关性降序）：`,
      '',
    ]

    // relevantList 已按 score 降序
    for (const r of relevantList) {
      const meta = contextEmails.value.find(e => e.key === r.key) ?? {}
      const relevancePct = Math.round(r.score * 100)
      const bodyMd = bodies[r.key] || ''
      const status = meta.is_read === false ? '未读' : '已读'

      lines.push('────────────────────────────────────────')
      lines.push(`【相关性 ${relevancePct}%】${meta.subject || '（无主题）'}`)
      lines.push(`发件人：${meta.from || '未知'}`)
      lines.push(`日期：${meta.date || '未知'}`)
      lines.push(`状态：${status}`)
      if (bodyMd) {
        lines.push('正文：')
        lines.push(bodyMd)
      }
      lines.push('')
    }

    return lines.join('\n')
  }

  // ─── 内部：构建系统提示 ────────────────────────────────────────────────────
  function _buildSystemPrompt(emailContextText) {
    const role       = promptsStore.get('chat', 'role')
    const rules      = promptsStore.get('chat', 'rules')
    const userPrompt = settingsStore.systemPrompt || ''
    const noContext  = promptsStore.get('chat', 'no_context')

    const prefix = [role, userPrompt, rules].filter(Boolean).join('\n')

    if (!emailContextText) {
      return `${prefix}\n\n${noContext}`
    }
    return `${prefix}\n\n${emailContextText}`
  }

  // ─── 清空 ──────────────────────────────────────────────────────────────────
  function clearChat() {
    messages.value  = []
    chatError.value = ''
    ragPhase.value  = null
    ragStatus.value = ''
  }

  function clearContext() {
    contextEmails.value    = []
    contextLoaded.value    = false
    contextAccountId.value = ''
    contextFolderId.value  = ''
    contextError.value     = ''
    selectedKeys.value     = null
  }

  /**
   * 从 Reader 页面跳转过来时调用：
   * 设置 pendingJump，DashboardView 挂载/激活时处理它
   */
  function jumpFromEmail({ accountId, folderId, key, subject }) {
    pendingJump.value = { accountId, folderId, key, subject }
  }

  return {
    // chat
    messages, thinking, chatError, ragPhase, ragStatus,
    sendMessage, clearChat,
    // context
    contextAccountId, contextFolderId, contextEmails,
    contextLoading, contextError, contextLoaded, contextSummary,
    selectedKeys,
    loadContext, clearContext,
    // cross-page jump
    pendingJump, jumpFromEmail,
  }
})
