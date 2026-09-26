"""监管通报:把问题落到具体发布版本的输入。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PLATFORMS = ("app", "mini_program")


@dataclass(frozen=True)
class NoticeEntry:
    """通报中一款应用的一个问题,定位到具体发布版本。"""

    app_id: str
    name: str
    platform: str
    channel: str
    version: str
    problem: str


@dataclass(frozen=True)
class Notice:
    """一次通报:日期、整改期限(工作日)和涉及的应用清单。"""

    notice_date: date
    term_workdays: int
    apps: tuple[NoticeEntry, ...]


def load_notice(path: Path) -> Notice:
    """读取通报,平台类型必须在约定范围内。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = {"notice_date", "term_workdays", "apps"} - data.keys()
    if missing:
        raise ValueError(f"通报缺少必要字段: {sorted(missing)}")
    entries = []
    for raw in data["apps"]:
        if raw["platform"] not in PLATFORMS:
            raise ValueError(f"未知平台类型: {raw['platform']}")
        entries.append(
            NoticeEntry(
                app_id=raw["app_id"],
                name=raw["name"],
                platform=raw["platform"],
                channel=raw["channel"],
                version=raw["version"],
                problem=raw["problem"],
            )
        )
    if not entries:
        raise ValueError("通报未列出任何应用")
    return Notice(
        notice_date=date.fromisoformat(data["notice_date"]),
        term_workdays=int(data["term_workdays"]),
        apps=tuple(entries),
    )
