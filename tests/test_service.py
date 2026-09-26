import unittest
from datetime import date, datetime
from pathlib import Path

from src.catalog import load_problem_catalog, load_role_contract
from src.evidence import EVIDENCE_CATEGORIES
from src.notice import Notice, NoticeEntry, load_notice
from src.registry import load_slots
from src.service import RemediationService
from src.workdays import load_calendar

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def build_service():
    service = RemediationService(
        calendar=load_calendar(FIXTURES / "holidays.json"),
        catalog=load_problem_catalog(FIXTURES / "problem-catalog.json"),
        roles=load_role_contract(FIXTURES / "role-contract.json"),
    )
    service.publish(load_slots(FIXTURES / "registry.json"))
    return service


def build_registered_service():
    service = build_service()
    items = service.register_notice(load_notice(FIXTURES / "notice.json"))
    return service, items


def notice_with(entry):
    return Notice(notice_date=date(2026, 9, 7), term_workdays=15, apps=(entry,))


class NoticeRegistrationTest(unittest.TestCase):
    def test_thirty_items_mapped_to_release_versions(self):
        _, items = build_registered_service()
        self.assertEqual(len(items), 30)
        # 通报 2026-09-07 起 15 个工作日,示例节假日 2026-09-25 不计入
        self.assertTrue(all(item.deadline == date(2026, 9, 29) for item in items))
        self.assertTrue(all(item.notice_date == date(2026, 9, 7) for item in items))
        problems = {item.problem for item in items}
        self.assertEqual(
            problems,
            {
                "rules_not_published",
                "excessive_permission_requests",
                "incomplete_disclosure",
                "account_not_deletable",
            },
        )

    def test_mini_program_gray_version_is_addressable(self):
        service, items = build_registered_service()
        item = next(item for item in items if item.app_id == "app-027")
        # 问题落在灰度版本 1.4.0 上,与全量版 1.3.0 同时在线
        self.assertEqual(item.version, "1.4.0")
        online = service.online_versions("app-027", datetime(2026, 9, 10))
        self.assertEqual({slot.version for slot in online}, {"1.3.0", "1.4.0"})
        stages = {slot.version: slot.stage for slot in online}
        self.assertEqual(stages, {"1.3.0": "full", "1.4.0": "gray"})

    def test_duplicate_notice_rejected(self):
        service = build_service()
        notice = load_notice(FIXTURES / "notice.json")
        service.register_notice(notice)
        with self.assertRaises(ValueError):
            service.register_notice(notice)

    def test_unknown_problem_rejected(self):
        service = build_service()
        entry = NoticeEntry(
            app_id="app-001", name="示例应用01", platform="app",
            channel="android_market", version="2.3.0", problem="location_tracking",
        )
        with self.assertRaises(ValueError):
            service.register_notice(notice_with(entry))

    def test_unregistered_version_rejected(self):
        service = build_service()
        entry = NoticeEntry(
            app_id="app-001", name="示例应用01", platform="app",
            channel="android_market", version="9.9.9", problem="rules_not_published",
        )
        with self.assertRaises(ValueError):
            service.register_notice(notice_with(entry))


