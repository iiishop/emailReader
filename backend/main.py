"""
EmailReader 后端服务
FastAPI + uvicorn + asyncio 线程池，为 Vue 前端提供 REST API
启动方式: uv run python main.py
"""
import asyncio
import functools
import json
import httpx
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path

from thunderbird import read_thunderbird_accounts
from mail_reader import MboxIndex, list_folders, read_emails, read_email_body, thread_pool
from email_processor import html_to_markdown, text_to_ai_content
from prompts import get_prompt

app = FastAPI(title="EmailReader API", version="0.3.0")


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def _normalize_base_url(base_url: str) -> str:
    """
    规范化 AI API base_url，确保末尾有正确的路径前缀。

    兼容规则：
    - https://api.openai.com          → https://api.openai.com/v1
    - https://api.openai.com/         → https://api.openai.com/v1
    - https://api.openai.com/v1       → 不变
    - https://api.openai.com/v1/      → https://api.openai.com/v1
    - https://api.deepseek.com        → https://api.deepseek.com/v1
    - https://api.deepseek.com/v1     → 不变
    - http://localhost:11434/v1       → 不变（Ollama）
    - http://localhost:11434          → http://localhost:11434/v1
    """
    url = base_url.strip().rstrip("/")
    # 已经以 /v1 结尾，或者包含更深路径（如 /v1/something），直接返回
    if "/v1" in url.split("://", 1)[-1]:
        return url
    return url + "/v1"


def _build_chat_payload(model: str, messages: list, temperature: float, max_tokens: int) -> dict:
    """
    构建 OpenAI 兼容的 chat/completions 请求体。
    对不支持 temperature 的模型（如 deepseek-reasoner）自动去除该字段。
    """
    # deepseek-reasoner 等推理模型不接受 temperature / top_p 参数
    _NO_TEMP_MODELS = {"deepseek-reasoner", "o1", "o1-mini", "o1-preview", "o3", "o3-mini"}
    payload: dict = {
        "model":      model,
        "messages":   messages,
        "max_tokens": max_tokens,
    }
    if not any(model.lower().startswith(m) for m in _NO_TEMP_MODELS):
        payload["temperature"] = temperature
    return payload


def _patch_event_datetime_from_mail(ev: dict, key_to_date: dict) -> None:
    """
    若事件的 datetime 缺失或为“仅日期/整点占位”（如 00:00、08:00 UTC 显示为 16:00），
    则用该事件来源邮件的真实接收时间覆盖，保证显示的是邮件收到时间。
    """
    import re
    source_key = ev.get("source_key")
    mail_date = key_to_date.get(source_key) if source_key else None
    if not mail_date:
        return
    dt = (ev.get("datetime") or "").strip()
    if not dt:
        ev["datetime"] = mail_date
        return
    # 仅日期（无 T 或 T 后无有效时间）
    if re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
        ev["datetime"] = mail_date
        return
    # 时间为 00:00:00 或 08:00:00 等常见占位（整点且多为 0 或 8）
    m = re.match(r"^\d{4}-\d{2}-\d{2}[T ](\d{2}):(\d{2})", dt)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if mi == 0 and (h == 0 or h == 8 or h == 16):
            ev["datetime"] = mail_date
        return


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── 辅助：在线程池中运行阻塞操作 ────────────────────────────────────────────

async def _run(fn, *args, **kwargs):
    """在共享线程池执行阻塞函数，不阻塞事件循环。"""
    loop = asyncio.get_event_loop()
    call = functools.partial(fn, *args, **kwargs) if kwargs else functools.partial(fn, *args)
    return await loop.run_in_executor(thread_pool, call)


def _get_account(account_id: str) -> dict:
    """从账号列表中查找指定账号（已验证存在）。"""
    result = read_thunderbird_accounts()
    if not result["success"]:
        raise HTTPException(502, detail=result["error"])
    account = next((a for a in result["accounts"] if a["account_id"] == account_id), None)
    if account is None:
        raise HTTPException(404, detail=f"账号 {account_id} 不存在")
    return account


def _require_mail_dir(account: dict) -> str:
    mail_dir = account.get("mail_dir")
    if not mail_dir:
        raise HTTPException(404, detail="该账号没有本地邮件目录")
    return mail_dir


# ─── 账号 ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "EmailReader"}


@app.get("/api/prompts")
def get_prompts():
    """返回完整的 prompts.yaml 内容（前端用于构建 system prompt，避免硬编码）。"""
    from prompts import _prompts
    return {"success": True, "prompts": _prompts}


@app.post("/api/prompts/reload")
def reload_prompts():
    """热重载 prompts.yaml，无需重启后端（开发调试用）。"""
    import prompts as _pm
    _pm.reload()
    from prompts import _prompts
    return {"success": True, "prompts": _prompts}


@app.get("/api/accounts")
def get_accounts():
    """返回 Thunderbird 所有邮箱账号配置。"""
    return read_thunderbird_accounts()


# ─── 文件夹 ──────────────────────────────────────────────────────────────────

@app.get("/api/accounts/{account_id}/folders")
async def get_folders(account_id: str):
    """列出某账号下所有本地 mbox 文件夹。"""
    account = _get_account(account_id)
    mail_dir = _require_mail_dir(account)
    folders = await _run(list_folders, mail_dir)
    return {"success": True, "account_id": account_id, "mail_dir": mail_dir, "folders": folders}


