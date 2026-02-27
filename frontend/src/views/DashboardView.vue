<template>
  <div class="dashboard">

    <!-- ══ 账号 Tab 栏 ══ -->
    <div class="account-tabs">
      <button
        class="acc-tab"
        :class="{ active: dash.selectedAccount === 'all' }"
        @click="dash.selectedAccount = 'all'"
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        全部
      </button>
      <button
        v-for="acc in accountsList"
        :key="acc.email"
        class="acc-tab"
        :class="{ active: dash.selectedAccount === acc.email }"
        @click="dash.selectedAccount = acc.email"
        :title="acc.email"
      >
        <span class="acc-tab-avatar">{{ acc.email[0].toUpperCase() }}</span>
        <span class="acc-tab-label">{{ acc.shortName }}</span>
        <span v-if="accEventCount(acc.email)" class="acc-tab-badge">{{ accEventCount(acc.email) }}</span>
      </button>
    </div>

    <!-- ══ 顶部简报栏（今日简报 + 历史入口） ══ -->
    <div class="brief-bar">
      <div class="brief-bar-inner">
        <!-- 今日简报预览 -->
        <div class="brief-today" @click="openTodayBrief" :class="{ clickable: dash.currentBrief || dash.isExtracting }">
          <div class="brief-today-icon">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
            </svg>
          </div>
          <div class="brief-today-content">
            <div class="brief-today-label">
              {{ dash.selectedAccount === 'all' ? '全局简报' : accShortName(dash.selectedAccount) + ' 简报' }} · {{ todayStr }}
            </div>
            <div v-if="dash.currentBrief" class="brief-today-preview">{{ currentBriefPreview }}</div>
            <div v-else-if="dash.isExtracting" class="brief-today-loading">
              <span class="spinner-xs"></span> AI 正在分析邮件…
            </div>
            <div v-else class="brief-today-empty">暂无简报，点击「提取」生成</div>
          </div>
          <svg v-if="dash.currentBrief" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="brief-arrow"><polyline points="9 18 15 12 9 6"/></svg>
        </div>

        <!-- 历史简报列表（横向滚动） -->
        <div class="brief-history" v-if="dash.filteredBriefs.length > 0">
          <div
            v-for="b in dash.filteredBriefs.slice(0, 14)"
            :key="b.id + dash.selectedAccount"
            class="brief-hist-item"
            @click="openBriefDetail(b)"
          >
            <div class="brief-hist-date">{{ formatBriefDate(b.date) }}</div>
            <div class="brief-hist-preview">{{ b.preview }}</div>
          </div>
        </div>

        <!-- 操作区 -->
        <div class="brief-actions">
          <button
            class="brief-extract-btn"
            :disabled="dash.isExtracting || !settings.isConfigured"
            @click="dash.triggerExtract()"
            :title="settings.isConfigured ? '重新提取' : '请先配置 AI'"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
              :class="{ spinning: dash.isExtracting }">
              <polyline points="23 4 23 10 17 10"/>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
            {{ dash.isExtracting ? '提取中…' : '提取' }}
          </button>
        </div>
      </div>
    </div>

    <!-- ══ 主体：左宽列 + 右窄列 ══ -->
    <div class="dashboard-body">

      <!-- ── 左宽列：日程 + Todo ── -->
      <div class="main-col">

        <!-- 周日程卡片 -->
        <div class="card card-schedule">
          <div class="card-hdr">
            <div class="card-hdr-left">
              <span class="card-icon schedule-icon">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              </span>
              <span class="card-title">本周日程</span>
            </div>
            <div class="week-nav">
              <button class="nav-arrow" @click="weekOffset--">‹</button>
              <span class="week-label">{{ weekLabel }}</span>
              <button class="nav-arrow" @click="weekOffset++">›</button>
              <button v-if="weekOffset !== 0" class="nav-today-btn" @click="weekOffset = 0">今</button>
            </div>
          </div>
          <WeeklySchedule
            :events="scheduleEvents"
            :week-offset="weekOffset"
            @drop-event="onScheduleDrop"
          />
        </div>

        <!-- Todo 看板卡片 -->
        <div class="card card-todo">
          <div class="card-hdr">
            <div class="card-hdr-left">
              <span class="card-icon todo-icon">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
              </span>
              <span class="card-title">任务看板</span>
              <span class="card-badge">{{ dash.todos.length }}</span>
            </div>
            <button class="add-todo-btn" @click="showAddTodo = true">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              新建
            </button>
          </div>
          <div class="todo-board">
            <TodoColumn
              v-for="col in TODO_COLS"
              :key="col.status"
              :status="col.status"
              :label="col.label"
              :color="col.color"
              :todos="dash.todosByStatus[col.status]"
              @update="dash.updateTodo"
              @delete="dash.deleteTodo"
              @drop="onTodoDrop"
            />
          </div>
        </div>

      </div>

      <!-- ── 右窄列：事件流 + 倒计时 + 话题 + 联系人 ── -->
      <div class="side-col">

        <!-- 事件 & 任务 -->
        <div class="card card-events">
          <div class="card-hdr">
            <div class="card-hdr-left">
              <span class="card-icon event-icon">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              </span>
              <span class="card-title">事件 & 任务</span>
              <span class="card-badge">{{ dash.filteredEvents.length }}</span>
            </div>
            <select v-model="eventFilter" class="mini-select">
              <option value="">全部</option>
              <option value="meeting">会议</option>
              <option value="deadline">截止</option>
              <option value="task">任务</option>
              <option value="reminder">提醒</option>
              <option value="milestone">里程碑</option>
            </select>
          </div>
          <div class="events-list">
            <div v-if="!dash.filteredEvents.length && !dash.isExtracting" class="card-empty">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity=".3"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <span>点击「提取」开始分析</span>
            </div>
            <TransitionGroup name="event-list" tag="div">
              <div
                v-for="ev in filteredEvents"
                :key="ev.source_key + ev.title"
                class="event-item"
                :class="[ev.type, ev.priority, { 'ev-added': dash.isEventAdded(ev) }]"
                draggable="true"
                @dragstart="onEventDragStart($event, ev)"
                @click.stop="openEventDetail(ev)"
              >
                <div class="event-type-dot" :class="ev.type"></div>
                <div class="event-body">
                  <div class="event-title">{{ ev.title }}</div>
                  <div class="event-meta">
                    <span v-if="ev.datetime" class="event-date">{{ formatEventDate(ev.datetime) }}</span>
                    <span v-if="ev.source_from" class="event-from">{{ shortFrom(ev.source_from) }}</span>
                    <span v-if="dash.isEventAdded(ev)" class="ev-added-tag">
                      <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                      已加入
                    </span>
                  </div>
                  <div v-if="ev.description" class="event-desc">{{ ev.description }}</div>
                  <div class="event-tags">
                    <span v-for="tag in (ev.tags || [])" :key="tag" class="tag">{{ tag }}</span>
                  </div>
                </div>
                <div class="event-actions">
                  <button
                    class="ev-btn"
                    :class="{ 'ev-btn-added': dash.isEventAdded(ev) }"
                    @click.stop="dash.addTodoFromEvent(ev)"
                    :title="dash.isEventAdded(ev) ? '再次加入 Todo' : '加入 Todo'"
                  >
                    <svg v-if="dash.isEventAdded(ev)" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                    <svg v-else width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                  </button>
                </div>
              </div>
            </TransitionGroup>
          </div>
        </div>

        <!-- 倒计时 -->
        <div class="card" v-if="dash.countdowns.length">
          <div class="card-hdr">
            <div class="card-hdr-left">
              <span class="card-icon countdown-icon">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              </span>
              <span class="card-title">重要倒计时</span>
            </div>
          </div>
          <div class="countdown-list">
            <div
              v-for="ev in dash.countdowns"
              :key="ev.title + ev.datetime"
              class="countdown-item"
              :class="countdownClass(ev)"
              @click="openEventDetail(ev)"
            >
              <div class="countdown-type-bar" :class="ev.type"></div>
              <div class="countdown-days">
                <template v-if="ev._diffMs < 0">
                  <span class="cd-num overdue">过期</span>
                </template>
                <template v-else-if="ev._diffMs < 86400000">
                  <span class="cd-num urgent">今天</span>
                </template>
                <template v-else>
                  <span class="cd-num">{{ Math.ceil(ev._diffMs / 86400000) }}</span>
                  <span class="cd-unit">天</span>
                </template>
              </div>
              <div class="countdown-body">
                <div class="countdown-title">{{ ev.title }}</div>
                <div class="countdown-date">{{ formatEventDate(ev.datetime) }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 话题 -->
        <div class="card" v-if="dash.filteredTopics.length || dash.filteredEvents.length">
          <div class="card-hdr">
            <div class="card-hdr-left">
              <span class="card-icon topic-icon">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
              </span>
              <span class="card-title">话题</span>
            </div>
            <button v-if="dash.filteredTopics.length" class="graph-open-btn" @click="graphModal = 'topic'" title="展开知识图谱">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
              图谱
            </button>
          </div>
          <div class="topics-grid">
            <div v-for="topic in dash.filteredTopics.slice(0, 12)" :key="topic.name" class="topic-chip" @click="openTopicDetail(topic)">
              <span class="topic-name">{{ topic.name }}</span>
              <span class="topic-count">{{ topic.count }}</span>
            </div>
          </div>
        </div>

        <!-- 联系人 -->
        <div class="card" v-if="dash.filteredPeople.length">
          <div class="card-hdr">
            <div class="card-hdr-left">
              <span class="card-icon people-icon">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
              </span>
              <span class="card-title">联系人</span>
            </div>
            <button class="graph-open-btn" @click="graphModal = 'contact'" title="展开关系图谱">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>
              图谱
            </button>
          </div>
          <div class="people-list">
            <div v-for="p in dash.filteredPeople.slice(0, 6)" :key="p.from" class="person-item" @click="openPersonDetail(p)">
              <div class="person-avatar">{{ (p.from || '?')[0].toUpperCase() }}</div>
              <div class="person-body">
                <div class="person-name">{{ shortFrom(p.from) }}</div>
                <div class="person-meta">{{ p.count }} 封 · {{ shortDate(p.latest) }}</div>
              </div>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="person-arrow"><polyline points="9 18 15 12 9 6"/></svg>
            </div>
          </div>
        </div>

        <!-- ══ 全屏图谱浮层（话题 / 联系人） ══ -->
        <Teleport to="body">
          <Transition name="graph-overlay-fade">
            <div v-if="graphModal" class="graph-overlay" @click.self="graphModal = null">
              <div class="graph-overlay-panel">
                <div class="graph-overlay-hdr">
                  <div class="graph-overlay-title">
                    <svg v-if="graphModal === 'topic'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
                    <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                    {{ graphModal === 'topic' ? '话题知识图谱' : '联系人关系图' }}
                    <span class="graph-overlay-hint">拖拽 · 滚轮缩放 · 点击节点查看详情</span>
                  </div>
                  <button class="graph-overlay-close" @click="graphModal = null">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </div>
                <div class="graph-overlay-body">
                  <TopicKnowledgeGraph
                    v-if="graphModal === 'topic'"
                    :topics="dash.filteredTopics"
                    :events="dash.filteredEvents"
                    :people="dash.filteredPeople"
                    @topic-click="t => { openTopicDetail(t); graphModal = null }"
                    @event-click="e => { openEventDetail(e); graphModal = null }"
                    @person-click="p => { openPersonDetail(p); graphModal = null }"
                  />
                  <ContactGraph
                    v-if="graphModal === 'contact'"
                    :people="dash.filteredPeople"
                    :account="dash.selectedAccount !== 'all' ? dash.selectedAccount : ''"
                    @person-click="p => { openPersonDetail(p); graphModal = null }"
                  />
                </div>
              </div>
            </div>
          </Transition>
        </Teleport>

        <!-- 统计 -->
        <div class="card" v-if="dash.currentStats.total_emails">
          <div class="card-hdr">
            <div class="card-hdr-left">
              <span class="card-icon stat-icon">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
              </span>
              <span class="card-title">统计</span>
            </div>
            <span v-if="dash.extractedAt" class="card-sub">{{ shortDate(dash.extractedAt) }}</span>
          </div>
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-num">{{ dash.currentStats.total_emails ?? 0 }}</div>
              <div class="stat-lbl">封邮件</div>
            </div>
            <div class="stat-card">
              <div class="stat-num accent">{{ dash.currentStats.total_events ?? 0 }}</div>
              <div class="stat-lbl">个事件</div>
            </div>
            <div class="stat-card">
              <div class="stat-num">{{ dash.currentStats.accounts_count ?? 0 }}</div>
              <div class="stat-lbl">个账号</div>
            </div>
            <div class="stat-card">
              <div class="stat-num">{{ dash.currentStats.ai_days ?? 0 }}</div>
              <div class="stat-lbl">天范围</div>
            </div>
          </div>
        </div>

        <!-- 未配置提示 -->
        <div v-if="!settings.isConfigured" class="warn-card">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span>AI 未配置，请在设置中填写 API Key 和模型</span>
        </div>

      </div>
    </div>

    <!-- ══ 简报详情弹窗 ══ -->
    <Transition name="drawer-fade">
      <div v-if="briefModal.show" class="drawer-overlay" @click.self="briefModal.show = false">
        <div class="drawer-panel">
          <div class="drawer-hdr">
            <div class="drawer-hdr-left">
              <div class="drawer-icon brief-drawer-icon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              </div>
              <div>
                <div class="drawer-title">{{ briefModal.title }}</div>
                <div class="drawer-sub">{{ briefModal.sub }}</div>
              </div>
            </div>
            <button class="drawer-close" @click="briefModal.show = false">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="drawer-body">
            <div v-if="briefModal.loading" class="drawer-loading">
              <span class="spinner-xs"></span> 加载中…
            </div>
            <div v-else class="brief-full-text" v-html="renderMd(briefModal.content)"></div>
            <div v-if="briefModal.stats && briefModal.stats.total_emails" class="brief-stats-row">
              <span>{{ briefModal.stats.total_emails }} 封邮件</span>
              <span>{{ briefModal.stats.total_events }} 个事件</span>
              <span>{{ briefModal.stats.accounts_count }} 个账号</span>
              <span>{{ briefModal.stats.ai_days }} 天范围</span>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ══ 事件详情弹窗 ══ -->
    <Transition name="drawer-fade">
      <div v-if="eventModal.show" class="drawer-overlay" @click.self="eventModal.show = false">
        <div class="drawer-panel drawer-panel-sm">
          <div class="drawer-hdr">
            <div class="drawer-hdr-left">
              <div class="drawer-icon" :class="`type-icon-${eventModal.event?.type}`">
                <span class="type-dot-lg" :class="eventModal.event?.type"></span>
              </div>
              <div>
                <div class="drawer-title">{{ eventModal.event?.title }}</div>
                <div class="drawer-sub">
                  <span class="type-badge" :class="eventModal.event?.type">{{ typeLabel(eventModal.event?.type) }}</span>
                  <span v-if="eventModal.event?.priority" class="priority-badge" :class="eventModal.event?.priority">{{ priorityLabel(eventModal.event?.priority) }}</span>
                </div>
              </div>
            </div>
            <button class="drawer-close" @click="eventModal.show = false">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="drawer-body">
            <div class="detail-grid">
              <template v-if="eventModal.event?.datetime">
                <div class="detail-label">时间</div>
                <div class="detail-value accent">{{ formatEventDateFull(eventModal.event.datetime) }}</div>
              </template>
              <template v-if="eventModal.event?.end_datetime">
                <div class="detail-label">结束</div>
                <div class="detail-value">{{ formatEventDateFull(eventModal.event.end_datetime) }}</div>
              </template>
              <template v-if="eventModal.event?.source_from">
                <div class="detail-label">发件人</div>
                <div class="detail-value">{{ eventModal.event.source_from }}</div>
              </template>
              <template v-if="eventModal.event?.account">
                <div class="detail-label">账号</div>
                <div class="detail-value muted">{{ eventModal.event.account }}</div>
              </template>
              <template v-if="eventModal.event?.description">
                <div class="detail-label">描述</div>
                <div class="detail-value">{{ eventModal.event.description }}</div>
              </template>
              <template v-if="eventModal.event?.source_subject">
                <div class="detail-label">来源邮件</div>
                <div class="detail-value">{{ eventModal.event.source_subject }}</div>
              </template>
            </div>
            <div v-if="eventModal.event?.tags?.length" class="detail-tags">
              <span v-for="tag in eventModal.event.tags" :key="tag" class="tag">{{ tag }}</span>
            </div>
            <div class="drawer-actions">
              <button
                class="drawer-action-btn"
                :class="{ 'drawer-action-added': dash.isEventAdded(eventModal.event) }"
                @click="dash.addTodoFromEvent(eventModal.event); eventModal.show = false"
              >
                <svg v-if="dash.isEventAdded(eventModal.event)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                {{ dash.isEventAdded(eventModal.event) ? '已加入 Todo（再次加入）' : '加入 Todo' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ══ 话题详情弹窗 ══ -->
    <Transition name="drawer-fade">
      <div v-if="topicModal.show" class="drawer-overlay" @click.self="topicModal.show = false">
        <div class="drawer-panel drawer-panel-sm">
          <div class="drawer-hdr">
            <div class="drawer-hdr-left">
              <div class="drawer-icon topic-drawer-icon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
              </div>
              <div>
                <div class="drawer-title">{{ topicModal.topic?.name }}</div>
                <div class="drawer-sub">{{ topicModal.topic?.count }} 封相关邮件</div>
              </div>
            </div>
            <button class="drawer-close" @click="topicModal.show = false">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="drawer-body">
            <div v-if="topicModal.topic?.summary" class="topic-summary">{{ topicModal.topic.summary }}</div>
            <div v-if="topicRelatedEvents.length" class="topic-events">
              <div class="detail-section-title">相关事件</div>
              <div v-for="ev in topicRelatedEvents" :key="ev.source_key + ev.title" class="topic-event-item" @click="openEventDetail(ev); topicModal.show = false">
                <span class="type-dot-sm" :class="ev.type"></span>
                <span class="topic-event-title">{{ ev.title }}</span>
                <span class="topic-event-date">{{ formatEventDate(ev.datetime) }}</span>
              </div>
            </div>
            <div v-else class="drawer-empty">暂无相关事件数据</div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ══ 联系人详情弹窗 ══ -->
    <Transition name="drawer-fade">
      <div v-if="personModal.show" class="drawer-overlay" @click.self="personModal.show = false">
        <div class="drawer-panel drawer-panel-sm">
          <div class="drawer-hdr">
            <div class="drawer-hdr-left">
              <div class="person-avatar-lg">{{ (personModal.person?.from || '?')[0].toUpperCase() }}</div>
              <div>
                <div class="drawer-title">{{ shortFrom(personModal.person?.from) }}</div>
                <div class="drawer-sub">{{ personModal.person?.from }}</div>
              </div>
            </div>
            <button class="drawer-close" @click="personModal.show = false">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="drawer-body">
            <div class="detail-grid">
              <div class="detail-label">邮件数</div>
              <div class="detail-value accent">{{ personModal.person?.count }} 封</div>
              <div class="detail-label">最近往来</div>
              <div class="detail-value">{{ shortDate(personModal.person?.latest) }}</div>
            </div>
            <div v-if="personRelatedEvents.length" class="topic-events" style="margin-top:14px">
              <div class="detail-section-title">相关事件</div>
              <div v-for="ev in personRelatedEvents" :key="ev.source_key + ev.title" class="topic-event-item" @click="openEventDetail(ev); personModal.show = false">
                <span class="type-dot-sm" :class="ev.type"></span>
                <span class="topic-event-title">{{ ev.title }}</span>
                <span class="topic-event-date">{{ formatEventDate(ev.datetime) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ══ 添加 Todo 弹窗 ══ -->
    <Transition name="modal-fade">
      <div v-if="showAddTodo" class="modal-overlay" @click.self="showAddTodo = false">
        <div class="modal-box">
          <div class="modal-title">新建任务</div>
          <input v-model="newTodo.title" class="modal-input" placeholder="任务标题" @keydown.enter="submitTodo" autofocus />
          <div class="modal-row">
            <select v-model="newTodo.priority" class="modal-select">
              <option value="high">🔴 高优先级</option>
              <option value="medium">🟡 中优先级</option>
              <option value="low">🟢 低优先级</option>
            </select>
            <input v-model="newTodo.due" type="date" class="modal-input" style="flex:1" />
          </div>
          <textarea v-model="newTodo.note" class="modal-textarea" placeholder="备注（可选）" rows="2"></textarea>
          <div class="modal-footer">
            <button class="modal-cancel" @click="showAddTodo = false">取消</button>
            <button class="modal-submit" @click="submitTodo" :disabled="!newTodo.title.trim()">创建</button>
          </div>
        </div>
      </div>
    </Transition>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onActivated } from 'vue'
import { marked } from 'marked'
import { useDashboardDataStore } from '../stores/dashboardData.js'
import { useSettingsStore }      from '../stores/settings.js'
import { useAccountsStore }      from '../stores/accounts.js'
import WeeklySchedule       from '../components/WeeklySchedule.vue'
import TodoColumn           from '../components/TodoColumn.vue'
import ContactGraph         from '../components/ContactGraph.vue'
import TopicKnowledgeGraph  from '../components/TopicKnowledgeGraph.vue'

marked.setOptions({ breaks: true, gfm: true })

const dash     = useDashboardDataStore()
const settings = useSettingsStore()
const accountsStore = useAccountsStore()

// ── 图谱全屏浮层（null | 'topic' | 'contact'） ────────────────────────────────
const graphModal = ref(null)

// ── 账号列表（用于 Tab） ──────────────────────────────────────────────────────
const accountsList = computed(() =>
  accountsStore.accounts.map(acc => ({
    email:     acc.email,
    shortName: accShortName(acc.email),
  }))
)

function accShortName(email) {
  if (!email) return '?'
  // 取 @ 前的部分，过长则截断
  const user = email.split('@')[0] ?? email
  return user.length > 10 ? user.slice(0, 10) + '…' : user
}

function accEventCount(email) {
  return (dash.accEvents[email] ?? []).length || 0
}

// ── 今日日期 ──────────────────────────────────────────────────────────────────
const WEEKDAY_CN = ['周日','周一','周二','周三','周四','周五','周六']
const todayStr = computed(() => {
  const d = new Date()
  return `${d.getMonth()+1}月${d.getDate()}日 ${WEEKDAY_CN[d.getDay()]}`
})

// ── 简报预览（截取前 80 字） ──────────────────────────────────────────────────
const currentBriefPreview = computed(() => {
  const text = dash.currentBrief || ''
  const plain = text.replace(/[#*`>\-]/g, '').replace(/\n+/g, ' ').trim()
  return plain.slice(0, 80) + (plain.length > 80 ? '…' : '')
})

// ── 事件筛选（在 store 的 filteredEvents 基础上再按类型筛） ───────────────────
const eventFilter = ref('')
const filteredEvents = computed(() =>
  eventFilter.value
    ? dash.filteredEvents.filter(e => e.type === eventFilter.value)
    : dash.filteredEvents
)

// ── 周日程 ────────────────────────────────────────────────────────────────────
const weekOffset = ref(0)
const weekLabel = computed(() => {
  const now = new Date()
  const day = now.getDay() || 7
  const mon = new Date(now); mon.setDate(now.getDate() - day + 1 + weekOffset.value * 7)
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6)
  return `${mon.getMonth()+1}/${mon.getDate()} – ${sun.getMonth()+1}/${sun.getDate()}`
})

const scheduleEvents = computed(() => {
  if (weekOffset.value === 0) return dash.weekEvents
  const now = new Date()
  const day = now.getDay() || 7
  const mon = new Date(now); mon.setDate(now.getDate() - day + 1 + weekOffset.value * 7); mon.setHours(0,0,0,0)
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6); sun.setHours(23,59,59,999)
  return dash.filteredEvents.filter(e => {
    if (!e.datetime) return false
    const t = new Date(e.datetime).getTime()
    return t >= mon.getTime() && t <= sun.getTime()
  })
})

function onScheduleDrop({ event, datetime }) {
  console.log('schedule drop', event, datetime)
}

// ── Todo ──────────────────────────────────────────────────────────────────────
const TODO_COLS = [
  { status: 'todo',  label: '待办',   color: '#6366f1' },
  { status: 'doing', label: '进行中', color: '#f59e0b' },
  { status: 'done',  label: '完成',   color: '#22c55e' },
]

const showAddTodo = ref(false)
const newTodo = ref({ title: '', priority: 'medium', due: '', note: '' })

async function submitTodo() {
  if (!newTodo.value.title.trim()) return
  await dash.addTodo({ ...newTodo.value })
  newTodo.value = { title: '', priority: 'medium', due: '', note: '' }
  showAddTodo.value = false
}

function onTodoDrop({ type, id, event, newStatus }) {
  if (type === 'event' && event) {
    // 将事件拖入看板 → 自动创建 Todo（并标记已加入）
    dash.addTodoFromEvent(event, { status: newStatus })
  } else if (type === 'todo' && id) {
    // Todo 卡片跨列拖动 → 更新状态
    dash.updateTodo(id, { status: newStatus })
  }
}

function onEventDragStart(e, ev) {
  e.dataTransfer.setData('application/event', JSON.stringify(ev))
  e.dataTransfer.effectAllowed = 'copy'
}

// ── 倒计时样式 ────────────────────────────────────────────────────────────────
function countdownClass(ev) {
  if (ev._diffMs < 0) return 'overdue'
  if (ev._diffMs < 86400000) return 'today'
  if (ev._diffMs < 3 * 86400000) return 'soon'
  return ''
}

// ══════════════════════════════════════════════════════════════════════════════
// 弹窗状态
// ══════════════════════════════════════════════════════════════════════════════

// ── 简报弹窗 ──────────────────────────────────────────────────────────────────
const briefModal = ref({ show: false, title: '', sub: '', content: '', stats: null, loading: false })

async function openTodayBrief() {
  if (!dash.currentBrief) return
  const title = dash.selectedAccount === 'all'
    ? '今日简报（全局）'
    : `今日简报 · ${accShortName(dash.selectedAccount)}`
  briefModal.value = {
    show: true,
    title,
    sub: todayStr.value,
    content: dash.currentBrief,
    stats: dash.currentStats,
    loading: false,
  }
}

async function openBriefDetail(b) {
  const accLabel = dash.selectedAccount === 'all' ? '' : ` · ${accShortName(dash.selectedAccount)}`
  briefModal.value = { show: true, title: `简报 · ${b.date}${accLabel}`, sub: shortDate(b.generated_at), content: '', stats: null, loading: true }
  const detail = await dash.fetchBriefDetail(b.id)
  if (detail) {
    // 根据当前选择的账号决定用哪个简报内容
    const accBriefs = detail.account_briefs ?? {}
    const content = dash.selectedAccount !== 'all' && accBriefs[dash.selectedAccount]
      ? accBriefs[dash.selectedAccount]
      : (detail.brief || '')
    briefModal.value.content = content
    briefModal.value.stats   = detail.stats || null
  }
  briefModal.value.loading = false
}

function formatBriefDate(dateStr) {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return dateStr
    const today = new Date().toISOString().slice(0, 10)
    if (dateStr === today) return '今天'
    const diff = Math.floor((new Date(today) - d) / 86400000)
    if (diff === 1) return '昨天'
    if (diff === 2) return '前天'
    return `${d.getMonth()+1}/${d.getDate()}`
  } catch { return dateStr }
}

// ── 事件详情弹窗 ──────────────────────────────────────────────────────────────
const eventModal = ref({ show: false, event: null })

function openEventDetail(ev) {
  eventModal.value = { show: true, event: ev }
}

const TYPE_LABELS = { meeting: '会议', deadline: '截止', task: '任务', reminder: '提醒', milestone: '里程碑' }
const PRIORITY_LABELS = { high: '高优先级', medium: '中优先级', low: '低优先级' }
function typeLabel(t) { return TYPE_LABELS[t] || t || '' }
function priorityLabel(p) { return PRIORITY_LABELS[p] || p || '' }

// ── 话题详情弹窗 ──────────────────────────────────────────────────────────────
const topicModal = ref({ show: false, topic: null })

function openTopicDetail(topic) {
  topicModal.value = { show: true, topic }
}

const topicRelatedEvents = computed(() => {
  if (!topicModal.value.topic) return []
  const name = topicModal.value.topic.name?.toLowerCase() || ''
  return dash.filteredEvents.filter(ev =>
    (ev.tags || []).some(t => t.toLowerCase().includes(name)) ||
    ev.title?.toLowerCase().includes(name) ||
    ev.description?.toLowerCase().includes(name)
  ).slice(0, 10)
})

// ── 联系人详情弹窗 ────────────────────────────────────────────────────────────
const personModal = ref({ show: false, person: null })

function openPersonDetail(p) {
  personModal.value = { show: true, person: p }
}

const personRelatedEvents = computed(() => {
  if (!personModal.value.person) return []
  const from = personModal.value.person.from?.toLowerCase() || ''
  return dash.filteredEvents.filter(ev =>
    ev.source_from?.toLowerCase().includes(from.split('@')[0]) ||
    ev.source_from?.toLowerCase().includes(from)
  ).slice(0, 8)
})

// ══════════════════════════════════════════════════════════════════════════════
// 格式化工具
// ══════════════════════════════════════════════════════════════════════════════
function renderMd(text) {
  try { return marked.parse(text || '') } catch { return text || '' }
}
function formatEventDate(dt) {
  if (!dt) return ''
  try {
    const d = new Date(dt)
    if (isNaN(d.getTime())) return dt
    const diff = Math.floor((d - Date.now()) / 86400000)
    const time = dt.includes('T') ? ` ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}` : ''
    if (diff === 0) return `今天${time}`
    if (diff === 1) return `明天${time}`
    if (diff === -1) return `昨天${time}`
    return `${d.getMonth()+1}/${d.getDate()}${time}`
  } catch { return dt }
}
function formatEventDateFull(dt) {
  if (!dt) return ''
  try {
    const d = new Date(dt)
    if (isNaN(d.getTime())) return dt
    const hasTime = dt.includes('T')
    const dateStr = `${d.getFullYear()}年${d.getMonth()+1}月${d.getDate()}日 ${WEEKDAY_CN[d.getDay()]}`
    const timeStr = hasTime ? ` ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}` : ''
    return dateStr + timeStr
  } catch { return dt }
}
function shortFrom(from) {
  if (!from) return ''
  const m = from.match(/^(.+?)\s*</) || from.match(/^([^@]+)/)
  return (m ? m[1].trim() : from).slice(0, 16)
}
function shortDate(dt) {
  if (!dt) return ''
  try {
    const d = new Date(dt)
    if (isNaN(d.getTime())) return ''
    return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
  } catch { return '' }
}

// ── 初始化 ────────────────────────────────────────────────────────────────────
async function init() {
  await Promise.all([dash.loadData(), dash.loadTodos(), dash.loadBriefs()])
}
onMounted(init)
onActivated(init)
</script>

<style scoped>
/* ══════════════════════════════════════════════════════
   DASHBOARD  —  卡片式工作台
   左宽列（日程+Todo）+ 右侧滚动栏（事件流+其他）
   ══════════════════════════════════════════════════════ */

/* ── 事件类型色 ── */
:root {
  --c-meeting:   #6366f1;
  --c-deadline:  #f43f5e;
  --c-task:      #f59e0b;
  --c-reminder:  #10b981;
  --c-milestone: #a855f7;
}

/* ══ 整体 ══ */
.dashboard {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--bg);
}

