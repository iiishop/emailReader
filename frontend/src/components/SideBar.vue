<template>
  <aside class="sidebar">
    <!-- 账号列表 -->
    <div class="sidebar-section">
      <div class="section-label">邮箱账号</div>
      <div v-if="accountsStore.loading" class="loading-sm">加载中…</div>
      <template v-else>
        <button
          v-for="acc in accountsStore.accounts"
          :key="acc.account_id"
          class="account-item"
          :class="{ active: accountsStore.selectedAccountId === acc.account_id }"
          @click="handleSelectAccount(acc)"
        >
          <span class="acc-icon" :class="acc.provider">{{ providerIcon(acc.provider) }}</span>
          <span class="acc-info">
            <span class="acc-email">{{ acc.email }}</span>
            <span class="acc-provider">{{ providerLabel(acc.provider) }}</span>
          </span>
          <!-- 账号级未读徽章：显示该账号 INBOX 的未读数 -->
          <span
            v-if="accountInboxUnread(acc.account_id) > 0"
            class="unread-badge acc-badge"
          >{{ accountInboxUnread(acc.account_id) }}</span>
          <span v-else-if="acc.is_default" class="def-dot" title="默认账号"></span>
        </button>
      </template>
    </div>

    <!-- 文件夹列表 -->
    <template v-if="accountsStore.selectedAccountId">
      <div class="sidebar-divider"></div>
      <div class="sidebar-section folders-section">
        <div class="section-label">文件夹</div>
        <div v-if="mailStore.foldersLoading" class="loading-sm">加载中…</div>
        <div v-else-if="mailStore.foldersError" class="error-sm">{{ mailStore.foldersError }}</div>
        <div v-else-if="!mailStore.foldersLoading && currentFolders.length === 0" class="loading-sm muted">
          暂无本地文件夹
        </div>
        <template v-else>
          <button
            v-for="folder in currentFolders"
            :key="folder.folder_id"
            class="folder-item"
            :class="{ active: mailStore.selectedFolder?.folder_id === folder.folder_id }"
            @click="handleSelectFolder(folder)"
          >
            <span class="folder-icon">{{ folderIcon(folder.name) }}</span>
            <span class="folder-name">{{ folderDisplayName(folder.name) }}</span>
            <!-- 文件夹未读徽章 -->
            <span
              v-if="folderUnreadCount(folder.folder_id) > 0"
              class="unread-badge folder-badge"
            >{{ folderUnreadCount(folder.folder_id) }}</span>
            <span v-else class="folder-size">{{ formatSize(folder.size_bytes) }}</span>
          </button>
        </template>
      </div>
    </template>
  </aside>
</template>

<script setup>
import { computed, watch } from 'vue'
import { useAccountsStore } from '../stores/accounts.js'
import { useMailStore }     from '../stores/mail.js'
import { useRefreshStore }  from '../stores/refresh.js'

const accountsStore  = useAccountsStore()
const mailStore      = useMailStore()
const refreshStore   = useRefreshStore()

/**
 * currentFolders：从 Map 里读取当前账号的文件夹列表。
 */
const currentFolders = computed(() =>
  mailStore.foldersByAccount.get(accountsStore.selectedAccountId) ?? []
)

/** 账号 INBOX 未读数（用于账号徽章）*/
function accountInboxUnread(accountId) {
  const folders = mailStore.foldersByAccount.get(accountId) ?? []
  const inbox = folders.find(f => f.name === 'INBOX')
  if (!inbox) return 0
  return mailStore.folderUnread.get(inbox.folder_id) ?? 0
}

/** 文件夹未读数 */
function folderUnreadCount(folderId) {
  return mailStore.folderUnread.get(folderId) ?? 0
}

/**
 * 点击账号按钮：
 * - 只在这里驱动"切换账号 → 拉文件夹 → 拉邮件"的完整流程
 */
async function handleSelectAccount(acc) {
  if (accountsStore.selectedAccountId === acc.account_id) return
  accountsStore.selectAccount(acc.account_id)
  mailStore.prefetchAccount(acc.account_id)
  await mailStore.fetchFolders(acc.account_id)
  await mailStore.fetchEmails({ reset: true })
}

