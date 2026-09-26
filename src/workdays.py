"""按工作日计算整改期限。"""

from datetime import date, timedelta
from typing import Collection


def is_workday(day: date, holidays: Collection[date] = ()) -> bool:
    """周一到周五且不在节假日集合内即为工作日。"""
    return day.weekday() < 5 and day not in holidays


def add_workdays(start: date, count: int, holidays: Collection[date] = ()) -> date:
    """返回从 start 次日起第 count 个工作日的日期。

    起始当日不计入期限，次一工作日为第 1 个工作日；count 为 0 时返回
    start 本身。holidays 用于传入法定节假日等额外非工作日。
    """
    if count < 0:
        raise ValueError("工作日数量不能为负")
    day = start
    remaining = count
    while remaining > 0:
        day += timedelta(days=1)
        if is_workday(day, holidays):
            remaining -= 1
    return day


def workdays_between(start: date, end: date, holidays: Collection[date] = ()) -> int:
    """统计 (start, end] 区间内的工作日数量，起始当日不计入。"""
    if end < start:
        raise ValueError("结束日期不能早于开始日期")
    day = start
    total = 0
    while day < end:
        day += timedelta(days=1)
        if is_workday(day, holidays):
            total += 1
    return total