/* ══ 账号 Tab 栏 ══ */
.account-tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 12px;
  height: 36px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  flex-shrink: 0;
}
.account-tabs::-webkit-scrollbar { height: 0; }
.acc-tab {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 10px;
  height: 26px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11.5px;
  cursor: pointer;
  transition: background .12s, color .12s;
  white-space: nowrap;
  flex-shrink: 0;
}
.acc-tab:hover { background: var(--bg-hover); color: var(--text); }
.acc-tab.active {
  background: var(--accent-dim);
  color: var(--accent);
  font-weight: 600;
}
.acc-tab-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px; height: 16px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  flex-shrink: 0;
}
.acc-tab.active .acc-tab-avatar { background: var(--accent); }
.acc-tab-label {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.acc-tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  line-height: 1;
}

/* ══ 简报栏 ══ */
.brief-bar {
  flex-shrink: 0;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
}
.brief-bar-inner {
  display: flex;
  align-items: stretch;
  gap: 0;
  height: 56px;
  overflow: hidden;
}

/* 今日简报预览区 */
.brief-today {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  min-width: 280px;
  max-width: 320px;
  border-right: 1px solid var(--border);
  flex-shrink: 0;
  transition: background .12s;
}
.brief-today.clickable { cursor: pointer; }
.brief-today.clickable:hover { background: var(--bg-hover); }
.brief-today-icon {
  width: 28px; height: 28px;
  border-radius: 8px;
  background: var(--accent-dim);
  color: var(--accent);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.brief-today-content { flex: 1; min-width: 0; }
.brief-today-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: .04em;
  line-height: 1.2;
}
.brief-today-preview {
  font-size: 11.5px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}
