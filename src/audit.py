"""监管回查:定位某时刻用户实际看到的规则与操作结果。

回查只读取只增不改的台账、证据与事件,因此后来的整改、发布、
下架都不会改写较早时刻的回查结果。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.evidence import Evidence, EvidenceLedger
from src.events import Event, EventLog
from src.registry import VersionRegistry, VersionSlot


@dataclass(frozen=True)
class AuditSnapshot:
    """某应用在某时刻的回查快照。

    disclosures 以 (version, channel) 为键,值为当时已生效的告知文本证据;
    operations 为当时已发生的用户侧操作结果;consent_withdrawals 为当时
    已发生的撤回授权记录。
    """

    app_id: str
    at: datetime
    versions_online: tuple[VersionSlot, ...]
    disclosures: dict[tuple[str, str], Evidence | None]
    operations: tuple[Event, ...]
    consent_withdrawals: tuple[Event, ...]


def snapshot_at(
    app_id: str,
    when: datetime,
    registry: VersionRegistry,
    evidence: EvidenceLedger,
    events: EventLog,
) -> AuditSnapshot:
    """还原 when 时刻的在线版本、生效告知文本与已发生的操作结果。"""
    online = registry.online_at(app_id, when)
    disclosures = {
        (slot.version, slot.channel): evidence.disclosure_at(
            app_id, slot.version, slot.channel, when
        )
        for slot in online
    }
    operations = events.for_app_until(app_id, when, ("operation_recorded",))
    withdrawals = events.for_app_until(app_id, when, ("consent_withdrawn",))
    return AuditSnapshot(
        app_id=app_id,
        at=when,
        versions_online=online,
        disclosures=disclosures,
        operations=operations,
        consent_withdrawals=withdrawals,
    )
