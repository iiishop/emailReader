/**
 * stores/assistant.js
 * 全局 AI 助手状态：浮动窗显隐、会话消息、# 引用语法解析与邮件拉取。
 *
 * ── # 引用语法 ──────────────────────────────────────────────────────────────
 *
 *  批量引用（经过 RAG 相关性筛选）
 *  ─────────────────────────────────────────────────────────────────────────
 *  #email@host.com/FolderName        → 该邮箱指定文件夹的所有邮件（受 aiDays 限制）
 *  #email@host.com/FolderName:7d     → 该邮箱指定文件夹最近 7 天的邮件
 *  #email@host.com/FolderName:30d    → 最近 30 天
 *  #email@host.com/FolderName:all    → 全部（不限天数）
 *  #email@host.com:7d                → 该邮箱 INBOX 最近 7 天
 *  #email@host.com[sender]           → 筛选发件人含 sender 的邮件（名称或邮箱）
 *  #email@host.com/Folder[sender]    → 文件夹 + 发件人双重筛选
 *  #email@host.com/Folder:7d[sender] → 文件夹 + 天数 + 发件人三重筛选
 *  #email@host.com/Folder~keyword    → 主题含 keyword 的邮件（模糊匹配，可能多封）
 *  #email@host.com/Folder!unread     → 只看未读邮件
 *
 *  精确引用单封邮件（直接读取正文，跳过 RAG 筛选）
 *  ─────────────────────────────────────────────────────────────────────────
 *  #email@host.com/Folder>"邮件主题"  → 主题完全匹配（引号内）
 *  #email@host.com/Folder>'主题'      → 同上，单引号也支持
 *  #email@host.com/Folder>主题关键词  → 主题精确前缀/全词匹配（无引号时取第一封）
 *
 * ── 示例 ────────────────────────────────────────────────────────────────────
 *  帮我总结 #alice@example.com/INBOX:7d 最近的邮件
 *  #bob@work.com[boss@company.com] 有没有发过合同？
 *  #alice@example.com/INBOX~发票 这些发票邮件的金额是多少？
 *  #alice@example.com/INBOX>"关于Q1财报的通知" 这封邮件说了什么？
 *  #alice@example.com/INBOX>Q1财报 帮我总结一下
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useSettingsStore }  from './settings.js'
import { useAccountsStore }  from './accounts.js'
import { useMailStore }      from './mail.js'
import { usePromptsStore }   from './prompts.js'

// ── # 引用语法正则 ────────────────────────────────────────────────────────────
// 捕获组：
//   1 = email
//   2 = folder（可选）
//   3 = days（可选，如 7d / 30d / all）
//   4 = sender 筛选（可选，[xxx]）
//   5 = 模糊主题关键词（可选，~xxx）
//   6 = unread 标志（可选，!unread）
//   7 = 精确主题（可选，>"xxx" 或 >'xxx' 或 >xxx，捕获引号内或无引号的内容）
const REF_REGEX = /#([\w.+-]+@[\w.-]+\.[a-z]{2,})(?:\/([\w\u4e00-\u9fa5 ._-]+?))?(?::(\d+d|all))?(?:\[([^\]]+)\])?(?:~([^\s#>]+))?(!unread)?(?:>(?:["']((?:[^"'\\]|\\.)+)["']|([^\s#,，。？?！!]+)))?(?=\s|$|[,，。？?！!])/gi

export function parseRefs(text) {
  const refs = []
  let m
  REF_REGEX.lastIndex = 0
  while ((m = REF_REGEX.exec(text)) !== null) {
    // 精确主题：优先取引号内（m[7]），其次取无引号内容（m[8]）
    const exactTitle = (m[7] || m[8])?.trim() || null
    refs.push({
      raw:        m[0],
      email:      m[1].toLowerCase(),
      folder:     m[2]?.trim() || null,   // null → 默认 INBOX
      days:       m[3] || null,           // '7d' | '30d' | 'all' | null
      sender:     m[4]?.trim() || null,
      keyword:    m[5]?.trim() || null,   // 模糊主题匹配（~xxx），可能多封
      unread:     !!m[6],
      exactTitle,                         // 精确主题匹配（>xxx），直接读正文，跳过 RAG
    })
  }
  return refs
}

/** 把 '7d' → 7, 'all' → 0, null → settingsStore.aiDays */
function _daysToInt(daysStr, defaultDays) {
  if (!daysStr) return defaultDays
  if (daysStr === 'all') return 0
  return parseInt(daysStr, 10) || defaultDays
}

