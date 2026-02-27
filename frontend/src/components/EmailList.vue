<template>
  <div class="email-list-pane">
    <!-- 头部 -->
    <div class="list-header">
      <div class="list-title">
        {{ mailStore.selectedFolder?.name ?? '选择文件夹' }}
        <span v-if="mailStore.totalEmails > 0" class="count-badge">
          {{ mailStore.emails.length }} / {{ mailStore.totalEmails }}
        </span>
      </div>
      <button class="icon-btn" @click="reload" :disabled="mailStore.emailsLoading" title="刷新">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          :class="{ spinning: mailStore.emailsLoading }">
          <path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/>
          <path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/>
        </svg>
      </button>
    </div>

    <!-- 虚拟滚动容器 -->
    <div class="list-body" ref="containerRef" @scroll.passive="onScroll">

      <!-- 初次加载 -->
      <div v-if="mailStore.emailsLoading && mailStore.emails.length === 0" class="state-center">
        <div class="spinner"></div>
        <span>建立索引中…</span>
      </div>

      <!-- 错误 -->
      <div v-else-if="mailStore.emailsError" class="state-center error">
        {{ mailStore.emailsError }}
      </div>

      <!-- 空状态 -->
      <div v-else-if="!mailStore.selectedFolder" class="state-center muted">
        请在左侧选择文件夹
      </div>

      <template v-else>
        <!--
          虚拟滚动：
          - topPad  ：已滚过但未渲染的行，用空白填高
          - 仅渲染 visibleEmails（可视区 + 缓冲区的条目）
          - bottomPad：后面已加载但未渲染的行，用空白填高
          - sentinel ：已加载完可见区末尾，触发下一批拉取
        -->
        <div :style="{ height: topPad + 'px' }" aria-hidden="true"></div>

        <div
          v-for="mail in visibleEmails"
          :key="mail.key"
          class="email-row"
          :class="{
            'is-selected':    mailStore.selectedEmail?.key === mail.key,
            'is-unread-new':  !mail.is_read && isFirstVisit,
            'is-unread-seen': !mail.is_read && !isFirstVisit,
            'is-new':         mailStore.newEmailKeys.has(mail.key),
          }"
          @click="openEmail(mail)"
        >
          <div class="row-dot-col">
            <span
              class="unread-dot"
              :class="{
                'dot-new':  !mail.is_read && isFirstVisit,
                'dot-seen': !mail.is_read && !isFirstVisit,
              }"
            ></span>
          </div>
          <div class="row-body">
            <div class="row-top">
              <span class="row-from">{{ shortSender(mail.from) }}</span>
              <span class="row-date">{{ formatDate(mail.date) }}</span>
            </div>
            <div class="row-subject">{{ mail.subject || '（无主题）' }}</div>
            <div class="row-preview">{{ mail.preview }}</div>
          </div>
          <div class="row-flags">
            <span v-if="mail.is_starred">⭐</span>
            <span v-if="mail.has_attachment">📎</span>
            <span v-if="mail.is_replied" class="replied-icon">↩</span>
          </div>
        </div>

        <!-- 底部填充 -->
        <div :style="{ height: bottomPad + 'px' }" aria-hidden="true"></div>

        <!-- 加载更多哨兵（IntersectionObserver 监听） -->
        <div ref="sentinelRef" style="height: 1px"></div>

        <!-- 加载中提示（非首次） -->
        <div v-if="mailStore.emailsLoading" class="load-hint">
          <div class="spinner-sm"></div> 加载更多…
        </div>

        <!-- 全部加载完毕提示 -->
        <div v-if="!mailStore.hasMore && mailStore.emails.length > 0 && !mailStore.emailsLoading"
          class="list-end">
          全部 {{ mailStore.totalEmails }} 封已加载完毕
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useMailStore }    from '../stores/mail.js'
import { useRefreshStore } from '../stores/refresh.js'

const mailStore    = useMailStore()
const refreshStore = useRefreshStore()

/**
 * isFirstVisit：当前文件夹是否为本 session 第一次进入
 * - true  → 未读邮件显示「亮色」（完全未处理）
 * - false → 未读邮件显示「灰色」（看过列表但未读）
 * seenFolders 在用户离开文件夹时才把旧 folder_id 加入，
 * 因此第一次进入时 seenFolders 不含当前 folder_id。
 */
const isFirstVisit = computed(() => {
  const folderId = mailStore.selectedFolder?.folder_id
  if (!folderId) return true
  return !mailStore.seenFolders.has(folderId)
})

// ── 虚拟滚动参数 ───────────────────────────────────────────────────────────
const ROW_HEIGHT = 76   // px，与 CSS .email-row height 保持一致
const BUFFER     = 8    // 可视区上下各多渲染 BUFFER 行

