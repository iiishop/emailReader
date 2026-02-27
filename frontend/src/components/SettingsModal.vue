<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="visible" class="modal-overlay" @click.self="cancel">
        <div class="modal-card" role="dialog" aria-modal="true" aria-label="设置">

          <!-- 标题栏 -->
          <div class="modal-header">
            <div class="modal-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
                <path d="M12 2v2M12 20v2M2 12h2M20 12h2"/>
              </svg>
              设置
            </div>
            <button class="close-btn" @click="cancel" title="关闭">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          <!-- 内容 -->
          <div class="modal-body">

            <!-- ── AI 连接配置 ── -->
            <section class="section">
              <div class="section-title">AI 连接配置</div>

              <div class="field">
                <label class="field-label">API 地址</label>
                <input
                  v-model="form.apiBaseUrl"
                  class="field-input"
                  type="url"
                  placeholder="https://api.openai.com/v1"
                  spellcheck="false"
                />
                <div class="url-examples">
                  <span class="url-ex-label">常用地址：</span>
                  <button type="button" class="url-ex-btn" @click="form.apiBaseUrl = 'https://api.deepseek.com/v1'">DeepSeek</button>
                  <button type="button" class="url-ex-btn" @click="form.apiBaseUrl = 'https://api.openai.com/v1'">OpenAI</button>
                  <button type="button" class="url-ex-btn" @click="form.apiBaseUrl = 'http://localhost:11434/v1'">Ollama</button>
                </div>
              </div>

              <div class="field">
                <label class="field-label">API Key</label>
                <div class="input-row">
                  <input
                    v-model="form.apiKey"
                    class="field-input"
                    :type="showKey ? 'text' : 'password'"
                    placeholder="sk-..."
                    spellcheck="false"
                  />
                  <button class="icon-btn-sm" @click="showKey = !showKey" :title="showKey ? '隐藏' : '显示'">
                    <!-- 眼睛开 -->
                    <svg v-if="showKey" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20C7 20 2.73 16.39 1 12c.74-1.9 2-3.6 3.6-4.9M9.88 9.88A3 3 0 0 1 15 12M21 21 3 3"/>
                      <path d="M10.73 5.08A10 10 0 0 1 12 5c5 0 9.27 3.61 11 8a10.09 10.09 0 0 1-1.6 2.92"/>
                    </svg>
                    <!-- 眼睛关 -->
                    <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M1 12C2.73 7.61 7 4 12 4c5 0 9.27 3.61 11 8-1.73 4.39-6 8-11 8-5 0-9.27-3.61-11-8z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                  </button>
                </div>
              </div>

              <!-- 测试按钮 + 状态 -->
              <div class="test-row">
                <button
                  class="btn btn-secondary"
                  @click="testConnection"
                  :disabled="testing || !form.apiBaseUrl"
                >
                  <span v-if="testing" class="spinner-xs"></span>
                  <span>{{ testing ? '测试中…' : '测试连接' }}</span>
                </button>
                <div v-if="testResult?.success" class="test-status ok">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                  <span>连接成功，共 {{ testResult.models.length }} 个模型</span>
                </div>
              </div>
              <!-- 错误信息单独一行，完整展示 -->
              <div v-if="testResult && !testResult.success" class="test-error">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0;margin-top:1px">
                  <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <span>{{ testResult.error || '连接失败（未知错误，请查看后端日志）' }}</span>
              </div>

              <!-- 测试成功且有模型列表：显示单选列表 -->
              <Transition name="fade">
                <div v-if="testResult?.success && testResult.models.length" class="field">
                  <label class="field-label">使用模型</label>
                  <div class="model-list">
                    <label
                      v-for="m in testResult.models"
                      :key="m"
                      class="model-option"
                      :class="{ selected: form.selectedModel === m }"
                    >
                      <input type="radio" :value="m" v-model="form.selectedModel" />
                      <span class="model-name">{{ m }}</span>
                      <span v-if="form.selectedModel === m" class="model-check">✓</span>
                    </label>
                  </div>
                </div>
              </Transition>

              <!-- 测试成功但 API 不支持 /models：提示手动输入 -->
              <Transition name="fade">
                <div v-if="testResult?.success && testResult.no_models_endpoint" class="no-models-hint">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  <span>{{ testResult.note }}</span>
                </div>
              </Transition>

              <!-- 手动输入模型名（未测试 或 API 不支持列表时显示） -->
              <div v-if="!testResult || testResult.no_models_endpoint" class="field">
                <label class="field-label">
                  模型名称
                  <span class="field-label-sub">（手动填写，如 gpt-4o、deepseek-chat）</span>
                </label>
                <input
                  v-model="form.selectedModel"
                  class="field-input"
                  type="text"
                  placeholder="请输入模型名称"
                  spellcheck="false"
                />
              </div>

              <!-- 已保存的模型且本次未测试时，额外展示 tag 提示 -->
              <div v-if="!testResult && form.selectedModel" class="current-model">
                <span class="field-label">当前已选</span>
                <span class="model-tag">{{ form.selectedModel }}</span>
              </div>
            </section>

            <div class="divider"></div>

            <!-- ── AI 邮件范围 ── -->
            <section class="section">
              <div class="section-title">AI 邮件范围</div>
              <div class="section-desc">
                AI 只读取最近 N 天内的邮件，避免加载过多历史邮件消耗大量 Token。
                设为"不限"时将处理全部本地邮件。
              </div>

              <!-- 快捷选项 -->
              <div class="days-pills">
                <button
                  v-for="opt in DAY_OPTIONS"
                  :key="opt.value"
                  class="day-pill"
                  :class="{ active: form.aiDays === opt.value && !customDays }"
                  @click="setPresetDays(opt.value)"
                >{{ opt.label }}</button>
                <button
                  class="day-pill"
                  :class="{ active: customDays }"
                  @click="enableCustomDays"
                >自定义</button>
              </div>

              <!-- 自定义天数输入 -->
              <Transition name="fade">
                <div v-if="customDays" class="custom-days-row">
                  <input
                    v-model.number="form.aiDays"
                    class="field-input days-input"
                    type="number"
                    min="1"
                    max="3650"
                    placeholder="天数"
                  />
                  <span class="days-unit">天</span>
                </div>
              </Transition>

              <!-- 当前选择说明 -->
              <div class="days-desc">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                </svg>
                <span>{{ daysDesc }}</span>
              </div>
            </section>

            <div class="divider"></div>

            <!-- ── RAG 相关性阈值 ── -->
            <section class="section">
              <div class="section-title">RAG 相关性阈值</div>
              <div class="section-desc">
                AI 助手对每封邮件打分（0~100%）。只有相关性达到阈值的邮件才会被纳入上下文，降低 Token 消耗。
              </div>
              <div class="field">
                <label class="field-label">
                  相关性阈值：<strong>{{ form.relevanceThreshold }}%</strong>
                </label>
                <div class="threshold-row">
                  <span class="threshold-hint">低（更多邮件）</span>
                  <input
                    v-model.number="form.relevanceThreshold"
                    class="threshold-slider"
                    type="range"
                    min="0"
                    max="100"
                    step="5"
                  />
                  <span class="threshold-hint">高（更精准）</span>
                </div>
                <div class="threshold-pills">
                  <button
                    v-for="v in [40, 50, 60, 70, 80]"
                    :key="v"
                    class="pill-btn"
                    :class="{ active: form.relevanceThreshold === v }"
                    @click="form.relevanceThreshold = v"
                  >{{ v }}%</button>
                </div>
                <div class="hint-text">
                  低于 {{ form.relevanceThreshold }}% 相关性的邮件将被过滤，不送入 AI 上下文
                </div>
              </div>
            </section>

            <div class="divider"></div>

            <!-- ── AI 人设 / 系统提示词 ── -->
            <section class="section">
              <div class="section-title">AI 人设 / 系统提示词</div>
              <div class="section-desc">
                定义 AI 助手的语气和个性。功能性指令由程序自动附加，无需在此填写。
              </div>
              <textarea
                v-model="form.systemPrompt"
                class="prompt-textarea"
                placeholder="例如：你是一个邮件助手，请用简洁、专业的语气回复…"
                rows="5"
              ></textarea>
            </section>

            <!-- ── 自动刷新 ── -->
            <section class="section">
              <div class="section-title">自动刷新</div>
              <div class="field">
                <label class="field-label">刷新间隔</label>
                <div class="pill-group">
                  <button
                    v-for="opt in REFRESH_OPTIONS"
                    :key="opt.value"
                    class="pill-btn"
                    :class="{ active: !customRefresh && form.refreshInterval === opt.value }"
                    @click="setPresetRefresh(opt.value)"
                  >{{ opt.label }}</button>
                  <button
                    class="pill-btn"
                    :class="{ active: customRefresh }"
                    @click="enableCustomRefresh"
                  >自定义</button>
                </div>
                <div v-if="customRefresh" class="custom-input-row">
                  <input
                    v-model.number="form.refreshInterval"
                    class="field-input custom-num"
                    type="number"
                    min="1"
                    max="1440"
                    placeholder="分钟数"
                  />
                  <span class="unit-hint">分钟</span>
                </div>
                <div class="hint-text">
                  <template v-if="form.refreshInterval === 0">已关闭自动刷新，仅手动刷新或切换文件夹时更新</template>
                  <template v-else>每 {{ form.refreshInterval }} 分钟自动刷新当前文件夹</template>
                </div>
              </div>
            </section>
          </div>

          <!-- 保存失败提示 -->
          <div v-if="saveError" class="save-error">{{ saveError }}</div>
          <!-- 底部按钮 -->
          <div class="modal-footer">
            <button class="btn btn-ghost" @click="cancel">取消</button>
            <button class="btn btn-primary" @click="saveSettings" :disabled="!canSave">
              保存设置
            </button>
          </div>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { useSettingsStore } from '../stores/settings.js'