.brief-today-loading {
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 2px;
}
.brief-today-empty {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
  font-style: italic;
}
.brief-arrow {
  color: var(--text-muted);
  flex-shrink: 0;
  opacity: .5;
}

/* 历史简报横向滚动 */
.brief-history {
  flex: 1;
  display: flex;
  align-items: stretch;
  overflow-x: auto;
  gap: 0;
  min-width: 0;
}
.brief-history::-webkit-scrollbar { height: 0; }
.brief-hist-item {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 14px;
  min-width: 120px;
  max-width: 160px;
  border-right: 1px solid var(--border-light);
  cursor: pointer;
  transition: background .12s;
  flex-shrink: 0;
}
.brief-hist-item:hover { background: var(--bg-hover); }
.brief-hist-date {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-muted);
  letter-spacing: .04em;
  line-height: 1.2;
}
.brief-hist-preview {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
  line-height: 1.4;
}

/* 操作区 */
.brief-actions {
  display: flex;
  align-items: center;
  padding: 0 14px;
  flex-shrink: 0;
  border-left: 1px solid var(--border);
}
.brief-extract-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all .15s;
  font-family: inherit;
  white-space: nowrap;
}
.brief-extract-btn:hover:not(:disabled) {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}
.brief-extract-btn:disabled { opacity: .4; cursor: not-allowed; }