const containerRef = ref(null)
const sentinelRef  = ref(null)
const scrollTop    = ref(0)
const viewHeight   = ref(600)  // 初始估算，ResizeObserver 会更新

// ── 可视区计算 ────────────────────────────────────────────────────────────
const visibleStart = computed(() =>
  Math.max(0, Math.floor(scrollTop.value / ROW_HEIGHT) - BUFFER)
)
const visibleEnd = computed(() =>
  Math.min(
    mailStore.emails.length,
    Math.ceil((scrollTop.value + viewHeight.value) / ROW_HEIGHT) + BUFFER
  )
)
const visibleEmails = computed(() =>
  mailStore.emails.slice(visibleStart.value, visibleEnd.value)
)
const topPad    = computed(() => visibleStart.value * ROW_HEIGHT)
const bottomPad = computed(() => (mailStore.emails.length - visibleEnd.value) * ROW_HEIGHT)

// ── 滚动处理 ─────────────────────────────────────────────────────────────
function onScroll(e) {
  scrollTop.value = e.target.scrollTop
}

// ── IntersectionObserver：哨兵进入视口 → 加载下一批 ─────────────────────
let _io = null

function _initObserver() {
  if (_io) _io.disconnect()
  if (!sentinelRef.value) return
  _io = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && mailStore.hasMore && !mailStore.emailsLoading) {
        mailStore.fetchEmails()
      }
    },
    { root: containerRef.value, rootMargin: '120px' }
  )
  _io.observe(sentinelRef.value)
}

// ── ResizeObserver：容器高度变化 → 更新 viewHeight ───────────────────────
let _ro = null

function _initResize() {
  if (_ro) _ro.disconnect()
  if (!containerRef.value) return
  _ro = new ResizeObserver((entries) => {
    viewHeight.value = entries[0].contentRect.height
  })
  _ro.observe(containerRef.value)
  viewHeight.value = containerRef.value.clientHeight
}

onMounted(() => {
  _initResize()
  // sentinel 在模板渲染后才存在
  nextTick(_initObserver)
})

onBeforeUnmount(() => {
  _io?.disconnect()
  _ro?.disconnect()
})

// 切换文件夹后重置滚动位置、重新观测哨兵
watch(() => mailStore.selectedFolder, async () => {
  scrollTop.value = 0
  if (containerRef.value) containerRef.value.scrollTop = 0
  await nextTick()
  _initObserver()
})

// 邮件列表首次填充后重新观测（哨兵此时才出现在 DOM）
watch(() => mailStore.emails.length, (newLen, oldLen) => {
  if (oldLen === 0 && newLen > 0) nextTick(_initObserver)
})

// ── 操作 ─────────────────────────────────────────────────────────────────
async function reload() {
  const prevTopKey = mailStore.emails[0]?.key ?? null
  await mailStore.refreshEmails()
  refreshStore.markRefreshed()

  // 有新邮件时平滑滚动到顶部，让用户看到动画
  const newTopKey = mailStore.emails[0]?.key ?? null
  if (newTopKey && newTopKey !== prevTopKey && containerRef.value) {
    containerRef.value.scrollTo({ top: 0, behavior: 'smooth' })
    scrollTop.value = 0
  }
  await nextTick()
  _initObserver()
}

async function openEmail(mail) {
  await mailStore.fetchEmailBody(mail.key)
}

// ── 格式化 ──────────────────────────────────────────────────────────────
function shortSender(from) {
  if (!from) return '（未知）'
  const match = from.match(/^"?([^"<]+)"?\s*</)
  if (match) return match[1].trim()
  return from.length > 28 ? from.slice(0, 28) + '…' : from
}

// 硬编码中文星期，完全不依赖 Intl，杜绝出现英文 Tuesday 等问题
const CN_WEEKDAY = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/**
 * 将 ISO 日期字符串格式化为人性化展示：
 * - 今天           → HH:MM
 * - 最近 6 天内   → 周X
 * - 今年之内       → M月D日
 * - 更早           → YYYY年M月D日
 *
 * 全部基于浏览器本地时区（d.getFullYear/Month/Date/getDay 均为本地时间），
 * 并用整天差（local midnight to local midnight）避免跨午夜误判。
 */
function formatDate(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  if (isNaN(d.getTime())) return _fallbackDate(isoStr)

  const now = new Date()
  // 取本地零点，消除时分秒干扰，得到精确的"相差几天"
  const todayMid  = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const emailMid  = new Date(d.getFullYear(),   d.getMonth(),   d.getDate())
  const daysDiff  = Math.round((todayMid - emailMid) / 86400000)

  if (daysDiff === 0) {
    // 今天：显示时分
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    return `${hh}:${mm}`
  }
  if (daysDiff >= 1 && daysDiff <= 6) {
    // 最近一周内：显示中文星期（hardcoded，不依赖 Intl）
    return CN_WEEKDAY[d.getDay()]
  }
  if (d.getFullYear() === now.getFullYear()) {
    // 今年：M月D日
    return `${d.getMonth() + 1}月${d.getDate()}日`
  }
  // 更早：年月日
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
}