const props = defineProps({ visible: Boolean })
const emit = defineEmits(['update:visible'])

const settingsStore = useSettingsStore()

// 本地表单（不直接改 store，保存时才写入）
const form = reactive({
  apiBaseUrl:         '',
  apiKey:             '',
  selectedModel:      '',
  systemPrompt:       '',
  aiDays:             7,
  relevanceThreshold: 60,
  refreshInterval:    5,
})

// ── 天数选择 ──────────────────────────────────────────────────────────────
const DAY_OPTIONS = [
  { label: '1 天',  value: 1  },
  { label: '3 天',  value: 3  },
  { label: '7 天',  value: 7  },
  { label: '14 天', value: 14 },
  { label: '30 天', value: 30 },
  { label: '90 天', value: 90 },
  { label: '不限',  value: 0  },
]
const PRESET_VALUES = DAY_OPTIONS.map(o => o.value)
const customDays = ref(false)

// ── 刷新间隔选择 ───────────────────────────────────────────────────────────
const REFRESH_OPTIONS = [
  { label: '关闭', value: 0  },
  { label: '1 分', value: 1  },
  { label: '3 分', value: 3  },
  { label: '5 分', value: 5  },
  { label: '10 分', value: 10 },
  { label: '30 分', value: 30 },
]
const REFRESH_PRESET_VALUES = REFRESH_OPTIONS.map(o => o.value)
const customRefresh = ref(false)