/* ══ 主体：左宽 + 右窄 ══ */
.dashboard-body {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 12px;
  padding: 12px;
  overflow: hidden;
  min-height: 0;
}

/* ── 左宽列 ── */
.main-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
  min-height: 0;
}

/* ── 右窄列 ── */
.side-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  min-height: 0;
  padding-right: 2px;
}

/* ══ 卡片基础 ══ */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  flex-shrink: 0;
}

.card-schedule {
  flex-shrink: 0;
}
.card-todo {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.card-events {
  flex-shrink: 0;
}

/* ══ 卡片头部 ══ */
.card-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px 8px;
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
}
.card-hdr-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-icon {
  width: 26px; height: 26px;
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.schedule-icon  { background: rgba(99,102,241,.1);  color: var(--c-meeting); }
.todo-icon      { background: rgba(16,185,129,.1);  color: var(--c-reminder); }
.event-icon     { background: rgba(245,158,11,.1);  color: var(--c-task); }
.countdown-icon { background: rgba(244,63,94,.1);   color: var(--c-deadline); }
.topic-icon     { background: rgba(168,85,247,.1);  color: var(--c-milestone); }
.people-icon    { background: rgba(99,102,241,.1);  color: var(--c-meeting); }
.stat-icon      { background: rgba(16,185,129,.1);  color: var(--c-reminder); }

.card-title {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -.01em;
}
.card-badge {
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 10px;
  font-weight: 800;
  padding: 1px 6px;
  border-radius: 10px;
  font-variant-numeric: tabular-nums;
}
.card-sub {
  font-size: 10px;
  color: var(--text-muted);
  opacity: .7;
}

/* ══ 周日程导航 ══ */
.week-nav {
  display: flex;
  align-items: center;
  gap: 3px;
}
.week-label {
  font-size: 11px;
  color: var(--text-secondary);
  min-width: 80px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.nav-arrow {
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  background: transparent; color: var(--text-muted);
  cursor: pointer; font-size: 16px; line-height: 1;
  transition: all .1s;
}
.nav-arrow:hover { background: var(--bg-hover); color: var(--text-primary); }
.nav-today-btn {
  padding: 2px 8px;
  border: 1px solid rgba(91,94,244,.4);
  border-radius: var(--radius-sm);
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
  transition: background .1s;
  font-family: inherit;
}
.nav-today-btn:hover { background: rgba(91,94,244,.18); }

/* ══ Todo 看板 ══ */
.add-todo-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all .12s;
  font-family: inherit;
}
.add-todo-btn:hover {
  background: var(--accent-dim);
  color: var(--accent);
  border-color: var(--accent);
}
.todo-board {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ══ 事件流 ══ */
.events-list {
  overflow-y: auto;
  max-height: 340px;
  padding: 4px 6px 6px;
}
.card-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 24px 12px;
  color: var(--text-muted);
  font-size: 12px;
  font-style: italic;
}
.event-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 8px 7px 11px;
  border-radius: var(--radius);
  cursor: grab;
  transition: background .12s;
  border: 1px solid transparent;
  margin-bottom: 2px;
  position: relative;
}
.event-item::before {
  content: '';
  position: absolute;
  left: 0; top: 5px; bottom: 5px;
  width: 2.5px;
  border-radius: 2px;
  opacity: .6;
  transition: opacity .12s;
}
.event-item.high::before   { background: var(--c-deadline); }
.event-item.medium::before { background: var(--c-task); }
.event-item.low::before    { background: var(--c-meeting); }
.event-item:hover {
  background: var(--bg-hover);
  border-color: var(--border);
}
.event-item:hover::before { opacity: 1; }

