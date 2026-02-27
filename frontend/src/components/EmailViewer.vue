<template>
  <div class="email-viewer">
    <!-- 回复链（组件内部自行判断是否有 ≥2 封同主题邮件） -->
    <EmailThreadGraph
      v-if="mailStore.selectedEmail"
      :emails="mailStore.emails"
      :selected-key="mailStore.selectedEmail?.key ?? ''"
      @select-email="onThreadSelect"
    />

    <!-- 空状态 -->
    <div v-if="!mailStore.selectedEmail && !mailStore.emailBodyLoading" class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
        <rect x="2" y="3" width="20" height="14" rx="2"/>
        <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
      </svg>
      <p>选择一封邮件以阅读</p>
    </div>

    <!-- 加载中 -->
    <div v-else-if="mailStore.emailBodyLoading" class="empty-state">
      <div class="spinner"></div>
      <p>加载中…</p>
    </div>

    <!-- 正文 -->
    <template v-else-if="mailStore.selectedEmail">
      <div class="viewer-header">
        <h1 class="subject">{{ mailStore.selectedEmail.subject || '（无主题）' }}</h1>
        <div class="meta-row">
          <div class="meta-group">
            <span class="meta-label">发件人</span>
            <span class="meta-val">{{ mailStore.selectedEmail.from }}</span>
          </div>
          <div class="meta-group">
            <span class="meta-label">收件人</span>
            <span class="meta-val">{{ mailStore.selectedEmail.to }}</span>
          </div>
          <div v-if="mailStore.selectedEmail.cc" class="meta-group">
            <span class="meta-label">抄送</span>
            <span class="meta-val">{{ mailStore.selectedEmail.cc }}</span>
          </div>
          <div class="meta-group">
            <span class="meta-label">时间</span>
            <span class="meta-val">{{ formatFullDate(mailStore.selectedEmail.date) }}</span>
          </div>
        </div>
        <div class="flag-row">
          <span v-if="mailStore.selectedEmail.is_starred" class="flag-tag star">⭐ 星标</span>
          <span v-if="mailStore.selectedEmail.has_attachment" class="flag-tag attach">📎 含附件</span>
          <span v-if="mailStore.selectedEmail.is_replied" class="flag-tag replied">↩ 已回复</span>
          <!-- 问 AI 按钮 -->
          <button class="ask-ai-btn" @click="askAI" title="在 AI 助手中分析这封邮件">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            问 AI
          </button>
        </div>
      </div>

      <div class="viewer-body">
        <!--
          HTML 邮件：用 <iframe srcdoc> 渲染，与应用主题完全隔离。
          邮件自带的 CSS（通常是黑字白底）完全保留，不被应用深色主题污染。
          sandbox 去掉 allow-scripts，阻止邮件内 JavaScript 执行。
        -->
        <iframe
          v-if="mailStore.selectedEmail.text_html"
          ref="iframeRef"
          class="email-iframe"
          :srcdoc="iframeSrcdoc"
          sandbox="allow-same-origin allow-popups"
          @load="onIframeLoad"
        ></iframe>

        <!-- 纯文本邮件 -->
        <pre
          v-else-if="mailStore.selectedEmail.text_plain"
          class="plain-body"
        >{{ mailStore.selectedEmail.text_plain }}</pre>

        <div v-else class="empty-state" style="height:200px">（邮件正文为空）</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useMailStore }       from '../stores/mail.js'
import { useAccountsStore }   from '../stores/accounts.js'
import { useAssistantStore }  from '../stores/assistant.js'
import EmailThreadGraph       from './EmailThreadGraph.vue'

const mailStore      = useMailStore()
const accountsStore  = useAccountsStore()
const assistantStore = useAssistantStore()

// 从回复链图点击跳转到指定邮件
function onThreadSelect(key) {
  mailStore.fetchEmailBody(key)
}