# ─── 预热：后台并行建索引 ─────────────────────────────────────────────────────

@app.post("/api/accounts/{account_id}/prefetch")
async def prefetch_account(account_id: str, background_tasks: BackgroundTasks):
    """
    触发后台并行预热该账号所有文件夹的索引。
    前端在切换账号/打开文件夹列表时调用此接口。
    返回立即，建索引在后台线程池中进行。
    """
    account = _get_account(account_id)
    mail_dir = _require_mail_dir(account)
    folders = list_folders(mail_dir)

    async def _warm_all():
        tasks = [
            _run(MboxIndex.get, f["path"])
            for f in folders
            if f["size_bytes"] > 0
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    background_tasks.add_task(_warm_all)
    return {"status": "warming", "folders": len(folders)}


# ─── 邮件列表（分页）────────────────────────────────────────────────────────

@app.get("/api/accounts/{account_id}/folders/{folder_id:path}/emails")
async def get_emails(
    account_id: str,
    folder_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    force: bool = Query(False),   # True = 强制清除缓存，重建索引
):
    """
    获取文件夹邮件列表（分页）。
    首次调用时在线程池中建索引；后续命中缓存，几乎无耗时。
    force=True 时先清除缓存再重建，用于手动/自动刷新场景。
    """
    account = _get_account(account_id)
    mail_dir = _require_mail_dir(account)
    mbox_path = str(Path(mail_dir) / folder_id.replace("/", "\\"))

    if force:
        await _run(MboxIndex.invalidate, mbox_path)

    data = await _run(read_emails, mbox_path, skip=skip, limit=limit)
    if not data["success"]:
        raise HTTPException(404, detail=data["error"])
    return data


# ─── 单封邮件正文 ─────────────────────────────────────────────────────────────

@app.get("/api/accounts/{account_id}/folders/{folder_id:path}/emails/{key}")
async def get_email_body(account_id: str, folder_id: str, key: str):
    """获取单封邮件完整内容（含 HTML/纯文本正文）。"""
    account = _get_account(account_id)
    mail_dir = _require_mail_dir(account)
    mbox_path = str(Path(mail_dir) / folder_id.replace("/", "\\"))
    data = await _run(read_email_body, mbox_path, key)
    if not data["success"]:
        raise HTTPException(404, detail=data["error"])
    return data


# ─── 邮件内容转换（HTML → Markdown）────────────────────────────────────────

class ConvertRequest(BaseModel):
    html: str = ""
    plain: str = ""
    keep_links: bool = False
    max_chars: int = 8000


@app.post("/api/ai/convert-email")
def convert_email_body(body: ConvertRequest):
    """
    将邮件 HTML / 纯文本正文转为 Markdown，供前端预览或测试。
    实际 AI 对话时会在后端直接调用 text_to_ai_content()，不走此接口。
    """
    md = text_to_ai_content(
        body.html, body.plain,
        max_chars=body.max_chars,
        keep_links=body.keep_links,
    )
    return {"success": True, "markdown": md, "chars": len(md)}


# ─── AI 邮件摘要准备（天数过滤 + HTML→Markdown）───────────────────────────

class PrepareEmailsRequest(BaseModel):
    account_id: str
    folder_id: str
    ai_days: int = 7          # 0 = 不限
    max_emails: int = 200     # 上限，避免单次传入过多
    max_chars_per_email: int = 2000   # 每封邮件正文最多字符
    metadata_only: bool = False       # True = 只返回元数据，不读正文（快速加载用）


def _filter_entries(mbox_path: str, ai_days: int, max_emails: int) -> tuple[list, object | None]:
    """
    从 MboxIndex 按日期过滤并返回 (filtered_entries, cutoff_dt)。
    纯元数据操作，不打开 mbox 文件，速度极快。
    """
    from datetime import datetime, timezone, timedelta

    cutoff = None
    if ai_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=ai_days)

    idx = MboxIndex.get(mbox_path)
    entries = idx._entries  # 已按日期倒序

    filtered = []
    for e in entries:
        if len(filtered) >= max_emails:
            break
        date_str = e.get("date")
        if cutoff and date_str:
            try:
                dt = datetime.fromisoformat(date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    break
            except Exception:
                pass
        filtered.append(e)
    return filtered, cutoff


def _read_msg_body(mbox, key: str, max_chars: int) -> str:
    """从已打开的 mbox 中读取单封邮件正文并转 Markdown。"""
    import mailbox as _mb
    try:
        msg = mbox.get(int(key))
        if not msg:
            return ""
        text_html = text_plain = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                cs = part.get_content_charset() or "utf-8"
                decoded = payload.decode(cs, errors="replace")
                if ct == "text/plain" and not text_plain:
                    text_plain = decoded
                elif ct == "text/html" and not text_html:
                    text_html = decoded
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                cs = msg.get_content_charset() or "utf-8"
                content = payload.decode(cs, errors="replace")
                if msg.get_content_type() == "text/html":
                    text_html = content
                else:
                    text_plain = content
        return text_to_ai_content(text_html, text_plain, max_chars=max_chars)
    except Exception:
        return ""


def _prepare_emails_blocking(
    mbox_path: str,
    ai_days: int,
    max_emails: int,
    max_chars_per_email: int,
    metadata_only: bool = False,
) -> dict:
    """
    从 mbox 文件按天数过滤邮件。
    metadata_only=True 时只返回元数据（不读正文），速度极快，适合显示列表。
    metadata_only=False 时同时将正文 HTML→Markdown 返回。
    """
    import mailbox as _mb

    if not Path(mbox_path).exists():
        return {"success": False, "error": "mbox 文件不存在"}

    filtered, cutoff = _filter_entries(mbox_path, ai_days, max_emails)

    if metadata_only:
        # 快速路径：只返回元数据，不打开 mbox 读正文
        result = [
            {
                "key":     e.get("key"),
                "subject": e.get("subject", ""),
                "from":    e.get("from", ""),
                "date":    e.get("date", ""),
                "is_read": e.get("is_read", True),
            }
            for e in filtered
        ]
    else:
        # 完整路径：读取正文并转 Markdown
        try:
            mbox = _mb.mbox(mbox_path, create=False)
        except Exception as e:
            return {"success": False, "error": str(e)}
        result = []
        for entry in filtered:
            key = entry.get("key")
            result.append({
                "key":      key,
                "subject":  entry.get("subject", ""),
                "from":     entry.get("from", ""),
                "date":     entry.get("date", ""),
                "is_read":  entry.get("is_read", True),
                "body_md":  _read_msg_body(mbox, key, max_chars_per_email),
            })
        mbox.close()

    return {
        "success":       True,
        "ai_days":       ai_days,
        "total":         len(result),
        "cutoff_utc":    cutoff.isoformat() if cutoff else None,
        "metadata_only": metadata_only,
        "emails":        result,
    }


@app.post("/api/ai/prepare-emails")
async def prepare_emails_for_ai(body: PrepareEmailsRequest):
    """
    按 ai_days 过滤邮件。
    metadata_only=True 时只返回元数据（快速加载列表用）。
    metadata_only=False 时同时返回正文 Markdown（供 AI 阅读）。
    返回供 AI 摘要/分析的结构化数据。
    """
    account = _get_account(body.account_id)
    mail_dir = _require_mail_dir(account)
    mbox_path = str(Path(mail_dir) / body.folder_id.replace("/", "\\"))
    return await _run(
        _prepare_emails_blocking,
        mbox_path,
        body.ai_days,
        body.max_emails,
        body.max_chars_per_email,
    )


# ─── AI 对话（代理转发，前端不直接暴露 Key）──────────────────────────────────

class AiChatMessage(BaseModel):
    role: str      # "system" | "user" | "assistant"
    content: str


class AiChatRequest(BaseModel):
    base_url: str
    api_key: str
    model: str
    messages: list[AiChatMessage]
    temperature: float = 0.7
    max_tokens: int = 2048


@app.post("/api/ai/chat")
async def ai_chat(body: AiChatRequest):
    """
    将对话请求代理转发给配置的 AI API（OpenAI 兼容接口）。
    API Key 只在后端使用，不暴露给外部网络。
    自动规范化 base_url，兼容 DeepSeek / OpenAI / Ollama 等各种填写方式。
    """
    base = _normalize_base_url(body.base_url)
    url  = base + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {body.api_key}",
        "Content-Type": "application/json",
    }
    payload = _build_chat_payload(
        model=body.model,
        messages=[{"role": m.role, "content": m.content} for m in body.messages],
        temperature=body.temperature,
        max_tokens=body.max_tokens,
    )
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException:
        return {"success": False, "error": "AI 请求超时（120 秒）"}
    except Exception as e:
        return {"success": False, "error": str(e) or repr(e)}

    if resp.status_code != 200:
        try:
            err = resp.json()
            msg = (err.get("error") or {}).get("message") or err.get("message") or resp.text[:400]
        except Exception:
            msg = resp.text[:400] or f"HTTP {resp.status_code}"
        return {"success": False, "error": f"HTTP {resp.status_code}: {msg}"}

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage   = data.get("usage", {})
        return {"success": True, "content": content, "usage": usage}
    except Exception as e:
        return {"success": False, "error": f"解析 AI 响应失败：{e}"}


