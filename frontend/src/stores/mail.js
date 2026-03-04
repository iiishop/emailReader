import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useMailStore = defineStore('mail', () => {
  // ─── 文件夹 ────────────────────────────────────────────────────────────────
  const foldersByAccount = ref(new Map())  // accountId -> folder[]
  const foldersLoading = ref(false)
  const foldersError = ref(null)
  const selectedFolder = ref(null)

  let _fetchingFolderFor = null

  async function fetchFolders(accountId) {
    if (foldersByAccount.value.has(accountId)) {
      const folders = foldersByAccount.value.get(accountId)
      _ensureFolderSelected(accountId, folders)
      return
    }
    if (_fetchingFolderFor === accountId) return
    _fetchingFolderFor = accountId

    foldersLoading.value = true
    foldersError.value = null
    try {
      const res = await fetch(`/api/accounts/${accountId}/folders`)
      const data = await res.json()
      if (data.success) {
        const newMap = new Map(foldersByAccount.value)
        newMap.set(accountId, data.folders)
        foldersByAccount.value = newMap
        _ensureFolderSelected(accountId, data.folders)
      } else {
        foldersError.value = data.error ?? '获取文件夹失败'
      }
    } catch (e) {
      foldersError.value = e.message
    } finally {
      foldersLoading.value = false
      if (_fetchingFolderFor === accountId) _fetchingFolderFor = null
    }
  }

  function _ensureFolderSelected(accountId, folders) {
    if (!selectedFolder.value || selectedFolder.value.account_id !== accountId) {
      const inbox = folders.find(f => f.name === 'INBOX') ?? folders[0]
      if (inbox) selectFolder(accountId, inbox)
    }
  }

  /**
   * selectFolder：切换文件夹
   * - 把「正在离开的文件夹」加入 seenFolders（下次回来显示灰色未读）
   * - 重置邮件列表
   */
  function selectFolder(accountId, folder) {
    if (selectedFolder.value?.folder_id) {
      const newSeen = new Set(seenFolders.value)
      newSeen.add(selectedFolder.value.folder_id)
      seenFolders.value = newSeen
    }
    selectedFolder.value = { account_id: accountId, ...folder }
    _resetEmailList()
  }

  async function refreshFolders(accountId) {
    const newMap = new Map(foldersByAccount.value)
    newMap.delete(accountId)
    foldersByAccount.value = newMap
    await fetchFolders(accountId)
  }

  async function prefetchAccount(accountId) {
    try {
      await fetch(`/api/accounts/${accountId}/prefetch`, { method: 'POST' })
    } catch { /* fire-and-forget */ }
  }

  // ─── 未读状态追踪 ──────────────────────────────────────────────────────────

  /**
   * seenFolders：用户「离开过」的文件夹集合（session 级别）
   * - 不在 seenFolders 里 = 本 session 第一次进入 = 亮色未读
   * - 在 seenFolders 里 = 曾经进入过、又切走过 = 灰色未读
   */
  const seenFolders = ref(new Set())

  /**
   * folderUnread：Map<folder_id, unread_count>
   * 每次 fetchEmails 成功后，从响应的 unread_total 更新
   */
  const folderUnread = ref(new Map())

  // ─── 邮件列表 ──────────────────────────────────────────────────────────────
  const emails = ref([])
  const totalEmails = ref(0)
  const emailsLoading = ref(false)
  const emailsError = ref(null)

  const _loadedPages = ref(0)
  const PAGE_SIZE = 50

  const hasMore = computed(() => emails.value.length < totalEmails.value)

  /**
   * newEmailKeys：本次增量刷新刚刚插入的邮件 key 集合。
   * EmailList.vue 据此给行加 is-new 动画 class；2.5 秒后自动清空。
   */
  const newEmailKeys = ref(new Set())
  let _newKeysTimer = null

  let _abortCtrl = null

  function _resetEmailList() {
    if (_abortCtrl) { _abortCtrl.abort(); _abortCtrl = null }
    emails.value = []
    totalEmails.value = 0
    _loadedPages.value = 0
    emailsLoading.value = false
    emailsError.value = null
    selectedEmail.value = null
  }

  /**
   * 应用挂载时调用，强制清除可能因 HMR / 模块热替换遗留的卡死加载状态。
   */
  function forceResetLoading() {
    if (_abortCtrl) { _abortCtrl.abort(); _abortCtrl = null }
    emailsLoading.value = false
  }

  async function fetchEmails({ reset = false, force = false } = {}) {
    if (!selectedFolder.value) return
    if (reset) _resetEmailList()
    if (emailsLoading.value) return

    emailsLoading.value = true
    emailsError.value = null

    const targetFolder = selectedFolder.value
    _abortCtrl = new AbortController()
    const signal = _abortCtrl.signal

    // 60 秒超时兜底：防止因 HMR / 网络异常导致 emailsLoading 永久卡死
    const _timeoutId = setTimeout(() => {
      if (_abortCtrl === signal.controller) _abortCtrl?.abort()
    }, 60_000)

    const { account_id, folder_id } = targetFolder
    const skip = _loadedPages.value * PAGE_SIZE
    const forceParam = force ? '&force=true' : ''
    const url = `/api/accounts/${account_id}/folders/${encodeURIComponent(folder_id)}/emails?skip=${skip}&limit=${PAGE_SIZE}${forceParam}`

    try {
      const res = await fetch(url, { signal })
      const data = await res.json()
      if (selectedFolder.value?.folder_id !== targetFolder.folder_id) return

      if (data.success) {
        // 合并新页并按 epoch_ms 严格降序排列，消除跨页边界的排序错位
        const merged = [...emails.value, ...data.emails]
        merged.sort((a, b) => (b.epoch_ms ?? 0) - (a.epoch_ms ?? 0))
        emails.value = merged
        totalEmails.value = data.total
        _loadedPages.value++

        // 更新该文件夹的未读数
        if (data.unread_total !== undefined) {
          const newMap = new Map(folderUnread.value)
          newMap.set(folder_id, data.unread_total)
          folderUnread.value = newMap
        }
      } else {
        emailsError.value = data.detail ?? '获取邮件失败'
      }
    } catch (e) {
      if (e.name !== 'AbortError') emailsError.value = e.message
    } finally {
      clearTimeout(_timeoutId)
      emailsLoading.value = false
      _abortCtrl = null
    }
  }

  /**
   * refreshEmails：增量刷新，不清空列表。
   * - 若列表为空，退化为完整 fetchEmails。
   * - 否则只 force 拉第一页，diff 出新邮件并前插，触发动画。
   */
  async function refreshEmails() {
    if (!selectedFolder.value) return

    // 列表为空时直接走完整拉取
    if (emails.value.length === 0) {
      return fetchEmails({ reset: true, force: true })
    }

    const targetFolder = selectedFolder.value
    const { account_id, folder_id } = targetFolder
    const url = `/api/accounts/${account_id}/folders/${encodeURIComponent(folder_id)}/emails?skip=0&limit=${PAGE_SIZE}&force=true`

    let data
    try {
      const res = await fetch(url)
      data = await res.json()
    } catch {
      return  // 静默失败，不显示错误
    }
    if (!data?.success) return
    if (selectedFolder.value?.folder_id !== targetFolder.folder_id) return

    const existingKeys = new Set(emails.value.map(e => e.key))
    const incoming     = data.emails ?? []

    // 找出本次新增的邮件（后端已按日期倒序，新邮件在头部）
    const brandNew = incoming.filter(e => !existingKeys.has(e.key))

    if (brandNew.length > 0) {
      // 前插新邮件（维持降序）
      emails.value     = [...brandNew, ...emails.value]
      totalEmails.value = data.total

      // 标记用于动画，2.5 秒后自动清除
      if (_newKeysTimer) clearTimeout(_newKeysTimer)
      newEmailKeys.value = new Set(brandNew.map(e => e.key))
      _newKeysTimer = setTimeout(() => {
        newEmailKeys.value = new Set()
        _newKeysTimer = null
      }, 2500)
    }

    // 更新未读数（即使没有新邮件，已读状态可能变化）
    if (data.unread_total !== undefined) {
      const newMap = new Map(folderUnread.value)
      newMap.set(folder_id, data.unread_total)
      folderUnread.value = newMap
    }
  }

  // ─── 单封邮件 ──────────────────────────────────────────────────────────────
  const selectedEmail = ref(null)
  const emailBodyLoading = ref(false)
  const emailBodyError = ref(null)

  async function fetchEmailBody(key) {
    if (!selectedFolder.value) return
    emailBodyLoading.value = true
    emailBodyError.value = null
    selectedEmail.value = null

    const { account_id, folder_id } = selectedFolder.value
    try {
      const res = await fetch(
        `/api/accounts/${account_id}/folders/${encodeURIComponent(folder_id)}/emails/${key}`
      )
      const data = await res.json()
      if (data.success) {
        selectedEmail.value = data
        // 本地标记为已读，并减少未读计数
        const item = emails.value.find(e => e.key === key)
        if (item && !item.is_read) {
          item.is_read = true
          const cur = folderUnread.value.get(folder_id) ?? 0
          if (cur > 0) {
            const newMap = new Map(folderUnread.value)
            newMap.set(folder_id, cur - 1)
            folderUnread.value = newMap
          }
        }
      } else {
        emailBodyError.value = data.detail ?? '读取邮件失败'
      }
    } catch (e) {
      emailBodyError.value = e.message
    } finally {
      emailBodyLoading.value = false
    }
  }

  /**
   * 从工作台等外部「按账号+文件夹+key」打开一封邮件（先切文件夹再拉正文）。
   * @param {string} accountId - 账号 ID
   * @param {object} folder - 文件夹对象，需含 folder_id、name 等
   * @param {string} key - 邮件 key
   */
  async function openEmailAt(accountId, folder, key) {
    if (!accountId || !folder?.folder_id || !key) return
    selectFolder(accountId, folder)
    await fetchEmailBody(key)
  }

  return {
    // folders
    foldersByAccount, foldersLoading, foldersError, selectedFolder,
    fetchFolders, selectFolder, refreshFolders, prefetchAccount,
    // unread tracking
    seenFolders, folderUnread,
    // emails list
    emails, totalEmails, emailsLoading, emailsError, hasMore, PAGE_SIZE,
    fetchEmails, refreshEmails, newEmailKeys, forceResetLoading,
    // email body
    selectedEmail, emailBodyLoading, emailBodyError, fetchEmailBody, openEmailAt,
  }
})
