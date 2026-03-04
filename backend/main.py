"""
EmailReader 后端服务
FastAPI + uvicorn + asyncio 线程池，为 Vue 前端提供 REST API
启动方式: uv run python main.py
"""
import asyncio
import functools
import json
import os
import re
import sys
import httpx
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from pathlib import Path

from thunderbird import read_thunderbird_accounts
from mail_reader import MboxIndex, list_folders, read_emails, read_email_body, thread_pool
from email_processor import html_to_markdown, text_to_ai_content
from prompts import get_prompt
from content_extract import extract_verification_code
from services.account import resolve_mbox_path
from services.notification import show_new_mail_toast, get_copy_code_html

app = FastAPI(title="EmailReader API", version="0.3.0")


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def _parse_extract_json(raw: str):
    """
    解析 AI 返回的事件 JSON，对常见 LLM 输出错误做容错（尾部逗号、缺逗号、单引号键名等）。
    返回 list；若仍无法解析则抛出 json.JSONDecodeError。
    """
    last_error: list[json.JSONDecodeError | None] = [None]

    def _repair(s: str) -> list[str]:
        """生成多种修复后的候选字符串，供依次尝试解析。"""
        candidates = [
            s,
            re.sub(r",\s*([}\]])", r"\1", s),  # 去掉 ] 或 } 前的尾部逗号
            re.sub(r"([{,]\s*)'([a-zA-Z_][a-zA-Z0-9_]*)'(\s*:)", r'\1"\2"\3', s),  # 单引号键名
        ]
        # 值内未转义双引号（如 description 里「礼"物」）导致提前截断，转义该引号
        # 匹配：非 \ 且非 :/空格的字符 + " + 非 "/:/空格的字符（即值中间的 "）
        _escaped_inner = re.sub(r'([^\\:\s])"([^":\s])', r'\1\\"\2', s)
        if _escaped_inner != s and _escaped_inner not in candidates:
            candidates.append(_escaped_inner)
        # 缺逗号：值后的 " 与下一键的 " 之间缺少逗号（如 "description": "x" "priority":）
        for pat, repl in [
            (r'(?<!\\)"(\s+)"(\s*:)', r'",\1"\2'),   # " 空白 " key":（前引号非转义）
            (r'(?<!\\)"(\s*\n\s*)"(\s*:)', r'",\1"\2'),  # 换行后直接下一键
            (r'(?<!\\)"(\s*)"(\s*:)', r'",\1"\2'),   # "任意空白"key":（含两引号紧挨）
            (r'(null|true|false)(\s+)"(\s*:)', r'\1,\2"\3'),  # null/true/false 后缺逗号
        ]:
            repaired = re.sub(pat, repl, s)
            if repaired != s and repaired not in candidates:
                candidates.append(repaired)
            # 对“先转义值内引号”后的串再做缺逗号修复
            if _escaped_inner != s:
                repaired2 = re.sub(pat, repl, _escaped_inner)
                if repaired2 not in candidates:
                    candidates.append(repaired2)
        return candidates

    def try_parse(s: str):
        for text in _repair(s):
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                last_error[0] = e
        return None

    result = try_parse(raw)
    if result is not None:
        return result
    # 尝试只取第一个 [ 到最后一个 ] 之间的内容（排除前后杂文）
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        segment = raw[start : end + 1]
        result = try_parse(segment)
        if result is not None:
            return result
    raise last_error[0]


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


def _normalize_mail_date(raw: str) -> str:
    """将邮件 Date 头常见格式转为 YYYY-MM-DD，供 AI 做相对日期基准。"""
    if not raw or not isinstance(raw, str):
        return ""
    import datetime as _dt
    raw = raw.strip()
    # 已有 ISO 或 YYYY-MM-DD 片段
    for part in raw.split():
        if part and len(part) >= 10 and part[4] == "-" and part[7] == "-":
            try:
                _dt.datetime.strptime(part[:10], "%Y-%m-%d")
                return part[:10]
            except ValueError:
                pass
    # 尝试 email.utils.parsedate_to_datetime
    try:
        from email.utils import parsedate_to_datetime
        t = parsedate_to_datetime(raw)
        return t.strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""