export const useAssistantStore = defineStore('assistant', () => {
  const settingsStore = useSettingsStore()
  const accountsStore = useAccountsStore()
  const mailStore     = useMailStore()
  const promptsStore  = usePromptsStore()

  // ── 浮动窗状态 ─────────────────────────────────────────────────────────────
  const visible   = ref(false)
  const minimized = ref(false)

  function open()    { visible.value = true;  minimized.value = false }
  function close()   { visible.value = false }
  function toggle()  { visible.value ? close() : open() }
  function minimize(){ minimized.value = !minimized.value }

  // ── 会话消息 ───────────────────────────────────────────────────────────────
  const messages  = ref([])
  const thinking  = ref(false)
  const chatError = ref('')
  const ragPhase  = ref(null)   // null | 'resolving' | 'screening' | 'loading' | 'answering'

  function _uid() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2)
  }
  function _addMsg(role, content, extra = {}) {
    messages.value.push({ role, content, id: _uid(), ts: Date.now(), ...extra })
  }
  function _removeLastStatus() {
    const idx = [...messages.value].reverse().findIndex(m => m.role === 'status')
    if (idx !== -1) messages.value.splice(messages.value.length - 1 - idx, 1)
  }

  function clearChat() {
    messages.value  = []
    chatError.value = ''
    ragPhase.value  = null
  }

  // ── 发送消息（解析 # 引用 → RAG 两阶段 → 回答）────────────────────────────
  async function sendMessage(rawText) {
    if (!rawText.trim() || thinking.value) return
    chatError.value = ''

    // 确保 prompts.yaml 已加载（首次调用时拉取，后续命中缓存）
    await promptsStore.ensure()

    _addMsg('user', rawText.trim())
    thinking.value = true
    ragPhase.value = null

    let emailContextText = ''

    try {
      // ── 步骤 0：解析 # 引用，拉取候选邮件元数据 ────────────────────────────
      const refs = parseRefs(rawText)
      let candidateEmails = []

      if (refs.length > 0) {
        ragPhase.value = 'resolving'
        _addMsg('status', `正在解析 ${refs.length} 个邮件引用…`, { phase: 'resolving' })

        const resolved = await _resolveRefs(refs)
        _removeLastStatus()

        candidateEmails = resolved.emails
        if (resolved.errors.length) {
          _addMsg('status', `⚠️ 部分引用解析失败：${resolved.errors.join('；')}`, { phase: 'warn' })
        }
        if (candidateEmails.length > 0) {
          _addMsg('status', `引用解析完成，共 ${candidateEmails.length} 封候选邮件`, { phase: 'info' })
        }
      }

      // ── 精确引用（_exact=true）：直接读正文，不走 RAG 筛选 ────────────────
      const exactEmails = candidateEmails.filter(e => e._exact)
      const bulkEmails  = candidateEmails.filter(e => !e._exact)

      if (exactEmails.length > 0) {
        ragPhase.value = 'loading'
        _addMsg('status', `正在加载 ${exactEmails.length} 封精确引用的邮件正文…`, { phase: 'loading' })
        const exactKeys    = exactEmails.map(e => e.key)
        const exactBodies  = await _fetchBodiesGrouped(exactKeys, exactEmails)
        _removeLastStatus()

        if (exactBodies.success) {
          // 精确邮件以 score=1.0 直接纳入上下文
          const fakeRelevant = exactEmails.map(e => ({ key: e.key, score: 1.0 }))
          const exactCtx = _buildEmailContext(fakeRelevant, exactBodies.bodies, exactEmails, 0)
          emailContextText += (emailContextText ? '\n\n' : '') + exactCtx
          _addMsg('status',
            `已加载 ${exactEmails.length} 封精确引用的邮件`,
            { phase: 'info', count: exactEmails.length }
          )
        }
      }

      // ── 步骤 1：批量邮件相关性筛选 ────────────────────────────────────────
      if (bulkEmails.length > 0 && settingsStore.isConfigured) {
        ragPhase.value = 'screening'
        _addMsg('status', `正在分析 ${bulkEmails.length} 封邮件的相关性…`, { phase: 'screening' })

        const threshold = (settingsStore.relevanceThreshold ?? 60) / 100
        // 用去掉 # 引用后的纯文本问题做筛选
        const cleanQuery = rawText.replace(REF_REGEX, '').trim() || rawText.trim()
        const screenRes  = await _screenEmails(cleanQuery, bulkEmails, threshold)
        _removeLastStatus()

        if (!screenRes.success) {
          _addMsg('status', `⚠️ 相关性筛选失败（${screenRes.error}），将不带邮件上下文回答`, { phase: 'warn' })
        } else if (screenRes.relevant.length === 0) {
          _addMsg('status', `未找到相关邮件（相关性均低于阈值 ${settingsStore.relevanceThreshold}%），AI 将如实告知`, { phase: 'info' })
        } else {
          // ── 步骤 2：拉取相关邮件正文 ────────────────────────────────────
          ragPhase.value = 'loading'
          const relevantKeys = screenRes.relevant.map(r => r.key)
          _addMsg('status', `找到 ${relevantKeys.length} 封相关邮件，正在加载内容…`, { phase: 'loading' })

          const bodiesRes = await _fetchBodiesGrouped(relevantKeys, bulkEmails)
          _removeLastStatus()

          if (bodiesRes.success) {
            const bulkCtx = _buildEmailContext(screenRes.relevant, bodiesRes.bodies, bulkEmails, threshold)
            emailContextText += (emailContextText ? '\n\n' : '') + bulkCtx
            _addMsg('status',
              `已加载 ${relevantKeys.length} 封相关邮件（相关性 ≥ ${settingsStore.relevanceThreshold}%）`,
              { phase: 'info', count: relevantKeys.length }
            )
          }
        }
      }

      // ── 步骤 3：调用主 AI 回答 ─────────────────────────────────────────────
      ragPhase.value = 'answering'
      const systemContent = _buildSystemPrompt(emailContextText)
      const historyMsgs = messages.value
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .slice(-20)
        .map(m => ({ role: m.role, content: m.content }))

      const res = await fetch('/api/ai/chat', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: settingsStore.apiBaseUrl,
          api_key:  settingsStore.apiKey,
          model:    settingsStore.selectedModel,
          messages: [{ role: 'system', content: systemContent }, ...historyMsgs],
        }),
      })
      const data = await res.json()

      if (data.success) {
        _addMsg('assistant', data.content, { usage: data.usage })
      } else {
        chatError.value = data.error ?? 'AI 请求失败'
        _addMsg('assistant', `⚠️ 请求失败：${chatError.value}`)
      }
    } catch (e) {
      chatError.value = e.message
      _addMsg('assistant', `⚠️ 网络错误：${e.message}`)
    } finally {
      thinking.value = false
      ragPhase.value = null
    }
  }

  // ── 内部：解析 # 引用，拉取元数据 ─────────────────────────────────────────
  async function _resolveRefs(refs) {
    const emails = []
    const errors = []

    for (const ref of refs) {
      // 找到对应账号
      const account = accountsStore.accounts.find(
        a => a.email.toLowerCase() === ref.email
      )
      if (!account) {
        errors.push(`找不到账号 ${ref.email}`)
        continue
      }

      // 确定文件夹
      let folders = mailStore.foldersByAccount.get(account.account_id) ?? []
      if (!folders.length) {
        // 尝试拉取文件夹
        try {
          const r = await fetch(`/api/accounts/${account.account_id}/folders`)
          const d = await r.json()
          if (d.success) folders = d.folders
        } catch { /* ignore */ }
      }

      const folderName = ref.folder || 'INBOX'
      const folder = folders.find(
        f => f.name.toUpperCase() === folderName.toUpperCase()
      ) || folders.find(
        f => f.name.toLowerCase().includes(folderName.toLowerCase())
      )

      if (!folder) {
        errors.push(`账号 ${ref.email} 中找不到文件夹 "${folderName}"`)
        continue
      }

      const aiDays = _daysToInt(ref.days, settingsStore.aiDays)

      try {
        const res = await fetch('/api/ai/prepare-emails', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            account_id:    account.account_id,
            folder_id:     folder.folder_id,
            ai_days:       aiDays,
            max_emails:    300,
            metadata_only: true,
          }),
        })
        const data = await res.json()
        if (!data.success) {
          errors.push(`加载 ${ref.email}/${folderName} 失败：${data.error}`)
          continue
        }

        let batch = data.emails.map(e => ({
          ...e,
          _accountId: account.account_id,
          _folderId:  folder.folder_id,
          _refRaw:    ref.raw,
          _exact:     false,
        }))

        // ── 精确主题匹配（> 语法）：直接取第一封完全匹配的，跳过后续 RAG ──
        if (ref.exactTitle) {
          const title = ref.exactTitle.toLowerCase()
          // 优先完整匹配，其次包含匹配
          const exact = batch.find(e => (e.subject || '').toLowerCase() === title)
            ?? batch.find(e => (e.subject || '').toLowerCase().includes(title))
          if (exact) {
            emails.push({ ...exact, _exact: true })
          } else {
            errors.push(`在 ${ref.email}/${folderName} 中未找到主题为"${ref.exactTitle}"的邮件`)
          }
          continue  // 精确引用不走后续批量筛选
        }

        // 发件人筛选
        if (ref.sender) {
          const s = ref.sender.toLowerCase()
          batch = batch.filter(e =>
            (e.from || '').toLowerCase().includes(s)
          )
        }

        // 主题关键词筛选（模糊，~语法）
        if (ref.keyword) {
          const kw = ref.keyword.toLowerCase()
          batch = batch.filter(e =>
            (e.subject || '').toLowerCase().includes(kw)
          )
        }

        // 未读筛选
        if (ref.unread) {
          batch = batch.filter(e => !e.is_read)
        }

        emails.push(...batch)
      } catch (e) {
        errors.push(`${ref.email}: ${e.message}`)
      }
    }

    return { emails, errors }
  }

  // ── 内部：相关性筛选 ───────────────────────────────────────────────────────
  async function _screenEmails(query, emails, threshold) {
    try {
      const res = await fetch('/api/ai/screen-emails', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url:  settingsStore.apiBaseUrl,
          api_key:   settingsStore.apiKey,
          model:     settingsStore.selectedModel,
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

  // ── 内部：按账号/文件夹分组批量拉正文 ─────────────────────────────────────
  async function _fetchBodiesGrouped(relevantKeys, allEmails) {
    // 建立 key → {accountId, folderId} 映射
    const keyMeta = {}
    for (const e of allEmails) {
      keyMeta[e.key] = { accountId: e._accountId, folderId: e._folderId }
    }

    // 按 accountId+folderId 分组
    const groups = {}
    for (const key of relevantKeys) {
      const m = keyMeta[key]
      if (!m) continue
      const gk = `${m.accountId}::${m.folderId}`
      if (!groups[gk]) groups[gk] = { accountId: m.accountId, folderId: m.folderId, keys: [] }
      groups[gk].keys.push(key)
    }

    const bodies = {}
    for (const g of Object.values(groups)) {
      try {
        const res = await fetch('/api/ai/fetch-bodies', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            account_id:          g.accountId,
            folder_id:           g.folderId,
            keys:                g.keys,
            max_chars_per_email: 2000,
          }),
        })
        const data = await res.json()
        if (data.success) Object.assign(bodies, data.bodies)
      } catch { /* ignore */ }
    }

    return { success: true, bodies }
  }

  // ── 内部：构建邮件上下文文本 ───────────────────────────────────────────────
  function _buildEmailContext(relevantList, bodies, allEmails, threshold) {
    if (!relevantList.length) return ''
    const pct = Math.round(threshold * 100)
    const lines = [
      `以下是与问题相关的邮件（共 ${relevantList.length} 封，相关性 ≥ ${pct}%）：`,
      '',
    ]
    for (const r of relevantList) {
      const meta = allEmails.find(e => e.key === r.key) ?? {}
      lines.push('────────────────────────────────────────')
      lines.push(`【相关性 ${Math.round(r.score * 100)}%】${meta.subject || '（无主题）'}`)
      lines.push(`发件人：${meta.from || '未知'}`)
      lines.push(`日期：${meta.date || '未知'}`)
      lines.push(`状态：${meta.is_read === false ? '未读' : '已读'}`)
      const body = bodies[r.key]
      if (body) { lines.push('正文：'); lines.push(body) }
      lines.push('')
    }
    return lines.join('\n')
  }

  // ── 内部：构建系统提示（所有文本均来自 prompts.yaml，不含硬编码）────────
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

  // ── 从 Reader 页面快速引用单封邮件 ────────────────────────────────────────
  /**
   * 在输入框中插入对某封邮件的 # 引用片段
   * 返回引用字符串，由 AiAssistant 组件插入输入框
   */
  function buildEmailRef(accountEmail, folderName, emailKey, subject) {
    // 用 key 作为精确定位（未来可扩展为 key 语法）
    // 目前退化为：打开助手并预填文本
    return `#${accountEmail}/${folderName} `
  }

  /** 打开助手并预填文本（从 Reader 跳转时使用） */
  function openWithText(text) {
    open()
    return text  // 由组件接收后填入输入框
  }

  // ── 窗口位置（拖拽持久化）─────────────────────────────────────────────────
  const position = ref(
    JSON.parse(localStorage.getItem('assistant-pos') || 'null') ?? { x: null, y: null }
  )
  function savePosition(x, y) {
    position.value = { x, y }
    localStorage.setItem('assistant-pos', JSON.stringify({ x, y }))
  }

  return {
    // 浮动窗
    visible, minimized, open, close, toggle, minimize,
    position, savePosition,
    // 会话
    messages, thinking, chatError, ragPhase,
    sendMessage, clearChat,
    // 工具
    buildEmailRef, openWithText,
  }
})
