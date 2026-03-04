<template>
  <!-- 仅有 ≥2 封同主题邮件时才渲染 -->
  <div v-if="threadEmails.length >= 2 && show" class="thread-bar">
    <div class="thread-bar-hdr">
      <div class="thread-hdr-left">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
        </svg>
        <span>对话链 · {{ threadEmails.length }} 封</span>
      </div>
      <button class="thread-close-btn" @click="show = false">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </div>

    <!-- 横向节点滚动列表（不用 VueFlow，用纯 CSS 横排 + 箭头） -->
    <div class="thread-scroll" ref="scrollRef">
      <template v-for="(mail, i) in threadEmails" :key="mail.key">
        <div
          class="thread-node"
          :class="{ active: mail.key === selectedKey, unread: !mail.is_read }"
          @click="emit('select-email', mail.key)"
        >
          <div class="tn-bar" :class="{ active: mail.key === selectedKey, unread: !mail.is_read }"></div>
          <div class="tn-from">{{ shortFrom(mail.from ?? mail.sender) }}</div>
          <div class="tn-date">{{ shortDate(mail.date) }}</div>
          <div v-if="mail.key === selectedKey" class="tn-active-pip"></div>
        </div>
        <!-- 箭头连接符 -->
        <div v-if="i < threadEmails.length - 1" class="thread-arrow">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  emails:      { type: Array,  default: () => [] },
  selectedKey: { type: String, default: '' },
})
const emit = defineEmits(['select-email'])

const show      = ref(true)
const scrollRef = ref(null)

watch(() => props.selectedKey, () => {
  show.value = true
  // 选中新邮件时，让对应节点滚动到视口
  nextTick(() => {
    const el = scrollRef.value?.querySelector('.thread-node.active')
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
  })
})

function normalizeSubject(s) {
  if (!s) return ''
  return s.replace(/^(re|fwd?|aw|回复|转发):\s*/gi, '').trim().toLowerCase()
}

const currentEmail = computed(() =>
  props.emails.find(e => e.key === props.selectedKey)
)

const threadEmails = computed(() => {
  if (!currentEmail.value) return []
  const base = normalizeSubject(currentEmail.value.subject)
  if (!base) return []
  const thread = props.emails
    .filter(e => normalizeSubject(e.subject) === base)
    .sort((a, b) => (a.epoch_ms ?? 0) - (b.epoch_ms ?? 0))
  return thread.length >= 2 ? thread : []
})

function shortFrom(from) {
  if (!from) return '?'
  from = from.trim()
  if (from.length >= 2 && from[0] === '"' && from[from.length - 1] === '"') from = from.slice(1, -1).trim()
  const m = from.match(/^(.+?)\s*</) ?? from.match(/^([^@]+)/)
  const s = m ? m[1].trim() : from
  return s.length > 12 ? s.slice(0, 11) + '…' : s
}

function shortDate(dateStr) {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return ''
    const now = new Date()
    if (d.toDateString() === now.toDateString())
      return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
    return `${d.getMonth()+1}/${d.getDate()}`
  } catch { return '' }
}
</script>

<style scoped>
.thread-bar {
  flex-shrink: 0;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}

.thread-bar-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px;
  border-bottom: 1px solid var(--border-light);
}
.thread-hdr-left {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: .04em;
  text-transform: uppercase;
}
.thread-hdr-left svg { color: var(--accent); }

.thread-close-btn {
  width: 18px; height: 18px;
  display: flex; align-items: center; justify-content: center;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all .1s;
  flex-shrink: 0;
}
.thread-close-btn:hover { background: var(--bg-hover); color: var(--text-primary); }

/* 横向滚动容器 */
.thread-scroll {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 6px 10px;
  overflow-x: auto;
  overflow-y: hidden;
  scroll-behavior: smooth;
}
.thread-scroll::-webkit-scrollbar { height: 3px; }
.thread-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.thread-scroll::-webkit-scrollbar-track { background: transparent; }

/* 节点 */
.thread-node {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 1px;
  padding: 4px 8px 4px 10px;
  min-width: 88px;
  max-width: 120px;
  height: 44px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 7px;
  cursor: pointer;
  flex-shrink: 0;
  overflow: hidden;
  transition: all .14s;
}
.thread-node:hover {
  border-color: var(--accent);
  background: var(--accent-dim);
}
.thread-node.active {
  border-color: var(--accent);
  background: var(--accent-dim);
  box-shadow: 0 0 0 2px var(--accent-dim);
}

/* 左侧状态条 */
.tn-bar {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  border-radius: 7px 0 0 7px;
  background: var(--border);
  transition: background .12s;
}
.tn-bar.unread { background: var(--accent-light); }
.tn-bar.active { background: var(--accent); }

.tn-from {
  font-size: 10.5px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tn-date {
  font-size: 9px;
  color: var(--text-muted);
  white-space: nowrap;
}

/* 当前节点小圆点 */
.tn-active-pip {
  position: absolute;
  top: 4px; right: 4px;
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-dim);
}

/* 箭头 */
.thread-arrow {
  flex-shrink: 0;
  color: var(--border);
  display: flex;
  align-items: center;
  padding: 0 2px;
}
</style>
