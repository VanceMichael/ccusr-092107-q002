import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.catalog import load_catalog, load_roles
from src.events import (
    CONCLUSION_SIGNED,
    DEADLINE_MISSED,
    RETEST_FAILED,
)
from src.service import VerificationService

TZ = timezone(timedelta(hours=8))


def at(day: int, hour: int = 10, month: int = 9) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=TZ)


def make_service(**kwargs) -> VerificationService:
    return VerificationService(
        load_catalog(Path("fixtures/problem_catalog.json")),
        load_roles(Path("fixtures/roles.json")),
        **kwargs,
    )


def close_problem(service: VerificationService, problem_id: str, day: int):
    """补齐证据并由三方签署通过，使问题闭环。"""
    status = service.problem_status(problem_id)
    for kind in status.missing_evidence:
        service.attach_evidence(
            problem_id=problem_id,
            kind=kind,
            summary=f"{kind} 已核验",
            artifact_ref=f"evidence-store://{problem_id}/{kind}",
            collected_by="privacy-team",
            at=at(day, 11),
        )
    for role in ("product", "legal", "engineering"):
        service.sign_conclusion(
            problem_id=problem_id,
            role=role,
            signer=f"{role}-owner",
            decision="approved",
            note="结论：通过",
            at=at(day, 12),
        )


class FileProblemTest(unittest.TestCase):
    def test_problem_lands_on_specific_version_with_workday_deadline(self):
        service = make_service()
        service.publish_version(
            app_id="app-a", version="1.0.0", channel="store", at=at(26)
        )
        problem_id = service.file_problem(
            app_id="app-a",
            version="1.0.0",
            category="rules_undisclosed",
            detail="未公开个人信息收集使用规则",
            at=at(26),
        )
        self.assertEqual(problem_id, "P-0001")
        status = service.problem_status(problem_id)
        self.assertEqual(status.version, "1.0.0")
        self.assertEqual(status.deadline, date(2026, 10, 16))
        self.assertFalse(status.closed)

    def test_holidays_extend_deadline(self):
        holidays = {date(2026, 10, day) for day in range(1, 9)}
        service = make_service(holidays=holidays)
        service.publish_version(
            app_id="app-a", version="1.0.0", channel="store", at=at(26)
        )
        problem_id = service.file_problem(
            app_id="app-a",
            version="1.0.0",
            category="incomplete_notice",
            detail="告知不完整",
            at=at(26),
        )
        self.assertEqual(
            service.problem_status(problem_id).deadline, date(2026, 10, 26)
        )

    def test_unknown_category_or_unpublished_version_rejected(self):
        service = make_service()
        service.publish_version(
            app_id="app-a", version="1.0.0", channel="store", at=at(26)
        )
        with self.assertRaises(KeyError):
            service.file_problem(
                app_id="app-a",
                version="1.0.0",
                category="not_a_category",
                detail="",
                at=at(26),
            )
        with self.assertRaises(ValueError):
            service.file_problem(
                app_id="app-a",
                version="9.9.9",
                category="rules_undisclosed",
                detail="",
                at=at(26),
            )


class SignOffTest(unittest.TestCase):
    def setUp(self):
        self.service = make_service()
        self.service.publish_version(
            app_id="app-a", version="1.0.0", channel="store", at=at(26)
        )
        self.problem_id = self.service.file_problem(
            app_id="app-a",
            version="1.0.0",
            category="incomplete_notice",
            detail="告知不完整",
            at=at(26),
        )

    def test_closure_requires_all_roles_and_required_evidence(self):
        status = self.service.problem_status(self.problem_id)
        self.assertEqual(
            status.missing_evidence, ("notice_text", "data_purpose")
        )
        self.assertEqual(
            status.missing_roles, ("product", "legal", "engineering")
        )
        close_problem(self.service, self.problem_id, day=27)
        status = self.service.problem_status(self.problem_id)
        self.assertTrue(status.closed)
        self.assertEqual(
            status.signed_roles, ("product", "legal", "engineering")
        )

    def test_rejected_decision_keeps_problem_open(self):
        self.service.attach_evidence(
            problem_id=self.problem_id,
            kind="notice_text",
            summary="告知文本已补充",
            artifact_ref="evidence-store://P-0001/notice_text",
            collected_by="privacy-team",
            at=at(27),
        )
        self.service.attach_evidence(
            problem_id=self.problem_id,
            kind="data_purpose",
            summary="数据用途已明示",
            artifact_ref="evidence-store://P-0001/data_purpose",
            collected_by="privacy-team",
            at=at(27),
        )
        for role, decision in (
            ("product", "approved"),
            ("legal", "rejected"),
            ("engineering", "approved"),
        ):
            self.service.sign_conclusion(
                problem_id=self.problem_id,
                role=role,
                signer=f"{role}-owner",
                decision=decision,
                note="结论",
                at=at(28),
            )
        status = self.service.problem_status(self.problem_id)
        self.assertFalse(status.closed)
        self.assertEqual(status.missing_roles, ("legal",))

    def test_unknown_role_kind_or_decision_rejected(self):
        with self.assertRaises(KeyError):
            self.service.sign_conclusion(
                problem_id=self.problem_id,
                role="not_a_role",
                signer="x",
                decision="approved",
                note="",
                at=at(27),
            )
        with self.assertRaises(ValueError):
            self.service.sign_conclusion(
                problem_id=self.problem_id,
                role="product",
                signer="x",
                decision="maybe",
                note="",
                at=at(27),
            )
        with self.assertRaises(ValueError):
            self.service.attach_evidence(
                problem_id=self.problem_id,
                kind="not_a_kind",
                summary="",
                artifact_ref="",
                collected_by="",
                at=at(27),
            )
        with self.assertRaises(KeyError):
            self.service.attach_evidence(
                problem_id="P-9999",
                kind="notice_text",
                summary="",
                artifact_ref="",
                collected_by="",
                at=at(27),
            )


