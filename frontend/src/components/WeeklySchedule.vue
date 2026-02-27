<template>
  <div class="weekly-schedule" ref="scheduleEl">
    <!-- 列头：周一~周日 -->
    <div class="schedule-grid">
      <div class="time-gutter"></div>
      <div
        v-for="(day, i) in weekDays"
        :key="i"
        class="day-header"
        :class="{ today: day.isToday }"
      >
        <span class="day-name">{{ day.name }}</span>
        <span class="day-num" :class="{ today: day.isToday }">{{ day.num }}</span>
      </div>
    </div>

    <!-- 时间格子 -->
    <div class="schedule-body" ref="bodyEl">
      <div class="schedule-grid schedule-rows">
        <!-- 时间轴 -->
        <div class="time-gutter">
          <div
            v-for="h in HOURS"
            :key="h"
            class="time-slot-label"
            :style="{ height: SLOT_H + 'px' }"
          >
            <span>{{ String(h).padStart(2,'0') }}:00</span>
          </div>
        </div>

        <!-- 每天的格子列 -->
        <div
          v-for="(day, di) in weekDays"
          :key="di"
          class="day-col"
          :class="{ today: day.isToday }"
          @dragover.prevent
          @drop="onDrop($event, day)"
        >
          <!-- 半小时分割线 -->
          <div
            v-for="h in HOURS"
            :key="h"
            class="hour-block"
            :style="{ height: SLOT_H + 'px' }"
          >
            <div class="half-line"></div>
          </div>

          <!-- 当前时间线 -->
          <div
            v-if="day.isToday"
            class="now-line"
            :style="{ top: nowTop + 'px' }"
          ></div>

          <!-- 事件块 -->
          <div
            v-for="ev in day.events"
            :key="ev._id"
            class="event-block"
            :class="[ev.type, ev.priority]"
            :style="ev._style"
            :title="ev.title + (ev.description ? '\n' + ev.description : '')"
          >
            <span class="eb-title">{{ ev.title }}</span>
            <span v-if="ev._duration > 30" class="eb-time">{{ ev._timeStr }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  events:     { type: Array,  default: () => [] },
  weekOffset: { type: Number, default: 0 },
})
const emit = defineEmits(['drop-event'])

const HOURS  = Array.from({ length: 24 }, (_, i) => i)   // 0~23
const SLOT_H = 48   // px per hour

const scheduleEl = ref(null)
const bodyEl     = ref(null)

// ── 当前时间线 ────────────────────────────────────────────────────────────────
const nowTop = ref(0)
function updateNow() {
  const d = new Date()
  nowTop.value = (d.getHours() + d.getMinutes() / 60) * SLOT_H
}
let _nowTimer = null
onMounted(() => {
  updateNow()
  _nowTimer = setInterval(updateNow, 60000)
  // 滚动到当前时间
  const scrollTo = Math.max(0, nowTop.value - 120)
  bodyEl.value?.scrollTo({ top: scrollTo, behavior: 'smooth' })
})
onUnmounted(() => clearInterval(_nowTimer))

// ── 周日期计算 ────────────────────────────────────────────────────────────────
const WEEKDAY_CN = ['周日','周一','周二','周三','周四','周五','周六']

const weekDays = computed(() => {
  const now    = new Date()
  const today  = now.toISOString().slice(0, 10)
  const dayOfWeek = now.getDay() || 7   // 1=Mon … 7=Sun
  const monday = new Date(now)
  monday.setDate(now.getDate() - dayOfWeek + 1 + props.weekOffset * 7)
  monday.setHours(0, 0, 0, 0)

  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday)
    d.setDate(monday.getDate() + i)
    const iso = d.toISOString().slice(0, 10)
    return {
      date:    iso,
      name:    WEEKDAY_CN[d.getDay()],
      num:     d.getDate(),
      isToday: iso === today,
      events:  _eventsForDay(iso),
    }
  })
})

// ── 事件定位 ──────────────────────────────────────────────────────────────────
function _eventsForDay(iso) {
  return props.events
    .filter(e => e.datetime?.startsWith(iso))
    .map((e, idx) => {
      const d = new Date(e.datetime)
      const hasTime = e.datetime.includes('T')
      const startMin = hasTime ? d.getHours() * 60 + d.getMinutes() : 9 * 60
      const endMin   = e.end_datetime
        ? (() => { const ed = new Date(e.end_datetime); return ed.getHours() * 60 + ed.getMinutes() })()
        : startMin + 60

      const top    = (startMin / 60) * SLOT_H
      const height = Math.max(((endMin - startMin) / 60) * SLOT_H, 20)
      const timeStr = `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`

      return {
        ...e,
        _id:       e.source_key + idx,
        _style:    { top: top + 'px', height: height + 'px', left: '2px', right: '2px' },
        _duration: endMin - startMin,
        _timeStr:  timeStr,
      }
    })
}

