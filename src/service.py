"""整改核验服务:把监管问题落到具体发布版本,并留存全程证据。

服务组合工作日历、问题分类、角色契约与只增不改的台账/证据/事件/
签署记录,提供通报登记、证据留存、三方签署、版本变更与监管回查
的完整入口。所有写入都是追加,任何操作都不会覆盖先前记录。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from src.audit import AuditSnapshot, snapshot_at
from src.catalog import ProblemCategory, RoleContract
from src.evidence import Evidence, EvidenceLedger
from src.events import Event, EventLog
from src.notice import Notice
from src.registry import VersionRegistry, VersionSlot
from src.signoff import Conclusion, SignoffBook
from src.workdays import WorkdayCalendar


@dataclass(frozen=True)
class RectificationItem:
    """一项整改事项:某应用的某个发布版本上的某类问题。"""

    item_id: str
    app_id: str
    name: str
    platform: str
    channel: str
    version: str
    problem: str
    notice_date: date
    deadline: date


class RemediationService:
    """整改核验服务门面。"""

    def __init__(
        self,
        calendar: WorkdayCalendar,
        catalog: tuple[ProblemCategory, ...],
        roles: tuple[RoleContract, ...],
        registry: VersionRegistry | None = None,
        evidence: EvidenceLedger | None = None,
        events: EventLog | None = None,
        signoffs: SignoffBook | None = None,
    ) -> None:
        self._calendar = calendar
        self._catalog = {category.code: category for category in catalog}
        self._registry = registry if registry is not None else VersionRegistry()
        self._evidence = evidence if evidence is not None else EvidenceLedger()
        self._events = events if events is not None else EventLog()
        self._signoffs = signoffs if signoffs is not None else SignoffBook(roles)
        self._items: dict[str, RectificationItem] = {}

    # -- 台账与通报登记 -------------------------------------------------

    def publish(self, slots: tuple[VersionSlot, ...]) -> None:
        """登记版本台账。"""
        for slot in slots:
            self._registry.publish(slot)

    def register_notice(self, notice: Notice) -> tuple[RectificationItem, ...]:
        """把通报中的每个问题落到具体发布版本,并按工作日算出期限。

        问题分类必须在分类输入中,版本必须在台账登记过;同一份通报
        不得重复登记。先整体校验再登记,避免半截数据。
        """
        for entry in notice.apps:
            if entry.problem not in self._catalog:
                raise ValueError(f"未知问题分类: {entry.problem}")
            if not self._registry.knows(entry.app_id, entry.version, entry.channel):
                raise ValueError(
                    f"版本未登记: {entry.app_id} {entry.version} {entry.channel}"
                )
            duplicate = any(
                item.app_id == entry.app_id
                and item.version == entry.version
                and item.problem == entry.problem
                for item in self._items.values()
            )
            if duplicate:
                raise ValueError(
                    f"同一版本同一问题不得重复登记: {entry.app_id} {entry.version}"
                )
        created = []
        for entry in notice.apps:
            item = RectificationItem(
                item_id=f"item-{len(self._items) + 1:03d}",
                app_id=entry.app_id,
                name=entry.name,
                platform=entry.platform,
                channel=entry.channel,
                version=entry.version,
                problem=entry.problem,
                notice_date=notice.notice_date,
                deadline=self._calendar.add(notice.notice_date, notice.term_workdays),
            )
            self._items[item.item_id] = item
            created.append(item)
        return tuple(created)

    # -- 查询 -----------------------------------------------------------

    def item(self, item_id: str) -> RectificationItem:
        try:
            return self._items[item_id]
        except KeyError:
            raise KeyError(f"未知整改事项: {item_id}") from None

    def items(self) -> tuple[RectificationItem, ...]:
        return tuple(self._items.values())

    def online_versions(self, app_id: str, when: datetime) -> tuple[VersionSlot, ...]:
        return self._registry.online_at(app_id, when)

    def events(self, kind: str | None = None) -> tuple[Event, ...]:
        if kind is None:
            return self._events.all()
        return self._events.of_kind(kind)

    def evidence_for(self, item_id: str) -> tuple[Evidence, ...]:
        return self._evidence.for_item(item_id)

    def conclusions(self, item_id: str) -> tuple[Conclusion, ...]:
        return self._signoffs.history(item_id)

    def current_round(self, item_id: str) -> int:
        """当前整改轮次:复测失败一次,轮次加一。"""
        self.item(item_id)
        return 1 + len(self._events.for_item(item_id, kind="retest_failed"))

    def is_complete(self, item_id: str) -> bool:
        """当前轮次是否集齐产品、法务、研发三方结论。"""
        return self._signoffs.is_complete(item_id, self.current_round(item_id))

    def item_status(self, item_id: str, today: date) -> str:
        """signed / overdue / pending。"""
        item = self.item(item_id)
        if self.is_complete(item_id):
            return "signed"
        if self._calendar.is_overdue(item.deadline, today):
            return "overdue"
        return "pending"

    # -- 证据与签署 -----------------------------------------------------

    def record_evidence(
        self,
        item_id: str,
        category: str,
        captured_at: datetime,
        effective_from: datetime,
        summary: str,
        source: str,
    ) -> Evidence:
        """为整改事项留存一份证据。"""
        item = self.item(item_id)
        evidence = Evidence(
            evidence_id=f"ev-{len(self._evidence) + 1:04d}",
            item_id=item.item_id,
            app_id=item.app_id,
            version=item.version,
            channel=item.channel,
            category=category,
            captured_at=captured_at,
            effective_from=effective_from,
            summary=summary,
            source=source,
        )
        self._evidence.record(evidence)
        return evidence

    def sign(
        self,
        item_id: str,
        role: str,
        conclusion: str,
        signed_by: str,
        signed_at: datetime,
    ) -> Conclusion:
        """以某角色身份签署当前轮次的结论。"""
        self.item(item_id)
        return self._signoffs.sign(
            item_id, role, self.current_round(item_id), conclusion, signed_by, signed_at
        )

    # -- 版本与生命周期事件 ---------------------------------------------

    def start_gray(
        self, app_id: str, version: str, channel: str, when: datetime
    ) -> Event:
        """登记一次灰度发布并留痕。"""
        self._registry.publish(
            VersionSlot(
                app_id=app_id,
                version=version,
                channel=channel,
                stage="gray",
                online_from=when,
            )
        )
        return self._events.record(
            "gray_release_started", at=when, app_id=app_id, version=version, channel=channel
        )

    def retire_version(
        self, app_id: str, version: str, channel: str, when: datetime
    ) -> Event:
        """记录一次旧版下架;历史在线记录保持不变。"""
        self._registry.retire(app_id, version, channel, when)
        return self._events.record(
            "version_retired", at=when, app_id=app_id, version=version, channel=channel
        )

    def withdraw_consent(
        self, app_id: str, user_ref: str, when: datetime, version: str | None = None
    ) -> Event:
        """记录一次用户撤回授权;既有证据与记录不受影响。"""
        return self._events.record(
            "consent_withdrawn", at=when, app_id=app_id, user_ref=user_ref, version=version
        )

    def fail_retest(self, item_id: str, when: datetime, note: str) -> Event:
        """记录一次复测失败;先前轮次的签署结论全部保留。"""
        item = self.item(item_id)
        return self._events.record(
            "retest_failed", at=when, app_id=item.app_id, item_id=item_id, note=note
        )

    def record_operation(
        self,
        app_id: str,
        version: str,
        operation: str,
        result: str,
        when: datetime,
        user_ref: str | None = None,
    ) -> Event:
        """记录一次用户侧操作结果(如注销尝试、权限弹窗)。"""
        return self._events.record(
            "operation_recorded",
            at=when,
            app_id=app_id,
            version=version,
            operation=operation,
            result=result,
            user_ref=user_ref,
        )

    def check_overdue(self, item_id: str, today: date) -> bool:
        """检查是否逾期;首次发现逾期时留痕一次,不重复记录。"""
        item = self.item(item_id)
        if not self._calendar.is_overdue(item.deadline, today):
            return False
        if self.is_complete(item_id):
            return False
        if not self._events.for_item(item_id, kind="overdue"):
            self._events.record(
                "overdue",
                at=datetime(today.year, today.month, today.day),
                app_id=item.app_id,
                item_id=item_id,
                deadline=item.deadline.isoformat(),
            )
        return True

    # -- 监管回查 ---------------------------------------------------------

    def audit_at(self, app_id: str, when: datetime) -> AuditSnapshot:
        """还原 when 时刻用户实际看到的规则与操作结果。"""
        return snapshot_at(app_id, when, self._registry, self._evidence, self._events)