def _patch_event_datetime_from_mail(ev: dict, key_to_date: dict) -> None:
    """
    仅当事件的 datetime 缺失或为“仅日期/整点占位”时，用邮件接收时间补全。
    若 AI 已从正文提取出具体日期（如相对日期换算后的 2026-03-05），则保留不覆盖。
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
    # 仅日期（无 T 或 T 后无有效时间）：仅当与邮件日相同时视为占位才替换，否则保留（AI 可能已做相对日期换算）
    if re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
        if dt == mail_date:
            ev["datetime"] = mail_date
        return
    # 时间为 00:00:00 或 08:00:00 等常见占位（整点且多为 0 或 8）
    m = re.match(r"^\d{4}-\d{2}-\d{2}[T ](\d{2}):(\d{2})", dt)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if mi == 0 and (h == 0 or h == 8 or h == 16):
            ev["datetime"] = mail_date
        return


def _extract_date_from_description(desc: str, current_year: int) -> str | None:
    """
    从 description 中尝试抽取一个明确日期（用于 deadline 类事件的兜底）。
    返回 ISO 日期 YYYY-MM-DD，无法解析时返回 None。
    """
    if not desc or not isinstance(desc, str):
        return None
    import datetime as _dt
    # 2026年3月28日 / 2026年03月28日
    m = re.search(r"20(\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", desc)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 20 <= y <= 40 and 1 <= mo <= 12 and 1 <= d <= 31:
            try:
                return _dt.date(2000 + y, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                pass
    # 3月28日 / 03月28日（用当前年）
    m = re.search(r"(\d{1,2})月\s*(\d{1,2})日", desc)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            try:
                return _dt.date(current_year, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                pass
    # 2026/Mar/18 或 2026/Mar/28
    m = re.search(r"20(\d{2})/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*/(\d{1,2})", desc, re.I)
    if m:
        y, mon, d = int(m.group(1)), m.group(2).lower()[:3], int(m.group(3))
        mon_map = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                   "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
        if 20 <= y <= 40 and mon in mon_map and 1 <= d <= 31:
            try:
                return _dt.date(2000 + y, mon_map[mon], d).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return None


def _sanitize_event_datetime(ev: dict, key_to_date: dict, current_year: int) -> None:
    """
    对事件 datetime 做校验与修正：错误年份修正、deadline 类优先用 description 中的截止日。
    """
    import datetime as _dt
    dt = (ev.get("datetime") or "").strip()
    fixed_year = False
    if dt:
        year_match = re.match(r"^(\d{4})", dt)
        if year_match:
            y = int(year_match.group(1))
            if y < 2020 or y > 2030:
                ev["datetime"] = re.sub(r"^\d{4}", str(current_year), dt, count=1)
                dt = ev["datetime"]
                fixed_year = True
    dt = (ev.get("datetime") or "").strip()
    source_key = ev.get("source_key")
    mail_date = key_to_date.get(source_key) if source_key else None
    # deadline 类：若当前等于邮件日或刚修正过年份，尝试用 description 中的截止日替代
    if (ev.get("type") or "").lower() != "deadline" or not mail_date:
        return
    use_description = fixed_year or (re.match(r"^\d{4}-\d{2}-\d{2}$", dt) and dt == mail_date)
    if not use_description:
        return
    desc = (ev.get("description") or "") + (ev.get("title") or "")
    extracted = _extract_date_from_description(desc, current_year)
    if not extracted or extracted == mail_date:
        return
    try:
        ext_d = _dt.datetime.strptime(extracted, "%Y-%m-%d").date()
        mail_d = _dt.datetime.strptime(mail_date, "%Y-%m-%d").date()
        if ext_d >= mail_d:
            ev["datetime"] = extracted
    except ValueError:
        pass


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


# 账号/路径解析已迁至 services.account（get_account, require_mail_dir, resolve_mbox_path）

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
    _, mail_dir, _ = resolve_mbox_path(account_id, None)
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
    _, mail_dir, _ = resolve_mbox_path(account_id, None)
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
    _, _, mbox_path = resolve_mbox_path(account_id, folder_id)

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
    _, _, mbox_path = resolve_mbox_path(account_id, folder_id)
    data = await _run(read_email_body, mbox_path, key)
    if not data["success"]:
        raise HTTPException(404, detail=data["error"])
    return data


# ─── 新邮件系统通知（逻辑在 services.notification，此处仅路由）────────────────

@app.get("/api/copy-code", response_class=HTMLResponse)
def copy_code_page(code: str = Query("", description="要复制到剪贴板的验证码")):
    """供 Toast「复制验证码」按钮打开：在浏览器中打开此页并执行复制，显示「已复制」。"""
    return HTMLResponse(content=get_copy_code_html(code))


class NotifyNewMailRequest(BaseModel):
    count: int
    subjects: list[str] = []
    from_str: str = ""
    folder_name: str = ""
    first_email_key: str | None = None
    account_id: str | None = None
    folder_id: str | None = None


@app.post("/api/notify-new-mail")
async def notify_new_mail(body: NotifyNewMailRequest):
    """由前端在检测到新邮件后调用，弹出 Windows 系统通知。若仅 1 封且提供 first_email 信息则尝试识别验证码并显示「复制验证码」按钮。"""
    if body.count <= 0:
        return {"success": True}
    verification_code = None
    if (
        body.count == 1
        and body.first_email_key
        and body.account_id
        and body.folder_id
    ):
        try:
            _, _, mbox_path = resolve_mbox_path(body.account_id, body.folder_id)
            data = await _run(read_email_body, mbox_path, body.first_email_key)
            if data.get("success"):
                raw = (data.get("text_plain") or "") + " " + (data.get("text_html") or "")
                if data.get("subject"):
                    raw = (data.get("subject") or "") + " " + raw
                verification_code = extract_verification_code(raw)
        except Exception:
            pass
    show_new_mail_toast(
        body.count,
        body.subjects or [],
        body.from_str or "",
        body.folder_name or "",
        verification_code=verification_code,
    )
    return {"success": True}


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
    _, _, mbox_path = resolve_mbox_path(body.account_id, body.folder_id)
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


# 不在模块加载时挂载 SPA，否则通配路由会先于后面的 /api/* 注册，导致 /api/dashboard/data 等返回 index.html
# 见文件末尾：所有 API 路由注册后再挂载


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
    _, _, mbox_path = resolve_mbox_path(body.account_id, body.folder_id)
    return await _run(_fetch_bodies_blocking, mbox_path, body.keys, body.max_chars_per_email)


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard — 事件提取 / 简报 / Todo 持久化
# ═══════════════════════════════════════════════════════════════════════════════

_DATA_DIR      = (Path(__file__).resolve().parent / "data")
_DASHBOARD_JSON = _DATA_DIR / "dashboard.json"
_TODOS_JSON     = _DATA_DIR / "todos.json"
_BRIEFS_JSON    = _DATA_DIR / "briefs.json"
_CONFIG_JSON    = _DATA_DIR / "config.json"
_EXTRACTED_KEYS_JSON = _DATA_DIR / "extracted_keys.json"
_DELETION_FEEDBACK_JSON  = _DATA_DIR / "deletion_feedback.json"
_PRIORITY_FEEDBACK_JSON  = _DATA_DIR / "priority_feedback.json"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
# dashboard / todos / briefs / config 均使用下方 _load_json / _save_json 统一读写
print(f"[Config] 数据目录（所有 JSON 均在此）: {_DATA_DIR.resolve()}")
print(f"[Config] config.json 路径: {(_DATA_DIR / 'config.json').resolve()}")
# 前端配置（API Key、主题、助手位置）与其它数据文件同目录
_DEFAULT_CONFIG = {
    "settings": {
        "apiBaseUrl": "https://api.openai.com/v1",
        "apiKey": "",
        "selectedModel": "",
        "systemPrompt": "你是一个邮件助手，请用简洁、专业的语气帮助用户处理和理解邮件内容。",
        "aiDays": 7,
        "relevanceThreshold": 60,
        "refreshInterval": 5,
    },
    "theme": "light",
    "assistantPos": {"x": None, "y": None},
}


def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_extracted_keys() -> set:
    """增量提取：返回已提取过的邮件 key 集合，每项为 'account_email|folder_id|key'。"""
    raw = _load_json(_EXTRACTED_KEYS_JSON, None)
    if raw is None or not isinstance(raw.get("keys"), list):
        return set()
    return set(raw["keys"])


def _save_extracted_keys(keys: set) -> None:
    _save_json(_EXTRACTED_KEYS_JSON, {"keys": list(keys)})


def _event_id(ev: dict) -> str:
    """用于标识同一事件，便于删除反馈与去重。None 与缺失统一为空串。"""
    t = ev.get("title")
    d = ev.get("datetime")
    s = ev.get("source_key")
    return f"{t if t is not None else ''}|{d if d is not None else ''}|{s if s is not None else ''}"


def _merge_key(ev: dict) -> tuple:
    """
    合并时的事件唯一键：按 (账号, source_key) 区分，避免不同账号相同 mail key 互相覆盖。
    无 source_key 时用 (account, __no_key_title|datetime) 兜底，避免被丢弃。
    """
    acc = ev.get("account") or "?"
    sk = (ev.get("source_key") or "").strip()
    if sk:
        return (acc, sk)
    return (acc, "__no_key_" + (ev.get("title") or "") + "|" + (ev.get("datetime") or ""))


def _load_deletion_feedback() -> list:
    raw = _load_json(_DELETION_FEEDBACK_JSON, None)
    if not isinstance(raw, list):
        return []
    return raw


def _save_deletion_feedback(items: list) -> None:
    _save_json(_DELETION_FEEDBACK_JSON, items[:500])


def _format_user_feedback_for_prompt() -> str:
    items = _load_deletion_feedback()
    if not items:
        return "（无）"
    lines = []
    for i, fb in enumerate(items[-50:], 1):
        title = fb.get("title", "")
        reason = fb.get("user_reason") or fb.get("ai_reason") or ""
        reject = " [用户不认同 AI 原因]" if fb.get("reject_ai_reason") else ""
        lines.append(f"{i}. 「{title}」 用户删除原因：{reason}{reject}")
    return "\n".join(lines) if lines else "（无）"


def _load_priority_feedback() -> list:
    raw = _load_json(_PRIORITY_FEEDBACK_JSON, None)
    if not isinstance(raw, list):
        return []
    return raw


def _save_priority_feedback(items: list) -> None:
    _save_json(_PRIORITY_FEEDBACK_JSON, items[:500])


def _format_priority_feedback_for_prompt() -> str:
    """将用户修改优先级的反馈格式化为 extract prompt 中的一段说明，供 AI 后续生成优先级时参考。"""
    items = _load_priority_feedback()
    if not items:
        return "（无）"
    lines = []
    for i, fb in enumerate(items[-30:], 1):
        title = fb.get("title", "")
        old_p = fb.get("old_priority", "")
        new_p = fb.get("new_priority", "")
        ai_reason = fb.get("ai_reason", "")
        user_reason = (fb.get("user_reason") or "").strip()
        part = f"{i}. 「{title}」 原优先级：{old_p}"
        if ai_reason:
            part += f"，AI 原因：{ai_reason}"
        part += f"；用户改为：{new_p}"
        if user_reason:
            part += f"，用户说明：{user_reason}"
        lines.append(part)
    return "\n".join(lines) if lines else "（无）"


# ─── 应用配置（替代前端 localStorage）──────────────────────────────────────────

class ConfigUpdate(BaseModel):
    """部分更新，未传的字段不覆盖."""
    settings: dict | None = None
    theme: str | None = None
    assistantPos: dict | None = None


@app.get("/api/config")
def get_config():
    """返回持久化配置：settings、theme、assistantPos，供 PyWebView 等无 localStorage 环境使用."""
    print("[Config] GET /api/config 收到请求")
    raw = _load_json(_CONFIG_JSON, None)
    if raw is None:
        print("[Config] GET: 未找到配置文件，返回默认值")
        return _DEFAULT_CONFIG.copy()
    print(f"[Config] GET: 从 {_CONFIG_JSON} 读取")
    out = _DEFAULT_CONFIG.copy()
    if isinstance(raw.get("settings"), dict):
        out["settings"] = {**out["settings"], **raw["settings"]}
    if raw.get("theme") in ("light", "dark"):
        out["theme"] = raw["theme"]
    if isinstance(raw.get("assistantPos"), dict):
        out["assistantPos"] = {
            "x": raw["assistantPos"].get("x"),
            "y": raw["assistantPos"].get("y"),
        }
    return out


@app.put("/api/config")
def put_config(body: ConfigUpdate):
    """部分更新配置并持久化."""
    print("[Config] PUT /api/config 收到请求")
    print(f"[Config] PUT: 目标文件 {_CONFIG_JSON.resolve()}")
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        current = _load_json(_CONFIG_JSON, _DEFAULT_CONFIG.copy())
        if not isinstance(current, dict):
            current = _DEFAULT_CONFIG.copy()
        if body.settings is not None:
            current["settings"] = {**(current.get("settings") or {}), **body.settings}
        if body.theme is not None:
            current["theme"] = body.theme
        if body.assistantPos is not None:
            current["assistantPos"] = {**(current.get("assistantPos") or {}), **body.assistantPos}
        _save_json(_CONFIG_JSON, current)
        print(f"[Config] PUT: 已写入 {_CONFIG_JSON.resolve()}")
        return get_config()
    except Exception as e:
        print(f"[Config] PUT 失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, detail=f"配置保存失败: {e}")


# ─── 读取 Dashboard 数据 ──────────────────────────────────────────────────────

@app.get("/api/dashboard/data")
def get_dashboard_data():
    """返回最近一次提取的 Dashboard 数据（事件、任务、话题、联系人、简报）。"""
    data = _load_json(_DASHBOARD_JSON, {
        "events":    [],
        "topics":    [],
        "people":    [],
        "brief":     "",
        "stats":     {},
        "extracted_at": None,
        "is_extracting": False,
    })
    # 过滤用户已删除的事件（持久化列表），重开软件后也不会再显示
    deleted_ids = set(data.get("deleted_event_ids") or [])
    if deleted_ids:
        data["events"] = [e for e in (data.get("events") or []) if _event_id(e) not in deleted_ids]
    # 兼容旧数据：确保每条都有 kind（event=已发生 / task=待办）
    for ev in data.get("events") or []:
        ev.setdefault("kind", "task")
    # 调试：提取中时打印进度；完成后也打一条，确认前端能拿到结束状态
    if data.get("is_extracting"):
        prog = data.get("extract_progress")
        if prog:
            print(f"[Dashboard] 提取进度 → 前端: {prog.get('current')}/{prog.get('total')} {prog.get('message', '')}")
        else:
            print("[Dashboard] 提取中，尚未写入进度（可能 work_items 为空或尚未开始写）")
    else:
        print(f"[Dashboard] API 返回已完成 is_extracting=False events={len(data.get('events') or [])} brief_len={len(data.get('brief') or '')}")
    return data


@app.get("/api/dashboard/context-for-assistant")
def get_dashboard_context_for_assistant():
    """返回供邮件助手使用的精简工作台上下文（简报摘要、任务/事件、看板、联系人），便于 AI 精确回答相关提问。"""
    data = _load_json(_DASHBOARD_JSON, {})
    deleted_ids = set(data.get("deleted_event_ids") or [])
    events = [e for e in (data.get("events") or []) if _event_id(e) not in deleted_ids]
    for ev in events:
        ev.setdefault("kind", "task")
    tasks = [e for e in events if (e.get("kind") or "task") == "task"]
    brief = (data.get("brief") or "").strip()[:800]
    people = data.get("people") or []
    todos_raw = _load_json(_TODOS_JSON, [])
    by_status = {"todo": [], "doing": [], "done": []}
    for t in todos_raw:
        s = (t.get("status") or "todo").lower()
        if s in by_status:
            by_status[s].append(t.get("title") or t.get("id", ""))
    return {
        "brief_excerpt": brief,
        "tasks_count": len(tasks),
        "tasks": [{"title": e.get("title"), "datetime": e.get("datetime"), "type": e.get("type")} for e in tasks[:30]],
        "todos_todo": by_status["todo"],
        "todos_doing": by_status["doing"],
        "todos_done": by_status["done"],
        "people": [p.get("from") or p.get("name", "") for p in people[:15]],
    }


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


class EventDeleteRequest(BaseModel):
    event: dict
    user_reason: str | None = None
    reject_ai_reason: bool = False


class EventPriorityRequest(BaseModel):
    event: dict
    new_priority: str  # high | medium | low
    user_reason: str | None = None


@app.post("/api/dashboard/event-priority")
def update_event_priority_and_record_feedback(body: EventPriorityRequest):
    """更新某条事件的优先级并记录用户反馈，供下次提取时 AI 参考。"""
    ev = body.event
    if not ev or not ev.get("title"):
        raise HTTPException(400, detail="缺少事件信息")
    new_priority = (body.new_priority or "").strip().lower()
    if new_priority not in ("high", "medium", "low"):
        raise HTTPException(400, detail="new_priority 须为 high / medium / low")
    eid = _event_id(ev)
    import datetime as _dt
    feedback = _load_priority_feedback()
    feedback.append({
        "event_id": eid,
        "title": ev.get("title", ""),
        "old_priority": (ev.get("priority") or "medium").lower(),
        "new_priority": new_priority,
        "ai_reason": ev.get("reason"),
        "user_reason": (body.user_reason or "").strip() or None,
        "updated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    })
    _save_priority_feedback(feedback)
    data = _load_json(_DASHBOARD_JSON, {})
    events = data.get("events") or []
    found = False
    for e in events:
        if _event_id(e) == eid:
            e["priority"] = new_priority
            found = True
            break
    if found:
        data["events"] = events
        _save_json(_DASHBOARD_JSON, data)
    return {"success": True, "message": "已更新优先级并记录反馈"}


@app.post("/api/dashboard/event-delete")
def delete_event_and_record_feedback(body: EventDeleteRequest):
    ev = body.event
    if not ev or not ev.get("title"):
        raise HTTPException(400, detail="缺少事件信息")
    eid = _event_id(ev)
    feedback = _load_deletion_feedback()
    import datetime as _dt
    feedback.append({
        "event_id": eid,
        "title": ev.get("title", ""),
        "datetime": ev.get("datetime", ""),
        "source_key": ev.get("source_key", ""),
        "user_reason": (body.user_reason or "").strip() or None,
        "reject_ai_reason": body.reject_ai_reason,
        "ai_reason": ev.get("reason"),
        "deleted_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    })
    _save_deletion_feedback(feedback)
    data = _load_json(_DASHBOARD_JSON, {})
    events = data.get("events") or []
    new_events = [e for e in events if _event_id(e) != eid]
    if len(new_events) == len(events):
        return {"success": True, "message": "未在列表中找到该事件"}
    data["events"] = new_events
    # 持久化已删除事件 ID，重开软件或重新提取后也不会再显示
    deleted_ids = list(data.get("deleted_event_ids") or [])
    if eid and eid not in deleted_ids:
        deleted_ids.append(eid)
        data["deleted_event_ids"] = deleted_ids[-500:]  # 最多保留 500 条
    _save_json(_DASHBOARD_JSON, data)
    return {"success": True, "message": "已删除并记录反馈"}


# ─── 触发事件提取 ─────────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    base_url: str
    api_key:  str
    model:    str
    ai_days:  int = 7
    max_emails_per_folder: int = 500  # 仅按天数筛选后的上限，不刻意压低；设置里填几天就读该天数内邮件
    max_chars_per_email:   int = 1500
    max_folders_per_account: int = 3  # 每账号最多处理几个文件夹（INBOX 优先）
    force_reextract: bool = False  # True = 清除已提取标记后全量重新提取


async def _do_extract(req: ExtractRequest) -> None:
    """后台任务：遍历所有账号所有文件夹，提取事件，更新 dashboard.json。"""
    import mailbox as _mb
    import datetime
    import logging
    log = logging.getLogger("extract")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("[extract] %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
    print("[提取] 任务开始")

    # 保存当前 dashboard 副本，用于错误时保留已有数据及最终合并
    previous_data = _load_json(_DASHBOARD_JSON, {})
    existing = dict(previous_data)
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

        # 预计算待处理列表，用于进度条 total
        work_items: list[tuple] = []
        for acc in accounts:
            mail_dir = acc.get("mail_dir", "")
            if not mail_dir or not Path(mail_dir).exists():
                continue
            all_folders = list_folders(mail_dir)
            folders = sorted(
                all_folders,
                key=lambda f: (0 if (f.get("name") or "").upper() == "INBOX" else 1, f.get("name") or ""),
            )[: req.max_folders_per_account]
            for folder in folders:
                mbox_path = str(Path(mail_dir) / folder["folder_id"].replace("/", "\\"))
                if Path(mbox_path).exists():
                    work_items.append((acc, folder, mail_dir))
        total_folders = len(work_items)
        _log(f"待处理文件夹总数: {total_folders}")
        print(f"[提取] 待处理文件夹总数: {total_folders}（0 则不会显示进度条）")

        # 提前设置，供后续简报生成使用（当所有文件夹均为「未提取: 0」时不会进循环，此处保证 base_url 已定义）
        base_url = _normalize_base_url(req.base_url)

        # 增量提取：仅处理未标记的邮件
        extracted_keys = _load_extracted_keys()
        _log(f"已提取标记数量: {len(extracted_keys)}")

        def _save_progress(current: int, message: str):
            try:
                prog = _load_json(_DASHBOARD_JSON, {})
                prog["is_extracting"] = True
                prog["extract_log"] = list(extract_log)
                prog["extract_progress"] = {"current": current, "total": total_folders, "message": message}
                _save_json(_DASHBOARD_JSON, prog)
                print(f"[提取] 进度已写入: {current}/{total_folders} — {message}")
            except Exception as e:
                print(f"[提取] 写入进度失败: {e}")

        current_step = 0
        for acc, folder, mail_dir in work_items:
            current_step += 1
            acc_email = acc.get("email", "?")
            folder_name = folder.get("name", "?")
            _save_progress(current_step, f"{acc_email} / {folder_name}")

            _log(f"--- 账号: {acc_email}, mail_dir: {mail_dir}")
            _log(f"  [{folder_name}] 开始处理 ({current_step}/{total_folders})")

            mbox_path = str(Path(mail_dir) / folder["folder_id"].replace("/", "\\"))

            try:
                idx = MboxIndex.get(mbox_path)
            except Exception as e:
                _log(f"  [{folder_name}] 索引失败: {e}")
                continue

            filtered = [
                e for e in idx.entries
                if e.get("epoch_ms")
                and datetime.datetime.fromtimestamp(
                    e["epoch_ms"] / 1000, datetime.timezone.utc
                ).date()
                >= cutoff
            ][: req.max_emails_per_folder]

            # 增量：只处理尚未标记的邮件
            folder_id = folder.get("folder_id", "")
            def _composite_key(entry):
                return f"{acc_email}|{folder_id}|{entry.get('key', '')}"
            filtered_new = [e for e in filtered if _composite_key(e) not in extracted_keys]
            _log(f"  [{folder_name}] 符合日期: {len(filtered)}，其中未提取: {len(filtered_new)}")
            if not filtered_new:
                continue
            filtered = filtered_new

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
                    raw_date = entry.get("date", "")
                    items.append({
                        "key":           key,
                        "subject":       entry.get("subject", ""),
                        "from":          entry.get("from", ""),
                        "date":          raw_date,
                        "received_date": _normalize_mail_date(raw_date),
                        "body":          body,
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
            acc_meta.setdefault(acc_email, []).extend(folder_meta)
            _log(f"  [{folder_name}] 读取正文完成: {len(emails_for_ai)} 封")

            if not emails_for_ai:
                continue

            system_p = get_prompt("extract", "system", current_year=today.year)
            user_p   = get_prompt(
                "extract", "user_template",
                today=today.isoformat(),
                count=len(emails_for_ai),
                emails_json=json.dumps(emails_for_ai, ensure_ascii=False),
                user_feedback=_format_user_feedback_for_prompt(),
                priority_feedback=_format_priority_feedback_for_prompt(),
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
                        events = _parse_extract_json(raw)
                        if isinstance(events, list):
                            key_to_date = {it["key"]: (it.get("received_date") or it.get("date") or "").strip() for it in emails_for_ai if (it.get("received_date") or it.get("date"))}
                            for ev in events:
                                ev.setdefault("kind", "task")  # event=已发生仅提醒, task=有未来待办
                                ev["account"] = acc.get("email", "")
                                ev["folder"]  = folder.get("name", "")
                                _patch_event_datetime_from_mail(ev, key_to_date)
                                _sanitize_event_datetime(ev, key_to_date, today.year)
                            all_events.extend(events)
                            acc_events.setdefault(acc.get("email", "?"), []).extend(events)
                            _log(f"  [{folder_name}] 提取事件: {len(events)} 个")
                            # 增量：标记本批邮件已提取
                            for e in filtered:
                                extracted_keys.add(_composite_key(e))
                            _save_extracted_keys(extracted_keys)
                        else:
                            _log(f"  [{folder_name}] AI 返回非列表: {type(events)}")
                    except json.JSONDecodeError as je:
                        _log(f"  [{folder_name}] JSON 解析失败: {je} | raw前200字: {raw[:200]}")
                else:
                    # API 明确错误（余额不足等）：停止重试，保留已有数据
                    err_body = ""
                    try:
                        err_body = resp.text
                        err_json = resp.json()
                        err_msg = err_json.get("error", {}).get("message") or err_json.get("message") or err_json.get("detail")
                        if isinstance(err_msg, list):
                            err_msg = err_msg[0] if err_msg else ""
                        if isinstance(err_msg, dict):
                            err_msg = err_msg.get("message", str(err_msg))
                    except Exception:
                        err_msg = err_body[:200] if err_body else ""
                    if resp.status_code == 402:
                        err_msg = "API 余额不足 (402)，请充值后再试。" + (f" 详情: {err_msg}" if err_msg else "")
                    elif resp.status_code == 401:
                        err_msg = "API 认证失败 (401)，请检查 API Key。" + (f" 详情: {err_msg}" if err_msg else "")
                    elif resp.status_code == 429:
                        err_msg = "API 请求过于频繁或配额用尽 (429)，请稍后再试。" + (f" 详情: {err_msg}" if err_msg else "")
                    else:
                        err_msg = f"API 错误 {resp.status_code}。" + (f" 详情: {err_msg}" if err_msg else "")
                    _log(f"  [{folder_name}] {err_msg}")
                    previous_data["extract_error"] = err_msg
                    previous_data["is_extracting"] = False
                    previous_data["extract_progress"] = None
                    previous_data["extract_log"] = list(extract_log)
                    _save_json(_DASHBOARD_JSON, previous_data)
                    print(f"[提取] 已停止并保留已有数据，错误: {err_msg[:80]}")
                    return
            except Exception as e:
                _log(f"  [{folder_name}] AI 调用异常: {type(e).__name__}: {e}")
            try:
                prog = _load_json(_DASHBOARD_JSON, {})
                prog["is_extracting"] = True
                prog["extract_log"] = list(extract_log)
                prog["extract_progress"] = {"current": current_step, "total": total_folders, "message": f"{acc_email} / {folder_name}"}
                _save_json(_DASHBOARD_JSON, prog)
                print(f"[提取] 进度已写入: {current_step}/{total_folders} — {acc_email} / {folder_name}")
            except Exception as e:
                print(f"[提取] 写入进度失败: {e}")

        # 去重（相同 title + datetime 认为是同一事件）
        seen = set()
        unique_events = []
        for ev in all_events:
            key = f"{ev.get('title','')}|{ev.get('datetime','')}"
            if key not in seen:
                seen.add(key)
                unique_events.append(ev)

        # 与已有数据合并：按 (账号, source_key) 以新覆盖旧，避免不同账号相同 key 互相覆盖导致事件丢失
        existing_events = previous_data.get("events") or []
        existing_metas = previous_data.get("extract_metas") or []
        ev_by_key = {_merge_key(e): e for e in existing_events}
        for e in unique_events:
            ev_by_key[_merge_key(e)] = e
        merged_events = list(ev_by_key.values())
        merged_meta = existing_metas + all_meta
        seen2 = set()
        unique_events = []
        for ev in merged_events:
            ev.setdefault("kind", "task")  # 旧数据无 kind 时视为任务
            k = f"{ev.get('title','')}|{ev.get('datetime','')}"
            if k not in seen2:
                seen2.add(k)
                unique_events.append(ev)

        # 按时间排序
        def _ev_sort_key(ev):
            dt = ev.get("datetime") or ""
            return dt

        unique_events.sort(key=_ev_sort_key)

        # 排除用户已删除的事件（持久化），重新提取后也不会再出现
        deleted_ids = set(previous_data.get("deleted_event_ids") or [])
        if deleted_ids:
            unique_events = [e for e in unique_events if _event_id(e) not in deleted_ids]

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

        def _normalize_sender(s):
            """去掉发件人字符串首尾的双引号并 trim，便于合并同一联系人且展示时不以引号开头。"""
            if not s or not isinstance(s, str):
                return (s or "未知").strip()
            s = s.strip()
            if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
                s = s[1:-1].strip()
            return s or "未知"

        # 联系人聚合（基于合并后 meta，发件人先规范化再作为 key）
        people_map: dict[str, dict] = {}
        for m in merged_meta:
            raw_from = m.get("from", "未知")
            sender = _normalize_sender(raw_from)
            if sender not in people_map:
                people_map[sender] = {"from": sender, "count": 0, "latest": ""}
            people_map[sender]["count"] += 1
            if m.get("date", "") > people_map[sender]["latest"]:
                people_map[sender]["latest"] = m.get("date", "")
        people = sorted(people_map.values(), key=lambda p: -p["count"])[:20]

        # 统计（基于合并后）
        stats = {
            "total_emails":   len(merged_meta),
            "total_events":   len(unique_events),
            "accounts_count": len(accounts),
            "ai_days":        req.ai_days,
        }

        # 按账号合并事件与 meta（先算好，供分账号简报与全局汇总用）
        merged_acc_events = {}
        for ev in unique_events:
            acc = ev.get("account", "?")
            merged_acc_events.setdefault(acc, []).append(ev)
        merged_acc_meta = {}
        for m in merged_meta:
            acc = m.get("account", "?")
            merged_acc_meta.setdefault(acc, []).append(m)

        # 生成今日简报：先各账号独立简报，再汇总为全局简报
        import datetime as _dt
        weekday_cn = ["周一","周二","周三","周四","周五","周六","周日"]
        wd = weekday_cn[today.weekday()]
        brief_system = get_prompt("brief", "system")

        async def _gen_brief(account_label: str, metas: list, evs: list) -> str:
            """为指定账号生成简报，返回简报文本。"""
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

        # 各账号独立简报（先生成，供全局汇总）
        account_briefs: dict[str, str] = {}
        for acc_email_key, a_metas in merged_acc_meta.items():
            a_events = merged_acc_events.get(acc_email_key, [])
            if a_metas:
                account_briefs[acc_email_key] = await _gen_brief(acc_email_key, a_metas, a_events)

        # 全局简报：由各子邮箱简报汇总，确保包含各子简报中的重要事项
        if account_briefs:
            account_briefs_text = "\n\n---\n\n".join(
                f"【{acc}】\n{text}" for acc, text in account_briefs.items()
            )
            try:
                global_sys = get_prompt("brief", "global_system")
                global_user = get_prompt(
                    "brief", "global_user_template",
                    today=today.isoformat(),
                    weekday=wd,
                    account_briefs_text=account_briefs_text,
                )
                payload_g = _build_chat_payload(
                    model=req.model,
                    messages=[
                        {"role": "system", "content": global_sys},
                        {"role": "user",   "content": global_user},
                    ],
                    temperature=0.3,
                    max_tokens=800,
                )
                _log("生成简报 [全局]（由各账号简报汇总）…")
                async with httpx.AsyncClient(timeout=60) as client:
                    resp_g = await client.post(
                        f"{base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {req.api_key}",
                                 "Content-Type": "application/json"},
                        json=payload_g,
                    )
                if resp_g.status_code == 200:
                    brief_text = resp_g.json()["choices"][0]["message"]["content"].strip()
                    _log(f"简报 [全局] 生成成功，长度 {len(brief_text)}")
                else:
                    _log(f"简报 [全局] 生成失败: {resp_g.status_code}，回退为单次生成")
                    brief_text = await _gen_brief("全局", merged_meta, unique_events)
            except Exception as e:
                _log(f"简报 [全局] 异常: {type(e).__name__}: {e}，回退为单次生成")
                brief_text = await _gen_brief("全局", merged_meta, unique_events)
        else:
            brief_text = await _gen_brief("全局", merged_meta, unique_events)

        _log(f"提取完成: 事件 {len(unique_events)} 个，邮件元数据 {len(merged_meta)} 封")
        print(f"[提取] 任务完成: 事件 {len(unique_events)} 个")
        now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")

        # 按账号统计（基于合并后）
        account_stats: dict[str, dict] = {}
        for ae, am in merged_acc_meta.items():
            account_stats[ae] = {
                "email_count": len(am),
                "event_count": len(merged_acc_events.get(ae, [])),
            }

        result = {
            "events":            unique_events,
            "topics":            topics,
            "people":            people,
            "brief":             brief_text,
            "account_briefs":    account_briefs,
            "account_stats":     account_stats,
            "acc_events":        {k: list(v) for k, v in merged_acc_events.items()},
            "stats":             stats,
            "extract_metas":     merged_meta,  # 供下次合并使用
            "deleted_event_ids": previous_data.get("deleted_event_ids") or [],  # 持久化用户删除列表
            "extracted_at":      now_iso,
            "is_extracting":     False,
            "extract_log":       extract_log,
            "extract_progress":  None,
        }
        _save_json(_DASHBOARD_JSON, result)
        # 确认写入成功，避免前端因缓存等原因一直拿到旧状态
        verify = _load_json(_DASHBOARD_JSON, {})
        print(f"[提取] dashboard 已写入 is_extracting={verify.get('is_extracting')} events={len(verify.get('events') or [])}")

        # ── 将本次简报追加到历史 ──────────────────────────────────────────────
        if brief_text or account_briefs:
            briefs = _load_json(_BRIEFS_JSON, [])
            today_key = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
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
        print(f"[提取] 任务异常: {e}\n{err_detail}")
        # 只更新错误状态，不覆盖已有 events/brief 等
        existing = _load_json(_DASHBOARD_JSON, {})
        existing["is_extracting"]   = False
        existing["extract_error"]   = str(e)
        existing["extract_progress"] = None
        existing["extract_log"]    = extract_log + [f"FATAL: {err_detail}"]
        _save_json(_DASHBOARD_JSON, existing)


@app.post("/api/dashboard/extract")
async def trigger_extract(req: ExtractRequest):
    """触发 Dashboard 事件提取（后台异步执行，立即返回）。增量提取：仅处理未标记的邮件。"""
    if req.force_reextract:
        _save_extracted_keys(set())
        print("[提取] 已清除已提取标记，将全量重新提取")
    # 立即写入「提取中」，方便前端第一次 loadData 就显示进度区域
    existing = _load_json(_DASHBOARD_JSON, {})
    existing["is_extracting"] = True
    existing.pop("extract_error", None)
    _save_json(_DASHBOARD_JSON, existing)
    print("[提取] 已标记 is_extracting=True，前端可轮询进度")
    asyncio.create_task(_do_extract(req))
    return {"success": True, "message": "提取任务已启动，请稍后刷新"}


@app.delete("/api/dashboard/extracted-keys")
def clear_extracted_keys():
    """清除「已提取」标记，下次提取将全量重新处理。并重置 dashboard 的提取中状态，避免提取按钮一直灰。"""
    _save_extracted_keys(set())
    data = _load_json(_DASHBOARD_JSON, {})
    if data.get("is_extracting") or data.get("extract_progress"):
        data["is_extracting"] = False
        data["extract_progress"] = None
        _save_json(_DASHBOARD_JSON, data)
    return {"success": True, "message": "已清除已提取标记"}


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
    now = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    d = item.model_dump()
    d["created_at"] = d["updated_at"] = now
    todos.append(d)
    _save_json(_TODOS_JSON, todos)
    return {"success": True, "todo": d}


@app.put("/api/dashboard/todos/{todo_id}")
def update_todo(todo_id: str, item: TodoItem):
    import datetime as _dt
    todos = _load_json(_TODOS_JSON, [])
    now = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
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

    # 每次启动前自动构建前端（路径相对 backend/main.py：项目根 = parent.parent）
    import subprocess
    project_root = Path(__file__).resolve().parent.parent
    frontend_dir = project_root / "frontend"
    if not frontend_dir.exists():
        print(f"未找到前端目录: {frontend_dir}")
        sys.exit(1)
    print("正在执行 npm run build …")
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
    # 必须在所有 API 路由注册后再挂载 SPA，否则 /api/* 会被通配路由吃掉并返回 index.html
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
