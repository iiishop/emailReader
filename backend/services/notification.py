"""
系统通知（Windows Toast）与「复制验证码」页面逻辑。
与路由解耦：路由只负责参数与 HTTP，此处负责文案与 winotify 调用。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from typing import List


NOTIFY_BASE_URL = os.environ.get("EMAILREADER_BASE_URL", "http://127.0.0.1:8000")


def show_new_mail_toast(
    count: int,
    subjects: List[str],
    from_str: str = "",
    folder_name: str = "",
    verification_code: str | None = None,
) -> None:
    """在系统托盘/操作中心显示新邮件提醒；若提供验证码则带「复制验证码」按钮。仅 Windows 使用 winotify。"""
    if sys.platform != "win32":
        return
    try:
        from winotify import Notification
        title = "新邮件"
        if count == 1:
            subj = subjects[0] if subjects else ""
            msg = (subj[:60] + "…") if len(subj) > 60 else (subj or "（无主题）")
            if from_str:
                msg = from_str[:30] + "：" + msg
        else:
            msg = f"共 {count} 封新邮件"
            if folder_name:
                msg += f"（{folder_name}）"
        toast = Notification(
            app_id="EmailReader",
            title=title,
            msg=msg,
            duration="short",
        )
        if verification_code:
            copy_url = f"{NOTIFY_BASE_URL}/api/copy-code?code={urllib.parse.quote(verification_code)}"
            toast.add_actions("复制验证码", copy_url)
        toast.show()
    except Exception as e:
        print(f"[Notify] 新邮件通知失败: {e}")


def get_copy_code_html(code: str) -> str:
    """生成「复制验证码」页的 HTML：脚本执行剪贴板写入并显示结果。"""
    escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>复制验证码</title></head>
<body style="font-family: system-ui; padding: 24px; text-align: center;">
  <p id="msg">正在复制…</p>
  <p style="color:#666; font-size:14px;" id="code">{escaped}</p>
  <script>
    var code = {json.dumps(code)};
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(code).then(function() {{
        document.getElementById("msg").textContent = "验证码已复制到剪贴板";
      }}, function() {{ document.getElementById("msg").textContent = "复制失败，请手动复制上方数字"; }});
    }} else {{
      document.getElementById("msg").textContent = "请手动复制上方验证码";
    }}
  </script>
</body></html>"""
