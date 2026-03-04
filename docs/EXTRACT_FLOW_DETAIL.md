# 提取流程详解

本文档详细介绍「工作台事件提取」的完整流程：从邮件读取、AI 解析、日期处理、任务/事件区分，到前端倒计时的生成与展示。

---

## 一、整体流程概览

```
前端点击「提取」或自动触发
    → POST /api/dashboard/extract（带 base_url、api_key、model、ai_days 等）
    → 后端 _do_extract(req) 异步执行
    → 按账号 × 文件夹遍历 mbox，按 ai_days 过滤邮件
    → 每批邮件：读正文 → 调用 AI 提取 JSON 事件列表 → 解析 + 日期补全
    → 去重、与已有事件合并、过滤已删除
    → 生成话题/联系人/简报
    → 写回 dashboard.json
    → 前端轮询 GET /api/dashboard/data 拿到 events，再算倒计时/任务/事件
```

---

## 二、提取前的数据准备

### 2.1 范围与来源

- **账号**：Thunderbird 配置中所有有 `mail_dir` 的账号。
- **文件夹**：每账号最多 `max_folders_per_account`（默认 3）个，**INBOX 优先**，再按名称排序。
- **邮件列表**：每个文件夹用 `MboxIndex.get(mbox_path)` 得到索引（按日期倒序），再按「邮件日期 ≥ 今天 - ai_days」过滤，最多保留 `max_emails_per_folder`（如 500）封。
- **增量**：每封邮件对应一个「复合键」`account_email|folder_id|key`，若已在 `extracted_keys.json` 中则**跳过**（除非本次是「强制重新提取」）。

### 2.2 发给 AI 的邮件结构

每封邮件会整理成如下结构（见 `_read_folder_bodies`）：

```python
{
    "key":           "邮件 key（mbox 内唯一）",
    "subject":       "主题",
    "from":          "发件人",
    "date":          "原始 Date 头（如 RFC 格式）",
    "received_date": "规范化后的 YYYY-MM-DD（_normalize_mail_date）",
    "body":          "正文（最多 max_chars_per_email 字符）"
}
```

- **received_date**：由 `_normalize_mail_date(raw)` 从邮件 Date 头解析出 `YYYY-MM-DD`，供 AI 做「相对日期」基准（如「本周四」要以邮件接收日为准换算）。

---

## 三、AI 提取与 Prompt 规则

### 3.1 使用的 Prompt

- **System**：`prompts.yaml` 中 `extract.system`，包含：
  - **事件 vs 任务** 的严格区分（见下节）
  - **type**：meeting / deadline / task / reminder / milestone
  - **时间规则**：优先正文真实日期、相对日期以 received_date 为基准、只写日期时不要补 00:00 等
  - **输出格式**：严格 JSON 数组，每项含 type、kind、title、datetime、source_key、reason 等
- **User**：`extract.user_template`，注入「今天日期」「邮件数量」「用户删除反馈」以及 **emails_json**（上面那一批邮件的 JSON）。

### 3.2 任务（task）与事件（event）的区分

由 **kind** 字段决定，且必须在 prompt 里遵守：

| kind   | 含义           | 典型例子 |
|--------|----------------|----------|
| `event` | **已发生**，仅作提醒，无后续待办 | 充值成功、包裹已送达、订单已确认、权限已激活 |
| `task`  | **有未来待办**，需要用户行动     | 下周一汇报、会议、截止日期、待回复、待支付、待提交 |

- **type** 是分类标签（meeting / deadline / task / reminder / milestone），**kind** 才是「事件 vs 任务」的判定字段。
- 后端解析到 AI 返回的列表后，会对每条 `ev.setdefault("kind", "task")`，即未填时默认为任务。

### 3.3 时间字段与相对日期

- **datetime**：ISO 日期或日期时间，如 `2026-03-05` 或 `2026-03-05T14:00:00`。
- Prompt 要求：
  - 正文有明确日期/时间时，必须填 **datetime**（否则倒计时等无法展示）。
  - 正文出现「本周四」「下周一」等时，以该邮件的 **received_date** 为基准换算成**具体日期**再填 datetime，而不是填邮件接收日。
- 每封邮件里的 **received_date** 就是给 AI 做相对日期换算的基准。

---

## 四、解析与日期补全（后端）

### 4.1 JSON 解析容错

