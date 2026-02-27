"""
读取本机 Thunderbird 配置，提取邮箱账号信息。
支持标准安装和 Microsoft Store (MSIX) 安装两种路径。
"""
import os
import re
import configparser
from pathlib import Path
from typing import Optional


def find_thunderbird_root() -> Optional[Path]:
    """查找 Thunderbird 配置根目录，兼容标准安装与 MSIX 安装。"""
    candidates = []

    appdata = os.environ.get("APPDATA", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")

    # 标准安装路径
    if appdata:
        candidates.append(Path(appdata) / "Thunderbird")
        candidates.append(Path(appdata) / "Mozilla" / "Thunderbird")

    # Microsoft Store (MSIX) 安装路径：扫描 Packages 目录
    if localappdata:
        packages_dir = Path(localappdata) / "Packages"
        if packages_dir.exists():
            for pkg in packages_dir.iterdir():
                if "MozillaThunderbird" in pkg.name or "thunderbird" in pkg.name.lower():
                    msix_path = pkg / "LocalCache" / "Roaming" / "Thunderbird"
                    if msix_path.exists():
                        candidates.append(msix_path)

    for path in candidates:
        if path.exists() and (path / "profiles.ini").exists():
            return path

    return None


def get_default_profile(tb_root: Path) -> Optional[Path]:
    """从 profiles.ini 读取当前活跃的 Profile 目录。

    优先级：
    1. [Install*] 节的 Default 路径（Thunderbird 实际启动时使用的）
    2. [Profile*] 节中 Default=1 的路径
    3. 第一个存在 prefs.js 的 Profile
    """
    profiles_ini = tb_root / "profiles.ini"
    config = configparser.ConfigParser()
    config.read(str(profiles_ini), encoding="utf-8")

    def resolve_path(raw_path: str, is_relative: bool) -> Path:
        if is_relative:
            return tb_root / raw_path.replace("/", os.sep)
        return Path(raw_path)

    # 优先：[Install*] 节（记录当前实际使用的 profile）
    for section in config.sections():
        if section.lower().startswith("install"):
            raw_path = config.get(section, "Default", fallback=None)
            if raw_path:
                candidate = tb_root / raw_path.replace("/", os.sep)
                if candidate.exists():
                    return candidate

    # 次选：[Profile*] 节中 Default=1
    fallback: Optional[Path] = None
    for section in config.sections():
        if not section.startswith("Profile"):
            continue
        raw_path = config.get(section, "Path", fallback=None)
        if not raw_path:
            continue
        is_relative = config.get(section, "IsRelative", fallback="1") == "1"
        profile_path = resolve_path(raw_path, is_relative)

        if fallback is None and profile_path.exists():
            fallback = profile_path

        if config.get(section, "Default", fallback="0") == "1":
            if profile_path.exists():
                return profile_path

    # 最后：第一个有 prefs.js 的 profile
    for section in config.sections():
        if not section.startswith("Profile"):
            continue
        raw_path = config.get(section, "Path", fallback=None)
        if not raw_path:
            continue
        is_relative = config.get(section, "IsRelative", fallback="1") == "1"
        profile_path = resolve_path(raw_path, is_relative)
        if (profile_path / "prefs.js").exists():
            return profile_path

    return fallback


def parse_prefs_js(prefs_file: Path) -> dict:
    """将 prefs.js 解析为 Python 字典。"""
    prefs: dict = {}
    pattern = re.compile(r'user_pref\("([^"]+)",\s*(.+?)\);$')

    with open(str(prefs_file), "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = pattern.match(line.strip())
            if not m:
                continue

            key = m.group(1)
            raw_val = m.group(2).strip()

            if raw_val.startswith('"') and raw_val.endswith('"'):
                value = raw_val[1:-1]
            elif raw_val == "true":
                value = True
            elif raw_val == "false":
                value = False
            else:
                try:
                    value = int(raw_val)
                except ValueError:
                    try:
                        value = float(raw_val)
                    except ValueError:
                        value = raw_val

            prefs[key] = value

    return prefs


def _detect_provider(hostname: str, is_gmail: bool) -> str:
    """根据 hostname 判断邮件服务商。"""
    h = hostname.lower()
    if is_gmail or "gmail" in h:
        return "gmail"
    if "outlook" in h or "office365" in h or "hotmail" in h or "live.com" in h:
        return "outlook"
    if "163.com" in h or "126.com" in h or "yeah.net" in h:
        return "163"
    if "qq.com" in h:
        return "qq"
    if "yahoo" in h:
        return "yahoo"
    if "icloud" in h or "me.com" in h:
        return "icloud"
    return "imap"


def extract_accounts(prefs: dict, profile_dir: Path | None = None) -> list:
    """从解析后的 prefs 中提取邮箱账号列表（过滤本地文件夹）。"""
    accounts_str = prefs.get("mail.accountmanager.accounts", "")
    local_folders_server = prefs.get("mail.accountmanager.localfoldersserver", "")
    default_account = prefs.get("mail.accountmanager.defaultaccount", "")

    if not accounts_str:
        return []

    accounts = []
    for account_id in [a.strip() for a in accounts_str.split(",")]:
        server_id = prefs.get(f"mail.account.{account_id}.server", "")
        if not server_id:
            continue

        server_type = prefs.get(f"mail.server.{server_id}.type", "")

        # 跳过本地文件夹（type=none）
        if server_type == "none" or server_id == local_folders_server:
            continue

        username = prefs.get(f"mail.server.{server_id}.userName", "")
        display_name = prefs.get(f"mail.server.{server_id}.name", username)
        hostname = prefs.get(f"mail.server.{server_id}.hostname", "")
        port = prefs.get(f"mail.server.{server_id}.port", 993)
        socket_type = prefs.get(f"mail.server.{server_id}.socketType", 3)
        auth_method = prefs.get(f"mail.server.{server_id}.authMethod", 0)
        is_gmail = bool(prefs.get(f"mail.server.{server_id}.is_gmail", False))
        check_new = bool(prefs.get(f"mail.server.{server_id}.check_new_mail", True))

        # socketType: 1=SSL/TLS(旧), 2=STARTTLS, 3=SSL/TLS
        ssl = socket_type in (1, 3)

        # 本地邮件存储目录（directory-rel 形如 [ProfD]ImapMail/imap.gmail.com）
        dir_rel = prefs.get(f"mail.server.{server_id}.directory-rel", "")
        mail_dir: str | None = None
        if dir_rel.startswith("[ProfD]") and profile_dir is not None:
            rel_part = dir_rel[len("[ProfD]"):].replace("/", os.sep)
            mail_dir = str(profile_dir / rel_part)

        # 身份信息（发件人名）
        identity_id = prefs.get(f"mail.account.{account_id}.identities", "").split(",")[0].strip()
        full_name = prefs.get(f"mail.identity.{identity_id}.fullName", "") if identity_id else ""
        reply_to = prefs.get(f"mail.identity.{identity_id}.reply_to", "") if identity_id else ""

        accounts.append({
            "account_id": account_id,
            "server_id": server_id,
            "email": username,
            "display_name": display_name,
            "full_name": full_name,
            "reply_to": reply_to,
            "hostname": hostname,
            "port": port,
            "protocol": server_type.upper(),
            "ssl": ssl,
            "auth_method": auth_method,
            "is_gmail": is_gmail,
            "check_new_mail": check_new,
            "mail_dir": mail_dir,
            "provider": _detect_provider(hostname, is_gmail),
            "is_default": account_id == default_account,
        })

    return accounts


def read_thunderbird_accounts() -> dict:
    """对外主接口：读取并返回 Thunderbird 所有账号信息。"""
    tb_root = find_thunderbird_root()
    if tb_root is None:
        return {
            "success": False,
            "error": "未找到 Thunderbird 配置目录",
            "accounts": [],
        }

    profile_dir = get_default_profile(tb_root)
    if profile_dir is None or not profile_dir.exists():
        return {
            "success": False,
            "error": f"未找到有效的 Profile 目录（tb_root={tb_root}）",
            "accounts": [],
        }

    prefs_file = profile_dir / "prefs.js"
    if not prefs_file.exists():
        return {
            "success": False,
            "error": f"prefs.js 不存在：{prefs_file}",
            "accounts": [],
        }

    prefs = parse_prefs_js(prefs_file)
    accounts = extract_accounts(prefs, profile_dir)

    return {
        "success": True,
        "error": None,
        "profile_path": str(profile_dir),
        "thunderbird_root": str(tb_root),
        "total": len(accounts),
        "accounts": accounts,
    }
