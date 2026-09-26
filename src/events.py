"""核验台账的追加式事件定义。

台账只追加不覆盖：版本发布（含灰度）、旧版下架、用户撤回授权、
复测失败与逾期等事实都以新事件记录，先前记录保持可查。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

VERSION_PUBLISHED = "version_published"  # 版本发布（含灰度发布）
VERSION_RETIRED = "version_retired"  # 旧版下架
PROBLEM_FILED = "problem_filed"  # 监管问题登记到具体发布版本
EVIDENCE_ATTACHED = "evidence_attached"  # 证据留存
CONCLUSION_SIGNED = "conclusion_signed"  # 角色签署结论
AUTHORIZATION_WITHDRAWN = "authorization_withdrawn"  # 用户撤回授权
RETEST_FAILED = "retest_failed"  # 复测失败
DEADLINE_MISSED = "deadline_missed"  # 逾期未闭环

ALL_TYPES = frozenset(
    {
        VERSION_PUBLISHED,
        VERSION_RETIRED,
        PROBLEM_FILED,
        EVIDENCE_ATTACHED,
        CONCLUSION_SIGNED,
        AUTHORIZATION_WITHDRAWN,
        RETEST_FAILED,
        DEADLINE_MISSED,
    }
)


@dataclass(frozen=True)
class Event:
    """台账中的一条记录。

    seq 为台账内的追加序号，at 为业务发生时间（须带时区）。事件一旦
    追加不得修改或删除，后续事实只能以新事件补充。
    """

    seq: int
    type: str
    at: datetime
    payload: Mapping[str, Any]

    def to_dict(self) -> dict:
        """导出为可 JSON 序列化的字典，便于归档或移送监管。"""
        return {
            "seq": self.seq,
            "type": self.type,
            "at": self.at.isoformat(),
            "payload": dict(self.payload),
        }
