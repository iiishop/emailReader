<template>
  <div class="account-card" :class="{ 'is-default': account.is_default }">
    <div class="card-left">
      <div class="provider-badge" :class="account.provider">
        <span class="provider-icon">{{ providerIcon }}</span>
      </div>
    </div>

    <div class="card-body">
      <div class="card-header">
        <span class="email">{{ account.email }}</span>
        <span v-if="account.is_default" class="badge default-badge">默认</span>
        <span class="badge protocol-badge">{{ account.protocol }}</span>
        <span v-if="account.ssl" class="badge ssl-badge">SSL</span>
      </div>

      <div class="card-meta">
        <span class="meta-item">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="2" y="3" width="20" height="14" rx="2"/>
            <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
          </svg>
          {{ account.hostname }}:{{ account.port }}
        </span>
        <span v-if="account.full_name" class="meta-item">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="8" r="4"/>
            <path d="M20 21a8 8 0 1 0-16 0"/>
          </svg>
          {{ account.full_name }}
        </span>
      </div>
    </div>

    <div class="card-right">
      <span class="provider-label">{{ providerLabel }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  account: {
    type: Object,
    required: true,
  },
})

const providerIcon = computed(() => {
  const icons = {
    gmail: 'G',
    outlook: 'O',
    '163': '网',
    qq: 'Q',
    yahoo: 'Y',
    icloud: '',
    imap: '✉',
  }
  return icons[props.account.provider] ?? '✉'
})

const providerLabel = computed(() => {
  const labels = {
    gmail: 'Gmail',
    outlook: 'Outlook / Exchange',
    '163': '163 网易邮箱',
    qq: 'QQ 邮箱',
    yahoo: 'Yahoo Mail',
    icloud: 'iCloud Mail',
    imap: 'IMAP',
  }
  return labels[props.account.provider] ?? 'IMAP'
})
</script>

<style scoped>
.account-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, transform 0.1s;
}

.account-card:hover {
  background: var(--bg-hover);
  border-color: var(--accent);
}

.account-card.is-default {
  border-color: var(--accent);
}

/* 左侧 provider 图标 */
.provider-badge {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  flex-shrink: 0;
}

.provider-badge.gmail    { background: rgba(234,67,53,.15);  color: var(--gmail); }
.provider-badge.outlook  { background: rgba(0,120,212,.15);  color: var(--outlook); }
.provider-badge\.163,
.provider-badge[class*="163"] { background: rgba(204,0,0,.15); color: var(--mail163); }
.provider-badge.qq       { background: rgba(18,183,245,.15); color: var(--qq); }
.provider-badge.imap,
.provider-badge.icloud   { background: rgba(99,102,241,.15); color: var(--accent-light); }

/* 中间内容 */
.card-body {
  flex: 1;
  min-width: 0;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.email {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.01em;
}

.badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 999px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.default-badge  { background: rgba(99,102,241,.2);  color: var(--accent-light); }
.protocol-badge { background: rgba(148,163,184,.1); color: var(--text-secondary); }
.ssl-badge      { background: rgba(34,197,94,.15);  color: var(--success); }

.card-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 4px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-muted);
}

/* 右侧 */
.card-right {
  flex-shrink: 0;
  text-align: right;
}

.provider-label {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
