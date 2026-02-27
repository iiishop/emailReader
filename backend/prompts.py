"""
prompts.py — 加载 prompts.yaml 并提供模板插值工具函数。

用法：
    from prompts import get_prompt
    text = get_prompt("screening", "system")
    text = get_prompt("screening", "user_template", query="...", count=10, emails_json="...")
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

_YAML_PATH = Path(__file__).parent / "prompts.yaml"

def _load() -> dict:
    with open(_YAML_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

# 模块级缓存，进程重启才重新读取
_prompts: dict = _load()


import re as _re

def get_prompt(section: str, key: str, **kwargs: Any) -> str:
    """
    获取指定 section.key 的提示词模板，并用 kwargs 进行插值。

    只替换 {varName} 形式的已知变量，其余花括号（如 JSON 示例）保持原样。
    YAML 中若需要输出字面量 { 或 }，无需双写，本函数已安全处理。

    示例：
        get_prompt("screening", "user_template", query="帮我找发票", count=5, emails_json="[...]")
    """
    try:
        text: str = _prompts[section][key]
    except KeyError as e:
        raise KeyError(f"prompts.yaml 中未找到 [{section}][{key}]") from e

    if kwargs:
        # 只替换 {identifier} 形式（字母/数字/下划线），不碰 JSON 花括号
        def _replacer(m: _re.Match) -> str:
            var = m.group(1)
            if var in kwargs:
                return str(kwargs[var])
            return m.group(0)   # 未知变量保持原样
        text = _re.sub(r'\{([A-Za-z_]\w*)\}', _replacer, text)

    return text.rstrip("\n")


def reload() -> None:
    """热重载配置文件（开发调试用）。"""
    global _prompts
    _prompts = _load()


class _SafeDict(dict):
    """format_map 辅助类（保留备用）。"""
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
