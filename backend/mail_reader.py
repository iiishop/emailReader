"""
快速 mbox 读取器：
1. 使用 mmap 只扫描邮件头部（跳过正文体），大幅减少 IO 和解析量
2. 内存索引缓存（mtime 失效），同一文件二次请求 <1ms
3. 线程安全，支持多线程并发预热

Thunderbird X-Mozilla-Status 标志（十六进制）：
  0x0001  MSG_FLAG_READ       已读
  0x0002  MSG_FLAG_REPLIED    已回复
  0x0004  MSG_FLAG_MARKED     星标
  0x0008  MSG_FLAG_EXPUNGED   逻辑删除（不显示）
  0x0080  MSG_FLAG_IMAP_DELETED  IMAP 删除

X-Mozilla-Status2：
  0x00080000  MSG_FLAG_ATTACHMENT  有附件
"""

import os
import re
import threading
import email
import email.header
import email.utils
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

# ─── 标志常量 ─────────────────────────────────────────────────────────────────

FLAG_READ          = 0x0001
FLAG_REPLIED       = 0x0002
FLAG_MARKED        = 0x0004
FLAG_EXPUNGED      = 0x0008
FLAG_IMAP_DELETED  = 0x0080
FLAG2_ATTACHMENT   = 0x00080000

# 共享线程池（4 线程，用于后台预热索引）
thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mbox")


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def _decode_header(raw: Optional[bytes | str]) -> str:
    if not raw:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        parts = email.header.decode_header(raw)
        return "".join(
            p.decode(cs or "utf-8", errors="replace") if isinstance(p, bytes) else p
            for p, cs in parts
        )
    except Exception:
        return str(raw)


def _parse_date(raw: Optional[bytes | str]) -> Optional[str]:
    """
    将邮件 Date 头解析为 UTC ISO-8601 字符串。
    依次尝试三种策略，均失败时返回 None（前端再也不会收到无法解析的字符串）。
    """
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    raw = raw.strip()
    if not raw:
        return None

    # 策略 1：标准 RFC 2822 解析
    try:
        return email.utils.parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    # 策略 2：parsedate 返回时间元组（对某些非标准格式更宽松）
    try:
        t = email.utils.parsedate(raw)
        if t and t[0]:  # t[0] 是年份，为 0 表示解析失败
            return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
    except Exception:
        pass

    # 策略 3：正则提取 "dd Mon yyyy HH:MM:SS" 核心部分再解析
    try:
        _MONTHS = {m: i+1 for i, m in enumerate(
            ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
        )}
        m = re.search(
            r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})",
            raw,
        )
        if m:
            day, mon, yr, hh, mm, ss = m.groups()
            month = _MONTHS.get(mon.lower())
            if month:
                return datetime(int(yr), month, int(day),
                                int(hh), int(mm), int(ss),
                                tzinfo=timezone.utc).isoformat()
    except Exception:
        pass

    return None  # 彻底无法解析，前端会显示"日期未知"


def _extract_preview_from_body(body_bytes: bytes, max_chars: int = 200) -> str:
    """从原始 mbox 正文 bytes 中提取纯文本预览（不解析完整结构）。"""
    try:
        msg = email.message_from_bytes(body_bytes)
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        cs = part.get_content_charset() or "utf-8"
                        return " ".join(payload.decode(cs, errors="replace").split())[:max_chars]
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                cs = msg.get_content_charset() or "utf-8"
                return " ".join(payload.decode(cs, errors="replace").split())[:max_chars]
    except Exception:
        pass
    return ""


# ─── 核心索引类 ───────────────────────────────────────────────────────────────