function setPresetRefresh(val) {
  form.refreshInterval = val
  customRefresh.value = false
}
function enableCustomRefresh() {
  customRefresh.value = true
  if (REFRESH_PRESET_VALUES.includes(form.refreshInterval)) form.refreshInterval = 15
}

function setPresetDays(val) {
  form.aiDays = val
  customDays.value = false
}
function enableCustomDays() {
  customDays.value = true
  if (PRESET_VALUES.includes(form.aiDays)) form.aiDays = 14
}

const daysDesc = computed(() => {
  if (form.aiDays === 0) return 'AI 将读取全部历史邮件（可能消耗大量 Token）'
  return `AI 只读取最近 ${form.aiDays} 天内的邮件`
})

const showKey   = ref(false)
const testing   = ref(false)
const testResult = ref(null)  // { success, models?, error? }

// 打开弹窗时，从 store 同步到表单
watch(() => props.visible, (v) => {
  if (v) {
    form.apiBaseUrl    = settingsStore.apiBaseUrl
    form.apiKey        = settingsStore.apiKey
    form.selectedModel = settingsStore.selectedModel
    form.systemPrompt  = settingsStore.systemPrompt
    form.aiDays             = settingsStore.aiDays
    form.relevanceThreshold = settingsStore.relevanceThreshold ?? 60
    form.refreshInterval    = settingsStore.refreshInterval
    customDays.value     = !PRESET_VALUES.includes(settingsStore.aiDays)
    customRefresh.value  = !REFRESH_PRESET_VALUES.includes(settingsStore.refreshInterval)
    testResult.value     = null
    showKey.value        = false
    saveError.value      = null
  }
})