# ─── AI 设置 ─────────────────────────────────────────────────────────────────

class AiTestRequest(BaseModel):
    base_url: str
    api_key: str = ""


@app.post("/api/ai/test-connection")
async def test_ai_connection(body: AiTestRequest):
    """
    测试 AI API 连接，返回可用模型列表。
    使用 httpx 发起请求，SSL 证书处理更可靠。
    自动规范化 base_url（补全 /v1 等路径前缀）。
    """
    if not body.base_url.strip():
        return {"success": False, "error": "API 地址不能为空"}

    base_url = _normalize_base_url(body.base_url)
    url = base_url + "/models"
    headers = {"Accept": "application/json"}
    if body.api_key.strip():
        headers["Authorization"] = f"Bearer {body.api_key.strip()}"

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
    except httpx.ConnectError as e:
        detail = str(e) or repr(e)
        return {"success": False, "error": f"无法连接到服务器，请检查 API 地址是否正确。详情：{detail}"}
    except httpx.TimeoutException as e:
        return {"success": False, "error": f"连接超时（20 秒），请检查网络或 API 地址。详情：{e}"}
    except httpx.SSLError as e:
        return {"success": False, "error": f"SSL 证书验证失败：{str(e) or repr(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e) or repr(e) or f"未知异常 {type(e).__name__}"}

    if resp.status_code == 404:
        # /models 端点不存在：服务器可达，但该 API 不暴露模型列表接口
        # 仍视为"连接成功"，让用户手动填写模型名称
        return {
            "success": True,
            "models": [],
            "no_models_endpoint": True,
            "note": "服务器连接正常，但该 API 不支持 /models 接口，请手动输入模型名称",
        }

    if resp.status_code == 401:
        return {"success": False, "error": "API Key 无效或未授权（HTTP 401），请检查 Key 是否正确"}

    if resp.status_code != 200:
        # 尝试从响应体提取 API 返回的错误信息
        try:
            err = resp.json()
            msg = (err.get("error") or {}).get("message") or err.get("message") or resp.text[:300]
        except Exception:
            msg = resp.text[:300] or f"HTTP {resp.status_code}"
        return {"success": False, "error": f"HTTP {resp.status_code}: {msg}"}

    try:
        data = resp.json()
    except Exception:
        return {"success": False, "error": "API 返回了非 JSON 响应，请确认 API 地址是否正确"}

    # 兼容多种响应格式
    # OpenAI: { "data": [{"id": "gpt-4", ...}, ...] }
    # Ollama: { "models": [{"name": "llama3", ...}] }
    # 部分私有 API: { "data": ["model-a", "model-b"] }
    models: list[str] = []
    if isinstance(data.get("data"), list):
        for m in data["data"]:
            if isinstance(m, dict):
                models.append(m.get("id") or m.get("name") or "")
            elif isinstance(m, str):
                models.append(m)
    elif isinstance(data.get("models"), list):
        for m in data["models"]:
            if isinstance(m, dict):
                models.append(m.get("id") or m.get("name") or "")
            elif isinstance(m, str):
                models.append(m)

    models = sorted(filter(None, models), key=str.lower)

    if not models:
        return {
            "success": False,
            "error": "API 连接成功，但未返回任何模型。原始响应：" + json.dumps(data, ensure_ascii=False)[:200],
        }

    return {"success": True, "models": models}


# ─── 生产模式：挂载 Vue 构建产物 ─────────────────────────────────────────────

DIST_DIR = Path(__file__).parent.parent / "frontend" / "dist"
_spa_mounted = False


def _mount_spa(dist_dir: Path) -> None:
    """挂载前端构建产物，供 PyWebView / 生产环境使用。构建后再调用，避免首次启动时 dist 尚未生成。"""
    global _spa_mounted
    if _spa_mounted or not dist_dir.exists():
        return
    assets = dist_dir / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
    index = dist_dir / "index.html"
    if index.exists():
        index_path = str(index)

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str):
            return FileResponse(index_path)
    _spa_mounted = True