function askAI() {
  const email  = mailStore.selectedEmail
  const folder = mailStore.selectedFolder
  if (!email || !folder) return

  const account = accountsStore.accounts.find(a => a.account_id === folder.account_id)
  const emailAddr = account?.email || folder.account_id
  const folderName = folder.name || folder.folder_id

  assistantStore.open()
  nextTick(() => {
    // 用精确主题语法（>"主题"）直接定位这封邮件，跳过 RAG 筛选
    const subject = (email.subject || '').replace(/"/g, '\\"')
    const text = `#${emailAddr}/${folderName}>"${subject}" `
    window.dispatchEvent(new CustomEvent('assistant:prefill', { detail: text }))
  })
}
const iframeRef = ref(null)

function formatFullDate(isoStr) {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    if (isNaN(d.getTime())) return isoStr  // 显示原始字符串，总比 "Invalid Date" 好
    return d.toLocaleString('zh-CN', {
      year: 'numeric', month: 'long', day: 'numeric',
      weekday: 'long', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return isoStr
  }
}

/**
 * 把邮件 HTML 包装成完整的 srcdoc 文档：
 * - 注入基础安全过滤（去掉 <script>、on* 事件）
 * - 若邮件本身带有 <html> 结构则直接使用
 * - 若只是 HTML 片段则包上最小外壳（白底黑字，移动端自适应宽度）
 *
 * 邮件内容与应用主题完全隔离，深色/浅色切换不影响邮件文字显示。
 */
const iframeSrcdoc = computed(() => {
  const raw = mailStore.selectedEmail?.text_html ?? ''
  const sanitized = raw
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/\son\w+\s*=\s*"[^"]*"/gi, '')
    .replace(/\son\w+\s*=\s*'[^']*'/gi, '')
    .replace(/\son\w+\s*=\s*[^\s>]+/gi, '')

  // 邮件本身已有完整 HTML 文档结构
  if (/<html[\s>]/i.test(sanitized)) return sanitized

  // 纯片段：包装最小外壳
  return `<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {
    margin: 0;
    padding: 12px 16px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    font-size: 14px;
    line-height: 1.7;
    color: #1a1a1a;
    background: #ffffff;
    word-break: break-word;
  }
  img { max-width: 100%; height: auto; }
  a { color: #4f46e5; }
  blockquote { border-left: 3px solid #d1d5db; margin: 0; padding-left: 12px; color: #6b7280; }
  pre { white-space: pre-wrap; word-break: break-word; }
</style>
</head>
<body>${sanitized}</body>
</html>`
})

/**
 * iframe 加载完毕后自动撑高到内容高度，避免内部滚动条，
 * 让外层 .viewer-body 统一负责滚动。
 */
function onIframeLoad() {
  const frame = iframeRef.value
  if (!frame) return
  try {
    const doc = frame.contentDocument
    if (!doc) return
    // 等一帧让浏览器完成布局
    requestAnimationFrame(() => {
      const h = doc.documentElement.scrollHeight || doc.body?.scrollHeight || 400
      frame.style.height = h + 32 + 'px'
    })
  } catch {
    // 跨域时无法访问，给个保底高度
    frame.style.height = '600px'
  }
}

// 切换邮件时重置 iframe 高度
watch(() => mailStore.selectedEmail?.key, () => {
  if (iframeRef.value) iframeRef.value.style.height = '200px'
})
</script>

<style scoped>
.email-viewer {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg);
}

/* 空/加载状态 */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--text-muted);
  font-size: 13px;
}
.spinner {
  width: 28px; height: 28px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 邮件头 */
.viewer-header {
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--bg-card);
}
.subject {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.4;
  margin-bottom: 12px;
}
.meta-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.meta-group {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
}
.meta-label {
  flex-shrink: 0;
  width: 44px;
  color: var(--text-muted);
  text-align: right;
}
.meta-val {
  color: var(--text-secondary);
  word-break: break-all;
}
.flag-row {
  display: flex;
  gap: 6px;
  margin-top: 10px;
}
.flag-tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 999px;
}
.flag-tag.star    { background: rgba(245,158,11,.15); color: #d97706; }
.flag-tag.attach  { background: rgba(148,163,184,.1);  color: var(--text-secondary); }
.flag-tag.replied { background: rgba(99,102,241,.15);  color: var(--accent); }

.ask-ai-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(99,102,241,.4);
  background: rgba(99,102,241,.08);
  color: var(--accent);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  margin-left: auto;
  transition: background .12s, border-color .12s;
}
.ask-ai-btn:hover {
  background: rgba(99,102,241,.18);
  border-color: var(--accent);
}

/* 邮件正文容器 */
.viewer-body {
  flex: 1;
  overflow-y: auto;
  background: var(--bg);
}

/*
  HTML 邮件 iframe：
  - 宽度撑满，无边框
  - 高度由 onIframeLoad 动态设置
  - 内部白底黑字与应用主题完全隔离
*/
.email-iframe {
  display: block;
  width: 100%;
  height: 200px;   /* 初始值，加载后会自动撑高 */
  border: none;
  background: #ffffff;
}

/* 纯文本邮件 */
.plain-body {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  padding: 20px 24px;
}
</style>