.event-type-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  margin-top: 5px;
  flex-shrink: 0;
}
.event-type-dot.meeting   { background: var(--c-meeting);   box-shadow: 0 0 0 2px rgba(99,102,241,.18); }
.event-type-dot.deadline  { background: var(--c-deadline);  box-shadow: 0 0 0 2px rgba(244,63,94,.18); }
.event-type-dot.task      { background: var(--c-task);      box-shadow: 0 0 0 2px rgba(245,158,11,.18); }
.event-type-dot.reminder  { background: var(--c-reminder);  box-shadow: 0 0 0 2px rgba(16,185,129,.18); }
.event-type-dot.milestone { background: var(--c-milestone); box-shadow: 0 0 0 2px rgba(168,85,247,.18); }

.event-body { flex: 1; min-width: 0; }
.event-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}
.event-meta {
  display: flex;
  gap: 5px;
  margin-top: 2px;
  align-items: center;
}
.event-date { font-size: 10px; color: var(--accent); font-weight: 600; font-variant-numeric: tabular-nums; }
.event-from { font-size: 10px; color: var(--text-muted); }
.event-desc {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.event-tags { display: flex; gap: 3px; flex-wrap: wrap; margin-top: 3px; }
.tag {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--accent-dim);
  color: var(--accent);
}
.event-actions { flex-shrink: 0; }
.ev-btn {
  width: 22px; height: 22px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border); border-radius: 5px;
  background: transparent; color: var(--text-muted);
  cursor: pointer; transition: all .1s;
  opacity: 0;
}
.event-item:hover .ev-btn { opacity: 1; }
.ev-btn:hover { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); }