if DIST_DIR.exists():
    _mount_spa(DIST_DIR)


# ─── RAG：邮件相关性筛选 ──────────────────────────────────────────────────────

class ScreenEmailsRequest(BaseModel):
    base_url: str
    api_key: str
    model: str
    query: str
    emails: list[dict]      # [{key, subject, from, date}]
    threshold: float = 0.6  # 相关性阈值，低于此值的邮件不纳入上下文
    screening_model: str = ""   # 可选：使用更轻量的模型做筛选（空 = 与 model 相同）


@app.post("/api/ai/screen-emails")
async def screen_emails(body: ScreenEmailsRequest):
    """
    第一阶段 RAG：仅凭邮件元数据（标题/发件人/日期）调用 AI 进行相关性评分。
    返回相关性 >= threshold 的邮件列表，并附带分数，按分数降序排列。
    """
    import json as _json

    if not body.emails:
        return {"success": True, "relevant": [], "all_scores": []}

    # 构建筛选请求的 emails_json（只传元数据，不传正文）
    emails_meta = [
        {"key": e.get("key", ""), "subject": e.get("subject", ""), "from": e.get("from", ""), "date": e.get("date", "")}
        for e in body.emails
    ]
    emails_json_str = _json.dumps(emails_meta, ensure_ascii=False)

    system_prompt = get_prompt("screening", "system")
    user_prompt   = get_prompt(
        "screening", "user_template",
        query=body.query,
        count=len(emails_meta),
        emails_json=emails_json_str,
    )

    use_model = body.screening_model.strip() or body.model
    base = _normalize_base_url(body.base_url)
    url  = base + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {body.api_key}",
        "Content-Type": "application/json",
    }
    payload = _build_chat_payload(
        model=use_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=2048,
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException:
        return {"success": False, "error": "筛选请求超时（60 秒）"}
    except Exception as e:
        return {"success": False, "error": str(e) or repr(e)}

    if resp.status_code != 200:
        try:
            err = resp.json()
            msg = (err.get("error") or {}).get("message") or err.get("message") or resp.text[:300]
        except Exception:
            msg = resp.text[:300] or f"HTTP {resp.status_code}"
        return {"success": False, "error": f"筛选 AI 返回错误：HTTP {resp.status_code}: {msg}"}

    # 解析 AI 返回的 JSON 数组
    try:
        raw_content: str = resp.json()["choices"][0]["message"]["content"].strip()
        # 去除可能的 markdown 代码块包裹
        if raw_content.startswith("```"):
            raw_content = raw_content.split("```")[1]
            if raw_content.startswith("json"):
                raw_content = raw_content[4:]
        all_scores: list[dict] = _json.loads(raw_content)
    except Exception as e:
        return {"success": False, "error": f"解析筛选结果失败：{e}，原始响应：{resp.text[:300]}"}

    # 过滤并排序
    relevant = [
        {"key": item["key"], "score": float(item.get("score", 0))}
        for item in all_scores
        if float(item.get("score", 0)) >= body.threshold
    ]
    relevant.sort(key=lambda x: x["score"], reverse=True)

    return {
        "success":    True,
        "relevant":   relevant,
        "all_scores": all_scores,
        "threshold":  body.threshold,
        "model_used": use_model,
    }


# ─── RAG：批量拉取邮件正文 ────────────────────────────────────────────────────

class FetchBodiesRequest(BaseModel):
    account_id: str
    folder_id: str
    keys: list[str]              # 要读取正文的邮件 key 列表
    max_chars_per_email: int = 2000


def _fetch_bodies_blocking(mbox_path: str, keys: list[str], max_chars: int) -> dict:
    """批量从 mbox 读取指定 key 的邮件正文，转为 Markdown。"""
    import mailbox as _mb

    if not Path(mbox_path).exists():
        return {"success": False, "error": "mbox 文件不存在"}
    try:
        mbox = _mb.mbox(mbox_path, create=False)
    except Exception as e:
        return {"success": False, "error": str(e)}

    bodies: dict[str, str] = {}
    for key in keys:
        bodies[key] = _read_msg_body(mbox, key, max_chars)
    mbox.close()

    return {"success": True, "bodies": bodies}


@app.post("/api/ai/fetch-bodies")
async def fetch_email_bodies(body: FetchBodiesRequest):
    """
    第二阶段 RAG：按 key 列表批量读取邮件正文（HTML→Markdown）。
    在相关性筛选之后，只拉取高相关性邮件的正文，减少 Token 消耗。
    """
    account  = _get_account(body.account_id)
    mail_dir = _require_mail_dir(account)
    mbox_path = str(Path(mail_dir) / body.folder_id.replace("/", "\\"))
    return await _run(_fetch_bodies_blocking, mbox_path, body.keys, body.max_chars_per_email)


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard — 事件提取 / 简报 / Todo 持久化
# ═══════════════════════════════════════════════════════════════════════════════

_DATA_DIR      = Path(__file__).parent / "data"
_DASHBOARD_JSON = _DATA_DIR / "dashboard.json"
_TODOS_JSON     = _DATA_DIR / "todos.json"
_BRIEFS_JSON    = _DATA_DIR / "briefs.json"
_DATA_DIR.mkdir(exist_ok=True)


def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── 读取 Dashboard 数据 ──────────────────────────────────────────────────────

@app.get("/api/dashboard/data")
def get_dashboard_data():
    """返回最近一次提取的 Dashboard 数据（事件、话题、联系人、简报）。"""
    return _load_json(_DASHBOARD_JSON, {
        "events":    [],
        "topics":    [],
        "people":    [],
        "brief":     "",
        "stats":     {},
        "extracted_at": None,
        "is_extracting": False,
    })


@app.get("/api/dashboard/debug-log")
def get_extract_log():
    """返回最近一次提取的详细日志（调试用）。"""
    data = _load_json(_DASHBOARD_JSON, {})
    return {
        "extract_log":   data.get("extract_log", []),
        "extract_error": data.get("extract_error", ""),
        "is_extracting": data.get("is_extracting", False),
        "extracted_at":  data.get("extracted_at"),
        "stats":         data.get("stats", {}),
    }


# ─── 触发事件提取 ─────────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    base_url: str
    api_key:  str
    model:    str
    ai_days:  int = 7
    max_emails_per_folder: int = 100
    max_chars_per_email:   int = 1500


async def _do_extract(req: ExtractRequest) -> None:
    """后台任务：遍历所有账号所有文件夹，提取事件，更新 dashboard.json。"""
    import mailbox as _mb
    import datetime
    import logging
    log = logging.getLogger("extract")

    # 标记提取中
    existing = _load_json(_DASHBOARD_JSON, {})
    existing["is_extracting"] = True
    existing.pop("extract_error", None)
    _save_json(_DASHBOARD_JSON, existing)

    all_events:   list[dict] = []
    all_meta:     list[dict] = []
    # 按账号分组的元数据和事件，供分账号生成简报
    acc_events:   dict[str, list] = {}   # email -> [events]
    acc_meta:     dict[str, list] = {}   # email -> [metas]
    extract_log:  list[str] = []         # 详细日志，写入 dashboard.json 供调试

    def _log(msg: str):
        log.info(msg)
        extract_log.append(msg)

    try:
        tb_result = read_thunderbird_accounts()
        accounts  = tb_result.get("accounts", []) if isinstance(tb_result, dict) else []
        _log(f"账号数量: {len(accounts)}")

        today  = datetime.date.today()
        cutoff = today - datetime.timedelta(days=req.ai_days)
        _log(f"提取范围: {req.ai_days} 天，截止 {cutoff}")

        for acc in accounts:
            mail_dir = acc.get("mail_dir", "")
            acc_email = acc.get("email", "?")
            _log(f"--- 账号: {acc_email}, mail_dir: {mail_dir}")
            if not mail_dir or not Path(mail_dir).exists():
                _log(f"  跳过：mail_dir 不存在")
                continue

            folders = list_folders(mail_dir)
            _log(f"  文件夹数: {len(folders)}")

            for folder in folders:
                folder_name = folder.get("name", "?")
                mbox_path = str(Path(mail_dir) / folder["folder_id"].replace("/", "\\"))
                if not Path(mbox_path).exists():
                    continue

                try:
                    idx = MboxIndex.get(mbox_path)
                except Exception as e:
                    _log(f"  [{folder_name}] 索引失败: {e}")
                    continue

                filtered = [
                    e for e in idx.entries
                    if e.get("epoch_ms") and
                       datetime.datetime.utcfromtimestamp(e["epoch_ms"] / 1000).date() >= cutoff
                ][:req.max_emails_per_folder]

                _log(f"  [{folder_name}] 符合日期的邮件: {len(filtered)}")
                if not filtered:
                    continue

                try:
                    mbox = _mb.mbox(mbox_path, create=False)
                except Exception as e:
                    _log(f"  [{folder_name}] 打开 mbox 失败: {e}")
                    continue

                def _read_folder_bodies():
                    items, metas = [], []
                    for entry in filtered:
                        key  = entry.get("key", "")
                        body = _read_msg_body(mbox, key, req.max_chars_per_email)
                        items.append({
                            "key":     key,
                            "subject": entry.get("subject", ""),
                            "from":    entry.get("from", ""),
                            "date":    entry.get("date", ""),
                            "body":    body,
                        })
                        metas.append({
                            "subject": entry.get("subject", ""),
                            "from":    entry.get("from", ""),
                            "date":    entry.get("date", ""),
                            "account": acc.get("email", ""),
                            "folder":  folder.get("name", ""),
                        })
                    mbox.close()
                    return items, metas

                emails_for_ai, folder_meta = await _run(_read_folder_bodies)
                all_meta.extend(folder_meta)
                # 按账号归档
                acc_email = acc.get("email", "?")
                acc_meta.setdefault(acc_email, []).extend(folder_meta)
                _log(f"  [{folder_name}] 读取正文完成: {len(emails_for_ai)} 封")

                if not emails_for_ai:
                    continue

                # 调用 AI 提取事件
                system_p = get_prompt("extract", "system", current_year=today.year)
                user_p   = get_prompt(
                    "extract", "user_template",
                    today=today.isoformat(),
                    count=len(emails_for_ai),
                    emails_json=json.dumps(emails_for_ai, ensure_ascii=False),
                )
                base_url = _normalize_base_url(req.base_url)
                payload  = _build_chat_payload(
                    model=req.model,
                    messages=[
                        {"role": "system", "content": system_p},
                        {"role": "user",   "content": user_p},
                    ],
                    temperature=0.1,
                    max_tokens=2000,
                )
                try:
                    _log(f"  [{folder_name}] 调用 AI ({req.model})…")
                    async with httpx.AsyncClient(timeout=120) as client:
                        resp = await client.post(
                            f"{base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {req.api_key}",
                                     "Content-Type": "application/json"},
                            json=payload,
                        )
                    _log(f"  [{folder_name}] AI 响应状态: {resp.status_code}")
                    if resp.status_code == 200:
                        raw = resp.json()["choices"][0]["message"]["content"].strip()
                        if raw.startswith("```"):
                            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                        try:
                            events = json.loads(raw)
                            if isinstance(events, list):
                                # 用邮件真实接收时间填补“仅日期”或整点占位（00:00/08:00 等）
                                key_to_date = {it["key"]: it["date"] for it in emails_for_ai if it.get("date")}
                                for ev in events:
                                    ev["account"] = acc.get("email", "")
                                    ev["folder"]  = folder.get("name", "")
                                    _patch_event_datetime_from_mail(ev, key_to_date)
                                all_events.extend(events)
                                # 按账号归档事件
                                acc_events.setdefault(acc.get("email", "?"), []).extend(events)
                                _log(f"  [{folder_name}] 提取事件: {len(events)} 个")
                            else:
                                _log(f"  [{folder_name}] AI 返回非列表: {type(events)}")
                        except json.JSONDecodeError as je:
                            _log(f"  [{folder_name}] JSON 解析失败: {je} | raw前200字: {raw[:200]}")
                    else:
                        _log(f"  [{folder_name}] AI 错误响应: {resp.text[:300]}")
                except Exception as e:
                    _log(f"  [{folder_name}] AI 调用异常: {type(e).__name__}: {e}")

        # 去重（相同 title + datetime 认为是同一事件）
        seen = set()
        unique_events = []
        for ev in all_events:
            key = f"{ev.get('title','')}|{ev.get('datetime','')}"
            if key not in seen:
                seen.add(key)
                unique_events.append(ev)

        # 按时间排序
        def _ev_sort_key(ev):
            dt = ev.get("datetime") or ""
            return dt

        unique_events.sort(key=_ev_sort_key)

        # 生成话题聚类（简单按 tags 聚合）
        topics_map: dict[str, dict] = {}
        for ev in unique_events:
            for tag in (ev.get("tags") or []):
                if tag not in topics_map:
                    topics_map[tag] = {"name": tag, "count": 0, "events": []}
                topics_map[tag]["count"] += 1
                if len(topics_map[tag]["events"]) < 3:
                    topics_map[tag]["events"].append(ev.get("title", ""))
        topics = sorted(topics_map.values(), key=lambda t: -t["count"])[:20]

        # 联系人聚合
        people_map: dict[str, dict] = {}
        for m in all_meta:
            sender = m.get("from", "未知")
            if sender not in people_map:
                people_map[sender] = {"from": sender, "count": 0, "latest": ""}
            people_map[sender]["count"] += 1
            if m.get("date", "") > people_map[sender]["latest"]:
                people_map[sender]["latest"] = m.get("date", "")
        people = sorted(people_map.values(), key=lambda p: -p["count"])[:20]

        # 统计
        stats = {
            "total_emails":   len(all_meta),
            "total_events":   len(unique_events),
            "accounts_count": len(accounts),
            "ai_days":        req.ai_days,
        }

        # 生成今日简报：全局简报 + 各账号独立简报
        import datetime as _dt
        weekday_cn = ["周一","周二","周三","周四","周五","周六","周日"]
        wd = weekday_cn[today.weekday()]
        brief_system = get_prompt("brief", "system")

        async def _gen_brief(account_label: str, metas: list, evs: list) -> str:
            """为指定账号（或全局）生成简报，返回简报文本。"""
            try:
                email_summary_lines = [
                    f"- {m['subject']} (from: {m['from']}, {m['date']})"
                    for m in metas[:30]
                ]
                brief_user = get_prompt(
                    "brief", "user_template",
                    today=today.isoformat(),
                    weekday=wd,
                    email_summary="\n".join(email_summary_lines) or "（无邮件）",
                    events_json=json.dumps(evs[:20], ensure_ascii=False),
                )
                payload_b = _build_chat_payload(
                    model=req.model,
                    messages=[
                        {"role": "system", "content": brief_system},
                        {"role": "user",   "content": brief_user},
                    ],
                    temperature=0.5,
                    max_tokens=600,
                )
                _log(f"生成简报 [{account_label}]…")
                async with httpx.AsyncClient(timeout=60) as client:
                    resp_b = await client.post(
                        f"{base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {req.api_key}",
                                 "Content-Type": "application/json"},
                        json=payload_b,
                    )
                if resp_b.status_code == 200:
                    text = resp_b.json()["choices"][0]["message"]["content"].strip()
                    _log(f"简报 [{account_label}] 生成成功，长度 {len(text)}")
                    return text
                else:
                    _log(f"简报 [{account_label}] 生成失败: {resp_b.status_code} {resp_b.text[:100]}")
                    return ""
            except Exception as e:
                _log(f"简报 [{account_label}] 异常: {type(e).__name__}: {e}")
                return ""

        # 全局简报（汇总所有账号）
        brief_text = await _gen_brief("全局", all_meta, unique_events)

        # 各账号独立简报
        account_briefs: dict[str, str] = {}
        for acc_email_key, a_metas in acc_meta.items():
            a_events = acc_events.get(acc_email_key, [])
            if a_metas:  # 有邮件才生成
                account_briefs[acc_email_key] = await _gen_brief(acc_email_key, a_metas, a_events)

        _log(f"提取完成: 事件 {len(unique_events)} 个，邮件元数据 {len(all_meta)} 封")
        now_iso = _dt.datetime.utcnow().isoformat() + "Z"

        # 按账号统计
        account_stats: dict[str, dict] = {}
        for ae, am in acc_meta.items():
            account_stats[ae] = {
                "email_count": len(am),
                "event_count": len(acc_events.get(ae, [])),
            }

        result = {
            "events":          unique_events,
            "topics":          topics,
            "people":          people,
            "brief":           brief_text,
            "account_briefs":  account_briefs,   # 各账号独立简报
            "account_stats":   account_stats,    # 各账号统计
            "acc_events":      {k: v for k, v in acc_events.items()},  # 各账号事件
            "stats":           stats,
            "extracted_at":    now_iso,
            "is_extracting":   False,
            "extract_log":     extract_log,
        }
        _save_json(_DASHBOARD_JSON, result)

        # ── 将本次简报追加到历史 ──────────────────────────────────────────────
        if brief_text or account_briefs:
            briefs = _load_json(_BRIEFS_JSON, [])
            today_key = _dt.datetime.utcnow().strftime("%Y-%m-%d")
            briefs = [b for b in briefs if b.get("date") != today_key]
            briefs.insert(0, {
                "id":              today_key,
                "date":            today_key,
                "generated_at":    now_iso,
                "brief":           brief_text,          # 全局简报
                "account_briefs":  account_briefs,      # 各账号简报 {email: text}
                "stats":           stats,
            })
            _save_json(_BRIEFS_JSON, briefs[:90])

    except Exception as e:
        import traceback
        err_detail = traceback.format_exc()
        log.error(f"_do_extract 顶层异常: {err_detail}")
        existing = _load_json(_DASHBOARD_JSON, {})
        existing["is_extracting"]  = False
        existing["extract_error"]  = str(e)
        existing["extract_log"]    = extract_log + [f"FATAL: {err_detail}"]
        _save_json(_DASHBOARD_JSON, existing)


