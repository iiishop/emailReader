<template>
  <div class="contact-graph-wrap">
    <VueFlow
      v-if="nodes.length"
      :nodes="nodes"
      :edges="edges"
      :default-zoom="1"
      :min-zoom="0.3"
      :max-zoom="3"
      :fit-view-on-init="true"
      :nodes-draggable="true"
      :zoom-on-scroll="true"
      :pan-on-drag="true"
      class="contact-flow"
      @node-click="onNodeClick"
    >
      <Background pattern-color="var(--border-light)" :gap="20" :size="1" />
      <MiniMap
        class="contact-minimap"
        :node-stroke-color="n => n.data?.isCenter ? '#6366f1' : '#94a3b8'"
        :node-color="n => n.data?.isCenter ? '#6366f1' : (n.data?.recent ? '#22c55e' : 'var(--bg-card)')"
        mask-color="rgba(0,0,0,0.06)"
      />
      <Controls :show-interactive="false" />

      <template #node-contact="{ data }">
        <div class="contact-node" :class="{ center: data.isCenter, recent: data.recent, selected: data.selected }">
          <div class="cn-avatar" :style="{ background: data.color }">
            {{ data.initial }}
          </div>
          <div class="cn-info">
            <div class="cn-name">{{ data.shortName }}</div>
            <div class="cn-count">{{ data.count }} 封</div>
          </div>
          <div v-if="data.recent" class="cn-recent-dot"></div>
        </div>
      </template>

      <template #node-center="{ data }">
        <div class="center-node">
          <div class="center-avatar">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <div class="center-label">{{ data.label }}</div>
        </div>
      </template>
    </VueFlow>

    <div v-else class="graph-empty">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity=".25">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
        <circle cx="9" cy="7" r="4"/>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
        <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
      <span>暂无联系人数据，请先提取</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { MiniMap } from '@vue-flow/minimap'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/minimap/dist/style.css'
import '@vue-flow/controls/dist/style.css'

const props = defineProps({
  people:  { type: Array, default: () => [] },
  account: { type: String, default: '' },
})
const emit = defineEmits(['person-click'])

// ── 颜色池（根据 from 字符串哈希取色） ────────────────────────────────────────
const PALETTE = [
  '#6366f1','#ec4899','#f59e0b','#10b981','#3b82f6',
  '#8b5cf6','#ef4444','#06b6d4','#84cc16','#f97316',
]
function strColor(s) {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return PALETTE[h % PALETTE.length]
}
function shortName(from) {
  if (!from) return '?'
  const m = from.match(/^(.+?)\s*</) ?? from.match(/^([^@]+)/)
  const s = (m ? m[1].trim() : from)
  return s.length > 10 ? s.slice(0, 9) + '…' : s
}
function initial(from) {
  const n = shortName(from)
  return n[0]?.toUpperCase() ?? '?'
}

// ── 构建节点和边 ──────────────────────────────────────────────────────────────
const NOW = Date.now()
const WEEK_MS = 7 * 86400000

const nodes = computed(() => {
  const people = props.people.slice(0, 30) // 最多30个联系人
  if (!people.length) return []

  const result = []
  const maxCount = Math.max(...people.map(p => p.count), 1)

  // 中心节点（当前账号）
  result.push({
    id: '__center__',
    type: 'center',
    position: { x: 0, y: 0 },
    data: {
      label: props.account ? props.account.split('@')[0] : '我',
      isCenter: true,
    },
  })

  // 联系人节点 - 环形布局，按 count 排序，越多的越近
  people.forEach((p, i) => {
    const angle = (i / people.length) * 2 * Math.PI - Math.PI / 2
    const countRatio = p.count / maxCount
    // 距离：count 越大离中心越近（160~340px 范围）
    const dist = 340 - countRatio * 180
    const isRecent = p.latest && (NOW - new Date(p.latest).getTime()) < WEEK_MS

    result.push({
      id: `p_${i}`,
      type: 'contact',
      position: {
        x: Math.cos(angle) * dist,
        y: Math.sin(angle) * dist,
      },
      data: {
        from:      p.from,
        shortName: shortName(p.from),
        initial:   initial(p.from),
        count:     p.count,
        latest:    p.latest,
        color:     strColor(p.from),
        recent:    isRecent,
        isCenter:  false,
        selected:  false,
      },
    })
  })

  return result
})