AI 返回的字符串可能带 markdown 代码块或小错误，后端会用 `_parse_extract_json(raw)` 做容错：

- 去掉 ``` 代码块外壳
- 去掉 `]` / `}` 前的**尾部逗号**
- 将形如 `'key':` 的**单引号键名**改为双引号
- **缺逗号**：在「值结尾的 `"`」与「下一键的 `"`」之间补逗号
- **值内未转义双引号**（如 description 里「礼"物」）：转义为 `\"`
- 若仍失败，会尝试只取第一个 `[` 到最后一个 `]` 之间的内容再解析

### 4.2 每条事件写入的字段

解析成功后，对每条事件：

- `ev.setdefault("kind", "task")`
- `ev["account"]` = 当前账号邮箱
- `ev["folder"]` = 当前文件夹名（如 INBOX）
- 调用 **`_patch_event_datetime_from_mail(ev, key_to_date)`** 做日期补全

### 4.4 datetime 校验与修正（_sanitize_event_datetime）

在 `_patch_event_datetime_from_mail` 之后会再执行一次 **\_sanitize_event_datetime**，用于：

1. **错误年份修正**：若 `datetime` 的年份不在 2020–2030（如 AI 笔误 2612），则改为当前年（如 2026），避免倒计时出现“几百年后”。
2. **deadline 类从 description 兜底**：对 `type === "deadline"` 且满足下列之一时：
   - 当前 `datetime` 等于该邮件 `received_date`（AI 可能只填了邮件日），或
   - 上一步刚做过错误年份修正，
   会从 `description`（及 `title`）中用正则抽取明确日期（如 `2026年3月28日`、`3月8日`、`2026/Mar/18`）。若抽到且该日期 ≥ 邮件日，则用该日期覆盖 `datetime`，使倒计时更贴近正文截止日。

前端倒计时在计算时也会**排除年份异常**（如不在 2020–2030）的条目，作为兜底。

### 4.5 日期补全规则（_patch_event_datetime_from_mail）

`key_to_date` 来自本批邮件：`key → received_date`（YYYY-MM-DD）。

补全逻辑（**仅当**该事件有对应邮件日期时）：

1. **datetime 为空**  
   → 直接设为该邮件的 `received_date`（YYYY-MM-DD）。

2. **datetime 仅为日期**（匹配 `^\d{4}-\d{2}-\d{2}$`，如 `2026-03-05`）  
   → **仅当**该日期与邮件 `received_date` **相同**时，才视为占位并用 `received_date` 替换；  
   → 若不同（例如 AI 已按「本周四」算出 2026-03-05，而邮件日是 2026-03-02），**保留 AI 的日期**，不覆盖。

3. **datetime 带时间**（如 `2026-03-05T14:00:00`）  
   → 若是**整点占位**（00:00、08:00、16:00，且分秒为 0），则用 `received_date` 替换；否则**不修改**，保留 AI 给出的时间。

因此：**AI 已推断出的具体日期（含相对日期换算）会保留；仅当「仅日期且等于邮件日」或「占位整点」时才用邮件接收日替换。**

---

## 五、去重、合并与删除过滤

### 5.1 去重

- 先按 `(title, datetime)` 去重：`key = f"{ev.get('title','')}|{ev.get('datetime','')}"`，相同则只保留一条。

### 5.2 与已有数据合并

- 已有事件来自 `dashboard.json` 的 `events`。
- 合并键为 **source_key**（邮件 key）：`ev_by_key[e["source_key"]] = e`，**新结果覆盖旧**。
- 再按 `(title, datetime)` 做一次去重。

### 5.3 过滤已删除

- 用户删除过的事件 ID 会写入 `dashboard.json` 的 **deleted_event_ids**（每条 ID 为 `title|datetime|source_key`）。
- 合并后的列表会**排除**这些 ID，写入和返回给前端的 `events` 中都不会再包含已删除项；重新提取时同样会过滤，因此删除是持久化的。

### 5.4 话题与联系人

- **topics**：从合并后事件的 `tags` 聚合（按出现次数排序，取前 20）。
- **people**：从本批与历史的邮件元数据（发件人）聚合，规范化后按联系次数排序。

---

## 六、前端如何区分「任务」与「事件」

数据来源：`GET /api/dashboard/data` 返回的 `events` 数组，前端写入 `dashboardData` store 的 `events`。