@app.post("/api/dashboard/extract")
async def trigger_extract(req: ExtractRequest):
    """触发 Dashboard 事件提取（后台异步执行，立即返回）。"""
    asyncio.create_task(_do_extract(req))
    return {"success": True, "message": "提取任务已启动，请稍后刷新"}


@app.get("/api/dashboard/briefs")
def get_briefs():
    """返回简报历史列表（最多 90 条，按日期倒序）。"""
    briefs = _load_json(_BRIEFS_JSON, [])
    # 只返回摘要字段，不含完整 brief 正文（节省流量）
    return {
        "briefs": [
            {
                "id":           b.get("id"),
                "date":         b.get("date"),
                "generated_at": b.get("generated_at"),
                "preview":      (b.get("brief") or "")[:120],
                "stats":        b.get("stats", {}),
            }
            for b in briefs
        ]
    }


@app.get("/api/dashboard/briefs/{brief_id}")
def get_brief_detail(brief_id: str):
    """返回指定日期简报的完整内容。"""
    briefs = _load_json(_BRIEFS_JSON, [])
    for b in briefs:
        if b.get("id") == brief_id:
            return {"success": True, "brief": b}
    return {"success": False, "detail": "not found"}


# ─── Todo 持久化 CRUD ─────────────────────────────────────────────────────────

