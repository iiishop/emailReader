<template>
  <div class="app-layout">

    <!-- ══ 左侧导航栏 ══ -->
    <aside class="sidebar">
      <!-- 品牌 Logo -->
      <div class="sidebar-brand" title="EmailReader">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <rect x="2" y="3" width="20" height="14" rx="2.5"/>
          <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
        </svg>
      </div>

      <!-- 主导航 -->
      <nav class="sidebar-nav">
        <button
          class="nav-item"
          :class="{ active: navStore.currentPage === 'dashboard' }"
          @click="navStore.navigate('dashboard')"
          title="Dashboard"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <rect x="3" y="3" width="7" height="7" rx="1.5"/>
            <rect x="14" y="3" width="7" height="7" rx="1.5"/>
            <rect x="3" y="14" width="7" height="7" rx="1.5"/>
            <rect x="14" y="14" width="7" height="7" rx="1.5"/>
          </svg>
          <span class="nav-label">工作台</span>
        </button>
        <button
          class="nav-item"
          :class="{ active: navStore.currentPage === 'reader' }"
          @click="navStore.navigate('reader')"
          title="Reader"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
            <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
          </svg>
          <span class="nav-label">邮件</span>
        </button>
      </nav>

      <!-- 底部工具 -->
      <div class="sidebar-bottom">
        <!-- 连接状态 -->
        <div class="sidebar-status" :title="accountsStore.accounts.length ? `${accountsStore.accounts.length} 个账号已连接` : '未连接'">
          <span class="status-dot" :class="accountsStore.accounts.length ? 'ok' : 'err'"></span>
        </div>

        <!-- 刷新 -->
        <button
          class="sidebar-btn"
          @click="refreshStore.doRefresh(true)"
          :disabled="refreshStore.isRefreshing"
          :title="refreshStore.isRefreshing ? '刷新中…' : (refreshStore.lastRefreshed ? '上次：' + refreshStore.formatTime(refreshStore.lastRefreshed) : '立即刷新')"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
            :class="{ spinning: refreshStore.isRefreshing }">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
        </button>

        <!-- AI 助手 -->
        <button
          class="sidebar-btn"
          :class="{ active: assistantStore.visible }"
          @click="assistantStore.toggle()"
          title="AI 邮件助手"
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
            <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-1H1a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 12 2z"/>
          </svg>
          <span v-if="assistantStore.thinking" class="ai-dot"></span>
        </button>

        <!-- 设置 -->
        <button class="sidebar-btn" @click="settingsOpen = true" title="设置">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          <span v-if="!settingsStore.isConfigured" class="cfg-dot"></span>
        </button>

        <!-- 日夜切换 -->
        <button class="sidebar-btn" @click="toggleTheme" :title="isDark ? '浅色模式' : '深色模式'">
          <svg v-if="isDark" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
            <circle cx="12" cy="12" r="4"/>
            <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
          </svg>
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
        </button>
      </div>
    </aside>

    <!-- ══ 主内容区 ══ -->
    <main class="main-area">
      <DashboardView v-show="navStore.currentPage === 'dashboard'" />
      <ReaderView    v-show="navStore.currentPage === 'reader'" />
    </main>

    <!-- 设置弹窗 -->
    <SettingsModal v-model:visible="settingsOpen" />

    <!-- AI 助手浮动窗（全局，跨页面持久） -->
    <AiAssistant ref="aiAssistantRef" />
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useAccountsStore }      from './stores/accounts.js'
import { useMailStore }          from './stores/mail.js'
import { useSettingsStore }      from './stores/settings.js'
import { useNavigationStore }    from './stores/navigation.js'
import { useRefreshStore }       from './stores/refresh.js'
import { useAssistantStore }     from './stores/assistant.js'
import { useDashboardDataStore } from './stores/dashboardData.js'
import DashboardView  from './views/DashboardView.vue'
import ReaderView     from './views/ReaderView.vue'
import SettingsModal  from './components/SettingsModal.vue'
import AiAssistant    from './components/AiAssistant.vue'

const accountsStore  = useAccountsStore()
const mailStore      = useMailStore()
const settingsStore  = useSettingsStore()
const navStore       = useNavigationStore()
const refreshStore   = useRefreshStore()
const assistantStore = useAssistantStore()
const dashDataStore  = useDashboardDataStore()

const aiAssistantRef = ref(null)
const settingsOpen   = ref(false)

// ── 主题（存后端，替代 localStorage）──────────────────────────────────────────
const isDark = ref(false)

function applyTheme(dark) {
  isDark.value = dark
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
  fetch('/api/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ theme: dark ? 'dark' : 'light' }),
  }).catch(() => {})
}
function toggleTheme() { applyTheme(!isDark.value) }