- **filteredEvents**：按当前选中账号过滤后的全部条目（事件 + 任务）。
- **filteredPastEvents**：`filteredEvents` 中 **kind === 'event'** 的项 → 展示在「已发生事件」区域。
- **filteredTasks**：`filteredEvents` 中 **kind === 'task'** 的项 → 展示在「任务（待办）」、周日程、以及**倒计时**。

即：**任务 / 事件的区分完全由每条 event 的 `kind` 决定**，与 `type`（meeting/deadline/task/reminder/milestone）无关；`type` 只用于分类标签和样式。

---

## 七、倒计时如何生成与时间从哪来

### 7.1 数据来源

- 倒计时**只从「任务」里出**：使用的是 **filteredTasks**（即 `kind === 'task'` 且通过账号过滤后的事件）。
- 每条任务的 **datetime** 即「截止/到期时间」，来自：
  1. AI 从邮件正文中提取的日期或日期时间；
  2. 若 AI 只给了日期或占位整点，则被 **`_patch_event_datetime_from_mail`** 替换为对应邮件的 **received_date**（见第四节）。

因此：**倒计时的时间 = 每条任务的 `datetime` 字段**，该字段要么是 AI 解析出的真实截止/会议时间（含相对日期换算），要么是邮件接收日（补全逻辑触发时）。

### 7.2 前端计算方式（countdowns）

在 `frontend/src/stores/dashboardData.js` 中：

```javascript
// 未来 7 天内的倒计时（仅任务 kind=task，有明确日期）
const countdowns = computed(() => {
  const now = Date.now()
  const types = ['deadline', 'milestone', 'task', 'meeting', 'reminder']
  return filteredTasks.value
    .filter(e => types.includes(e.type) && e.datetime)
    .map(e => {
      const ts = new Date(e.datetime).getTime()
      return { ...e, _ts: ts, _diffMs: ts - now }
    })
    .filter(e => e._ts > now - 86400000)   // 只保留「未过期或刚过期 1 天内」
    .sort((a, b) => a._ts - b._ts)
    .slice(0, 10)   // 最多 10 条
})
```

- **筛选**：在 **filteredTasks** 中再筛 `type` 属于 deadline/milestone/task/meeting/reminder 且 **有 datetime**。
- **时间**：`new Date(e.datetime).getTime()`，即用 **event.datetime** 的 ISO 字符串转成时间戳。
- **_diffMs**：`ts - now`，正数表示未到期，负数表示已过期；用于展示「还剩 N 天」或「已过期」。
- **展示范围**：只保留 `_ts > now - 86400000`（约「今天 0 点往前 1 天」），再按时间排序取前 10 条。

所以：**倒计时的时间完全由每条任务的 `datetime` 决定**，该字段在提取阶段由 AI 与 `_patch_event_datetime_from_mail` 共同确定（见第二、四节）。

---

## 八、日期在前端的展示格式

- **datetime** 在后端和接口里始终是 **ISO 字符串**（如 `2026-03-05` 或 `2026-03-05T14:00:00`），不做「格式化存储」。
- 前端展示时再按需格式化，例如：
  - 列表中的「事件日期」：`formatEventDate(ev.datetime)` 等（今天显示时间，近期显示「周X」，更早显示月/日等）。
  - 倒计时：用 `_diffMs` 换算成「N 天」或「今天」「已过期」等。

---

## 九、流程小结表

| 环节           | 日期/时间来源说明 |
|----------------|-------------------|
| 发给 AI        | 每封邮件带 `received_date`（YYYY-MM-DD），供相对日期换算 |
| AI 输出        | 每条事件带 `datetime`（ISO），可为仅日期或带时分 |
| _patch_event_datetime_from_mail | 仅日期或占位整点时用邮件 `received_date` 替换 |
| 写入 dashboard | `events` 中每条保留 `datetime`、`kind`、`type` 等 |
| 前端任务/事件  | `kind === 'task'` → 任务；`kind === 'event'` → 已发生事件 |
| 前端倒计时     | 从 **filteredTasks** 中取有 **datetime** 且 type 在约定列表中的项，用 `e.datetime` 算 `_ts` 和 `_diffMs`，排序取前 10 |

若你希望调整「仅日期时是否用邮件日替换」或倒计时的筛选规则，可以在此基础上改 `_patch_event_datetime_from_mail` 或前端的 `countdowns` 计算逻辑。
