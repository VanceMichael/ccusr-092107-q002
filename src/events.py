"""事件流:灰度发布、旧版下架、用户撤回授权、复测失败、逾期等只增不改。

事件流是整改过程的审计轨迹:只提供追加与读取,不提供修改或删除;
任何后续事件都不会覆盖先前记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

EVENT_TYPES = (
    "gray_release_started",
    "version_retired",
    "consent_withdrawn",
    "retest_failed",
    "overdue",
    "operation_recorded",
)


@dataclass(frozen=True)
class Event:
    """一条事件记录,detail 存放与类型相关的字段。"""

    seq: int
    kind: str
    at: datetime
    app_id: str
    item_id: str | None
    detail: dict = field(default_factory=dict)


class EventLog:
    """只增不改的事件流。"""

    def __init__(self) -> None:
        self._events: list[Event] = []

    def record(
        self,
        kind: str,
        at: datetime,
        app_id: str,
        item_id: str | None = None,
        **detail: object,
    ) -> Event:
        """追加一条事件,类型必须在约定范围内。"""
        if kind not in EVENT_TYPES:
            raise ValueError(f"未知事件类型: {kind}")
        event = Event(
            seq=len(self._events) + 1,
            kind=kind,
            at=at,
            app_id=app_id,
            item_id=item_id,
            detail=dict(detail),
        )
        self._events.append(event)
        return event

    def all(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def of_kind(self, kind: str) -> tuple[Event, ...]:
        return tuple(event for event in self._events if event.kind == kind)

    def for_item(self, item_id: str, kind: str | None = None) -> tuple[Event, ...]:
        return tuple(
            event
            for event in self._events
            if event.item_id == item_id and (kind is None or event.kind == kind)
        )

    def for_app_until(
        self, app_id: str, when: datetime, kinds: tuple[str, ...]
    ) -> tuple[Event, ...]:
        """when 时刻(含)之前已发生的指定类型事件,按发生时间排序。"""
        matched = [
            event
            for event in self._events
            if event.app_id == app_id and event.at <= when and event.kind in kinds
        ]
        return tuple(sorted(matched, key=lambda event: (event.at, event.seq)))