const canSave = computed(() =>
  form.apiBaseUrl.trim() && form.apiKey.trim() && form.selectedModel.trim()
)

async function testConnection() {
  testing.value = true
  testResult.value = null
  try {
    const res = await fetch('/api/ai/test-connection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url: form.apiBaseUrl, api_key: form.apiKey }),
    })

    let data
    try {
      data = await res.json()
    } catch {
      testResult.value = { success: false, error: `服务器返回了非 JSON 响应（HTTP ${res.status}）` }
      return
    }

    // FastAPI 自身的错误格式是 {detail: "..."} 而不是我们的 {success, error}
    if (!res.ok) {
      const msg = data?.detail
        ?? data?.message
        ?? data?.error
        ?? `服务器错误 HTTP ${res.status}`
      testResult.value = { success: false, error: String(msg) }
      return
    }

    // 正常业务响应
    if (data.success === undefined && data.detail) {
      testResult.value = { success: false, error: String(data.detail) }
      return
    }

    testResult.value = {
      ...data,
      // 确保 error 字段一定是字符串，防止空框
      error: data.error ? String(data.error) : '连接失败（服务器未返回错误详情）',
    }

    if (data.success && data.models?.length && !form.selectedModel) {
      form.selectedModel = data.models[0]
    }
  } catch (e) {
    testResult.value = { success: false, error: e.message || '网络请求失败，请检查后端服务是否运行' }
  } finally {
    testing.value = false
  }
}

const saveError = ref(null)
async function saveSettings() {
  saveError.value = null
  settingsStore.apiBaseUrl    = form.apiBaseUrl
  settingsStore.apiKey        = form.apiKey
  settingsStore.selectedModel = form.selectedModel
  settingsStore.systemPrompt  = form.systemPrompt
  settingsStore.aiDays             = Number(form.aiDays) || 7
  settingsStore.relevanceThreshold = Number(form.relevanceThreshold) ?? 60
  settingsStore.refreshInterval    = Number(form.refreshInterval) ?? 5
  try {
    await settingsStore.save()
    emit('update:visible', false)
  } catch (e) {
    saveError.value = e.message || '配置保存失败，请查看终端或重试'
  }
}

function cancel() {
  emit('update:visible', false)
}
</script>

<style scoped>
/* ── 遮罩层 ── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

/* ── 弹窗主体 ── */
.modal-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.25);
  width: 100%;
  max-width: 520px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── 标题栏 ── */
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.close-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background .12s, color .12s;
}
.close-btn:hover { background: var(--bg-hover); color: var(--text-primary); }

/* ── 内容区 ── */
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.section { padding-bottom: 4px; }
.section-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text-muted);
  margin-bottom: 14px;
}
.section-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 12px;
  line-height: 1.6;
}
.divider {
  height: 1px;
  background: var(--border);
  margin: 20px 0;
}

/* ── 表单字段 ── */
.field { margin-bottom: 14px; }
.field-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.field-input {
  width: 100%;
  padding: 8px 11px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color .15s, box-shadow .15s;
  font-family: inherit;
}
.field-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(99,102,241,.12);
}
.field-input::placeholder { color: var(--text-muted); }

.input-row {
  display: flex;
  gap: 6px;
}
.input-row .field-input { flex: 1; }
.icon-btn-sm {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color .12s, background .12s;
}
.icon-btn-sm:hover { background: var(--bg-hover); color: var(--text-primary); }

/* ── 测试按钮行 ── */
.test-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.test-status {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 500;
}
.test-status.ok { color: var(--success); }

/* 错误信息独占一行，可换行显示完整内容 */
.test-error {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(239, 68, 68, .08);
  border: 1px solid rgba(239, 68, 68, .2);
  color: #ef4444;
  font-size: 12px;
  line-height: 1.55;
  word-break: break-all;
}

