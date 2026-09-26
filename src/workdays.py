"""按工作日计算整改期限。

约定:期限自通报日期的次日起数,周末与节假日不计入工作日;
期限日当天仍属期限内,次日起才算逾期。示例中的时间为本地时间,不含时区。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class WorkdayCalendar:
    """周末与给定节假日之外的日子计为工作日。"""

    holidays: frozenset[date] = field(default_factory=frozenset)

    def is_workday(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.holidays

    def add(self, start: date, workdays: int) -> date:
        """从 start 次日起数 workdays 个工作日,返回期限日。"""
        if workdays < 1:
            raise ValueError("工作日数必须为正整数")
        day = start
        remaining = workdays
        while remaining > 0:
            day += timedelta(days=1)
            if self.is_workday(day):
                remaining -= 1
        return day

    def is_overdue(self, deadline: date, today: date) -> bool:
        """期限日次日及以后视为逾期。"""
        return today > deadline


def load_calendar(path: Path) -> WorkdayCalendar:
    """读取节假日表,返回工作日历。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if "holidays" not in data:
        raise ValueError("工作日历缺少 holidays 字段")
    holidays = frozenset(date.fromisoformat(item) for item in data["holidays"])
    return WorkdayCalendar(holidays=holidays)
