"""
从邮件正文/主题等文本中提取结构化信息（如验证码）。
与 email_processor（格式转换）分离，专注「内容理解」类抽取。
"""
from __future__ import annotations

import re


def extract_verification_code(text: str) -> str | None:
    """从邮件正文/主题中提取验证码（4～8 位数字）。若无法判定为验证码邮件则返回 None。"""
    if not (text and text.strip()):
        return None
    # 去掉 HTML 标签，便于正则匹配
    plain = re.sub(r"<[^>]+>", " ", text)
    plain = re.sub(r"\s+", " ", plain).strip()
    # 常见验证码关键词 + 数字
    patterns = [
        r"验证码[：:\s]*(\d{4,8})",
        r"您的验证码[：:\s]*(\d{4,8})",
        r"动态码[：:\s]*(\d{4,8})",
        r"校验码[：:\s]*(\d{4,8})",
        r"verification code[：:\s]*(\d{4,8})",
        r"(?i)code[：:\s]*(\d{4,8})",
        r"验证码是\s*(\d{4,8})",
        r"为[：:\s]*(\d{4,8})\s*[，,。.；;]",
    ]
    for pat in patterns:
        m = re.search(pat, plain)
        if m:
            return m.group(1)
    # 若文中含「验证码」且存在 6 位数字，取第一个 6 位
    if "验证码" in plain or "verification" in plain.lower():
        m = re.search(r"\b(\d{6})\b", plain)
        if m:
            return m.group(1)
    return None
