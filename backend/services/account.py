"""
账号与 mbox 路径解析：统一 get_account、require_mail_dir、resolve_mbox_path，
避免在各路由中重复「account → mail_dir → mbox_path」三段式。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from thunderbird import read_thunderbird_accounts


def get_account(account_id: str) -> dict:
    """从 Thunderbird 账号列表中查找指定账号；不存在或失败时抛出 HTTPException。"""
    result = read_thunderbird_accounts()
    if not result["success"]:
        raise HTTPException(502, detail=result["error"])
    account = next((a for a in result["accounts"] if a["account_id"] == account_id), None)
    if account is None:
        raise HTTPException(404, detail=f"账号 {account_id} 不存在")
    return account


def require_mail_dir(account: dict) -> str:
    """返回账号本地邮件目录；无目录时抛出 HTTPException。"""
    mail_dir = account.get("mail_dir")
    if not mail_dir:
        raise HTTPException(404, detail="该账号没有本地邮件目录")
    return mail_dir


def resolve_mbox_path(
    account_id: str,
    folder_id: Optional[str] = None,
) -> tuple[dict, str, Optional[str]]:
    """
    统一解析：账号 → 邮件目录 → mbox 路径。
    返回 (account, mail_dir, mbox_path)。
    folder_id 为 None 或空时，mbox_path 为 None（仅需 account/mail_dir 时使用）。
    """
    account = get_account(account_id)
    mail_dir = require_mail_dir(account)
    if not folder_id or not folder_id.strip():
        return (account, mail_dir, None)
    mbox_path = str(Path(mail_dir) / folder_id.replace("/", "\\"))
    return (account, mail_dir, mbox_path)
