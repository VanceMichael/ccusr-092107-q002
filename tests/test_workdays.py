import unittest
from datetime import date
from pathlib import Path

from src.workdays import WorkdayCalendar, load_calendar

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class WorkdayCalendarTest(unittest.TestCase):
    def test_deadline_counts_from_day_after_notice(self):
        # 2026-09-07 为周一,次日起数 15 个工作日
        calendar = WorkdayCalendar()
        self.assertEqual(calendar.add(date(2026, 9, 7), 15), date(2026, 9, 28))

    def test_weekends_are_not_counted(self):
        calendar = WorkdayCalendar()
        # 周五与周六起算,周末均不计入,期限一致
        self.assertEqual(calendar.add(date(2026, 9, 4), 15), date(2026, 9, 25))
        self.assertEqual(calendar.add(date(2026, 9, 5), 15), date(2026, 9, 25))

    def test_holidays_extend_deadline(self):
        calendar = WorkdayCalendar(holidays=frozenset({date(2026, 9, 25)}))
        self.assertEqual(calendar.add(date(2026, 9, 7), 15), date(2026, 9, 29))

    def test_fixture_calendar_matches_sample(self):
        calendar = load_calendar(FIXTURES / "holidays.json")
        self.assertEqual(calendar.add(date(2026, 9, 7), 15), date(2026, 9, 29))

    def test_overdue_only_after_deadline_day(self):
        calendar = WorkdayCalendar()
        deadline = date(2026, 9, 28)
        self.assertFalse(calendar.is_overdue(deadline, date(2026, 9, 28)))
        self.assertTrue(calendar.is_overdue(deadline, date(2026, 9, 29)))

    def test_rejects_non_positive_workdays(self):
        with self.assertRaises(ValueError):
            WorkdayCalendar().add(date(2026, 9, 7), 0)


if __name__ == "__main__":
    unittest.main()