const edges = computed(() => {
  const people = props.people.slice(0, 30)
  return people.map((p, i) => {
    const countRatio = p.count / Math.max(...people.map(x => x.count), 1)
    const isRecent = p.latest && (NOW - new Date(p.latest).getTime()) < WEEK_MS
    return {
      id:     `e_${i}`,
      source: '__center__',
      target: `p_${i}`,
      type:   'default',
      style: {
        stroke:      isRecent ? '#6366f1' : 'var(--border)',
        strokeWidth: Math.max(1, countRatio * 3),
        strokeDasharray: isRecent ? '0' : '4 3',
        opacity: 0.6 + countRatio * 0.4,
      },
      animated: isRecent && countRatio > 0.5,
    }
  })
})

// ── 事件 ──────────────────────────────────────────────────────────────────────
function onNodeClick({ node }) {
  if (node.data?.from) {
    emit('person-click', { from: node.data.from, count: node.data.count, latest: node.data.latest })
  }
}
</script>

<style>
/* VueFlow 全局覆盖 - 适配项目主题 */
.contact-flow .vue-flow__renderer { background: transparent !important; }
.contact-flow .vue-flow__edge-path { pointer-events: none; }
.contact-flow .vue-flow__controls {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  box-shadow: var(--shadow-sm) !important;
}
.contact-flow .vue-flow__controls-button {
  background: transparent !important;
  border-bottom-color: var(--border) !important;
  color: var(--text-secondary) !important;
  width: 22px !important;
  height: 22px !important;
}
.contact-flow .vue-flow__controls-button:hover {
  background: var(--bg-hover) !important;
}
.contact-flow .vue-flow__minimap {
  border-radius: 8px !important;
  border: 1px solid var(--border) !important;
  overflow: hidden;
}
</style>

<style scoped>
.contact-graph-wrap {
  width: 100%;
  height: 100%;
  position: relative;
}

.contact-flow {
  width: 100%;
  height: 100%;
  background: var(--bg);
}

/* 联系人节点 */
.contact-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px 5px 5px;
  background: var(--bg-card);
  border: 1.5px solid var(--border);
  border-radius: 20px;
  cursor: pointer;
  transition: all .15s;
  box-shadow: var(--shadow-sm);
  min-width: 100px;
  position: relative;
}
.contact-node:hover, .contact-node.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-dim), var(--shadow);
  transform: scale(1.04);
}
.contact-node.recent {
  border-color: rgba(34,197,94,.4);
}
.contact-node.recent:hover {
  border-color: #22c55e;
  box-shadow: 0 0 0 3px rgba(34,197,94,.12), var(--shadow);
}
.cn-avatar {
  width: 26px; height: 26px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.cn-info { flex: 1; min-width: 0; }
.cn-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cn-count {
  font-size: 9px;
  color: var(--text-muted);
  line-height: 1.3;
}
.cn-recent-dot {
  position: absolute;
  top: -2px; right: -2px;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #22c55e;
  border: 2px solid var(--bg-card);
  box-shadow: 0 0 0 2px rgba(34,197,94,.25);
}

/* 中心节点 */
.center-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  padding: 10px 14px;
  background: var(--accent);
  border-radius: 14px;
  cursor: default;
  box-shadow: 0 0 0 4px var(--accent-dim), var(--shadow);
  min-width: 80px;
}
.center-avatar {
  width: 32px; height: 32px;
  border-radius: 50%;
  background: rgba(255,255,255,.2);
  display: flex; align-items: center; justify-content: center;
  color: #fff;
}
.center-label {
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  white-space: nowrap;
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 空状态 */
.graph-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