class TodoItem(BaseModel):
    id:          str
    title:       str
    status:      str = "todo"       # todo | doing | done
    priority:    str = "medium"     # high | medium | low
    due:         str | None = None  # ISO date string
    tags:        list[str] = []
    source_key:  str | None = None  # 来源邮件 key
    source_from: str | None = None
    note:        str = ""
    created_at:  str = ""
    updated_at:  str = ""


@app.get("/api/dashboard/todos")
def get_todos():
    return {"success": True, "todos": _load_json(_TODOS_JSON, [])}


@app.post("/api/dashboard/todos")
def create_todo(item: TodoItem):
    import datetime as _dt
    todos = _load_json(_TODOS_JSON, [])
    now = _dt.datetime.utcnow().isoformat() + "Z"
    d = item.model_dump()
    d["created_at"] = d["updated_at"] = now
    todos.append(d)
    _save_json(_TODOS_JSON, todos)
    return {"success": True, "todo": d}


@app.put("/api/dashboard/todos/{todo_id}")
def update_todo(todo_id: str, item: TodoItem):
    import datetime as _dt
    todos = _load_json(_TODOS_JSON, [])
    now = _dt.datetime.utcnow().isoformat() + "Z"
    for i, t in enumerate(todos):
        if t["id"] == todo_id:
            d = item.model_dump()
            d["created_at"] = t.get("created_at", now)
            d["updated_at"] = now
            todos[i] = d
            _save_json(_TODOS_JSON, todos)
            return {"success": True, "todo": d}
    raise HTTPException(status_code=404, detail="Todo not found")


