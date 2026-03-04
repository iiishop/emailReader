<template>
  <Teleport to="body">
    <Transition name="panel-fade">
      <div
        v-if="assistant.visible"
        class="ai-panel"
        :class="{ minimized: assistant.minimized }"
        :style="panelStyle"
        ref="panelRef"
      >
        <!-- ── 标题栏（可拖拽）── -->
        <div
          class="panel-header"
          @mousedown="startDrag"
          @touchstart.passive="startDragTouch"
        >
          <div class="panel-title">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-1H1a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 12 2z"/>
            </svg>
            AI 邮件助手
            <span v-if="assistant.thinking" class="thinking-badge">
              <span class="dot-flash"></span>
              <span class="dot-flash" style="animation-delay:.15s"></span>
              <span class="dot-flash" style="animation-delay:.3s"></span>
            </span>
          </div>
          <div class="panel-actions">
            <button class="hdr-btn hdr-btn-extract" @click.stop="onTriggerExtract()" title="重新提取工作台事件与简报" v-if="settings.isConfigured" :disabled="dash.isExtracting">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ spinning: dash.isExtracting }"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              <span class="hdr-btn-label">重新提取</span>
            </button>
            <button class="hdr-btn" @click.stop="assistant.clearChat()" title="清空对话" v-if="assistant.messages.length">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
              </svg>
            </button>
            <button class="hdr-btn" @click.stop="assistant.minimize()" :title="assistant.minimized ? '展开' : '最小化'">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <line v-if="!assistant.minimized" x1="5" y1="12" x2="19" y2="12"/>
                <polyline v-else points="18 15 12 9 6 15"/>
              </svg>
            </button>
            <button class="hdr-btn close" @click.stop="assistant.close()" title="关闭">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- ── 内容区（最小化时隐藏）── -->
        <template v-if="!assistant.minimized">
          <!-- 语法提示条 -->
          <div v-if="showSyntaxHint" class="syntax-hint">
            <div class="syntax-hint-title">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              # 引用语法
              <button class="link-btn" @click="showSyntaxHint = false">收起</button>
            </div>
            <div class="syntax-examples">
              <code>#email@host.com/INBOX</code> 指定文件夹<br>
              <code>#email@host.com:7d</code> 最近 7 天<br>
              <code>#email@host.com[发件人]</code> 按发件人筛选<br>
              <code>#email@host.com~关键词</code> 按主题模糊匹配<br>
              <code>#email@host.com!unread</code> 仅未读邮件<br>
              <code>#email@host.com/INBOX>"主题"</code> 精确引用单封<br>
              <code>#email@host.com/INBOX:30d[boss]</code> 组合使用
            </div>
          </div>

          <!-- 消息列表 -->
          <div class="chat-messages" ref="messagesEl">
            <!-- 空状态 -->
            <div v-if="assistant.messages.length === 0" class="chat-empty">
              <div class="empty-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
              </div>
              <p class="empty-title">开始对话</p>
              <p class="empty-sub">
                用 <code>#邮箱/文件夹:7d</code> 批量引用，<br>
                用 <code>#邮箱/文件夹>"主题"</code> 精确引用单封，<br>
                或直接提问
              </p>
              <button class="syntax-toggle-btn" @click="showSyntaxHint = true" v-if="!showSyntaxHint">
                查看引用语法 →
              </button>
            </div>

            <!-- 消息气泡 -->
            <template v-else>
              <div
                v-for="msg in assistant.messages"
                :key="msg.id"
                class="chat-msg"
                :class="msg.role"
              >
                <!-- 状态/进度消息 -->
                <div v-if="msg.role === 'status'" class="status-msg" :class="msg.phase">
                  <svg v-if="msg.phase === 'resolving' || msg.phase === 'screening' || msg.phase === 'loading'"
                    width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" class="spin-icon">
                    <polyline points="23 4 23 10 17 10"/>
                    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                  </svg>
                  <svg v-else-if="msg.phase === 'info'" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                  <svg v-else-if="msg.phase === 'warn'" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  {{ msg.content }}
                </div>

                <!-- 普通消息 -->
                <template v-else>
                  <div class="msg-avatar" :class="msg.role">
                    <template v-if="msg.role === 'user'">你</template>
                    <template v-else>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-1H1a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 12 2z"/>
                      </svg>
                    </template>
                  </div>
                  <div class="msg-bubble" :class="msg.role">
                    <!-- 用户消息：高亮 # 引用 -->
                    <div v-if="msg.role === 'user'" class="msg-content" v-html="highlightRefs(msg.content)"></div>
                    <!-- AI 消息：渲染 Markdown -->
                    <div v-else class="msg-content" v-html="renderMd(msg.content)"></div>
                    <div v-if="msg.usage" class="msg-usage">{{ msg.usage.total_tokens ?? '?' }} tokens</div>
                  </div>
                </template>
              </div>

              <!-- 思考动画 -->
              <div v-if="assistant.thinking" class="chat-msg assistant">
                <div class="msg-avatar assistant">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-1H1a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73A2 2 0 0 1 12 2z"/>
                  </svg>
                </div>
                <div class="msg-bubble assistant thinking">
                  <span class="dot-flash"></span>
                  <span class="dot-flash" style="animation-delay:.2s"></span>
                  <span class="dot-flash" style="animation-delay:.4s"></span>
                </div>
              </div>
            </template>
          </div>

          <!-- 输入区 -->
          <div class="chat-input-area">
            <!-- # 引用自动补全下拉 -->
            <div v-if="autocomplete.show" class="autocomplete-dropdown" ref="autocompleteEl">
              <div
                v-for="(item, i) in autocomplete.items"
                :key="item.value"
                class="ac-item"
                :class="{ active: i === autocomplete.index }"
                @mousedown.prevent="applyAutocomplete(item)"
              >
                <span class="ac-icon">{{ item.icon }}</span>
                <span class="ac-label">{{ item.label }}</span>
                <span class="ac-sub">{{ item.sub }}</span>
              </div>
            </div>

            <div class="input-wrap" :class="{ focused: inputFocused }">
              <textarea
                ref="inputEl"
                v-model="inputText"
                class="chat-input"
                :placeholder="settings.isConfigured ? '输入问题，用 # 引用邮件…' : '请先在设置中配置 AI'"
                :disabled="!settings.isConfigured || assistant.thinking"
                rows="1"
                @keydown="onKeydown"
                @input="onInput"
                @focus="inputFocused = true"
                @blur="inputFocused = false; setTimeout(() => autocomplete.show = false, 150)"
              ></textarea>
              <button
                class="send-btn"
                :disabled="!inputText.trim() || !settings.isConfigured || assistant.thinking"
                @click="send"
                title="发送 (Enter)"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
              </button>
            </div>
            <div class="input-hint">Enter 发送 · Shift+Enter 换行 · # 引用邮件</div>
          </div>
        </template>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick, reactive, onMounted, onUnmounted } from 'vue'
