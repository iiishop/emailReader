<template>
  <div class="topic-graph-wrap">
    <VueFlow
      v-if="nodes.length"
      :nodes="nodes"
      :edges="edges"
      :fit-view-on-init="true"
      :min-zoom="0.25"
      :max-zoom="3"
      :nodes-draggable="true"
      :zoom-on-scroll="true"
      :pan-on-drag="true"
      class="topic-flow"
      @node-click="onNodeClick"
    >
      <Background pattern-color="var(--border-light)" :gap="24" :size="1" />
      <MiniMap
        class="topic-minimap"
        :node-color="n => n.data?._color ?? 'var(--bg-card)'"
        mask-color="rgba(0,0,0,0.06)"
      />
      <Controls :show-interactive="false" />

      <!-- 话题节点 -->
      <template #node-topic="{ data }">
        <div class="topic-node" :style="{ '--tc': data._color, '--ts': data._size + 'px' }">
          <div class="tn-ring"></div>
          <div class="tn-label">{{ data.name }}</div>
          <div class="tn-count">{{ data.count }}</div>
        </div>
      </template>

      <!-- 事件节点 -->
      <template #node-event="{ data }">
        <div class="event-node" :class="data.type" :style="{ '--ec': typeColor(data.type) }">
          <div class="en-dot"></div>
          <div class="en-body">
            <div class="en-title">{{ data.title }}</div>
            <div v-if="data.datetime" class="en-date">{{ shortDate(data.datetime) }}</div>
          </div>
        </div>
      </template>

      <!-- 联系人节点 -->
      <template #node-person="{ data }">
        <div class="person-node" :style="{ '--pc': data._color }">
          <div class="pn-avatar">{{ data.initial }}</div>
          <div class="pn-name">{{ data.shortName }}</div>
        </div>
      </template>
    </VueFlow>

    <div v-else class="graph-empty">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity=".25">
        <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/>
        <line x1="7" y1="7" x2="7.01" y2="7"/>
      </svg>
      <span>暂无话题数据，请先提取</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { MiniMap } from '@vue-flow/minimap'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/minimap/dist/style.css'
import '@vue-flow/controls/dist/style.css'

const props = defineProps({
  topics:  { type: Array, default: () => [] },
  events:  { type: Array, default: () => [] },
  people:  { type: Array, default: () => [] },
})
const emit = defineEmits(['topic-click', 'event-click', 'person-click'])

// ── 颜色系统 ──────────────────────────────────────────────────────────────────
const TOPIC_COLORS = [
  '#6366f1','#ec4899','#f59e0b','#10b981','#3b82f6',
  '#8b5cf6','#ef4444','#06b6d4','#84cc16','#f97316',
]
const TYPE_COLORS = {
  meeting:   '#6366f1',
  deadline:  '#ef4444',
  task:      '#f59e0b',
  reminder:  '#10b981',
  milestone: '#8b5cf6',
}
function typeColor(t) { return TYPE_COLORS[t] ?? '#94a3b8' }

function strHash(s) {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return h
}

function shortNameFrom(from) {
  if (!from) return '?'
  from = from.trim()
  if (from.length >= 2 && from[0] === '"' && from[from.length - 1] === '"') from = from.slice(1, -1).trim()
  const m = from.match(/^(.+?)\s*</) ?? from.match(/^([^@]+)/)
  const s = m ? m[1].trim() : from
  return s.length > 8 ? s.slice(0, 7) + '…' : s
}

function shortDate(dt) {
  if (!dt) return ''
  try {
    const d = new Date(dt)
    if (isNaN(d.getTime())) return ''
    return `${d.getMonth()+1}/${d.getDate()}`
  } catch { return '' }
}

// ── 构建图 ────────────────────────────────────────────────────────────────────
const nodes = computed(() => {
  const topics = props.topics.slice(0, 12)
  const events = props.events
  if (!topics.length) return []

  const allNodes = []
  const maxCount = Math.max(...topics.map(t => t.count), 1)

  // ① 话题节点 - 环形放置
  topics.forEach((topic, ti) => {
    const angle = (ti / topics.length) * 2 * Math.PI - Math.PI / 2
    const color = TOPIC_COLORS[ti % TOPIC_COLORS.length]
    const size  = 36 + (topic.count / maxCount) * 28 // 36~64px

    allNodes.push({
      id:   `t_${ti}`,
      type: 'topic',
      position: {
        x: Math.cos(angle) * 280,
        y: Math.sin(angle) * 200,
      },
      data: {
        name:   topic.name,
        count:  topic.count,
        _color: color,
        _size:  size,
        _ti:    ti,
      },
    })

    // ② 该话题的相关事件节点（最多3个）
    const relEvents = events
      .filter(ev => (ev.tags ?? []).some(tag =>
        tag.toLowerCase().includes(topic.name.toLowerCase()) ||
        topic.name.toLowerCase().includes(tag.toLowerCase())
      ))
      .slice(0, 3)

    relEvents.forEach((ev, ei) => {
      const evId = `ev_${ti}_${ei}`
      const evAngle = angle + (ei - (relEvents.length - 1) / 2) * 0.4
      const evDist  = 480

      allNodes.push({
        id:   evId,
        type: 'event',
        position: {
          x: Math.cos(evAngle) * evDist,
          y: Math.sin(evAngle) * evDist,
        },
        data: {
          title:    ev.title,
          type:     ev.type,
          datetime: ev.datetime,
          _raw:     ev,
        },
      })
    })
  })

  // ③ 高频联系人节点（最多8个）
  const topPeople = props.people.slice(0, 8)
  topPeople.forEach((p, pi) => {
    const angle = (pi / topPeople.length) * 2 * Math.PI - Math.PI / 4
    allNodes.push({
      id:   `person_${pi}`,
      type: 'person',
      position: {
        x: Math.cos(angle) * 650,
        y: Math.sin(angle) * 450,
      },
      data: {
        from:      p.from,
        shortName: shortNameFrom(p.from),
        initial:   (shortNameFrom(p.from)[0] ?? '?').toUpperCase(),
        count:     p.count,
        _color:    TOPIC_COLORS[strHash(p.from) % TOPIC_COLORS.length],
        _raw:      p,
      },
    })
  })

  return allNodes
})