/* 已加入 Todo 的事件样式 */
.event-item.ev-added {
  opacity: .65;
}
.event-item.ev-added .event-title {
  text-decoration: line-through;
  text-decoration-color: var(--text-muted);
}
.ev-added-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 9px;
  color: #22c55e;
  font-weight: 600;
  letter-spacing: .02em;
}
.ev-btn-added {
  opacity: 1 !important;
  color: #22c55e !important;
  border-color: rgba(34,197,94,.3) !important;
  background: rgba(34,197,94,.06) !important;
}

/* 事件列表动画 */
.event-list-enter-active { transition: all .22s cubic-bezier(.4,0,.2,1); }
.event-list-leave-active { transition: all .18s ease; }
.event-list-enter-from   { opacity: 0; transform: translateX(-8px); }
.event-list-leave-to     { opacity: 0; transform: translateX(-8px); }

/* ══ 倒计时 ══ */
.countdown-list {
  padding: 6px 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.countdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px 8px 13px;
  border-radius: var(--radius);
  background: var(--bg);
  border: 1px solid var(--border);
  position: relative;
  overflow: hidden;
  transition: box-shadow .15s;
}
.countdown-item:hover { box-shadow: var(--shadow-sm); }
.countdown-item.overdue { border-color: rgba(244,63,94,.3); background: rgba(244,63,94,.03); }
.countdown-item.today   { border-color: rgba(245,158,11,.4); background: rgba(245,158,11,.04); }
.countdown-item.soon    { border-color: rgba(91,94,244,.25); }