import { marked } from 'marked'
import { useAssistantStore, parseRefs } from '../stores/assistant.js'
import { useSettingsStore }  from '../stores/settings.js'
import { useAccountsStore }  from '../stores/accounts.js'
import { useMailStore }         from '../stores/mail.js'
import { useDashboardDataStore } from '../stores/dashboardData.js'

marked.setOptions({ breaks: true, gfm: true })

const assistant = useAssistantStore()
const settings  = useSettingsStore()
const accounts  = useAccountsStore()
const mailStore = useMailStore()
const dash      = useDashboardDataStore()

function onTriggerExtract() {
  dash.triggerExtract()
}

// ── 面板位置 ──────────────────────────────────────────────────────────────────
const panelRef   = ref(null)
const DEFAULT_W  = 380
const DEFAULT_H  = 560

const pos = ref(assistant.position.x !== null
  ? { x: assistant.position.x, y: assistant.position.y }
  : { x: window.innerWidth - DEFAULT_W - 24, y: window.innerHeight - DEFAULT_H - 24 }
)

const panelStyle = computed(() => ({
  left:   `${Math.max(0, Math.min(pos.value.x, window.innerWidth - DEFAULT_W))}px`,
  top:    `${Math.max(0, Math.min(pos.value.y, window.innerHeight - 48))}px`,
  width:  `${DEFAULT_W}px`,
}))

