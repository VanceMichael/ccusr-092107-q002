"""三方签署:产品、法务、研发分别签署自己的结论,留痕不覆盖。

签署按整改事项与轮次记录:复测失败开启新一轮后,先前轮次的结论
完整保留;同一角色在同一轮次不得重复签署。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.catalog import RoleContract


@dataclass(frozen=True)
class Conclusion:
    """一个角色在一轮整改中签署的结论。"""

    item_id: str
    role: str
    round: int
    conclusion: str
    signed_by: str
    signed_at: datetime


class SignoffBook:
    """只增不改的签署记录。"""

    def __init__(self, roles: tuple[RoleContract, ...]) -> None:
        if not roles:
            raise ValueError("角色契约不得为空")
        self._roles = frozenset(contract.role for contract in roles)
        self._records: list[Conclusion] = []

    def sign(
        self,
        item_id: str,
        role: str,
        round_no: int,
        conclusion: str,
        signed_by: str,
        signed_at: datetime,
    ) -> Conclusion:
        """记录一次签署;角色必须存在,同一角色同一轮次不得重复签署。"""
        if role not in self._roles:
            raise ValueError(f"未知角色: {role}")
        if round_no < 1:
            raise ValueError("轮次必须为正整数")
        duplicate = any(
            record.item_id == item_id and record.role == role and record.round == round_no
            for record in self._records
        )
        if duplicate:
            raise ValueError("该角色本轮已签署,不得覆盖先前结论")
        record = Conclusion(
            item_id=item_id,
            role=role,
            round=round_no,
            conclusion=conclusion,
            signed_by=signed_by,
            signed_at=signed_at,
        )
        self._records.append(record)
        return record

    def is_complete(self, item_id: str, round_no: int) -> bool:
        """该轮是否集齐全部角色的结论。"""
        signed = {
            record.role
            for record in self._records
            if record.item_id == item_id and record.round == round_no
        }
        return signed == self._roles

    def history(self, item_id: str) -> tuple[Conclusion, ...]:
        """该事项全部轮次的签署记录,按签署时间排序。"""
        matched = [record for record in self._records if record.item_id == item_id]
        return tuple(sorted(matched, key=lambda record: record.signed_at))
