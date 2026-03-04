<template>
  <div
    class="todo-col"
    :class="{ 'drag-over': isDragOver }"
    @dragover.prevent="isDragOver = true"
    @dragleave="isDragOver = false"
    @drop="onDrop"
  >
    <!-- 列头 -->
    <div class="col-header" :style="{ borderTopColor: color }">
      <span class="col-label">{{ label }}</span>
      <span class="col-count">{{ todos.length }}</span>
    </div>

    <!-- 卡片列表 -->
    <div class="col-body">
      <TransitionGroup name="todo-card" tag="div" class="cards-wrap">
        <div
          v-for="todo in todos"
          :key="todo.id"
          class="todo-card"
          :class="[todo.priority, { editing: editingId === todo.id }]"
          draggable="true"
          @dragstart="onCardDragStart($event, todo)"
          @dragend="isDragOver = false"
        >
          <!-- 优先级条 -->
          <div class="priority-bar" :class="todo.priority"></div>

          <!-- 内容 -->
          <div class="card-body">
            <div v-if="editingId === todo.id" class="card-edit">
              <input
                v-model="editTitle"
                class="edit-input"
                @keydown.enter="saveEdit(todo)"
                @keydown.esc="editingId = null"
                @blur="saveEdit(todo)"
                ref="editInputRef"
              />
            </div>
            <div v-else class="card-title" @dblclick="startEdit(todo)">{{ todo.title }}</div>

            <div class="card-meta">
              <span v-if="todo.due" class="card-due" :class="{ overdue: isDue(todo.due) }">
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                {{ formatDue(todo.due) }}
              </span>
              <span v-if="todo.source_from" class="card-source">
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
                {{ shortFrom(todo.source_from) }}
              </span>
            </div>

            <div v-if="todo.tags?.length" class="card-tags">
              <span v-for="tag in todo.tags.slice(0,3)" :key="tag" class="card-tag">{{ tag }}</span>
            </div>

            <div v-if="todo.note" class="card-note">{{ todo.note }}</div>
          </div>

          <!-- 操作 -->
          <div class="card-actions">
            <select
              class="status-select"
              :value="todo.status"
              @change="emit('update', todo.id, { status: $event.target.value })"
            >
              <option value="todo">待办</option>
              <option value="doing">进行中</option>
              <option value="done">完成</option>
            </select>
            <button class="card-del-btn" @click="emit('delete', todo.id)" title="删除">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>
      </TransitionGroup>

      <!-- 空状态 / 拖放提示 -->
      <div v-if="!todos.length" class="col-empty">
        <span>{{ isDragOver ? '松开放入' : '暂无任务' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const props = defineProps({
  status: String,
  label:  String,
  color:  String,
  todos:  { type: Array, default: () => [] },
})
const emit = defineEmits(['update', 'delete', 'drop'])

const isDragOver  = ref(false)
const editingId   = ref(null)
const editTitle   = ref('')
const editInputRef = ref(null)

function startEdit(todo) {
  editingId.value = todo.id
  editTitle.value = todo.title
  nextTick(() => editInputRef.value?.focus())
}
function saveEdit(todo) {
  if (editTitle.value.trim() && editTitle.value !== todo.title) {
    emit('update', todo.id, { title: editTitle.value.trim() })
  }
  editingId.value = null
}

// ── 拖拽 ──────────────────────────────────────────────────────────────────────
function onCardDragStart(e, todo) {
  e.dataTransfer.setData('application/todo', JSON.stringify(todo))
  e.dataTransfer.effectAllowed = 'move'
}

function onDrop(e) {
  isDragOver.value = false

  // 从事件流拖入
  const evRaw = e.dataTransfer.getData('application/event')
  if (evRaw) {
    try {
      const ev = JSON.parse(evRaw)
      emit('drop', { type: 'event', event: ev, newStatus: props.status })
    } catch { /* ignore */ }
    return
  }

  // Todo 卡片跨列拖动
  const todoRaw = e.dataTransfer.getData('application/todo')
  if (todoRaw) {
    try {
      const todo = JSON.parse(todoRaw)
      if (todo.status !== props.status) {
        emit('drop', { type: 'todo', id: todo.id, newStatus: props.status })
      }
    } catch { /* ignore */ }
  }
}

// ── 格式化 ────────────────────────────────────────────────────────────────────
function isDue(due) {
  return due && new Date(due).getTime() < Date.now()
}
function formatDue(due) {
  if (!due) return ''
  const d    = new Date(due)
  const diff = Math.floor((d - Date.now()) / 86400000)
  if (diff === 0)  return '今天'
  if (diff === 1)  return '明天'
  if (diff === -1) return '昨天'
  if (diff < 0)    return `${-diff}天前`
  return `${d.getMonth()+1}/${d.getDate()}`
}
function shortFrom(from) {
  if (!from) return ''
  from = from.trim()
  if (from.length >= 2 && from[0] === '"' && from[from.length - 1] === '"') from = from.slice(1, -1).trim()
  const m = from.match(/^(.+?)\s*</) || from.match(/^([^@]+)/)
  return (m ? m[1].trim() : from).slice(0, 10)
}
</script>

<style scoped>
/* ══ Todo 列 ══ */
.todo-col {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  overflow: hidden;
  transition: background .15s;
}
.todo-col:last-child { border-right: none; }
.todo-col.drag-over  { background: rgba(99,102,241,.04); }

/* 列头 */
.col-header {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 11px;
  border-top: 2.5px solid transparent;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
  flex-shrink: 0;
}
.col-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: .1em;
}
.col-count {
  font-size: 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-muted);
  padding: 0 6px;
  border-radius: 10px;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

/* 列体 */
.col-body {
  flex: 1;
  overflow-y: auto;
  padding: 6px 5px;
}
.cards-wrap { display: flex; flex-direction: column; gap: 4px; }

/* 卡片 */
.todo-card {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 8px 9px 7px 12px;
  cursor: grab;
  transition: box-shadow .14s, border-color .14s, transform .1s;
  overflow: hidden;
}
.todo-card:hover {
  box-shadow: 0 3px 12px rgba(0,0,0,.09);
  border-color: rgba(99,102,241,.25);
  transform: translateY(-1px);
}
.todo-card:active { cursor: grabbing; transform: translateY(0); }

/* 优先级左侧条 */
.priority-bar {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  border-radius: 9px 0 0 9px;
}
.priority-bar.high   { background: #f43f5e; }
.priority-bar.medium { background: #f59e0b; }
.priority-bar.low    { background: #10b981; }

.card-body { display: flex; flex-direction: column; gap: 3px; }
.card-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.45;
  word-break: break-word;
}
.edit-input {
  width: 100%;
  border: 1px solid var(--accent);
  border-radius: 5px;
  padding: 2px 6px;
  font-size: 12px;
  background: var(--bg);
  color: var(--text-primary);
  outline: none;
  font-family: inherit;
  box-shadow: 0 0 0 2px rgba(99,102,241,.15);
}
.card-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.card-due {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  color: var(--text-muted);
}
.card-due.overdue { color: #f43f5e; font-weight: 600; }
.card-source {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  color: var(--text-muted);
  opacity: .8;
}
.card-tags { display: flex; gap: 3px; flex-wrap: wrap; }
.card-tag {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(99,102,241,.08);
  color: var(--accent);
  letter-spacing: .02em;
}
.card-note {
  font-size: 10px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-style: italic;
  opacity: .85;
}

/* 操作区（hover 显示） */
.card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  opacity: 0;
  transition: opacity .14s;
}
.todo-card:hover .card-actions { opacity: 1; }

.status-select {
  flex: 1;
  padding: 2px 5px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 10px;
  cursor: pointer;
  outline: none;
  font-family: inherit;
  transition: border-color .12s;
}
.status-select:focus { border-color: var(--accent); }
.card-del-btn {
  width: 20px; height: 20px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border); border-radius: 5px;
  background: transparent; color: var(--text-muted);
  cursor: pointer; transition: all .1s;
  flex-shrink: 0;
}
.card-del-btn:hover {
  background: rgba(244,63,94,.08);
  color: #f43f5e;
  border-color: rgba(244,63,94,.3);
}

/* 空状态 */
.col-empty {
  padding: 22px 10px;
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
  border: 1.5px dashed var(--border);
  border-radius: 9px;
  margin-top: 4px;
  font-style: italic;
  transition: border-color .15s, background .15s;
}
.todo-col.drag-over .col-empty {
  border-color: rgba(99,102,241,.4);
  background: rgba(99,102,241,.04);
  color: var(--accent);
}

/* 动画 */
.todo-card-enter-active { transition: all .22s cubic-bezier(.4,0,.2,1); }
.todo-card-leave-active { transition: all .16s ease; }
.todo-card-enter-from   { opacity: 0; transform: translateY(-6px); }
.todo-card-leave-to     { opacity: 0; transform: scale(.96); }

/* 滚动条 */
.col-body::-webkit-scrollbar { width: 3px; }
.col-body::-webkit-scrollbar-track { background: transparent; }
.col-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
