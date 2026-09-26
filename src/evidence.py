"""证据台账:为数据用途、权限触发、告知文本、第三方组件、注销路径保留证据。

证据只增不改;每份证据同时记录取证时间(captured_at)与内容对用户
生效的时间(effective_from),监管回查按生效时间定位用户当时实际看
到的内容。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

EVIDENCE_CATEGORIES = (
    "data_purpose",
    "permission_trigger",
    "disclosure_text",
    "third_party_component",
    "deletion_path",
)


@dataclass(frozen=True)
class Evidence:
    """一份证据记录,summary 为内容摘要或哈希。"""

    evidence_id: str
    item_id: str
    app_id: str
    version: str
    channel: str
    category: str
    captured_at: datetime
    effective_from: datetime
    summary: str
    source: str


class EvidenceLedger:
    """只增不改的证据台账。"""

    def __init__(self) -> None:
        self._records: list[Evidence] = []

    def __len__(self) -> int:
        return len(self._records)

    def record(self, evidence: Evidence) -> None:
        """登记一份证据,类别必须合法且编号不得重复。"""
        if evidence.category not in EVIDENCE_CATEGORIES:
            raise ValueError(f"未知证据类别: {evidence.category}")
        if any(existing.evidence_id == evidence.evidence_id for existing in self._records):
            raise ValueError("证据编号已存在,不得覆盖")
        self._records.append(evidence)

    def for_item(self, item_id: str) -> tuple[Evidence, ...]:
        return tuple(record for record in self._records if record.item_id == item_id)

    def disclosure_at(
        self, app_id: str, version: str, channel: str, when: datetime
    ) -> Evidence | None:
        """when 时刻用户实际看到的告知文本:已生效记录中生效时间最新的一份。"""
        candidates = [
            record
            for record in self._records
            if record.category == "disclosure_text"
            and record.app_id == app_id
            and record.version == version
            and record.channel == channel
            and record.effective_from <= when
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda record: record.effective_from)
