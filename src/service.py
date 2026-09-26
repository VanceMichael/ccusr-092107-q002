"""移动应用整改核验服务。

核验台账只追加不覆盖：灰度发布、旧版下架、用户撤回授权、复测失败
与逾期都以新事件记录，先前记录保持可查。所有状态由事件折叠得出，
监管回查可按时间点重建用户当时实际看到的规则与操作结果。
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Optional

from src.catalog import Catalog, RoleContract
from src.events import (
    ALL_TYPES,
    AUTHORIZATION_WITHDRAWN,
    CONCLUSION_SIGNED,
    DEADLINE_MISSED,
    EVIDENCE_ATTACHED,
    PROBLEM_FILED,
    RETEST_FAILED,
    VERSION_PUBLISHED,
    VERSION_RETIRED,
    Event,
)
from src.workdays import add_workdays

CHANNEL_STORE = "store"  # 正式发布渠道
CHANNEL_GRAY = "gray"  # 灰度发布渠道

DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"


@dataclass(frozen=True)
class EvidenceRef:
    """某一类证据在某一时间点的有效记录。"""

    kind: str
    summary: str
    artifact_ref: str
    attached_at: datetime


@dataclass(frozen=True)
class ProblemStatus:
    """一个监管问题在某一时间点的核验状态。"""

    problem_id: str
    app_id: str
    version: str
    category: str
    filed_at: datetime
    deadline: date
    closed: bool
    overdue: bool
    signed_roles: tuple[str, ...]
    missing_roles: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    retest_failures: int
    last_event_at: datetime


@dataclass(frozen=True)
class VersionSnapshot:
    """监管回查时一个在线版本的快照。"""

    version: str
    channel: str
    published_at: datetime
    gray_percent: Optional[int]
    rules_in_effect: Mapping[str, EvidenceRef]
    open_problems: tuple[str, ...]
    withdrawn_user_refs: tuple[str, ...]


@dataclass(frozen=True)
class UserView:
    """监管回查结果：某时间点用户实际看到的规则与操作结果。"""

    app_id: str
    as_of: datetime
    versions: tuple[VersionSnapshot, ...]


def _require_aware(at: datetime) -> None:
    if at.tzinfo is None or at.tzinfo.utcoffset(at) is None:
        raise ValueError("事件时间必须携带时区")


class VerificationService:
    """整改核验台账。

    catalog 与 roles 来自问题分类与角色契约；rectification_workdays
    为整改期限的工作日数量（默认十五个工作日）；holidays 可传入法定
    节假日以便准确计算期限。
    """

    def __init__(
        self,
        catalog: Catalog,
        roles: RoleContract,
        *,
        holidays: Iterable[date] = (),
        rectification_workdays: int = 15,
    ):
        if rectification_workdays < 1:
            raise ValueError("整改期限至少为一个工作日")
        self._catalog = catalog
        self._roles = roles
        self._holidays = frozenset(holidays)
        self._rectification_workdays = rectification_workdays
        self._events: list[Event] = []

    # ---- 命令：只追加事件，不修改历史 ----

    def publish_version(
        self,
        *,
        app_id: str,
        version: str,
        channel: str,
        at: datetime,
        gray_percent: Optional[int] = None,
    ) -> Event:
        """记录版本发布；灰度发布须给出灰度比例。同一版本在线期间不得重复发布。"""
        _require_aware(at)
        if channel not in (CHANNEL_STORE, CHANNEL_GRAY):
            raise ValueError(f"未知发布渠道: {channel}")
        if channel == CHANNEL_GRAY:
            if gray_percent is None or not 1 <= gray_percent <= 100:
                raise ValueError("灰度发布需给出 1-100 的灰度比例")
        elif gray_percent is not None:
            raise ValueError("正式渠道不携带灰度比例")
        if self._is_online(app_id, version, at):
            raise ValueError(f"版本 {app_id}@{version} 已在线，不能重复发布")
        return self._append(
            VERSION_PUBLISHED,
            at,
            {
                "app_id": app_id,
                "version": version,
                "channel": channel,
                "gray_percent": gray_percent,
            },
        )

    def retire_version(
        self, *, app_id: str, version: str, at: datetime, reason: str
    ) -> Event:
        """记录旧版下架；不下线任何历史记录。"""
        _require_aware(at)
        if not self._is_online(app_id, version, at):
            raise ValueError(f"版本 {app_id}@{version} 不在在线状态，无法下架")
        return self._append(
            VERSION_RETIRED,
            at,
            {"app_id": app_id, "version": version, "reason": reason},
        )

    def file_problem(
        self,
        *,
        app_id: str,
        version: str,
        category: str,
        detail: str,
        at: datetime,
    ) -> str:
        """把监管问题登记到具体发布版本，返回问题编号。

        整改期限自登记次日起按工作日计算。
        """
        _require_aware(at)
        self._catalog.category(category)
        if not self._was_published(app_id, version, at):
            raise ValueError(f"问题必须落到已发布的版本: {app_id}@{version}")
        problem_id = f"P-{self._problem_count() + 1:04d}"
        deadline = add_workdays(
            at.date(), self._rectification_workdays, self._holidays
        )
        self._append(
            PROBLEM_FILED,
            at,
            {
                "problem_id": problem_id,
                "app_id": app_id,
                "version": version,
                "category": category,
                "detail": detail,
                "deadline": deadline.isoformat(),
            },
        )
        return problem_id

    def attach_evidence(
        self,
        *,
        problem_id: str,
        kind: str,
        summary: str,
        artifact_ref: str,
        collected_by: str,
        at: datetime,
    ) -> Event:
        """为问题留存一类证据；同类新证据不覆盖旧证据。"""
        if not self._catalog.has_evidence_kind(kind):
            raise ValueError(f"未知证据种类: {kind}")
        self._filed_payload(problem_id)
        return self._append(
            EVIDENCE_ATTACHED,
            at,
            {
                "problem_id": problem_id,
                "kind": kind,
                "summary": summary,
                "artifact_ref": artifact_ref,
                "collected_by": collected_by,
            },
        )

    def sign_conclusion(
        self,
        *,
        problem_id: str,
        role: str,
        signer: str,
        decision: str,
        note: str,
        at: datetime,
    ) -> Event:
        """记录一个角色签署的本人结论；重复签署只追加不覆盖。"""
        self._roles.role(role)
        self._filed_payload(problem_id)
        if decision not in (DECISION_APPROVED, DECISION_REJECTED):
            raise ValueError(f"未知签署结论: {decision}")
        return self._append(
            CONCLUSION_SIGNED,
            at,
            {
                "problem_id": problem_id,
                "role": role,
                "signer": signer,
                "decision": decision,
                "note": note,
            },
        )

    def withdraw_authorization(
        self, *, app_id: str, version: str, user_ref: str, at: datetime
    ) -> Event:
        """记录用户撤回授权；user_ref 为不含个人信息的 opaque 引用。"""
        _require_aware(at)
        if not self._was_published(app_id, version, at):
            raise ValueError(f"撤回授权须落在已发布的版本: {app_id}@{version}")
        return self._append(
            AUTHORIZATION_WITHDRAWN,
            at,
            {"app_id": app_id, "version": version, "user_ref": user_ref},
        )

    def record_retest_failure(
        self, *, problem_id: str, detail: str, at: datetime
    ) -> Event:
        """记录复测失败；此前签署与证据全部保留，问题重新打开。"""
        self._filed_payload(problem_id)
        return self._append(
            RETEST_FAILED, at, {"problem_id": problem_id, "detail": detail}
        )

    def mark_overdue(self, *, as_of: datetime) -> tuple[Event, ...]:
        """为截至 as_of 已超期且未闭环的问题补记逾期事件，幂等。"""
        _require_aware(as_of)
        appended = []
        for problem_id in self.problem_ids():
            status = self.problem_status(problem_id, as_of=as_of)
            already_marked = any(
                event.type == DEADLINE_MISSED
                and event.payload["problem_id"] == problem_id
                for event in self._events
            )
            if status.overdue and not already_marked:
                appended.append(
                    self._append(
                        DEADLINE_MISSED,
                        as_of,
                        {
                            "problem_id": problem_id,
                            "deadline": status.deadline.isoformat(),
                        },
                    )
                )
        return tuple(appended)

    # ---- 查询：由事件折叠得出 ----

    def events(self) -> tuple[Event, ...]:
        """返回台账全部事件的只读副本。"""
        return tuple(self._events)

    def problem_ids(self) -> tuple[str, ...]:
        return tuple(
            event.payload["problem_id"]
            for event in self._events
            if event.type == PROBLEM_FILED
        )

    def timeline(self, problem_id: str) -> tuple[Event, ...]:
        """返回一个问题的全部历史记录，含被后续事实超越的记录。"""
        self._filed_payload(problem_id)
        return tuple(
            event
            for event in self._ordered()
            if event.payload.get("problem_id") == problem_id
        )

    def problem_status(
        self, problem_id: str, *, as_of: Optional[datetime] = None
    ) -> ProblemStatus:
        """折叠事件得出问题在 as_of（缺省为台账最新时间）的状态。

        闭环条件：分类要求的证据种类齐全，且每个角色在最近一次复测失败
        （若无则自登记起）之后的最新结论均为通过。复测失败不清除历史
        签署，但问题需重新签署才能闭环。
        """
        filed = self._filed_payload(problem_id)
        if as_of is not None:
            _require_aware(as_of)
        relevant = [
            event
            for event in self._ordered(as_of)
            if event.payload.get("problem_id") == problem_id
        ]
        if not relevant:
            raise ValueError(f"as_of 早于问题 {problem_id} 的登记时间")
        filed_at = next(
            event.at for event in relevant if event.type == PROBLEM_FILED
        )
        reset = next(
            (event for event in reversed(relevant) if event.type == RETEST_FAILED),
            None,
        )
        latest_signatures: dict[str, Event] = {}
        for event in relevant:
            if event.type != CONCLUSION_SIGNED:
                continue
            if reset is not None and (event.at, event.seq) <= (reset.at, reset.seq):
                continue
            latest_signatures[event.payload["role"]] = event
        signed_roles = tuple(
            role.code
            for role in self._roles.roles
            if latest_signatures.get(role.code) is not None
            and latest_signatures[role.code].payload["decision"]
            == DECISION_APPROVED
        )
        missing_roles = tuple(
            role.code for role in self._roles.roles if role.code not in signed_roles
        )
        attached = {
            event.payload["kind"]
            for event in relevant
            if event.type == EVIDENCE_ATTACHED
        }
        category = self._catalog.category(filed["category"])
        missing_evidence = tuple(
            kind for kind in category.evidence_kinds if kind not in attached
        )
        closed = not missing_roles and not missing_evidence
        deadline = date.fromisoformat(filed["deadline"])
        effective_as_of = as_of if as_of is not None else relevant[-1].at
        overdue = not closed and effective_as_of.date() > deadline
        return ProblemStatus(
            problem_id=problem_id,
            app_id=filed["app_id"],
            version=filed["version"],
            category=filed["category"],
            filed_at=filed_at,
            deadline=deadline,
            closed=closed,
            overdue=overdue,
            signed_roles=signed_roles,
            missing_roles=missing_roles,
            missing_evidence=missing_evidence,
            retest_failures=sum(
                1 for event in relevant if event.type == RETEST_FAILED
            ),
            last_event_at=relevant[-1].at,
        )

    def user_view(self, app_id: str, *, at: datetime) -> UserView:
        """监管回查：重建 at 时刻用户实际看到的规则与操作结果。

        返回该时刻全部在线版本（含灰度），每个版本当时有效的各类证据、
        未闭环问题与已撤回授权的用户引用。版本下线、证据更新、授权撤回
        都不影响按更早时间点重建。
        """
        _require_aware(at)
        events = self._ordered(at)
        filed = {
            event.payload["problem_id"]: event.payload
            for event in events
            if event.type == PROBLEM_FILED
        }
        snapshots = []
        for version in self._known_versions(app_id, events):
            if not self._is_online(app_id, version, at):
                continue
            publish = self._latest_publish(app_id, version, events)
            rules: dict[str, EvidenceRef] = {}
            for kind in self._catalog.evidence_kinds:
                candidates = [
                    event
                    for event in events
                    if event.type == EVIDENCE_ATTACHED
                    and event.payload["kind"] == kind.code
                    and filed.get(event.payload["problem_id"], {}).get("version")
                    == version
                    and filed[event.payload["problem_id"]]["app_id"] == app_id
                ]
                if candidates:
                    latest = candidates[-1]
                    rules[kind.code] = EvidenceRef(
                        kind=kind.code,
                        summary=latest.payload["summary"],
                        artifact_ref=latest.payload["artifact_ref"],
                        attached_at=latest.at,
                    )
            open_problems = tuple(
                problem_id
                for problem_id, payload in filed.items()
                if payload["app_id"] == app_id
                and payload["version"] == version
                and not self.problem_status(problem_id, as_of=at).closed
            )
            withdrawn = tuple(
                dict.fromkeys(
                    event.payload["user_ref"]
                    for event in events
                    if event.type == AUTHORIZATION_WITHDRAWN
                    and event.payload["app_id"] == app_id
                    and event.payload["version"] == version
                )
            )
            snapshots.append(
                VersionSnapshot(
                    version=version,
                    channel=publish.payload["channel"],
                    published_at=publish.at,
                    gray_percent=publish.payload["gray_percent"],
                    rules_in_effect=rules,
                    open_problems=open_problems,
                    withdrawn_user_refs=withdrawn,
                )
            )
        return UserView(app_id=app_id, as_of=at, versions=tuple(snapshots))

    # ---- 内部 ----

    def _append(
        self, type_: str, at: datetime, payload: Mapping[str, Any]
    ) -> Event:
        if type_ not in ALL_TYPES:
            raise ValueError(f"未知事件类型: {type_}")
        _require_aware(at)
        event = Event(
            seq=len(self._events) + 1, type=type_, at=at, payload=dict(payload)
        )
        self._events.append(event)
        return event

    def _ordered(self, as_of: Optional[datetime] = None) -> list[Event]:
        events = (
            self._events
            if as_of is None
            else [event for event in self._events if event.at <= as_of]
        )
        return sorted(events, key=lambda event: (event.at, event.seq))

    def _problem_count(self) -> int:
        return sum(1 for event in self._events if event.type == PROBLEM_FILED)

    def _filed_payload(self, problem_id: str) -> Mapping[str, Any]:
        for event in self._events:
            if (
                event.type == PROBLEM_FILED
                and event.payload["problem_id"] == problem_id
            ):
                return event.payload
        raise KeyError(f"未知问题编号: {problem_id}")

    def _known_versions(
        self, app_id: str, events: Iterable[Event]
    ) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                event.payload["version"]
                for event in events
                if event.type == VERSION_PUBLISHED
                and event.payload["app_id"] == app_id
            )
        )

    def _latest_publish(
        self, app_id: str, version: str, events: Iterable[Event]
    ) -> Optional[Event]:
        publishes = [
            event
            for event in events
            if event.type == VERSION_PUBLISHED
            and event.payload["app_id"] == app_id
            and event.payload["version"] == version
        ]
        return publishes[-1] if publishes else None

    def _is_online(self, app_id: str, version: str, at: datetime) -> bool:
        events = self._ordered(at)
        publish = self._latest_publish(app_id, version, events)
        if publish is None:
            return False
        return not any(
            event.type == VERSION_RETIRED
            and event.payload["app_id"] == app_id
            and event.payload["version"] == version
            and (event.at, event.seq) > (publish.at, publish.seq)
            for event in events
        )

    def _was_published(self, app_id: str, version: str, at: datetime) -> bool:
        return (
            self._latest_publish(app_id, version, self._ordered(at)) is not None
        )