/* ── 模型列表 ── */
.model-list {
  max-height: 180px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
}
.model-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  transition: background .1s;
  border-bottom: 1px solid var(--border);
}
.model-option:last-child { border-bottom: none; }
.model-option:hover { background: var(--bg-hover); }
.model-option.selected { background: rgba(99,102,241,.08); }
.model-option input[type="radio"] { display: none; }
.model-name {
  flex: 1;
  font-size: 12px;
  font-family: 'Consolas', 'Menlo', monospace;
  color: var(--text-primary);
}
.model-check { color: var(--accent); font-size: 12px; font-weight: 700; }

/* ── 天数选择 ── */
.days-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.day-pill {
  padding: 5px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all .15s;
}
.day-pill:hover { background: var(--bg-hover); border-color: var(--accent); color: var(--accent); }
.day-pill.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.custom-days-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.days-input { width: 100px !important; }
.days-unit { font-size: 13px; color: var(--text-secondary); }
.days-desc {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

/* 不支持 /models 时的提示条 */
.no-models-hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(99,102,241,.08);
  border: 1px solid rgba(99,102,241,.2);
  color: var(--accent);
  font-size: 12px;
  line-height: 1.55;
  margin-bottom: 12px;
}
.no-models-hint svg { flex-shrink: 0; margin-top: 1px; }

.field-label-sub {
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 4px;
}

.current-model {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}
.model-tag {
  background: rgba(99,102,241,.1);
  color: var(--accent);
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 12px;
  font-family: 'Consolas', 'Menlo', monospace;
}

/* ── 提示词 ── */
.prompt-textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  transition: border-color .15s, box-shadow .15s;
  font-family: inherit;
}
.prompt-textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(99,102,241,.12);
}

/* ── 底部 ── */
.save-error {
  padding: 8px 20px;
  color: var(--color-error, #c00);
  font-size: 13px;
  background: rgba(200, 0, 0, 0.08);
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

/* ── 按钮 ── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: background .15s, opacity .15s;
}
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn-primary {
  background: var(--accent);
  color: #fff;
}
.btn-primary:not(:disabled):hover { background: var(--accent-light); }
.btn-secondary {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-primary);
}
.btn-secondary:not(:disabled):hover { background: var(--bg-hover); }
.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
}
.btn-ghost:hover { background: var(--bg-hover); }

/* ── 过渡动画 ── */
.modal-enter-active,
.modal-leave-active {
  transition: opacity .2s ease;
}
.modal-enter-active .modal-card,
.modal-leave-active .modal-card {
  transition: transform .2s cubic-bezier(0.34, 1.20, 0.64, 1), opacity .2s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from .modal-card {
  transform: scale(0.94) translateY(-12px);
  opacity: 0;
}
.modal-leave-to .modal-card {
  transform: scale(0.96) translateY(-6px);
  opacity: 0;
}

.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ── 加载小圆圈 ── */
.spinner-xs {
  width: 12px; height: 12px;
  border: 2px solid rgba(255,255,255,.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin .65s linear infinite;
  flex-shrink: 0;
}
[data-theme="light"] .spinner-xs,
:root:not([data-theme="dark"]) .btn-secondary .spinner-xs {
  border-color: rgba(0,0,0,.15);
  border-top-color: var(--accent);
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── API 地址快捷填写 ── */
.url-examples {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.url-ex-label {
  font-size: 11px;
  color: var(--text-muted);
}
.url-ex-btn {
  padding: 2px 9px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition: border-color .12s, color .12s, background .12s;
}
.url-ex-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(99,102,241,.06);
}

/* ── 相关性阈值滑块 ── */
.threshold-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 8px 0;
}
.threshold-slider {
  flex: 1;
  accent-color: var(--accent);
  cursor: pointer;
  height: 4px;
}
.threshold-hint {
  font-size: 10px;
  color: var(--text-muted);
  white-space: nowrap;
}
.threshold-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

/* ── 通用胶囊选项（刷新间隔、阈值快捷按钮） ── */
.pill-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.pill-btn {
  padding: 5px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all .15s;
}
.pill-btn:hover { background: var(--bg-hover); border-color: var(--accent); color: var(--accent); }
.pill-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.custom-input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.custom-num { width: 100px !important; }
.unit-hint  { font-size: 13px; color: var(--text-secondary); }
</style>