async function handleSelectFolder(folder) {
  if (mailStore.selectedFolder?.folder_id === folder.folder_id) return
  mailStore.selectFolder(accountsStore.selectedAccountId, folder)
  // 切换文件夹只需普通重置，mtime 变化时后端会自动重建缓存
  await mailStore.fetchEmails({ reset: true })
  refreshStore.markRefreshed()
}

/**
 * watch 只负责"应用初始化"时加载默认账号。
 */
watch(() => accountsStore.selectedAccountId, async (id, prevId) => {
  if (!id) return
  if (prevId != null) return
  mailStore.prefetchAccount(id)
  await mailStore.fetchFolders(id)
  await mailStore.fetchEmails({ reset: true })
  refreshStore.markRefreshed()
}, { immediate: true })

function providerIcon(p) {
  return { gmail: 'G', outlook: 'O', '163': '网', qq: 'Q', imap: '✉' }[p] ?? '✉'
}
function providerLabel(p) {
  return { gmail: 'Gmail', outlook: 'Outlook', '163': '163', qq: 'QQ', imap: 'IMAP' }[p] ?? p
}
function folderIcon(name) {
  const n = name.toUpperCase()
  if (n === 'INBOX') return '📥'
  if (n.includes('SENT') || n.includes('已发')) return '📤'
  if (n.includes('DRAFT') || n.includes('草稿')) return '📝'
  if (n.includes('TRASH') || n.includes('已删') || n.includes('垃圾')) return '🗑'
  if (n.includes('JUNK') || n.includes('SPAM')) return '🚫'
  if (n.includes('STAR') || n.includes('星标')) return '⭐'
  return '📁'
}
function folderDisplayName(name) {
  return name.replace(/^\[Gmail\]\//, '').replace(/^\[.*?\]\//, '')
}
function formatSize(bytes) {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}K`
  return `${(bytes / 1024 / 1024).toFixed(1)}M`
}
</script>

<style scoped>
.sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 12px 0;
}

.sidebar-section { padding: 4px 8px; }
.folders-section  { flex: 1; overflow-y: auto; }
.sidebar-divider  { height: 1px; background: var(--border); margin: 8px 0; }

.section-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  padding: 4px 8px 6px;
}

/* 账号按钮 */
.account-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 8px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
  position: relative;
}
.account-item:hover  { background: var(--bg-hover); }
.account-item.active { background: rgba(99,102,241,.15); }

.acc-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.acc-icon.gmail   { background: rgba(234,67,53,.15);  color: var(--gmail); }
.acc-icon.outlook { background: rgba(0,120,212,.15);  color: var(--outlook); }
.acc-icon\.163, [class*="acc-icon"][class*="163"] { background: rgba(204,0,0,.15); color: var(--mail163); }
.acc-icon.qq      { background: rgba(18,183,245,.15); color: var(--qq); }
.acc-icon.imap    { background: rgba(99,102,241,.15); color: var(--accent-light); }

.acc-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}
.acc-email    { font-size: 12px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.acc-provider { font-size: 10px; color: var(--text-muted); }

.def-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}

/* 未读徽章 */
.unread-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  flex-shrink: 0;
}
.acc-badge {
  background: var(--unread-bright-bg, #ef4444);
  color: #fff;
}
.folder-badge {
  background: rgba(239,68,68,.15);
  color: #ef4444;
}

/* 文件夹按钮 */
.folder-item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}
.folder-item:hover  { background: var(--bg-hover); }
.folder-item.active { background: rgba(99,102,241,.15); }

.folder-icon { font-size: 13px; flex-shrink: 0; }
.folder-name { flex: 1; font-size: 12px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.folder-size { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }

.loading-sm, .error-sm {
  font-size: 11px;
  color: var(--text-muted);
  padding: 6px 8px;
}
.loading-sm.muted { color: var(--text-muted); opacity: .6; }
.error-sm { color: #f87171; }
</style>