class MboxIndex:
    """
    线程安全的 mbox 消息索引。

    首次访问：用 mmap 扫描文件，只读取每封邮件的头部（遇到 \\n\\n 停止），
    解析出元数据后按日期排序并缓存。

    文件未变化时再次访问直接返回缓存，耗时 <1ms。
    """

    _cache: dict[str, "MboxIndex"] = {}
    _lock = threading.Lock()

    def __init__(self, path: str) -> None:
        self.path = path
        self.mtime: float = 0.0
        self._entries: list[dict] = []  # 已过滤删除，按日期倒序
        self.unread_count: int = 0       # 未读邮件数（同步更新）

    # ── 公共接口 ──────────────────────────────────────────────────────────────

    @classmethod
    def get(cls, path: str) -> "MboxIndex":
        """返回缓存索引；文件 mtime 改变时自动重建。"""
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return cls._empty(path)

        with cls._lock:
            cached = cls._cache.get(path)
            if cached is not None and cached.mtime == mtime:
                return cached

        # 在锁外构建，避免阻塞其他线程
        idx = cls(path)
        idx._build()
        idx.mtime = mtime

        with cls._lock:
            cls._cache[path] = idx
        return idx

    @classmethod
    def invalidate(cls, path: str) -> None:
        """手动清除指定文件的缓存，下次 get() 时强制重建索引。"""
        with cls._lock:
            cls._cache.pop(path, None)

    @classmethod
    def _empty(cls, path: str) -> "MboxIndex":
        obj = cls.__new__(cls)
        obj.path = path
        obj.mtime = 0.0
        obj._entries = []
        obj.unread_count = 0
        return obj

    @property
    def entries(self) -> list[dict]:
        """所有邮件条目（只读视图）。"""
        return self._entries

    def page(self, skip: int, limit: int) -> tuple[int, int, list[dict]]:
        """返回 (总数, 未读数, 当前页条目)。"""
        return len(self._entries), self.unread_count, self._entries[skip : skip + limit]

    # ── 构建索引 ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        entries: list[dict] = []
        try:
            file_size = os.path.getsize(self.path)
            if file_size == 0:
                self._entries = []
                return
            entries = self._scan_fast(self.path)
        except Exception:
            pass

        # 按 ISO 字符串排序（UTC 时间，字典序等价于时间序）
        # None 的邮件排到最末尾（sort key 用空字符串）
        entries.sort(key=lambda e: e.get("date") or "", reverse=True)
        self._entries = entries
        self.unread_count = sum(1 for e in entries if not e.get("is_read", True))

        # 顺便把 epoch_ms 写入每条记录，供前端排序校验使用
        for e in self._entries:
            if e.get("date"):
                try:
                    from datetime import datetime as _dt
                    e["epoch_ms"] = int(
                        _dt.fromisoformat(e["date"]).timestamp() * 1000
                    )
                except Exception:
                    e["epoch_ms"] = 0
            else:
                e["epoch_ms"] = 0

    @staticmethod
    def _scan_fast(path: str) -> list[dict]:
        """
        快速扫描策略：
        1. 一次性读取整个文件到内存
        2. 用 bytes.split(b'\\nFrom ') 在 C 层级切割消息边界（远快于反复 find）
        3. 对每块只取头部（到 \\n\\n 为止）进行解析，跳过正文体
        """
        with open(path, "rb") as f:
            data = f.read()

        # 切割：第一块可能以 "From " 开头（无前置换行），其余块在 "\nFrom " 处断开
        SEP = b"\nFrom "
        if data.startswith(b"From "):
            # 把第一块和后续块统一成同一个列表
            parts = data.split(SEP)
            # 第一块本身已是完整头部区段；其余块前面丢掉了 \n，不影响内容
        else:
            first = data.find(SEP)
            if first == -1:
                return []
            parts = data[first + 1:].split(SEP)

        entries: list[dict] = []
        for key, part in enumerate(parts):
            # 取头部（到第一个空行）
            nl2 = part.find(b"\n\n")
            header_bytes = part[:nl2] if nl2 != -1 else part[:16_384]
            entry = MboxIndex._parse_headers(header_bytes, key)
            if entry is not None:
                entries.append(entry)

        return entries

    @staticmethod
    def _parse_headers(raw: bytes, key: int) -> Optional[dict]:
        """解析原始头部 bytes，返回消息摘要 dict；逻辑删除的返回 None。"""
        # 快速读取 X-Mozilla-Status（二进制查找，比全量解析快）
        status, status2 = 0, 0

        si = raw.find(b"X-Mozilla-Status:")
        if si != -1:
            se = raw.find(b"\n", si)
            val = raw[si + 17 : se].strip() if se != -1 else raw[si + 17 : si + 27].strip()
            try:
                status = int(val, 16)
            except ValueError:
                pass

        # 过滤逻辑删除
        if status & (FLAG_EXPUNGED | FLAG_IMAP_DELETED):
            return None

        s2i = raw.find(b"X-Mozilla-Status2:")
        if s2i != -1:
            s2e = raw.find(b"\n", s2i)
            val2 = raw[s2i + 18 : s2e].strip() if s2e != -1 else raw[s2i + 18 : s2i + 28].strip()
            try:
                status2 = int(val2, 16)
            except ValueError:
                pass

        # 全量解析头部字段
        hdrs: dict[str, bytes] = {}
        cur: Optional[str] = None

        for line in raw.split(b"\n"):
            line = line.rstrip(b"\r")
            if not line:
                continue
            if line.startswith(b"From ") and cur is None:
                continue  # 跳过 mbox 分隔行
            if line[0:1] in (b" ", b"\t") and cur:
                hdrs[cur] = hdrs[cur] + b" " + line.strip()
            elif b":" in line:
                colon = line.index(b":")
                k = line[:colon].strip().lower().decode("ascii", errors="replace")
                hdrs[k] = line[colon + 1 :].strip()
                cur = k

        def _h(k: str) -> str:
            return _decode_header(hdrs.get(k, b""))

        date_raw = hdrs.get("date", b"").decode("utf-8", errors="replace")

        return {
            "key": str(key),
            "message_id": _h("message-id").strip(),
            "subject": _h("subject"),
            "from": _h("from"),
            "to": _h("to"),
            "date": _parse_date(date_raw),
            "date_raw": date_raw,
            "is_read": bool(status & FLAG_READ),
            "is_replied": bool(status & FLAG_REPLIED),
            "is_starred": bool(status & FLAG_MARKED),
            "has_attachment": bool(status2 & FLAG2_ATTACHMENT),
            "preview": "",  # 预览需要读正文，按需加载
        }