// ── 拖拽 ──────────────────────────────────────────────────────────────────────
let _drag = null

function startDrag(e) {
  if (e.button !== 0) return
  _drag = { startX: e.clientX - pos.value.x, startY: e.clientY - pos.value.y }
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', stopDrag)
}
function startDragTouch(e) {
  const t = e.touches[0]
  _drag = { startX: t.clientX - pos.value.x, startY: t.clientY - pos.value.y }
  window.addEventListener('touchmove', onDragMoveTouch, { passive: false })
  window.addEventListener('touchend', stopDrag)
}
function onDragMove(e) {
  if (!_drag) return
  pos.value = { x: e.clientX - _drag.startX, y: e.clientY - _drag.startY }
}
function onDragMoveTouch(e) {
  if (!_drag) return
  e.preventDefault()
  const t = e.touches[0]
  pos.value = { x: t.clientX - _drag.startX, y: t.clientY - _drag.startY }
}
function stopDrag() {
  _drag = null
  assistant.savePosition(pos.value.x, pos.value.y)
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', stopDrag)
  window.removeEventListener('touchmove', onDragMoveTouch)
  window.removeEventListener('touchend', stopDrag)
}

// ── 监听来自 Dashboard 的预填事件 ────────────────────────────────────────────
function onPrefill(e) {
  appendText(e.detail || '')
}
onMounted(()  => window.addEventListener('assistant:prefill', onPrefill))
onUnmounted(() => window.removeEventListener('assistant:prefill', onPrefill))

// ── 消息列表自动滚底 ──────────────────────────────────────────────────────────
const messagesEl = ref(null)
watch(() => assistant.messages.length, async () => {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
})

// ── 语法提示 ──────────────────────────────────────────────────────────────────
const showSyntaxHint = ref(false)

// ── 输入框 ────────────────────────────────────────────────────────────────────
const inputEl     = ref(null)
const inputText   = ref('')
const inputFocused = ref(false)

// 暴露给外部（如 EmailViewer 的"问 AI"按钮）
defineExpose({ appendText })

function appendText(text) {
  inputText.value = (inputText.value + text).trimStart()
  nextTick(() => {
    if (inputEl.value) {
      autoResize()
      inputEl.value.focus()
      const len = inputText.value.length
      inputEl.value.setSelectionRange(len, len)
    }
  })
}

function autoResize() {
  if (!inputEl.value) return
  inputEl.value.style.height = 'auto'
  inputEl.value.style.height = Math.min(inputEl.value.scrollHeight, 140) + 'px'
}

async function send() {
  const text = inputText.value.trim()
  if (!text || !settings.isConfigured || assistant.thinking) return
  inputText.value = ''
  await nextTick()
  if (inputEl.value) inputEl.value.style.height = 'auto'
  await assistant.sendMessage(text)
}

function onKeydown(e) {
  // 自动补全导航
  if (autocomplete.show) {
    if (e.key === 'ArrowDown') { e.preventDefault(); autocomplete.index = Math.min(autocomplete.index + 1, autocomplete.items.length - 1); return }
    if (e.key === 'ArrowUp')   { e.preventDefault(); autocomplete.index = Math.max(autocomplete.index - 1, 0); return }
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault()
      if (autocomplete.items[autocomplete.index]) applyAutocomplete(autocomplete.items[autocomplete.index])
      return
    }
    if (e.key === 'Escape') { autocomplete.show = false; return }
  }

  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

// ── # 自动补全 ────────────────────────────────────────────────────────────────
const autocomplete = reactive({
  show:  false,
  items: [],
  index: 0,
  triggerPos: 0,  // # 符号在文本中的位置
})

function onInput() {
  autoResize()
  _updateAutocomplete()
}