/** 从原始字符串中提取可读日期部分，避免显示 "Invalid Date" */
function _fallbackDate(raw) {
  if (!raw) return ''
  const m1 = raw.match(/(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})/i)
  if (m1) return `${m1[3]}/${m1[2]}/${m1[1].padStart(2, '0')}`
  const m2 = raw.match(/(\d{4}-\d{2}-\d{2})/)
  if (m2) return m2[1]
  return raw.slice(0, 10)
}
</script>

<style scoped>
.email-list-pane {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  background: var(--bg);
  overflow: hidden;
}

/* 头部 */
.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.list-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.count-badge {
  font-size: 10px;
  padding: 1px 7px;
  background: rgba(99,102,241,.18);
  color: var(--accent-light);
  border-radius: 999px;
  font-weight: 500;
}
.icon-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 5px;
  border-radius: 5px;
  display: flex;
  transition: color .12s;
}
.icon-btn:hover:not(:disabled) { color: var(--text-primary); }
.icon-btn:disabled { opacity: .4; cursor: not-allowed; }

/* 滚动体 */
.list-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  contain: strict;           /* 开启渲染隔离，提升滚动性能 */
}

/* 状态占位 */
.state-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: 200px;
  font-size: 13px;
  color: var(--text-muted);
}
.state-center.error { color: #f87171; }
.state-center.muted { color: var(--text-muted); }

/* 邮件行 —— 固定高度是虚拟滚动的关键 */
.email-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  height: 76px;                 /* 与 JS ROW_HEIGHT 保持一致 */
  padding: 10px 10px 10px 8px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background .1s;
  overflow: hidden;
  box-sizing: border-box;
  will-change: transform;       /* 提示浏览器此元素会频繁变换 */
}
.email-row:hover       { background: var(--bg-card); }
.email-row.is-selected { background: rgba(99,102,241,.12); }

/* ── 亮色未读（完全未处理：本 session 第一次进入文件夹） */
.email-row.is-unread-new .row-from    { font-weight: 700; color: var(--text-primary); }
.email-row.is-unread-new .row-subject { font-weight: 700; color: var(--accent-light); }
.email-row.is-unread-new .row-preview { color: var(--text-secondary); }

/* ── 灰色未读（看过列表但未读：曾离开再回来） */
.email-row.is-unread-seen .row-from    { font-weight: 600; color: var(--text-secondary); }
.email-row.is-unread-seen .row-subject { font-weight: 600; color: var(--text-secondary); }

/* 已读/未读指示点 */
.row-dot-col { width: 8px; flex-shrink: 0; padding-top: 4px; }
.unread-dot {
  display: block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: transparent;
  transition: background .15s;
}
/* 亮色点 */
.unread-dot.dot-new  { background: var(--accent); }
/* 灰色点 */
.unread-dot.dot-seen { background: var(--text-muted); opacity: 0.55; }

/* 行内容 */
.row-body { flex: 1; min-width: 0; }
.row-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 4px;
}
.row-from {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}
.row-date {
  font-size: 10px;
  color: var(--text-muted);
  flex-shrink: 0;
  white-space: nowrap;
}
.row-subject {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}
.row-preview {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

/* 标记图标 */
.row-flags {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-end;
  flex-shrink: 0;
  font-size: 11px;
}
.replied-icon { color: var(--accent-light); font-size: 12px; }

/* 加载中提示 */
.load-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  font-size: 12px;
  color: var(--text-muted);
}
.list-end {
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
  padding: 14px;
}

/* 加载动画 */
.spinner {
  width: 24px; height: 24px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
.spinner-sm {
  width: 14px; height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.spinning { animation: spin .7s linear infinite; }

/* ── 新邮件滑入动画 ── */
@keyframes emailSlideIn {
  0% {
    opacity: 0;
    transform: translateY(-10px);
    background-color: rgba(99, 102, 241, 0.12);
  }
  40% {
    opacity: 1;
    transform: translateY(0);
    background-color: rgba(99, 102, 241, 0.10);
  }
  100% {
    background-color: transparent;
  }
}

.email-row.is-new {
  animation: emailSlideIn 0.45s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

/* 多封新邮件时，按索引错开出现，形成瀑布效果 */
.email-row.is-new:nth-child(2)  { animation-delay: 0.04s; }
.email-row.is-new:nth-child(3)  { animation-delay: 0.08s; }
.email-row.is-new:nth-child(4)  { animation-delay: 0.12s; }
.email-row.is-new:nth-child(5)  { animation-delay: 0.16s; }
</style>
