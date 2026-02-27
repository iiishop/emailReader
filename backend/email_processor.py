"""
邮件内容预处理：将 HTML 转为 Markdown，供 AI 读取。

设计原则：
- 只保留文字语义内容（段落、链接、列表、标题、引用）
- 删除图片（用 [图片] 占位）、删除样式/脚本
- 不换行截断（body_width=0），让 AI 自己处理段落
- 对纯文本邮件直接原样返回
"""

from __future__ import annotations

import re
import html2text as _h2t


def _make_converter() -> _h2t.HTML2Text:
    h = _h2t.HTML2Text()
    h.ignore_links        = False   # 保留链接文字（去掉 URL 本身可选）
    h.ignore_images       = True    # 忽略图片 src，减少无用 Token
    h.ignore_emphasis     = False   # 保留粗体/斜体语义
    h.ignore_tables       = False   # 表格转 ASCII 表格
    h.body_width          = 0       # 不强制换行
    h.unicode_snob        = True    # 保留 Unicode（中文）
    h.protect_links       = False
    h.wrap_links          = False
    h.skip_internal_links = True    # 忽略锚点链接
    h.single_line_break   = False
    h.mark_code           = True    # <code> → `code`
    return h


_CONVERTER = _make_converter()
_BLANK_LINES = re.compile(r'\n{3,}')
_ONLY_URL_LINK = re.compile(r'\[([^\]]+)\]\(https?://[^\)]+\)')


def html_to_markdown(html: str, *, keep_links: bool = False) -> str:
    """
    将 HTML 字符串转换为 Markdown。

    Args:
        html:        原始 HTML 字符串
        keep_links:  True 保留超链接 URL，False 只保留链接文字（默认，减少 Token）

    Returns:
        清洗后的 Markdown 字符串
    """
    if not html or not html.strip():
        return ""

    _CONVERTER.ignore_links = not keep_links

    try:
        md = _CONVERTER.handle(html)
    except Exception:
        # 极端情况（编码损坏等），直接返回去标签的纯文本
        md = re.sub(r"<[^>]+>", " ", html)

    # 折叠多余空行
    md = _BLANK_LINES.sub('\n\n', md).strip()
    return md


def text_to_ai_content(
    text_html: str,
    text_plain: str,
    *,
    max_chars: int = 8000,
    keep_links: bool = False,
) -> str:
    """
    将邮件的 HTML / 纯文本正文转换为适合喂给 AI 的 Markdown 字符串。

    优先使用 HTML（信息更完整），其次使用纯文本。
    超过 max_chars 时截断并附注提示。
    """
    if text_html and text_html.strip():
        content = html_to_markdown(text_html, keep_links=keep_links)
        source = "html"
    elif text_plain and text_plain.strip():
        content = text_plain.strip()
        source = "plain"
    else:
        return ""

    _ = source  # 保留供调试用
    if len(content) > max_chars:
        content = content[:max_chars] + f"\n\n…（正文过长，已截断至 {max_chars} 字符）"

    return content