class RectificationFlowTest(unittest.TestCase):
    def setUp(self):
        self.service, self.items = build_registered_service()
        self.item = next(item for item in self.items if item.app_id == "app-001")

    def sign_all_three(self, conclusions=("用途与告知已整改", "符合监管要求", "权限与注销已修复")):
        self.service.sign(self.item.item_id, "product", conclusions[0], "pm-demo-1", datetime(2026, 9, 10, 9))
        self.service.sign(self.item.item_id, "legal", conclusions[1], "legal-demo-1", datetime(2026, 9, 10, 10))
        self.service.sign(self.item.item_id, "engineering", conclusions[2], "eng-demo-1", datetime(2026, 9, 10, 11))

    def test_evidence_kept_for_all_five_categories(self):
        for category in EVIDENCE_CATEGORIES:
            self.service.record_evidence(
                self.item.item_id, category,
                captured_at=datetime(2026, 9, 8, 10),
                effective_from=datetime(2026, 9, 8, 10),
                summary=f"{category} 证据摘要",
                source="录屏存档",
            )
        kept = self.service.evidence_for(self.item.item_id)
        self.assertEqual({record.category for record in kept}, set(EVIDENCE_CATEGORIES))

    def test_three_roles_sign_then_retest_failure_preserves_history(self):
        self.sign_all_three()
        self.assertTrue(self.service.is_complete(self.item.item_id))
        self.assertEqual(self.service.item_status(self.item.item_id, date(2026, 9, 11)), "signed")

        # 复测失败:开启第二轮,第一轮三方结论全部保留
        self.service.fail_retest(self.item.item_id, datetime(2026, 9, 14, 9), "注销路径仍不可达")
        self.assertEqual(self.service.current_round(self.item.item_id), 2)
        self.assertFalse(self.service.is_complete(self.item.item_id))
        self.assertEqual(self.service.item_status(self.item.item_id, date(2026, 9, 15)), "pending")
        first_round = [r for r in self.service.conclusions(self.item.item_id) if r.round == 1]
        self.assertEqual(
            [r.conclusion for r in first_round],
            ["用途与告知已整改", "符合监管要求", "权限与注销已修复"],
        )

        # 第二轮同一角色不得覆盖自己的结论
        self.service.sign(self.item.item_id, "product", "第二轮产品结论", "pm-demo-1", datetime(2026, 9, 15, 9))
        with self.assertRaises(ValueError):
            self.service.sign(self.item.item_id, "product", "改写结论", "pm-demo-1", datetime(2026, 9, 15, 10))
        self.assertEqual(len(self.service.conclusions(self.item.item_id)), 4)

    def test_gray_retire_and_withdrawal_never_overwrite(self):
        # 灰度发布新版本
        self.service.start_gray("app-001", "2.4.0", "android_market", datetime(2026, 9, 12, 10))
        online = self.service.online_versions("app-001", datetime(2026, 9, 13))
        self.assertEqual({slot.version for slot in online}, {"2.3.0", "2.4.0"})

        # 旧版下架:之后的查询不再看到 2.3.0,之前的查询结果不变
        self.service.retire_version("app-001", "2.3.0", "android_market", datetime(2026, 9, 20, 10))
        online_after = self.service.online_versions("app-001", datetime(2026, 9, 21))
        self.assertEqual({slot.version for slot in online_after}, {"2.4.0"})
        online_before = self.service.online_versions("app-001", datetime(2026, 9, 13))
        self.assertEqual({slot.version for slot in online_before}, {"2.3.0", "2.4.0"})

        # 用户撤回授权:只追加事件,既有证据与版本记录不变
        self.service.record_evidence(
            self.item.item_id, "data_purpose",
            captured_at=datetime(2026, 9, 8, 10), effective_from=datetime(2026, 9, 8, 10),
            summary="数据用途证据", source="页面存档",
        )
        self.service.withdraw_consent("app-001", "user-demo-1", datetime(2026, 9, 21, 9), version="2.4.0")
        self.assertEqual(len(self.service.evidence_for(self.item.item_id)), 1)

        kinds = [event.kind for event in self.service.events()]
        self.assertEqual(
            kinds,
            ["gray_release_started", "version_retired", "consent_withdrawn"],
        )

    def test_overdue_recorded_once_and_not_before_deadline(self):
        item = next(item for item in self.items if item.app_id == "app-005")
        # 期限日 2026-09-29 当天不算逾期
        self.assertFalse(self.service.check_overdue(item.item_id, date(2026, 9, 29)))
        self.assertEqual(self.service.item_status(item.item_id, date(2026, 9, 29)), "pending")
        # 次日逾期,留痕一次;再次检查不重复记录,期限与先前记录不变
        self.assertTrue(self.service.check_overdue(item.item_id, date(2026, 9, 30)))
        self.assertTrue(self.service.check_overdue(item.item_id, date(2026, 10, 9)))
        self.assertEqual(len(self.service.events(kind="overdue")), 1)
        self.assertEqual(self.service.item(item.item_id).deadline, date(2026, 9, 29))
        self.assertEqual(self.service.item_status(item.item_id, date(2026, 9, 30)), "overdue")

    def test_completed_item_is_not_marked_overdue(self):
        self.sign_all_three()
        self.assertFalse(self.service.check_overdue(self.item.item_id, date(2026, 10, 9)))
        self.assertEqual(self.service.events(kind="overdue"), ())


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.service, self.items = build_registered_service()
        self.item = next(item for item in self.items if item.app_id == "app-004")
        # 整改前:用户看到的告知文本未说明注销路径,注销操作无入口
        self.service.record_evidence(
            self.item.item_id, "disclosure_text",
            captured_at=datetime(2026, 9, 9, 10), effective_from=datetime(2026, 8, 22, 10),
            summary="告知文本v1:未说明注销路径", source="页面存档",
        )
        self.service.record_operation(
            "app-004", "3.5.2", "account_deletion", "no_entry",
            datetime(2026, 9, 9, 11), user_ref="user-demo-1",
        )
        # 整改后:新告知文本生效,注销操作完成
        self.service.record_evidence(
            self.item.item_id, "disclosure_text",
            captured_at=datetime(2026, 9, 16, 10), effective_from=datetime(2026, 9, 16, 9),
            summary="告知文本v2:已补充注销路径", source="页面存档",
        )
        self.service.record_operation(
            "app-004", "3.5.2", "account_deletion", "completed",
            datetime(2026, 9, 16, 12), user_ref="user-demo-2",
        )

    def test_audit_locates_rules_and_results_at_that_time(self):
        # 监管回查 09-10:用户看到的是 v1,操作结果是无注销入口
        snapshot = self.service.audit_at("app-004", datetime(2026, 9, 10))
        self.assertEqual(
            snapshot.disclosures[("3.5.2", "ios_store")].summary,
            "告知文本v1:未说明注销路径",
        )
        self.assertEqual(
            [event.detail["result"] for event in snapshot.operations],
            ["no_entry"],
        )
        self.assertEqual(
            [slot.version for slot in snapshot.versions_online],
            ["3.5.2"],
        )

        # 回查 09-17:用户看到的是 v2,两条操作结果按时间排列
        snapshot = self.service.audit_at("app-004", datetime(2026, 9, 17))
        self.assertEqual(
            snapshot.disclosures[("3.5.2", "ios_store")].summary,
            "告知文本v2:已补充注销路径",
        )
        self.assertEqual(
            [event.detail["result"] for event in snapshot.operations],
            ["no_entry", "completed"],
        )

    def test_later_records_never_change_earlier_audit(self):
        before = self.service.audit_at("app-004", datetime(2026, 9, 10))
        # 再发生撤回授权与下架,较早时刻的回查结果不变
        self.service.withdraw_consent("app-004", "user-demo-3", datetime(2026, 9, 18, 9))
        self.service.retire_version("app-004", "3.5.2", "ios_store", datetime(2026, 9, 19, 10))
        after = self.service.audit_at("app-004", datetime(2026, 9, 10))
        self.assertEqual(before, after)
        # 撤回记录出现在其后的回查中;下架只影响下架时刻之后的回查
        snapshot = self.service.audit_at("app-004", datetime(2026, 9, 18, 10))
        self.assertEqual(len(snapshot.consent_withdrawals), 1)
        self.assertEqual(len(snapshot.versions_online), 1)
        snapshot = self.service.audit_at("app-004", datetime(2026, 9, 20))
        self.assertEqual(snapshot.versions_online, ())


if __name__ == "__main__":
    unittest.main()