@app.delete("/api/dashboard/todos/{todo_id}")
def delete_todo(todo_id: str):
    todos = _load_json(_TODOS_JSON, [])
    todos = [t for t in todos if t["id"] != todo_id]
    _save_json(_TODOS_JSON, todos)
    return {"success": True}


@app.patch("/api/dashboard/todos/reorder")
def reorder_todos(body: dict):
    """批量更新 todos 顺序（前端拖拽后调用）。"""
    todos = body.get("todos", [])
    _save_json(_TODOS_JSON, todos)
    return {"success": True}


if __name__ == "__main__":
    import sys
    import threading
    import time
    import uvicorn

    port = 8000
    url = f"http://127.0.0.1:{port}"

    # 无 dist 时先构建，构建完成后挂载 SPA（模块加载时 dist 可能还不存在）
    if not DIST_DIR.exists():
        print("前端未构建，正在执行 npm run build …")
        import subprocess
        frontend_dir = Path(__file__).parent.parent / "frontend"
        try:
            subprocess.run(
                ["npm", "run", "build"],
                cwd=str(frontend_dir),
                shell=(sys.platform == "win32"),
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"构建失败: {e}\n请手动执行: cd frontend && npm run build")
            sys.exit(1)
        _mount_spa(DIST_DIR)

    def run_server():
        uvicorn.run(app, host="127.0.0.1", port=port, reload=False)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # 等待服务就绪
    for _ in range(30):
        try:
            import urllib.request
            urllib.request.urlopen(url, timeout=0.5)
            break
        except Exception:
            time.sleep(0.2)
    else:
        print("后端启动超时")
        sys.exit(1)

    import webview
    webview.create_window("EmailReader", url, width=1200, height=800, min_size=(800, 500))
    webview.start()
    sys.exit(0)
