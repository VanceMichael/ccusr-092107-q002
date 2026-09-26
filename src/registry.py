"""版本台账:记录各发布版本的在线区间,下架只追加记录、不改写历史。

同一应用(含小程序)允许灰度版、全量版、旧版等多个版本同时在线;
下架以独立的 Retirement 记录表达,已登记的 VersionSlot 保持不变,
因此任何历史时刻的在线情况都可以重现。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

STAGES = ("gray", "full")


@dataclass(frozen=True)
class VersionSlot:
    """某发布版本在某渠道开始在线的记录。"""

    app_id: str
    version: str
    channel: str
    stage: str
    online_from: datetime


@dataclass(frozen=True)
class Retirement:
    """一次旧版下架记录,不影响已登记的 VersionSlot。"""

    app_id: str
    version: str
    channel: str
    retired_at: datetime


class VersionRegistry:
    """只增不改的版本台账。"""

    def __init__(self) -> None:
        self._slots: list[VersionSlot] = []
        self._retirements: list[Retirement] = []

    def publish(self, slot: VersionSlot) -> None:
        """登记一个开始在线的版本,同一记录不得重复登记。"""
        if slot.stage not in STAGES:
            raise ValueError(f"未知发布阶段: {slot.stage}")
        duplicate = any(
            existing.app_id == slot.app_id
            and existing.version == slot.version
            and existing.channel == slot.channel
            and existing.stage == slot.stage
            for existing in self._slots
        )
        if duplicate:
            raise ValueError("该版本已登记,不得重复发布")
        self._slots.append(slot)

    def retire(self, app_id: str, version: str, channel: str, when: datetime) -> Retirement:
        """记录一次下架;版本当前不在线时拒绝。"""
        online = any(
            slot.version == version and slot.channel == channel
            for slot in self.online_at(app_id, when)
        )
        if not online:
            raise ValueError("该版本当前不在线,无法下架")
        record = Retirement(app_id=app_id, version=version, channel=channel, retired_at=when)
        self._retirements.append(record)
        return record

    def online_at(self, app_id: str, when: datetime) -> tuple[VersionSlot, ...]:
        """when 时刻仍在线的版本;下架只影响其后的查询,不改写历史。"""
        result = []
        for slot in self._slots:
            if slot.app_id != app_id or slot.online_from > when:
                continue
            retired = any(
                record.app_id == slot.app_id
                and record.version == slot.version
                and record.channel == slot.channel
                and record.retired_at <= when
                for record in self._retirements
            )
            if not retired:
                result.append(slot)
        return tuple(result)

    def knows(self, app_id: str, version: str, channel: str) -> bool:
        """该版本是否曾在台账登记(无论是否已下架)。"""
        return any(
            slot.app_id == app_id and slot.version == version and slot.channel == channel
            for slot in self._slots
        )

    def slots(self) -> tuple[VersionSlot, ...]:
        return tuple(self._slots)

    def retirements(self) -> tuple[Retirement, ...]:
        return tuple(self._retirements)


def load_slots(path: Path) -> tuple[VersionSlot, ...]:
    """读取版本台账示例资料。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("slots")
    if not entries:
        raise ValueError("版本台账缺少 slots 字段")
    return tuple(
        VersionSlot(
            app_id=entry["app_id"],
            version=entry["version"],
            channel=entry["channel"],
            stage=entry["stage"],
            online_from=datetime.fromisoformat(entry["online_from"]),
        )
        for entry in entries
    )
