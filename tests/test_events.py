import unittest
from datetime import datetime

from src.events import EVENT_TYPES, EventLog


class EventLogTest(unittest.TestCase):
    def test_records_all_protected_event_types(self):
        log = EventLog()
        for index, kind in enumerate(EVENT_TYPES):
            log.record(kind, at=datetime(2026, 9, 8, 10 + index), app_id="app-001")
        self.assertEqual([event.seq for event in log.all()], [1, 2, 3, 4, 5, 6])
        self.assertEqual({event.kind for event in log.all()}, set(EVENT_TYPES))

    def test_unknown_kind_rejected(self):
        log = EventLog()
        with self.assertRaises(ValueError):
            log.record("record_deleted", at=datetime(2026, 9, 8), app_id="app-001")

    def test_history_is_never_rewritten(self):
        log = EventLog()
        log.record("gray_release_started", at=datetime(2026, 9, 8, 10), app_id="app-001")
        snapshot = log.all()
        # 后续的下架、撤回、复测失败、逾期都追加在末尾,先前记录不变
        log.record("version_retired", at=datetime(2026, 9, 9, 10), app_id="app-001")
        log.record("consent_withdrawn", at=datetime(2026, 9, 10, 10), app_id="app-001")
        log.record("retest_failed", at=datetime(2026, 9, 11, 10), app_id="app-001", item_id="item-001")
        log.record("overdue", at=datetime(2026, 9, 12, 10), app_id="app-001", item_id="item-001")
        self.assertEqual(log.all()[: len(snapshot)], snapshot)
        self.assertIsInstance(log.all(), tuple)

    def test_for_app_until_orders_by_event_time(self):
        log = EventLog()
        # 乱序追加:后记录的事件发生在更早的时刻
        log.record("operation_recorded", at=datetime(2026, 9, 10, 10), app_id="app-001", result="later")
        log.record("operation_recorded", at=datetime(2026, 9, 9, 10), app_id="app-001", result="earlier")
        log.record("operation_recorded", at=datetime(2026, 9, 11, 10), app_id="app-001", result="excluded")
        events = log.for_app_until("app-001", datetime(2026, 9, 10, 12), ("operation_recorded",))
        self.assertEqual([e.detail["result"] for e in events], ["earlier", "later"])


if __name__ == "__main__":
    unittest.main()