class AppendOnlyTest(unittest.TestCase):
    def setUp(self):
        self.service = make_service()
        self.service.publish_version(
            app_id="app-a", version="1.0.0", channel="store", at=at(26)
        )
        self.problem_id = self.service.file_problem(
            app_id="app-a",
            version="1.0.0",
            category="account_cancellation_unavailable",
            detail="账号无法注销",
            at=at(26),
        )

    def test_retest_failure_reopens_without_erasing_history(self):
        close_problem(self.service, self.problem_id, day=27)
        self.assertTrue(self.service.problem_status(self.problem_id).closed)

        self.service.record_retest_failure(
            problem_id=self.problem_id, detail="复测仍无注销入口", at=at(29)
        )
        status = self.service.problem_status(self.problem_id)
        self.assertFalse(status.closed)
        self.assertEqual(status.retest_failures, 1)

        # 复测失败前的三方签署仍完整保留在台账中
        timeline = self.service.timeline(self.problem_id)
        signatures = [e for e in timeline if e.type == CONCLUSION_SIGNED]
        self.assertEqual(len(signatures), 3)
        self.assertEqual(timeline[-1].type, RETEST_FAILED)

        # 复测失败后需重新签署方可闭环，新旧记录并存
        for role in ("product", "legal", "engineering"):
            self.service.sign_conclusion(
                problem_id=self.problem_id,
                role=role,
                signer=f"{role}-owner",
                decision="approved",
                note="复测整改后重新签署",
                at=at(30),
            )
        self.assertTrue(self.service.problem_status(self.problem_id).closed)
        signatures = [
            e
            for e in self.service.timeline(self.problem_id)
            if e.type == CONCLUSION_SIGNED
        ]
        self.assertEqual(len(signatures), 6)

    def test_event_log_is_append_only_and_exportable(self):
        close_problem(self.service, self.problem_id, day=27)
        events = self.service.events()
        self.assertIsInstance(events, tuple)
        self.assertEqual(
            [event.seq for event in events], list(range(1, len(events) + 1))
        )
        json.dumps([event.to_dict() for event in events])


class OverdueTest(unittest.TestCase):
    def test_overdue_marking_is_idempotent_and_skips_closed(self):
        service = make_service()
        service.publish_version(
            app_id="app-a", version="1.0.0", channel="store", at=at(26)
        )
        open_id = service.file_problem(
            app_id="app-a",
            version="1.0.0",
            category="rules_undisclosed",
            detail="规则未公开",
            at=at(26),
        )
        closed_id = service.file_problem(
            app_id="app-a",
            version="1.0.0",
            category="account_cancellation_unavailable",
            detail="账号无法注销",
            at=at(26),
        )
        close_problem(service, closed_id, day=28)

        # 期限当日（2026-10-16）不算逾期
        self.assertEqual(
            service.mark_overdue(as_of=datetime(2026, 10, 16, 23, tzinfo=TZ)),
            (),
        )
        # 超期后仅为未闭环问题补记一次逾期
        missed = service.mark_overdue(
            as_of=datetime(2026, 10, 17, 9, tzinfo=TZ)
        )
        self.assertEqual(len(missed), 1)
        self.assertEqual(missed[0].type, DEADLINE_MISSED)
        self.assertEqual(missed[0].payload["problem_id"], open_id)
        self.assertEqual(
            service.mark_overdue(as_of=datetime(2026, 10, 20, 9, tzinfo=TZ)),
            (),
        )
        status = service.problem_status(open_id)
        self.assertTrue(status.overdue)
        self.assertFalse(service.problem_status(closed_id).overdue)