.countdown-type-bar {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
}
.countdown-type-bar.deadline  { background: var(--c-deadline); }
.countdown-type-bar.milestone { background: var(--c-milestone); }
.countdown-type-bar.task      { background: var(--c-task); }
.countdown-type-bar.meeting   { background: var(--c-meeting); }

.countdown-days {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 36px;
  flex-shrink: 0;
}
.cd-num {
  font-size: 20px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1;
  font-variant-numeric: tabular-nums;
  letter-spacing: -.02em;
}
.cd-num.overdue { font-size: 10px; color: var(--c-deadline); font-weight: 700; letter-spacing: 0; }
.cd-num.urgent  { font-size: 11px; color: var(--c-task); font-weight: 800; letter-spacing: 0; }
.cd-unit { font-size: 9px; color: var(--text-muted); margin-top: 1px; }
.countdown-body { flex: 1; min-width: 0; }
.countdown-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.countdown-date { font-size: 10px; color: var(--text-muted); margin-top: 1px; }

/* ══ 话题 ══ */
/* ── 视图切换按钮 ── */
/* ── 图谱展开按钮 ── */
.graph-open-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: transparent;
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all .12s;
  font-family: inherit;
}
.graph-open-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-dim);
}

/* ── 全屏图谱浮层 ── */
.graph-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0,0,0,.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.graph-overlay-panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: 100%;
  max-width: 1100px;
  height: 80vh;
  overflow: hidden;
}
.graph-overlay-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.graph-overlay-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}
.graph-overlay-hint {
  font-size: 10.5px;
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 4px;
}
.graph-overlay-close {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all .12s;
  flex-shrink: 0;
}
.graph-overlay-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--text-muted);
}
.graph-overlay-body {
  flex: 1;
  overflow: hidden;
  position: relative;
}

/* 浮层动画 */
.graph-overlay-fade-enter-active,
.graph-overlay-fade-leave-active { transition: opacity .2s ease; }
.graph-overlay-fade-enter-active .graph-overlay-panel,
.graph-overlay-fade-leave-active .graph-overlay-panel { transition: transform .2s cubic-bezier(.4,0,.2,1), opacity .2s; }
.graph-overlay-fade-enter-from { opacity: 0; }
.graph-overlay-fade-enter-from .graph-overlay-panel { transform: scale(.96); opacity: 0; }
.graph-overlay-fade-leave-to { opacity: 0; }
.graph-overlay-fade-leave-to .graph-overlay-panel { transform: scale(.96); opacity: 0; }

.topics-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 8px 12px 12px;
}
.topic-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 20px;
  background: var(--bg);
  border: 1px solid var(--border);
  font-size: 11px;
  cursor: default;
  transition: all .12s;
}
.topic-chip:hover { background: var(--accent-dim); border-color: rgba(91,94,244,.3); }
.topic-name { color: var(--text-primary); font-weight: 500; }
.topic-count {
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 9px;
  font-weight: 800;
  padding: 0 5px;
  border-radius: 8px;
  font-variant-numeric: tabular-nums;
}

/* ══ 联系人 ══ */
.people-list { padding: 4px 10px 10px; }
.person-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 6px 4px;
  border-radius: var(--radius);
  transition: background .1s;
}
.person-item:hover { background: var(--bg-hover); }
.person-avatar {
  width: 30px; height: 30px;
  border-radius: 9px;
  background: linear-gradient(135deg, rgba(91,94,244,.18) 0%, rgba(168,85,247,.12) 100%);
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  border: 1px solid rgba(91,94,244,.12);
}
.person-name  { font-size: 12px; color: var(--text-primary); font-weight: 600; }
.person-meta  { font-size: 10px; color: var(--text-muted); margin-top: 1px; }

/* ══ 统计 ══ */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  padding: 8px 10px 12px;
}
.stat-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 8px;
  text-align: center;
  transition: border-color .12s;
}
.stat-card:hover { border-color: rgba(91,94,244,.3); }
.stat-num {
  font-size: 22px;
  font-weight: 800;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -.02em;
  line-height: 1.1;
}
.stat-num.accent { color: var(--accent); }
.stat-lbl { font-size: 9.5px; color: var(--text-muted); margin-top: 2px; }

/* ══ 警告卡片 ══ */
.warn-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--radius);
  background: rgba(245,158,11,.06);
  border: 1px solid rgba(245,158,11,.25);
  font-size: 11.5px;
  color: #d97706;
  flex-shrink: 0;
}

/* ══ 弹窗 ══ */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.45);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 8000;
}
.modal-box {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 22px;
  width: 360px;
  display: flex;
  flex-direction: column;
  gap: 11px;
  box-shadow: var(--shadow-lg);
}
.modal-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -.01em;
}
.modal-input {
  padding: 8px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color .15s, box-shadow .15s;
  font-family: inherit;
}
.modal-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.modal-row { display: flex; gap: 8px; }
.modal-select {
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
  outline: none;
  font-family: inherit;
}
.modal-textarea {
  padding: 8px 11px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--text-primary);
  font-size: 12px;
  resize: none;
  outline: none;
  font-family: inherit;
  line-height: 1.6;
  transition: border-color .15s, box-shadow .15s;
}
.modal-textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.modal-footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 2px; }
.modal-cancel {
  padding: 7px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: transparent;
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
  transition: background .1s;
  font-family: inherit;
}
.modal-cancel:hover { background: var(--bg-hover); }
.modal-submit {
  padding: 7px 18px;
  border: none;
  border-radius: var(--radius);
  background: var(--accent);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .12s, transform .1s;
  font-family: inherit;
}
.modal-submit:disabled { opacity: .35; cursor: not-allowed; }
.modal-submit:hover:not(:disabled) { opacity: .88; }
.modal-submit:active:not(:disabled) { transform: scale(.98); }

.modal-fade-enter-active { transition: opacity .18s, transform .18s cubic-bezier(.4,0,.2,1); }
.modal-fade-leave-active { transition: opacity .14s; }
.modal-fade-enter-from   { opacity: 0; transform: scale(.97) translateY(6px); }
.modal-fade-leave-to     { opacity: 0; }

/* ══ 工具 ══ */
.mini-select {
  padding: 3px 7px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 10.5px;
  cursor: pointer;
  outline: none;
  font-family: inherit;
}
.spinner-xs {
  width: 10px; height: 10px;
  border: 1.5px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin .7s linear infinite;
  display: inline-block;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }
.spinning { animation: spin .7s linear infinite; transform-origin: center; }