function _updateAutocomplete() {
  const text   = inputText.value
  const cursor = inputEl.value?.selectionStart ?? text.length

  // 找到光标前最近的 # 符号
  const before  = text.slice(0, cursor)
  const hashIdx = before.lastIndexOf('#')
  if (hashIdx === -1) { autocomplete.show = false; return }

  const fragment = before.slice(hashIdx + 1)  // # 后面到光标的内容
  // 如果 fragment 包含空格，说明引用已结束
  if (/\s/.test(fragment)) { autocomplete.show = false; return }

  autocomplete.triggerPos = hashIdx

  // 根据 fragment 生成补全项
  const items = _buildAutocompleteItems(fragment)
  if (!items.length) { autocomplete.show = false; return }

  autocomplete.items = items
  autocomplete.index = 0
  autocomplete.show  = true
}

function _buildAutocompleteItems(fragment) {
  const items = []
  const frag  = fragment.toLowerCase()

  // 阶段 1：匹配邮箱账号
  const matchedAccounts = accounts.accounts.filter(a =>
    a.email.toLowerCase().includes(frag) || frag === ''
  ).slice(0, 6)

  for (const acc of matchedAccounts) {
    // 基础：整个账号
    items.push({
      value: acc.email,
      label: acc.email,
      sub:   '所有邮件（受天数限制）',
      icon:  '📬',
      suffix: ' ',
    })

    // 如果 fragment 已经包含完整邮箱，提供文件夹/修饰符补全
    if (frag.startsWith(acc.email.toLowerCase())) {
      const afterEmail = fragment.slice(acc.email.length)

      // 文件夹补全
      const folders = mailStore.foldersByAccount.get(acc.account_id) ?? []
      for (const f of folders.slice(0, 4)) {
        items.push({
          value: `${acc.email}/${f.name}`,
          label: `${acc.email}/${f.name}`,
          sub:   '指定文件夹',
          icon:  '📁',
          suffix: ' ',
        })
      }

      // 天数修饰符
      for (const d of ['1d', '3d', '7d', '14d', '30d', 'all']) {
        items.push({
          value: `${acc.email}:${d}`,
          label: `${acc.email}:${d}`,
          sub:   d === 'all' ? '全部邮件' : `最近 ${d}`,
          icon:  '📅',
          suffix: ' ',
        })
      }

      // 未读修饰符
      items.push({
        value: `${acc.email}!unread`,
        label: `${acc.email}!unread`,
        sub:   '仅未读邮件',
        icon:  '🔴',
        suffix: ' ',
      })

      // 精确引用语法提示
      items.push({
        value: `${acc.email}/INBOX>"`,
        label: `${acc.email}/INBOX>"主题"`,
        sub:   '精确引用单封邮件',
        icon:  '📌',
        suffix: '',
      })
    }
  }

  return items.slice(0, 8)
}

function applyAutocomplete(item) {
  const text   = inputText.value
  const cursor = inputEl.value?.selectionStart ?? text.length
  const before = text.slice(0, autocomplete.triggerPos)
  const after  = text.slice(cursor)
  inputText.value = `${before}#${item.value}${item.suffix}${after}`
  autocomplete.show = false
  nextTick(() => {
    const newPos = before.length + 1 + item.value.length + item.suffix.length
    inputEl.value?.setSelectionRange(newPos, newPos)
    inputEl.value?.focus()
    autoResize()
  })
}

// ── 渲染工具 ──────────────────────────────────────────────────────────────────
function renderMd(text) {
  try { return marked.parse(text || '') }
  catch { return text || '' }
}

// 高亮用户消息中的 # 引用
function highlightRefs(text) {
  if (!text) return ''
  // 先 HTML 转义
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // 替换 # 引用为高亮 span
  return escaped.replace(
    /#([\w.+-]+@[\w.-]+\.[a-z]{2,}[^\s,，。？?！!]*)/gi,
    '<span class="ref-tag">#$1</span>'
  )
}
</script>