# ─── 文件夹扫描 ───────────────────────────────────────────────────────────────

def list_folders(mail_dir: str) -> list[dict]:
    """扫描账号邮件目录，返回所有可读的 mbox 文件夹（无扩展名文件）。"""
    root = Path(mail_dir)
    if not root.exists():
        return []

    msf_names = {p.stem for p in root.rglob("*.msf")}
    folders: list[dict] = []

    for candidate in root.rglob("*"):
        if candidate.is_dir():
            continue
        if candidate.suffix.lower() in (".msf", ".dat", ".html", ".txt"):
            continue
        if candidate.name not in msf_names:
            continue
        try:
            size = candidate.stat().st_size
        except OSError:
            continue

        rel = candidate.relative_to(root)
        folder_id = str(rel).replace("\\", "/")
        folders.append({
            "folder_id": folder_id,
            "name": candidate.name,
            "path": str(candidate),
            "size_bytes": size,
        })

    folders.sort(key=lambda f: (f["name"] != "INBOX", f["name"].lower()))
    return folders


# ─── 邮件读取接口 ─────────────────────────────────────────────────────────────

def read_emails(
    mbox_path: str,
    *,
    skip: int = 0,
    limit: int = 100,
) -> dict:
    """
    从缓存索引分页返回邮件摘要列表（不含正文，速度极快）。
    首次调用会触发建索引；后续调用直接命中缓存。
    响应中包含 unread_total，供前端显示未读数徽章。
    """
    if not Path(mbox_path).exists():
        return {"success": False, "error": f"文件不存在: {mbox_path}", "emails": [], "total": 0, "unread_total": 0}

    idx = MboxIndex.get(mbox_path)
    total, unread_total, page = idx.page(skip, limit)

    return {
        "success": True,
        "error": None,
        "mbox_path": mbox_path,
        "total": total,
        "unread_total": unread_total,
        "skip": skip,
        "limit": limit,
        "emails": page,
    }


def read_email_body(mbox_path: str, key: str) -> dict:
    """读取单封邮件完整内容（含 HTML/纯文本正文）。key 为文件序号。"""
    import mailbox as _mailbox

    if not Path(mbox_path).exists():
        return {"success": False, "error": "mbox 文件不存在"}

    try:
        mbox = _mailbox.mbox(mbox_path, create=False)
        msg = mbox.get(int(key))
        mbox.close()
    except Exception as e:
        return {"success": False, "error": str(e)}

    if msg is None:
        return {"success": False, "error": "邮件不存在"}

    # 复用 MboxIndex 的状态解析
    status_raw = msg.get("X-Mozilla-Status", "0000")
    status2_raw = msg.get("X-Mozilla-Status2", "00000000")
    try:
        status = int(status_raw.strip(), 16)
    except ValueError:
        status = 0
    try:
        status2 = int(status2_raw.strip(), 16)
    except ValueError:
        status2 = 0

    def _dh(k: str) -> str:
        return _decode_header(msg.get(k, ""))

    text_plain = text_html = ""
    try:
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
    except Exception:
        pass

    return {
        "success": True,
        "key": key,
        "subject": _dh("Subject"),
        "from": _dh("From"),
        "to": _dh("To"),
        "cc": _dh("Cc"),
        "date": _parse_date(msg.get("Date", "")),
        "message_id": msg.get("Message-ID", "").strip(),
        "is_read": bool(status & FLAG_READ),
        "is_replied": bool(status & FLAG_REPLIED),
        "is_starred": bool(status & FLAG_MARKED),
        "has_attachment": bool(status2 & FLAG2_ATTACHMENT),
        "text_plain": text_plain,
        "text_html": text_html,
    }