// ── 拖放 ──────────────────────────────────────────────────────────────────────
function onDrop(e, day) {
  const raw = e.dataTransfer.getData('application/event')
  if (!raw) return
  try {
    const event = JSON.parse(raw)
    // 计算落点时间
    const rect = e.currentTarget.getBoundingClientRect()
    const y    = e.clientY - rect.top + (bodyEl.value?.scrollTop ?? 0)
    const mins = Math.round((y / SLOT_H) * 60 / 30) * 30
    const h    = Math.floor(mins / 60)
    const m    = mins % 60
    const datetime = `${day.date}T${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:00`
    emit('drop-event', { event, datetime })
  } catch { /* ignore */ }
}
</script>

<style scoped>
/* ══ 周日程 ══ */
.weekly-schedule {
  display: flex;
  flex-direction: column;
  height: 280px;
  overflow: hidden;
  font-size: 11px;
}

/* 列头 */
.schedule-grid {
  display: grid;
  grid-template-columns: 34px repeat(7, 1fr);
}
.time-gutter { flex-shrink: 0; }
.day-header {
  padding: 5px 2px 4px;
  text-align: center;
  border-left: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  transition: background .12s;
}
.day-header.today {
  background: rgba(99,102,241,.05);
}
.day-name {
  font-size: 9px;
  color: var(--text-muted);
  letter-spacing: .06em;
  text-transform: uppercase;
}
.day-num {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-secondary);
  width: 22px; height: 22px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  font-variant-numeric: tabular-nums;
  transition: background .12s, color .12s;
}
.day-num.today {
  background: var(--accent);
  color: #fff;
  box-shadow: 0 2px 8px rgba(99,102,241,.4);
}

/* 主体滚动区 */
.schedule-body {
  flex: 1;
  overflow-y: auto;
}
.schedule-rows {
  position: relative;
  min-height: calc(24 * 44px);
}

/* 时间轴标签 */
.time-gutter {
  display: flex;
  flex-direction: column;
}
.time-slot-label {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding-right: 5px;
  padding-top: 2px;
  font-size: 8.5px;
  color: var(--text-muted);
  border-right: 1px solid var(--border);
  box-sizing: border-box;
  flex-shrink: 0;
  opacity: .7;
}

/* 日列 */
.day-col {
  position: relative;
  border-left: 1px solid var(--border);
}
.day-col.today { background: rgba(99,102,241,.018); }

.hour-block {
  position: relative;
  border-bottom: 1px solid var(--border);
  box-sizing: border-box;
}
.half-line {
  position: absolute;
  top: 50%;
  left: 0; right: 0;
  border-top: 1px dashed var(--border);
  opacity: .4;
}

/* 当前时间线 */
.now-line {
  position: absolute;
  left: -1px; right: 0;
  height: 1.5px;
  background: #f43f5e;
  z-index: 10;
  pointer-events: none;
}
.now-line::before {
  content: '';
  position: absolute;
  left: -2px; top: -3px;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #f43f5e;
  box-shadow: 0 0 0 2px rgba(244,63,94,.25);
}

/* 事件块 */
.event-block {
  position: absolute;
  border-radius: 4px;
  padding: 2px 5px;
  overflow: hidden;
  cursor: pointer;
  font-size: 10px;
  z-index: 5;
  border-left: 2.5px solid transparent;
  transition: filter .1s;
}
.event-block:hover { filter: brightness(1.08); }
.event-block.meeting   { background: rgba(99,102,241,.18);  border-color: #6366f1; color: #6366f1; }
.event-block.deadline  { background: rgba(244,63,94,.15);   border-color: #f43f5e; color: #f43f5e; }
.event-block.task      { background: rgba(245,158,11,.15);  border-color: #f59e0b; color: #d97706; }
.event-block.reminder  { background: rgba(16,185,129,.13);  border-color: #10b981; color: #059669; }
.event-block.milestone { background: rgba(168,85,247,.15);  border-color: #a855f7; color: #9333ea; }

[data-theme="dark"] .event-block.reminder  { color: #34d399; }
[data-theme="dark"] .event-block.task      { color: #fbbf24; }
[data-theme="dark"] .event-block.deadline  { color: #fb7185; }
[data-theme="dark"] .event-block.milestone { color: #c084fc; }

.eb-title {
  display: block;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.eb-time {
  display: block;
  opacity: .75;
  font-size: 9px;
  font-variant-numeric: tabular-nums;
}

/* 滚动条 */
.schedule-body::-webkit-scrollbar { width: 3px; }
.schedule-body::-webkit-scrollbar-track { background: transparent; }
.schedule-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