<style scoped>
/* ── 浮动面板 ── */
.ai-panel {
  position: fixed;
  z-index: 9000;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 20px 60px rgba(0,0,0,.22), 0 4px 16px rgba(0,0,0,.12);
  overflow: hidden;
  /* 最小化时只显示标题栏 */
  max-height: 560px;
  transition: max-height .25s cubic-bezier(.4,0,.2,1), box-shadow .15s;
  user-select: none;
}
.ai-panel.minimized {
  max-height: 44px;
}

/* ── 过渡动画 ── */
.panel-fade-enter-active { transition: opacity .2s, transform .2s cubic-bezier(.34,1.56,.64,1); }
.panel-fade-leave-active { transition: opacity .15s, transform .15s ease-in; }
.panel-fade-enter-from   { opacity: 0; transform: scale(.92) translateY(12px); }
.panel-fade-leave-to     { opacity: 0; transform: scale(.94) translateY(8px); }

/* ── 标题栏 ── */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px 0 14px;
  height: 44px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  cursor: grab;
  flex-shrink: 0;
}
.panel-header:active { cursor: grabbing; }

.panel-title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  user-select: none;
}

.thinking-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 2px;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.hdr-btn {
  width: 26px; height: 26px;
  display: flex; align-items: center; justify-content: center;
  border: none; border-radius: 6px;
  background: transparent; color: var(--text-muted);
  cursor: pointer;
  transition: background .1s, color .1s;
}
.hdr-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.hdr-btn.close:hover { background: rgba(239,68,68,.12); color: #ef4444; }
.hdr-btn-extract { min-width: auto; padding: 0 6px; }
.hdr-btn-extract:disabled { opacity: .6; cursor: not-allowed; }
.hdr-btn-label { margin-left: 3px; font-size: 11px; white-space: nowrap; }
.hdr-btn .spinning { animation: spin 1s linear infinite; }

/* ── 语法提示 ── */
.syntax-hint {
  padding: 8px 12px;
  background: rgba(99,102,241,.06);
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  flex-shrink: 0;
}
.syntax-hint-title {
  display: flex;
  align-items: center;
  gap: 5px;
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 5px;
}
.syntax-examples {
  color: var(--text-secondary);
  line-height: 1.9;
}
.syntax-examples code {
  background: rgba(99,102,241,.12);
  color: var(--accent);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 10.5px;
  font-family: monospace;
}
.link-btn {
  margin-left: auto;
  border: none; background: transparent;
  color: var(--text-muted); font-size: 11px;
  cursor: pointer; text-decoration: underline;
}

/* ── 消息列表 ── */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

/* 空状态 */
.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  text-align: center;
}
.empty-icon {
  width: 52px; height: 52px;
  border-radius: 14px;
  background: var(--bg);
  border: 1px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted);
}
.empty-title { font-size: 14px; font-weight: 600; color: var(--text-primary); margin: 0; }
.empty-sub   { font-size: 12px; color: var(--text-muted); line-height: 1.6; margin: 0; }
.empty-sub code {
  background: rgba(99,102,241,.1);
  color: var(--accent);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 11px;
}
.syntax-toggle-btn {
  margin-top: 4px;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--accent);
  font-size: 11px;
  cursor: pointer;
  transition: background .1s;
}
.syntax-toggle-btn:hover { background: rgba(99,102,241,.08); }