class UserViewTest(unittest.TestCase):
    def setUp(self):
        self.service = make_service()
        self.service.publish_version(
            app_id="app-a", version="1.0.0", channel="store", at=at(26)
        )
        self.service.publish_version(
            app_id="app-a",
            version="1.1.0",
            channel="gray",
            gray_percent=20,
            at=at(28),
        )
        self.problem_id = self.service.file_problem(
            app_id="app-a",
            version="1.0.0",
            category="rules_undisclosed",
            detail="规则未公开",
            at=at(26),
        )
        self.service.attach_evidence(
            problem_id=self.problem_id,
            kind="notice_text",
            summary="第一版隐私政策文本",
            artifact_ref="evidence-store://P-0001/notice-v1",
            collected_by="privacy-team",
            at=at(27),
        )

    def test_versions_online_simultaneously_with_gray_channel(self):
        view = self.service.user_view("app-a", at=at(29))
        self.assertEqual(
            {snapshot.version for snapshot in view.versions},
            {"1.0.0", "1.1.0"},
        )
        gray = next(s for s in view.versions if s.version == "1.1.0")
        self.assertEqual(gray.channel, "gray")
        self.assertEqual(gray.gray_percent, 20)

    def test_lookback_pins_rules_seen_at_that_moment(self):
        self.service.attach_evidence(
            problem_id=self.problem_id,
            kind="notice_text",
            summary="整改后隐私政策文本",
            artifact_ref="evidence-store://P-0001/notice-v2",
            collected_by="privacy-team",
            at=at(30),
        )
        before = self.service.user_view("app-a", at=at(29))
        after = self.service.user_view("app-a", at=at(30, 23))
        seen_before = next(
            s for s in before.versions if s.version == "1.0.0"
        ).rules_in_effect["notice_text"]
        seen_after = next(
            s for s in after.versions if s.version == "1.0.0"
        ).rules_in_effect["notice_text"]
        self.assertEqual(seen_before.summary, "第一版隐私政策文本")
        self.assertEqual(seen_after.summary, "整改后隐私政策文本")

    def test_retirement_and_withdrawal_do_not_rewrite_earlier_view(self):
        self.service.withdraw_authorization(
            app_id="app-a", version="1.0.0", user_ref="user-ref-1", at=at(29)
        )
        self.service.retire_version(
            app_id="app-a", version="1.0.0", reason="旧版下架", at=at(30)
        )
        current = self.service.user_view("app-a", at=at(30, 23))
        self.assertEqual(
            {snapshot.version for snapshot in current.versions}, {"1.1.0"}
        )
        earlier = self.service.user_view("app-a", at=at(29, 12))
        snapshot = next(s for s in earlier.versions if s.version == "1.0.0")
        self.assertEqual(snapshot.withdrawn_user_refs, ("user-ref-1",))
        before_withdrawal = self.service.user_view("app-a", at=at(28, 12))
        snapshot = next(
            s for s in before_withdrawal.versions if s.version == "1.0.0"
        )
        self.assertEqual(snapshot.withdrawn_user_refs, ())

    def test_open_problems_tracked_per_version(self):
        view = self.service.user_view("app-a", at=at(29))
        old = next(s for s in view.versions if s.version == "1.0.0")
        new = next(s for s in view.versions if s.version == "1.1.0")
        self.assertEqual(old.open_problems, (self.problem_id,))
        self.assertEqual(new.open_problems, ())
        close_problem(self.service, self.problem_id, day=30)
        view = self.service.user_view("app-a", at=at(30, 23))
        old = next(s for s in view.versions if s.version == "1.0.0")
        self.assertEqual(old.open_problems, ())


class ReleaseDisciplineTest(unittest.TestCase):
    def setUp(self):
        self.service = make_service()

    def test_gray_release_requires_percent(self):
        with self.assertRaises(ValueError):
            self.service.publish_version(
                app_id="app-a", version="1.0.0", channel="gray", at=at(26)
            )
        with self.assertRaises(ValueError):
            self.service.publish_version(
                app_id="app-a",
                version="1.0.0",
                channel="gray",
                gray_percent=0,
                at=at(26),
            )
        with self.assertRaises(ValueError):
            self.service.publish_version(
                app_id="app-a",
                version="1.0.0",
                channel="store",
                gray_percent=50,
                at=at(26),
            )
        with self.assertRaises(ValueError):
            self.service.publish_version(
                app_id="app-a", version="1.0.0", channel="beta", at=at(26)
            )

    def test_republish_and_retire_discipline(self):
        self.service.publish_version(
            app_id="app-a", version="1.0.0", channel="store", at=at(26)
        )
        with self.assertRaises(ValueError):
            self.service.publish_version(
                app_id="app-a", version="1.0.0", channel="store", at=at(27)
            )
        self.service.retire_version(
            app_id="app-a", version="1.0.0", reason="旧版下架", at=at(28)
        )
        with self.assertRaises(ValueError):
            self.service.retire_version(
                app_id="app-a", version="1.0.0", reason="重复下架", at=at(29)
            )
        # 下架后重新上线是新的追加记录
        self.service.publish_version(
            app_id="app-a", version="1.0.0", channel="store", at=at(30)
        )
        view = self.service.user_view("app-a", at=at(30, 12))
        self.assertEqual(
            {snapshot.version for snapshot in view.versions}, {"1.0.0"}
        )

    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValueError):
            self.service.publish_version(
                app_id="app-a",
                version="1.0.0",
                channel="store",
                at=datetime(2026, 9, 26, 10),
            )


if __name__ == "__main__":
    unittest.main()