/* ── 滚动条 ── */
.side-col::-webkit-scrollbar,
.events-list::-webkit-scrollbar { width: 4px; }
.side-col::-webkit-scrollbar-track,
.events-list::-webkit-scrollbar-track { background: transparent; }
.side-col::-webkit-scrollbar-thumb,
.events-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ══ 倒计时可点击 ══ */
.countdown-item { cursor: pointer; }

/* ══ 联系人箭头 ══ */
.person-item { cursor: pointer; }
.person-arrow { color: var(--text-muted); opacity: 0; flex-shrink: 0; transition: opacity .1s; }
.person-item:hover .person-arrow { opacity: .5; }

/* ══ 话题可点击 ══ */
.topic-chip { cursor: pointer; }

/* ══════════════════════════════════════════════════════
   抽屉式弹窗（Drawer）
   ══════════════════════════════════════════════════════ */
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.38);
  backdrop-filter: blur(3px);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  z-index: 9000;
  padding: 16px;
}

.drawer-panel {
  width: 520px;
  max-width: calc(100vw - 80px);
  height: calc(100vh - 32px);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.drawer-panel-sm {
  width: 400px;
  height: auto;
  max-height: calc(100vh - 80px);
}

/* 弹窗头部 */
.drawer-hdr {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.drawer-hdr-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.drawer-icon {
  width: 36px; height: 36px;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.brief-drawer-icon  { background: var(--accent-dim); color: var(--accent); }
.topic-drawer-icon  { background: rgba(168,85,247,.12); color: var(--c-milestone); }

.drawer-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -.01em;
}
.drawer-sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.drawer-close {
  width: 30px; height: 30px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border); border-radius: 8px;
  background: transparent; color: var(--text-muted);
  cursor: pointer; transition: all .12s;
  flex-shrink: 0;
}
.drawer-close:hover { background: var(--bg-hover); color: var(--text-primary); }

/* 弹窗内容 */
.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
}
.drawer-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
  font-size: 13px;
  padding: 20px 0;
}
.drawer-empty {
  color: var(--text-muted);
  font-size: 12.5px;
  font-style: italic;
  padding: 12px 0;
}

/* 简报全文 */
.brief-full-text {
  font-size: 13.5px;
  color: var(--text-primary);
  line-height: 1.75;
}
.brief-full-text :deep(h1),
.brief-full-text :deep(h2),
.brief-full-text :deep(h3) {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 14px 0 6px;
}
.brief-full-text :deep(p)      { margin: 0 0 8px; }
.brief-full-text :deep(ul)     { margin: 6px 0; padding-left: 20px; }
.brief-full-text :deep(li)     { margin: 3px 0; }
.brief-full-text :deep(strong) { color: var(--accent); font-weight: 700; }
.brief-stats-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--border-light);
  font-size: 11px;
  color: var(--text-muted);
}

/* 事件详情网格 */
.detail-grid {
  display: grid;
  grid-template-columns: 60px 1fr;
  gap: 8px 12px;
  align-items: start;
}
.detail-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: .06em;
  padding-top: 1px;
}
.detail-value {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
  word-break: break-word;
}
.detail-value.accent { color: var(--accent); font-weight: 600; }
.detail-value.muted  { color: var(--text-muted); font-size: 12px; }
.detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 14px;
}
.detail-section-title {
  font-size: 10.5px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: .08em;
  margin-bottom: 8px;
}

/* 类型/优先级徽章 */
.type-badge, .priority-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 10px;
  letter-spacing: .04em;
}
.type-badge.meeting   { background: rgba(99,102,241,.12);  color: var(--c-meeting); }
.type-badge.deadline  { background: rgba(244,63,94,.1);    color: var(--c-deadline); }
.type-badge.task      { background: rgba(245,158,11,.12);  color: var(--c-task); }
.type-badge.reminder  { background: rgba(16,185,129,.1);   color: var(--c-reminder); }
.type-badge.milestone { background: rgba(168,85,247,.1);   color: var(--c-milestone); }
.priority-badge.high   { background: rgba(244,63,94,.08);  color: var(--c-deadline); }
.priority-badge.medium { background: rgba(245,158,11,.08); color: var(--c-task); }
.priority-badge.low    { background: rgba(16,185,129,.08); color: var(--c-reminder); }

/* 类型圆点（大/小） */
.type-dot-lg, .type-dot-sm {
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.type-dot-lg { width: 10px; height: 10px; }
.type-dot-sm { width: 7px; height: 7px; }
.type-dot-lg.meeting, .type-dot-sm.meeting   { background: var(--c-meeting); }
.type-dot-lg.deadline, .type-dot-sm.deadline { background: var(--c-deadline); }
.type-dot-lg.task, .type-dot-sm.task         { background: var(--c-task); }
.type-dot-lg.reminder, .type-dot-sm.reminder { background: var(--c-reminder); }
.type-dot-lg.milestone, .type-dot-sm.milestone { background: var(--c-milestone); }

/* 话题相关事件列表 */
.topic-events { margin-top: 8px; }
.topic-event-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 6px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background .1s;
}
.topic-event-item:hover { background: var(--bg-hover); }
.topic-event-title {
  flex: 1;
  font-size: 12.5px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.topic-event-date { font-size: 10.5px; color: var(--text-muted); flex-shrink: 0; }

/* 联系人大头像 */
.person-avatar-lg {
  width: 40px; height: 40px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(91,94,244,.2) 0%, rgba(168,85,247,.14) 100%);
  color: var(--accent);
  font-size: 16px;
  font-weight: 800;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  border: 1px solid rgba(91,94,244,.15);
}

/* 弹窗底部操作 */
.drawer-actions {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--border-light);
  display: flex;
  gap: 8px;
}
.drawer-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all .12s;
  font-family: inherit;
}
.drawer-action-btn:hover {
  background: var(--accent-dim);
  color: var(--accent);
  border-color: var(--accent);
}
.drawer-action-added {
  color: #22c55e;
  border-color: rgba(34,197,94,.3);
  background: rgba(34,197,94,.06);
}
.drawer-action-added:hover {
  color: #16a34a;
  border-color: rgba(34,197,94,.5);
  background: rgba(34,197,94,.12);
}

/* 事件详情图标背景 */
.type-icon-meeting   { background: rgba(99,102,241,.1); }
.type-icon-deadline  { background: rgba(244,63,94,.1); }
.type-icon-task      { background: rgba(245,158,11,.1); }
.type-icon-reminder  { background: rgba(16,185,129,.1); }
.type-icon-milestone { background: rgba(168,85,247,.1); }

/* 弹窗动画 */
.drawer-fade-enter-active { transition: opacity .2s, transform .2s cubic-bezier(.4,0,.2,1); }
.drawer-fade-leave-active { transition: opacity .15s, transform .15s ease; }
.drawer-fade-enter-from   { opacity: 0; transform: translateX(24px); }
.drawer-fade-leave-to     { opacity: 0; transform: translateX(16px); }

/* 弹窗滚动条 */
.drawer-body::-webkit-scrollbar { width: 4px; }
.drawer-body::-webkit-scrollbar-track { background: transparent; }
.drawer-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