/* 状态消息 */
.chat-msg.status { justify-content: center; }
.status-msg {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  max-width: 90%;
  text-align: center;
}
.status-msg.resolving,
.status-msg.screening,
.status-msg.loading {
  background: rgba(99,102,241,.1);
  color: var(--accent);
  border: 1px solid rgba(99,102,241,.2);
}
.status-msg.info {
  background: rgba(34,197,94,.1);
  color: #16a34a;
  border: 1px solid rgba(34,197,94,.2);
}
[data-theme="dark"] .status-msg.info { color: #4ade80; }
.status-msg.warn {
  background: rgba(245,158,11,.1);
  color: #d97706;
  border: 1px solid rgba(245,158,11,.2);
}
[data-theme="dark"] .status-msg.warn { color: #fbbf24; }

@keyframes spin { to { transform: rotate(360deg); } }
.spin-icon { animation: spin .8s linear infinite; flex-shrink: 0; }

/* 普通消息 */
.chat-msg {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.chat-msg.user { flex-direction: row-reverse; }

.msg-avatar {
  width: 26px; height: 26px;
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 700;
  flex-shrink: 0;
}
.msg-avatar.user      { background: var(--accent); color: #fff; }
.msg-avatar.assistant { background: var(--bg); border: 1px solid var(--border); color: var(--accent); }

.msg-bubble {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.6;
}
.msg-bubble.user {
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 3px;
}
.msg-bubble.assistant {
  background: var(--bg);
  border: 1px solid var(--border);
  border-bottom-left-radius: 3px;
  color: var(--text-primary);
}
.msg-bubble.thinking {
  display: flex; align-items: center; gap: 5px;
  padding: 10px 14px;
}

/* # 引用高亮 */
:deep(.ref-tag) {
  display: inline-block;
  background: rgba(255,255,255,.2);
  border-radius: 4px;
  padding: 0 4px;
  font-family: monospace;
  font-size: .9em;
}

.msg-usage {
  margin-top: 4px;
  font-size: 10px;
  color: var(--text-muted);
  opacity: .6;
}

/* Markdown */
.msg-content :deep(p)  { margin: 0 0 6px; }
.msg-content :deep(p:last-child) { margin-bottom: 0; }
.msg-content :deep(ul),
.msg-content :deep(ol) { margin: 4px 0; padding-left: 18px; }
.msg-content :deep(li) { margin: 2px 0; }
.msg-content :deep(code) {
  background: rgba(0,0,0,.08);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: .88em;
  font-family: monospace;
}
.msg-bubble.user .msg-content :deep(code) { background: rgba(255,255,255,.2); }
.msg-content :deep(pre) {
  background: rgba(0,0,0,.06);
  padding: 8px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 6px 0;
}
.msg-content :deep(blockquote) {
  border-left: 3px solid var(--accent);
  margin: 6px 0;
  padding: 3px 8px;
  color: var(--text-secondary);
}

/* 思考动画 */
@keyframes dotBlink {
  0%, 80%, 100% { opacity: .2; transform: scale(.8); }
  40%           { opacity: 1;  transform: scale(1.1); }
}
.dot-flash {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: dotBlink 1.4s ease-in-out infinite;
}

/* ── 输入区 ── */
.chat-input-area {
  border-top: 1px solid var(--border);
  padding: 8px 10px;
  background: var(--bg-card);
  flex-shrink: 0;
  position: relative;
}

.autocomplete-dropdown {
  position: absolute;
  bottom: 100%;
  left: 10px; right: 10px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0,0,0,.15);
  overflow: hidden;
  z-index: 10;
  margin-bottom: 4px;
}
.ac-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  cursor: pointer;
  transition: background .08s;
}
.ac-item:hover, .ac-item.active { background: var(--bg-hover); }
.ac-icon  { font-size: 13px; flex-shrink: 0; }
.ac-label { font-size: 12px; color: var(--text-primary); font-family: monospace; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ac-sub   { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }

.input-wrap {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 6px 6px 6px 10px;
  transition: border-color .15s;
}
.input-wrap.focused { border-color: var(--accent); }

.chat-input {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.5;
  resize: none;
  outline: none;
  min-height: 20px;
  max-height: 140px;
  font-family: inherit;
}
.chat-input::placeholder { color: var(--text-muted); }
.chat-input:disabled { cursor: not-allowed; }

.send-btn {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border: none; border-radius: 7px;
  background: var(--accent); color: #fff;
  cursor: pointer; flex-shrink: 0;
  transition: opacity .12s;
}
.send-btn:disabled { opacity: .4; cursor: not-allowed; }
.send-btn:hover:not(:disabled) { opacity: .85; }

.input-hint {
  margin-top: 4px;
  font-size: 10px;
  color: var(--text-muted);
  text-align: center;
}

/* ── 滚动条 ── */
.chat-messages::-webkit-scrollbar { width: 3px; }
.chat-messages::-webkit-scrollbar-track { background: transparent; }
.chat-messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