onMounted(async () => {
  // 从后端加载配置（PyWebView 无 localStorage，全部走后端）
  try {
    const res = await fetch('/api/config?t=' + Date.now(), { cache: 'no-store' })
    const config = await res.json()
    applyTheme(config.theme === 'dark')
    settingsStore.loadFrom(config.settings)
    assistantStore.loadPosition(config.assistantPos)
  } catch {
    applyTheme(false)
  }
  mailStore.forceResetLoading()
  await accountsStore.fetchAccounts()
  refreshStore.init()
  dashDataStore.loadData()
  dashDataStore.loadTodos()
})

// 新邮件刷新后，若 AI 已配置，自动触发 Dashboard 提取
watch(() => refreshStore.lastRefreshed, (val, old) => {
  if (val && old && settingsStore.isConfigured) {
    dashDataStore.triggerExtract()
  }
})
</script>

<style scoped>
/* ══ 整体布局：左侧导航 + 右侧内容 ══ */
.app-layout {
  display: flex;
  flex-direction: row;
  height: 100vh;
  overflow: hidden;
  position: relative;
  z-index: 1;
}

/* ══ 左侧导航栏：略宽、带层次 ══ */
.sidebar {
  width: var(--sidebar-w);
  flex-shrink: 0;
  background: var(--bg-sidebar);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0 14px;
  gap: 0;
  border-right: 1px solid rgba(255,255,255,.06);
  user-select: none;
  z-index: 100;
  box-shadow: 4px 0 24px rgba(0,0,0,.08);
}
[data-theme="dark"] .sidebar {
  box-shadow: 4px 0 20px rgba(0,0,0,.25);
}

/* 品牌 Logo */
.sidebar-brand {
  width: 40px; height: 40px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 12px;
  background: var(--accent);
  color: #fff;
  margin-bottom: 18px;
  flex-shrink: 0;
  box-shadow: 0 4px 14px rgba(13,148,136,.35);
  transition: transform var(--duration-fast) var(--ease-spring), box-shadow var(--duration-fast) var(--ease-soft);
}
.sidebar-brand:hover { box-shadow: 0 6px 18px rgba(13,148,136,.4); }
[data-theme="dark"] .sidebar-brand { box-shadow: 0 4px 14px rgba(45,212,191,.25); }
[data-theme="dark"] .sidebar-brand:hover { box-shadow: 0 6px 18px rgba(45,212,191,.35); }

/* 主导航 */
.sidebar-nav {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex: 1;
  width: 100%;
  padding: 0 8px;
}

.nav-item {
  width: 36px; height: 36px;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 3px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text-sidebar-muted);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-soft), color var(--duration-fast) var(--ease-soft);
  position: relative;
}
.nav-item:hover {
  background: rgba(255,255,255,.07);
  color: var(--text-sidebar);
}
.nav-item.active {
  background: rgba(13,148,136,.2);
  color: var(--accent-light);
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: -8px; top: 50%;
  transform: translateY(-50%);
  width: 3px; height: 22px;
  background: var(--accent-light);
  border-radius: 0 3px 3px 0;
  animation: navPillIn 0.35s var(--ease-spring) forwards;
}
[data-theme="dark"] .nav-item.active { background: rgba(45,212,191,.18); }
@keyframes navPillIn {
  from { opacity: 0; transform: translateY(-50%) scaleX(0); }
  to { opacity: 1; transform: translateY(-50%) scaleX(1); }
}
.nav-label {
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: .04em;
  line-height: 1;
}

/* 底部工具区 */
.sidebar-bottom {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 0 8px;
}

.sidebar-status {
  width: 36px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 4px;
}
.status-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-dot.ok  { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,.6); }
.status-dot.err { background: #f43f5e; }

.sidebar-btn {
  position: relative;
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--text-sidebar-muted);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-soft), color var(--duration-fast) var(--ease-soft);
  flex-shrink: 0;
}
.sidebar-btn:hover {
  background: rgba(255,255,255,.07);
  color: var(--text-sidebar);
}
.sidebar-btn:disabled { opacity: .4; cursor: not-allowed; }
.sidebar-btn.active {
  background: rgba(13,148,136,.2);
  color: var(--accent-light);
}
[data-theme="dark"] .sidebar-btn.active { background: rgba(45,212,191,.18); }

.ai-dot {
  position: absolute;
  top: 5px; right: 5px;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--accent-light);
  animation: aiPulse 1s ease-in-out infinite;
}
.cfg-dot {
  position: absolute;
  top: 5px; right: 5px;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #f43f5e;
  border: 1.5px solid var(--bg-sidebar);
}

/* ══ 主内容区 ══ */
.main-area {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: opacity var(--duration-normal) var(--ease-soft);
}

/* ── 动画 ── */
@keyframes spin {
  to { transform: rotate(360deg); }
}
.spinning {
  animation: spin .7s linear infinite;
  transform-origin: center;
}

@keyframes aiPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: .4; transform: scale(.65); }
}
</style>