const edges = computed(() => {
  const topics = props.topics.slice(0, 12)
  const events = props.events
  const topPeople = props.people.slice(0, 8)
  const allEdges = []

  topics.forEach((topic, ti) => {
    const color = TOPIC_COLORS[ti % TOPIC_COLORS.length]

    // 话题 → 相关事件
    const relEvents = events
      .filter(ev => (ev.tags ?? []).some(tag =>
        tag.toLowerCase().includes(topic.name.toLowerCase()) ||
        topic.name.toLowerCase().includes(tag.toLowerCase())
      ))
      .slice(0, 3)

    relEvents.forEach((_, ei) => {
      allEdges.push({
        id:     `te_${ti}_${ei}`,
        source: `t_${ti}`,
        target: `ev_${ti}_${ei}`,
        type:   'smoothstep',
        style:  { stroke: color, strokeWidth: 1.5, opacity: 0.6 },
      })
    })

    // 话题 → 相关联系人（事件的 source_from 匹配）
    topPeople.forEach((p, pi) => {
      const hasRelation = relEvents.some(ev =>
        ev.source_from && ev.source_from.toLowerCase().includes(
          p.from.split('@')[0].toLowerCase()
        )
      )
      if (hasRelation) {
        allEdges.push({
          id:       `tp_${ti}_${pi}`,
          source:   `t_${ti}`,
          target:   `person_${pi}`,
          type:     'bezier',
          style:    { stroke: color, strokeWidth: 1, opacity: 0.3, strokeDasharray: '5 4' },
          animated: false,
        })
      }
    })
  })

  return allEdges
})

// ── 事件处理 ──────────────────────────────────────────────────────────────────
function onNodeClick({ node }) {
  if (node.type === 'topic')  emit('topic-click', node.data)
  if (node.type === 'event')  emit('event-click', node.data._raw)
  if (node.type === 'person') emit('person-click', node.data._raw)
}
</script>

<style>
.topic-flow .vue-flow__renderer { background: transparent !important; }
.topic-flow .vue-flow__controls {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  box-shadow: var(--shadow-sm) !important;
}
.topic-flow .vue-flow__controls-button {
  background: transparent !important;
  border-bottom-color: var(--border) !important;
  color: var(--text-secondary) !important;
  width: 22px !important;
  height: 22px !important;
}
.topic-flow .vue-flow__controls-button:hover { background: var(--bg-hover) !important; }
.topic-flow .vue-flow__minimap {
  border-radius: 8px !important;
  border: 1px solid var(--border) !important;
  overflow: hidden;
}
</style>

<style scoped>
.topic-graph-wrap {
  width: 100%;
  height: 100%;
  position: relative;
}
.topic-flow {
  width: 100%;
  height: 100%;
  background: var(--bg);
}

/* ── 话题节点 ── */
.topic-node {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: var(--ts);
  height: var(--ts);
  border-radius: 50%;
  background: color-mix(in srgb, var(--tc) 12%, var(--bg-card));
  border: 2px solid color-mix(in srgb, var(--tc) 50%, transparent);
  cursor: pointer;
  transition: all .15s;
  box-shadow: 0 0 0 0 var(--tc);
}
.topic-node:hover {
  border-color: var(--tc);
  box-shadow: 0 0 0 5px color-mix(in srgb, var(--tc) 15%, transparent);
}
.tn-ring {
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  border: 1px dashed color-mix(in srgb, var(--tc) 30%, transparent);
  pointer-events: none;
}
.tn-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--tc);
  text-align: center;
  word-break: break-all;
  padding: 0 4px;
  line-height: 1.3;
  max-width: calc(var(--ts) - 8px);
}
.tn-count {
  font-size: 9px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

/* ── 事件节点 ── */
.event-node {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  padding: 5px 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--ec);
  border-radius: 6px;
  cursor: pointer;
  min-width: 100px;
  max-width: 150px;
  transition: all .14s;
  box-shadow: var(--shadow-sm);
}
.event-node:hover {
  border-color: var(--ec);
  box-shadow: var(--shadow);
}
.en-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--ec);
  flex-shrink: 0;
  margin-top: 3px;
}
.en-body { flex: 1; min-width: 0; }
.en-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.en-date {
  font-size: 9px;
  color: var(--text-muted);
}

/* ── 联系人节点 ── */
.person-node {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px 4px 4px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 20px;
  cursor: pointer;
  transition: all .14s;
  box-shadow: var(--shadow-sm);
}
.person-node:hover {
  border-color: var(--pc);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--pc) 12%, transparent);
}
.pn-avatar {
  width: 20px; height: 20px;
  border-radius: 50%;
  background: var(--pc);
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.pn-name {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  white-space: nowrap;
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
